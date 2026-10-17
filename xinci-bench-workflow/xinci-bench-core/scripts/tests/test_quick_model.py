import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_model as Q
from _common import BenchError


def rec(estimate, aio=False, series=None, by_geo=None):
    return {"volume": {"estimate_7d": estimate, "by_geo": by_geo or {"US": estimate},
                       "trend": Q.trend(series or list(range(20, 50)))},
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
        self.assertEqual(out["scenarios"]["base"], {"share": 0.2, "visits": 25000, "us_visits": 25000, "revenue": 100.0})
        self.assertTrue(out["single_site_100"])
        self.assertFalse(Q.compute(rec(124995))["single_site_100"])

    def test_other_english_countries_count_but_earn_less(self):
        out = Q.compute(rec(50000, by_geo={"US": 25000, "GB": 15000, "AU": 10000}))
        base = out["scenarios"]["base"]
        self.assertEqual((base["visits"], base["us_visits"], base["revenue"]), (10000, 5000, 30.0))  # 5000×$4 + 5000×$2
        self.assertTrue(out["passes"])                       # 门槛按英文区合计
        self.assertEqual(out["us_share"], 0.5)
        half = Q.compute(rec(125000, by_geo={"US": 62500, "GB": 62500}))
        self.assertFalse(half["single_site_100"])            # 2.5 万访问但一半在英国,只有 $75

    def test_by_geo_must_add_up(self):
        with self.assertRaisesRegex(BenchError, "by_geo"):
            Q.compute(rec(50000, by_geo={"US": 20000}))
        with self.assertRaisesRegex(BenchError, "by_geo"):
            Q.compute(rec(50000, by_geo={"US": 25000, "IN": 25000}))

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


class ForecastTest(unittest.TestCase):
    def test_go_on_p25(self):
        m = Q.forecast({"US": 300000, "GB": 100000},
                       [{"task": "map", "r_p25": 0.15, "r_median": 0.25}, {"task": "build", "r_p25": 0.06, "r_median": 0.1}])
        self.assertEqual((m["forecast_p25"], m["forecast_median"]), (84000, 140000))
        base = m["scenarios"]["base"]
        self.assertEqual((base["visits"], base["us_visits"], base["revenue"]), (10080, 7560, 35.28))
        self.assertEqual((m["passes"], m["suggestion"], m["basis"], m["aio_factor"]), (True, "go", "forecast", 0.6))
        self.assertEqual(m["median_scenarios"]["base"]["visits"], 16800)

    def test_median_only_is_watching(self):
        m = Q.forecast({"US": 400000}, [{"task": "map", "r_p25": 0.1, "r_median": 0.25}])
        self.assertEqual((m["passes"], m["passes_median"], m["suggestion"]), (False, True, "watching"))

    def test_threshold_boundary(self):
        one = [{"task": "map", "r_p25": 1.0, "r_median": 1.0}]
        self.assertEqual(Q.forecast({"US": 83334}, one)["suggestion"], "go")     # floor(83334×0.12)=10000
        self.assertEqual(Q.forecast({"US": 83333}, one)["suggestion"], "skip")
        self.assertEqual(Q.forecast({"US": 83334}, one * 4)["suggestion"], "go")  # 任务数边界:1 与 4 项可以
        for by_geo, tasks in (({"US": 1}, []), ({"US": 1}, one * 5),                  # 0 项、5 项拒收
                              ({"US": 1}, [{"task": "map", "r_p25": 0.3, "r_median": 0.2}]),    # 下四分位大于中位数
                              ({"US": 1}, [{"task": "map", "r_p25": -0.1, "r_median": 0.2}]),   # 倍数为负
                              ({"US": 1, "IN": 1}, one), ({}, one)):                # 非英文区、没有量
            with self.assertRaises(BenchError):
                Q.forecast(by_geo, tasks)

    def test_us_only_cutoff_uses_median(self):
        t = lambda med: [{"task": "map", "r_p25": 0.01, "r_median": med}]
        # 美国单国中位数基准 floor(300000×0.15×0.12)=5400 ≥ 门槛 × 50% → 还要测其他 5 国
        self.assertEqual(Q.forecast({"US": 300000}, t(0.15), complete=False)["suggestion"], "measure_rest")
        self.assertEqual(Q.forecast({"US": 300000}, t(0.1), complete=False)["suggestion"], "skip")

    def test_dates_and_windows(self):
        self.assertEqual(Q.forecast_dates("2026-10-29"), {"launch_by": "2026-10-28", "review_at": "2026-11-05"})
        self.assertEqual(Q.reference_object_window("2026-08-22"), ["2026-08-13", "2026-08-19"])

    def test_recompute_dispatches_on_model_basis(self):
        f = {"object_volume_pre": {"US": 400000}, "tasks": [{"task": "map", "r_p25": 0.1, "r_median": 0.25}]}
        m = Q.forecast(f["object_volume_pre"], f["tasks"])
        self.assertEqual(Q.recompute({"model": m, "forecast": f}), m)
        cur = {"volume": {"estimate_7d": 50000, "by_geo": {"US": 50000}, "trend": {"non_declining": True}},
               "serp": {"aio_present": False, "aio_completes": False}}
        self.assertEqual(Q.recompute({"model": {"basis": "current"}, **cur}), Q.compute(cur))   # 现行方向不写 basis 也走 compute
        self.assertEqual(Q.recompute(cur), Q.compute(cur))

    def test_compute_unchanged(self):
        # 抽出 _scenarios 的守护:改动前就会通过,改完仍须通过(美国 50000 → 基准 10000)
        r = {"volume": {"estimate_7d": 50000, "by_geo": {"US": 50000}, "trend": {"non_declining": True}},
             "serp": {"aio_present": False, "aio_completes": False}}
        self.assertEqual(Q.compute(r)["scenarios"]["base"], {"share": 0.2, "visits": 10000, "us_visits": 10000, "revenue": 40.0})


class ParamsTest(unittest.TestCase):
    def test_reference_params(self):
        self.assertEqual(Q.reference_params(), {"object_window": [9, 3], "task_days": 14, "task_span": 60})

    def test_forecast_params(self):
        self.assertEqual(Q.forecast_params(), {"forecast_days": [3, 21], "min_references": 3, "threshold_visits": 10000,
                                               "share_base": 0.2, "aio_factor": 0.6, "us_only_cutoff": 0.5})

    def test_params_follow_the_given_table(self):
        a = dict(Q.QUICK_ASSUMPTIONS, reference_object_window=(10, 4), forecast_days=(2, 9), share={"base": 0.3})
        self.assertEqual(Q.reference_params(a)["object_window"], [10, 4])
        self.assertEqual(Q.forecast_params(a)["forecast_days"], [2, 9])
        self.assertEqual(Q.forecast_params(a)["share_base"], 0.3)

    def test_assumptions_from_params_roundtrips_current(self):
        a = Q.assumptions_from_params({**Q.reference_params(), **Q.forecast_params()})
        for k in ("reference_object_window", "reference_task_days", "reference_task_span", "forecast_days",
                  "min_references", "threshold_visits", "aio_factor", "us_only_cutoff"):
            self.assertEqual(a[k], Q.QUICK_ASSUMPTIONS[k], k)
        self.assertEqual(a["share"], Q.QUICK_ASSUMPTIONS["share"])
        self.assertIsInstance(a["reference_object_window"], tuple)        # 假设表里是元组,不是 JSON 的列表
        self.assertIsInstance(a["forecast_days"], tuple)

    def test_assumptions_from_params_overrides_and_copies(self):
        params = {"object_window": [10, 4], "task_days": 7, "task_span": 90, "forecast_days": [2, 9], "min_references": 4,
                  "threshold_visits": 5000, "share_base": 0.3, "aio_factor": 0.5, "us_only_cutoff": 0.4}
        a = Q.assumptions_from_params(params)
        self.assertEqual((a["reference_object_window"], a["reference_task_days"], a["reference_task_span"],
                          a["forecast_days"], a["min_references"], a["threshold_visits"], a["aio_factor"],
                          a["us_only_cutoff"]), ((10, 4), 7, 90, (2, 9), 4, 5000, 0.5, 0.4))
        self.assertEqual(a["share"], {"low": 0.10, "base": 0.3, "high": 0.30})     # 只换 base,其余档照旧
        self.assertEqual(Q.reference_object_window("2026-07-01", a), ["2026-06-21", "2026-06-27"])
        self.assertEqual(Q.forecast_suggestion(200000, 300000, True, a=a), "go")
        self.assertEqual(Q.QUICK_ASSUMPTIONS["share"]["base"], 0.20)               # 原表没被改
        self.assertEqual(Q.QUICK_ASSUMPTIONS["reference_object_window"], (9, 3))
        self.assertIsNot(a["share"], Q.QUICK_ASSUMPTIONS["share"])

    def test_assumptions_from_partial_params_keeps_the_rest(self):
        a = Q.assumptions_from_params({"task_days": 7})
        self.assertEqual((a["reference_task_days"], a["reference_task_span"]), (7, 60))
        base = dict(Q.QUICK_ASSUMPTIONS, threshold_visits=777)
        self.assertEqual(Q.assumptions_from_params({"task_days": 7}, base)["threshold_visits"], 777)


if __name__ == "__main__":
    unittest.main()
