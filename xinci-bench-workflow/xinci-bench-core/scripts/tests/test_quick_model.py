import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_model as Q
from _common import BenchError


def rec(estimate, aio=False, series=None):
    return {"volume": {"estimate_7d": estimate, "trend": Q.trend(series or list(range(20, 50)))},
            "serp": {"aio_present": aio, "aio_completes": False}}


class QuickModelTest(unittest.TestCase):
    def test_anchor_estimate(self):
        out = Q.anchor_estimate(60000, [0] * 23 + [50] * 7, [0] * 23 + [60] * 7)
        self.assertEqual((out["ratio"], out["estimate"], out["ratio_ok"]), (0.8333, 50000, True))
        far = Q.anchor_estimate(74000, [5] * 7, [72] * 7)
        self.assertFalse(far["ratio_ok"])          # 2026-10-13 实测那次约 1/15,应换锚词

    def test_anchor_zero_refused(self):
        with self.assertRaisesRegex(BenchError, "锚词"):
            Q.anchor_estimate(1000, [1] * 7, [0] * 7)

    def test_trend_rules(self):
        self.assertTrue(Q.trend(list(range(20, 50)))["non_declining"])
        self.assertFalse(Q.trend([50] * 23 + [30] * 7)["non_declining"])     # 30 < 50 × 0.8
        self.assertTrue(Q.trend([0] * 23 + [5] * 7)["non_declining"])       # 前 7 天为 0,刚起量
        self.assertTrue(Q.trend([0] * 10 + [100] + [5] * 19)["spike_decay"])
        self.assertFalse(Q.trend([0] * 30)["non_declining"])

    def test_threshold_edge(self):
        self.assertTrue(Q.compute(rec(50000))["passes"])
        out = Q.compute(rec(49995))
        self.assertEqual(out["scenarios"]["base"]["visits"], 9999)
        self.assertFalse(out["passes"])

    def test_aio_factor_and_searches_needed(self):
        out = Q.compute(rec(50000, aio=True))
        self.assertEqual((out["aio_factor"], out["scenarios"]["base"]["visits"], out["searches_needed"]), (0.6, 6000, 83334))
        self.assertEqual(Q.compute(rec(50000))["searches_needed"], 50000)

    def test_revenue_and_single_site(self):
        out = Q.compute(rec(125000))
        self.assertEqual(out["scenarios"]["base"], {"share": 0.2, "visits": 25000, "revenue": 100.0})
        self.assertTrue(out["single_site_100"])
        self.assertFalse(Q.compute(rec(124995))["single_site_100"])

    def test_answered_refused(self):
        r = rec(50000)
        r["serp"]["aio_completes"] = True
        with self.assertRaisesRegex(BenchError, "答完"):
            Q.compute(r)

    def test_suggestion(self):
        self.assertEqual(Q.compute(rec(5000))["suggestion"], "watching")
        self.assertEqual(Q.compute(rec(5000, series=[50] * 23 + [30] * 7))["suggestion"], "rejected:volume")
        self.assertEqual(Q.compute(rec(90000, series=[0] * 10 + [100] + [5] * 19))["suggestion"], "rejected:oneoff")
        self.assertEqual(Q.compute(rec(60000))["suggestion"], "go")

    def test_milestones_and_stop_line(self):
        self.assertEqual([m["date"] for m in Q.milestones("2026-11-01")], ["2026-11-15", "2026-12-01", "2027-01-30"])
        self.assertEqual(Q.stop_line(Q.compute(rec(50000))), 2500)
        self.assertEqual(Q.add_days("2026-10-20", 7), "2026-10-27")


if __name__ == "__main__":
    unittest.main()
