import contextlib
import io
import json
import sys
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_pool
import upstream_fetch as U
import write_observation as W
from _common import BenchError
from helpers import QUICK_BASE, TmpRoot

ON = "2026-10-19"
PH = """<?xml version="1.0" encoding="UTF-8"?>
<feed xml:lang="en-US" xmlns="http://www.w3.org/2005/Atom">
  <entry><id>tag:x,1</id><published>2026-10-18T06:50:27-07:00</published>
    <link rel="alternate" type="text/html" href="https://www.producthunt.com/products/taxbot"/><title>TaxBot</title>
    <content type="html">&lt;p&gt;File your 2026 taxes with AI&lt;/p&gt;</content></entry>
  <entry><id>tag:x,2</id><published>2026-10-01T06:50:27-07:00</published>
    <link rel="alternate" type="text/html" href="https://www.producthunt.com/products/old"/><title>OldThing</title></entry>
</feed>"""
HN = json.dumps({"hits": [
    {"title": "Show HN: PetCalc – a vet dosage helper", "url": "https://petcalc.dev", "objectID": "1",
     "created_at": "2026-10-17T10:00:00Z", "points": 120},
    {"title": "Show HN: Ancient", "url": None, "objectID": "2", "created_at": "2026-09-01T10:00:00Z", "points": 300}]})
GH = json.dumps({"items": [
    {"full_name": "acme/deskpet", "name": "deskpet", "html_url": "https://github.com/acme/deskpet",
     "created_at": "2026-10-15T00:00:00Z", "stargazers_count": 4200, "description": "A desktop pet"}]})
FR = json.dumps({"results": [
    {"title": "Overtime Pay Exemption Thresholds", "type": "Rule", "html_url": "https://www.federalregister.gov/d/1",
     "publication_date": "2026-10-16", "agencies": [{"name": "Labor Department"}]},
    {"title": "Old Rule", "type": "Rule", "html_url": "https://www.federalregister.gov/d/2",
     "publication_date": "2026-09-01", "agencies": []}]})


def texts(fail=()):
    def f(url):
        for key, body in (("producthunt", PH), ("algolia", HN), ("api.github.com", GH), ("federalregister", FR)):
            if key in url:
                if key in fail:
                    raise OSError("HTTP 503")
                return body
        raise AssertionError(url)
    return f


def suggest(answers):
    calls = []

    def f(q):
        calls.append(q)
        return list(answers.get(q, []))
    f.calls = calls
    return f


class ParseTest(unittest.TestCase):
    def test_parsers_and_since(self):
        since = "2026-10-12"
        ph = U.parse_producthunt(PH, since)
        self.assertEqual([(c["object"], c["published"], c["url"]) for c in ph],
                         [("TaxBot", "2026-10-18", "https://www.producthunt.com/products/taxbot")])
        self.assertEqual(ph[0]["note"], "File your 2026 taxes with AI")
        hn = U.parse_hackernews(HN, since)
        self.assertEqual([(c["object"], c["url"]) for c in hn], [("PetCalc", "https://petcalc.dev")])
        gh = U.parse_github(GH, since)
        self.assertEqual([(c["object"], c["url"], c["note"]) for c in gh],
                         [("deskpet", "https://github.com/acme/deskpet", "A desktop pet(4200 star)")])
        fr = U.parse_policy(FR, since)
        self.assertEqual([(c["object"], c["published"]) for c in fr], [("Overtime Pay Exemption Thresholds", "2026-10-16")])
        self.assertIn("Labor Department", fr[0]["note"])

    def test_hn_object_name_split(self):
        for title, want in (("Show HN: Foo – bar", "Foo"), ("Show HN: Foo - bar", "Foo"), ("Show HN: Foo: bar", "Foo"),
                            ("Show HN: Foo — bar", "Foo"), ("Show HN: Foo", "Foo")):
            self.assertEqual(U.hn_object(title), want)


class FetchTest(unittest.TestCase):
    def test_task_hits_and_items(self):
        with TmpRoot() as root:
            sug = suggest({"TaxBot ": ["taxbot calculator", "taxbot login"], "PetCalc ": ["petcalc"],
                           "deskpet ": ["deskpet tracker", "deskpet github"]})
            out = U.fetch_all(root, on=ON, text_fetcher=texts(), suggest_fetcher=sug, sleeper=lambda s: None)
            hits = {c["object"]: c["task_hits"] for c in out["candidates"]}
            self.assertEqual(hits, {"TaxBot": ["taxbot calculator"], "PetCalc": [], "deskpet": ["deskpet tracker"],
                                    "Overtime Pay Exemption Thresholds": None})
            self.assertNotIn("Overtime Pay Exemption Thresholds ", sug.calls)       # 政策不查补全
            items = out["items"]
            self.assertEqual({(i["source"], i["object"], i["term"]) for i in items},
                             {("producthunt", "TaxBot", "taxbot calculator"), ("github", "deskpet", "deskpet tracker")})
            W.validate({**QUICK_BASE, "slug": None, "kind": "quick_signal", "readings": {"items": items}})

    def test_one_source_failing_does_not_stop_others(self):
        with TmpRoot() as root:
            out = U.fetch_all(root, on=ON, text_fetcher=texts(fail=("api.github.com",)), suggest_fetcher=suggest({}),
                              sleeper=lambda s: None)
            self.assertIn("HTTP 503", out["sources"]["github"]["error"])
            self.assertEqual(out["sources"]["producthunt"]["count"], 1)

    def test_limit_and_spacing(self):
        with TmpRoot() as root:
            pauses = []
            out = U.fetch_all(root, on=ON, text_fetcher=texts(), suggest_fetcher=suggest({}), sleeper=pauses.append,
                              sources=("producthunt", "hackernews"), limit=1)
            self.assertEqual(len(out["candidates"]), 2)
            self.assertEqual(len(pauses), 1)                     # 两次补全之间停 1 次
            self.assertTrue(all(p >= 1.0 for p in pauses))

    def test_known_objects_not_queried(self):
        with TmpRoot() as root:
            quick_pool.add_items(root, [{"source": "github", "object": "DeskPet", "term": "deskpet tracker",
                                         "url": "https://x", "seen_at": "2026-10-18"}], "证据/_quick/x-quick_signal.json")
            sug = suggest({})
            out = U.fetch_all(root, on=ON, text_fetcher=texts(), suggest_fetcher=sug, sleeper=lambda s: None,
                              sources=("github",))
            self.assertEqual(sug.calls, [])
            c = out["candidates"][0]
            self.assertEqual((c["known"], c["task_hits"]), (True, None))

    def test_bad_source_refused(self):
        with TmpRoot() as root:
            with self.assertRaises(BenchError):
                U.fetch_all(root, on=ON, text_fetcher=texts(), suggest_fetcher=suggest({}), sleeper=lambda s: None,
                            sources=("twitter",))

    def test_urls_cover_seven_days(self):
        urls = {k: urllib.parse.unquote(v) for k, v in U.source_urls("2026-10-19").items()}
        self.assertIn("created:>=2026-10-12", urls["github"])
        self.assertIn("[gte]=2026-10-12", urls["policy"])
        self.assertIn("points>50", urls["hackernews"])


class CliTest(unittest.TestCase):
    def test_cli(self):
        with TmpRoot() as root:
            out_file = Path(root) / "up.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = U.main(["--data-root", str(root), "--on", ON, "--output", str(out_file)],
                            text_fetcher=texts(), suggest_fetcher=suggest({}), sleeper=lambda s: None)
            self.assertEqual(rc, 0)
            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(len(data["candidates"]), 4)
            self.assertIn("候选", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
