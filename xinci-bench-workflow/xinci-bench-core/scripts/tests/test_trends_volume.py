import contextlib
import io
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import trends_volume as TV
import write_observation as W
from _common import BenchError
from helpers import TmpRoot

NEW, ANCHOR = "gag2 calculator", "what county am i in"


def series(geo, new, anchor, new_term=NEW):
    dates = [(date(2026, 9, 14) + timedelta(days=i)).isoformat() for i in range(len(new))]
    return {"geo": geo, "terms": [new_term, ANCHOR], "time": "today 1-m",
            "url": f"https://trends.google.com/trends/explore?date=today%201-m&geo={geo}&q=x", "dates": dates,
            "values": [[n, a] for n, a in zip(new, anchor)]}


def payload():
    return {"series": [series("US", list(range(20, 50)), [60] * 30),
                       series("GB", [10] * 30, [20] * 30),
                       series("CA", [0] * 30, [5] * 30)],
            "anchors": {"US": {"volume": 60000, "source": "lexicon", "measured_at": "2026-10-08"},
                        "GB": {"volume": 8000, "source": "semrush", "measured_at": "2026-10-14"}},
            "skipped": {"AU": "Trends 返回 429,本次没查", "NZ": "Trends 返回 429,本次没查", "IE": "Trends 返回 429,本次没查"}}


class TrendsVolumeTest(unittest.TestCase):
    def test_build_observation_validates(self):
        obs = TV.build_observation(payload(), "gag2-calculator", semrush_calls=1, at="2026-10-14T03:00:00+00:00")
        W.validate(obs)
        r = obs["readings"]
        by_geo = {c["geo"]: c for c in r["countries"]}
        self.assertEqual((by_geo["US"]["estimate_7d"], by_geo["GB"]["estimate_7d"]), (46000, 4000))  # 60000×46/60、8000×10/20
        self.assertEqual((r["estimate_7d"], r["trend_geo"]), (50000, "US"))
        self.assertFalse(by_geo["CA"]["readable"])                  # 新词最近 7 天全为 0
        self.assertIn("429", by_geo["IE"]["basis"])
        self.assertEqual(r["series_30d"], list(range(20, 50)))
        self.assertEqual((obs["semrush_calls"], len(obs["source_urls"])), (1, 3))

    def test_empty_curve_counts_as_unreadable(self):
        p = payload()
        del p["skipped"]["AU"]
        p["series"].append(dict(series("AU", [], []), dates=[]))              # Trends 对量太小的词返回空曲线
        self.assertEqual(TV.analyze(p)["countries"]["AU"]["status"], "empty_curve")
        obs = TV.build_observation(p, "gag2-calculator", at="2026-10-14T03:00:00+00:00")
        W.validate(obs)
        au = next(c for c in obs["readings"]["countries"] if c["geo"] == "AU")
        self.assertFalse(au["readable"])
        self.assertIn("空曲线", au["basis"])

    def test_readable_country_without_anchor_volume_is_listed(self):
        p = payload()
        del p["anchors"]["GB"]
        self.assertEqual(TV.analyze(p)["needs_anchor_volume"], ["GB"])      # 只有读得出的国家才要查 Semrush
        with self.assertRaisesRegex(BenchError, "锚词月量"):
            TV.build_observation(p, "gag2-calculator")

    def test_ratio_out_of_range_and_anchor_zero(self):
        p = payload()
        p["series"][1] = series("GB", [1] * 30, [20] * 30)
        self.assertEqual(TV.analyze(p)["countries"]["GB"]["status"], "ratio_out_of_range")
        with self.assertRaisesRegex(BenchError, "0.2–5"):
            TV.build_observation(p, "gag2-calculator")
        p["series"][1] = series("GB", [5] * 30, [0] * 30)
        self.assertEqual(TV.analyze(p)["countries"]["GB"]["status"], "anchor_zero")
        with self.assertRaises(BenchError) as cm:
            TV.build_observation(p, "gag2-calculator")
        self.assertIn("换锚词", str(cm.exception))
        self.assertNotIn("放进 skipped 写明原因", str(cm.exception))          # 读得出的国家不能放进 skipped 按 0 计

    def test_every_country_once_and_same_new_term(self):
        p = payload()
        del p["skipped"]["IE"]
        with self.assertRaisesRegex(BenchError, "6 国"):
            TV.analyze(p)
        p = payload()
        p["skipped"]["US"] = "重复"
        with self.assertRaisesRegex(BenchError, "6 国"):
            TV.analyze(p)
        p = payload()
        p["series"][1] = series("GB", [10] * 30, [20] * 30, new_term="other term")
        with self.assertRaisesRegex(BenchError, "新词"):
            TV.analyze(p)

    def test_cli_writes_or_lists_what_is_missing(self):
        with TmpRoot() as root:
            src = root / "trends.json"
            src.write_text(json.dumps(payload(), ensure_ascii=False), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = TV.main(["--data-root", str(root), "--input", str(src), "--slug", "gag2-calculator"])
            self.assertEqual(code, 0)
            self.assertEqual(len(list((root / "证据" / "gag2-calculator").glob("*-quick_volume.json"))), 1)
            self.assertIn("证据/gag2-calculator/", out.getvalue())
            p = payload()
            del p["anchors"]["GB"]
            src.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = TV.main(["--data-root", str(root), "--input", str(src), "--slug", "gag2-calculator"])
            self.assertEqual(code, 2)
            self.assertIn("GB", out.getvalue())
            self.assertEqual(len(list((root / "证据" / "gag2-calculator").glob("*-quick_volume.json"))), 1)


if __name__ == "__main__":
    unittest.main()
