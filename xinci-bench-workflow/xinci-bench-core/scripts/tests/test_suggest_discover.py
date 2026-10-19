import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_pool
import suggest_discover as D
import write_observation as W
from _common import BenchError
from helpers import QUICK_BASE, TmpRoot

AT1, AT2 = "2026-10-18T08:00:00+00:00", "2026-10-19T08:00:00+00:00"


def fetcher(answers):
    """answers: {查询: 建议列表};没列的查询返回空列表。记下查过哪些。"""
    calls = []

    def f(q):
        calls.append(q)
        return list(answers.get(q, []))
    f.calls = calls
    return f


def run(root, answers, at, letters="ab", patterns=None):
    return D.discover(root, fetcher(answers), sleeper=lambda s: None, at=at, letters=letters,
                      patterns=patterns or D.DISCOVER_PATTERNS)


class ExtractTest(unittest.TestCase):
    def test_object_after_prefix(self):
        self.assertEqual(D.extract("tier list azeroth survivors 2026", "tier list"), ("azeroth survivors", None))
        self.assertEqual(D.extract("codes for anime zero roblox", "codes for"), ("anime zero", "roblox"))
        self.assertEqual(D.extract("best builds in abyssus", "best builds in"), ("abyssus", None))
        self.assertEqual(D.extract("release date for iphone 18 pro max", "release date for"), ("iphone 18 pro max", None))

    def test_noise_and_generic_dropped(self):
        self.assertEqual(D.extract("codes for sols rng update 2", "codes for"), ("sols rng", None))
        for s in ("tier list maker", "tier list templates", "tier list app", "tier list a", "codes for roblox"):
            self.assertIsNone(D.extract(s, s.split()[0] + " " + s.split()[1])[0], s)
        self.assertIsNone(D.extract("tierlist anime", "tier list")[0])      # 不以前缀开头的不要

    def test_object_names_with_platform_words_kept(self):
        self.assertEqual(D.extract("release date for nintendo switch sports resort", "release date for"),
                         ("nintendo switch sports resort", None))


class DiscoverTest(unittest.TestCase):
    def test_first_run_is_baseline(self):
        with TmpRoot() as root:
            out = run(root, {"tier list a": ["tier list anime vanguards"], "codes for a": ["codes for anime zero"]}, AT1)
            self.assertEqual(out["items"], [])
            self.assertEqual((out["queries"], out["baseline_queries"]), (8, 8))      # 4 个前缀 × 2 个字母

    def test_new_suggestions_become_items(self):
        with TmpRoot() as root:
            run(root, {"tier list a": ["tier list anime vanguards"], "codes for a": ["codes for anime zero"],
                       "release date for a": ["release date for avengers doomsday"]}, AT1)
            out = run(root, {"tier list a": ["tier list anime vanguards", "tier list azeroth survivors 2026"],
                             "codes for a": ["codes for anime zero", "codes for anime ball battles roblox"],
                             "best builds in a": ["best builds in abyssus"],
                             "release date for a": ["release date for avengers doomsday", "release date for aion 3"]}, AT2)
            got = {(i["object"], i["term"], i.get("platform")) for i in out["items"]}
            self.assertEqual(got, {("azeroth survivors", "azeroth survivors tier list", None),
                                   ("anime ball battles", "anime ball battles codes", "roblox"),
                                   ("abyssus", "abyssus build", None),
                                   ("aion 3", None, None)})
            self.assertEqual(out["baseline_queries"], 0)
            it = next(i for i in out["items"] if i["object"] == "azeroth survivors")
            self.assertEqual((it["source"], it["seen_at"]), ("autocomplete", "2026-10-19"))
            self.assertIn("suggestqueries.google.com", it["url"])
            self.assertEqual(it["suggestion"], "tier list azeroth survivors 2026")

    def test_known_objects_and_terms_skipped(self):
        with TmpRoot() as root:
            run(root, {}, AT1)
            quick_pool.add_items(root, [{"source": "wikipedia", "object": "Azeroth Survivors", "term": None,
                                         "url": "https://x", "seen_at": "2026-10-18"}], "证据/_quick/x-quick_signal.json")
            out = run(root, {"tier list a": ["tier list azeroth survivors"], "codes for a": ["codes for abyss world"]}, AT2)
            self.assertEqual([i["object"] for i in out["items"]], ["abyss world"])
            self.assertEqual(out["skipped_known"], 1)

    def test_same_object_from_two_letters_once(self):
        with TmpRoot() as root:
            run(root, {}, AT1)
            out = run(root, {"tier list a": ["tier list abyss world"], "tier list b": ["tier list abyss world"]}, AT2)
            self.assertEqual(len(out["items"]), 1)

    def test_fetch_errors_reported_not_fatal(self):
        with TmpRoot() as root:
            def boom(q):
                raise OSError("HTTP 429")
            out = D.discover(root, boom, sleeper=lambda s: None, at=AT1, letters="a", patterns=D.DISCOVER_PATTERNS[:1])
            self.assertEqual((out["items"], len(out["errors"])), ([], 1))

    def test_requests_spaced(self):
        with TmpRoot() as root:
            pauses = []
            D.discover(root, fetcher({}), sleeper=pauses.append, at=AT1, letters="ab", patterns=D.DISCOVER_PATTERNS)
            self.assertEqual(len(pauses), 7)                              # 8 次请求之间停 7 次
            self.assertTrue(all(p >= 1.0 for p in pauses))

    def test_items_are_valid_quick_signal(self):
        with TmpRoot() as root:
            run(root, {}, AT1)
            out = run(root, {"codes for a": ["codes for anime ball battles roblox"],
                             "release date for a": ["release date for aion 3"]}, AT2)
            W.validate({**QUICK_BASE, "slug": None, "kind": "quick_signal", "readings": {"items": out["items"]}})

    def test_bad_args(self):
        with TmpRoot() as root:
            with self.assertRaises(BenchError):
                D.discover(root, fetcher({}), sleeper=lambda s: None, at=AT1, letters="", patterns=D.DISCOVER_PATTERNS)
            with self.assertRaises(BenchError):
                D.discover(root, fetcher({}), sleeper=lambda s: None, at=AT1, letters="a", patterns=D.DISCOVER_PATTERNS, gl="fr")


class CliTest(unittest.TestCase):
    def test_cli_writes_output(self):
        with TmpRoot() as root:
            out_file = Path(root) / "discover.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = D.main(["--data-root", str(root), "--letters", "a", "--output", str(out_file)],
                            fetcher=fetcher({}), sleeper=lambda s: None)
            self.assertIn('"查询": 4', buf.getvalue())
            self.assertEqual(rc, 0)
            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual((data["queries"], data["items"]), (4, []))


if __name__ == "__main__":
    unittest.main()
