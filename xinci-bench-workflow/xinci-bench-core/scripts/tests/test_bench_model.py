import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bench_model as M
from _common import BenchError
from helpers import benchmark_record, cluster_record, model_record


class BenchModelTest(unittest.TestCase):
    def test_wisconsin_example_is_about_11_dollars(self):
        # 设计稿 §4.5:当前 5,400、仍在爬坡、照搬单标杆 → 基准 2,700 访问 → AdSense $10.80
        out = M.compute(model_record())
        base = out["scenarios"]["base"]
        self.assertEqual((base["visits_m12"], base["network"], base["total"]), (2700, "adsense", 10.8))
        self.assertTrue(out["ramping"])
        self.assertFalse(out["passes"])

    def test_threshold_is_ten_thousand_visits(self):
        ok = M.compute(model_record(benchmarks=[benchmark_record(us_organic_m12=20000)]))
        self.assertEqual(ok["scenarios"]["base"]["visits_m12"], 10000)
        self.assertEqual(ok["scenarios"]["base"]["network"], "mediavine_journey")
        self.assertEqual(ok["scenarios"]["base"]["total"], 160.0)
        self.assertTrue(ok["passes"])
        just_under = M.compute(model_record(benchmarks=[benchmark_record(us_organic_m12=19998)]))
        self.assertEqual(just_under["scenarios"]["base"]["total"], 40.0)
        self.assertFalse(just_under["passes"])

    def test_visits_needed_and_fraction(self):
        out = M.compute(model_record())
        self.assertEqual(out["visits_needed_for_threshold"], 10000)
        self.assertEqual(out["benchmark_fraction_needed"], 1.85)

    def test_cap_at_fifteen_percent(self):
        out = M.compute(model_record(benchmarks=[benchmark_record(us_organic_m12=50000)]))
        self.assertEqual(out["scenarios"]["high"]["visits_m12"], 15000)

    def test_crowding_lowers_base_coef(self):
        out = M.compute(model_record(benchmarks=[benchmark_record(us_organic_m12=20000)], crowding=3))
        self.assertEqual(out["scenarios"]["base"]["coef"], 0.33)
        self.assertEqual(out["scenarios"]["base"]["visits_m12"], 6600)

    def test_near_me_and_answered_clusters(self):
        clusters = [cluster_record(), cluster_record(id="near", volume=50000, near_me=True),
                    cluster_record(id="gone", volume=90000, answered=True)]
        out = M.compute(model_record(clusters=clusters))
        self.assertEqual(out["covered_demand"], 110000)

    def test_paid_only_when_applicable(self):
        paid = {"applicable": True, "price_month": 5, "evidence": "定价页 + 评价数"}
        out = M.compute(model_record(paid=paid))
        self.assertEqual(out["scenarios"]["base"]["paid"], 27.0)   # 2,700 × 0.2% × $5
        self.assertIn("付费转化率 0.1%/0.2%/0.5%", out["unconfirmed_assumptions"])
        self.assertEqual(M.visits_needed_for_threshold(paid), 7143)

    def test_link_driven_benchmarks_ignored_median_of_clean(self):
        bs = [benchmark_record(domain="a.com", us_organic_m12=10000),
              benchmark_record(domain="b.com", us_organic_m12=30000),
              benchmark_record(domain="c.com", us_organic_m12=90000, clean=False, link_driven=True)]
        out = M.compute(model_record(benchmarks=bs))
        self.assertEqual(out["share_rate"], 0.2)

    def test_content_site_flags_unconfirmed_rpm(self):
        out = M.compute(model_record(site_type="game"))
        self.assertTrue(any("游戏" in x for x in out["unconfirmed_assumptions"]))

    def test_zero_covered_demand_refused_zero_traffic_ok(self):
        with self.assertRaisesRegex(BenchError, "covered_demand"):
            M.compute(model_record(benchmarks=[benchmark_record(covered_demand=0)]))
        out = M.compute(model_record(benchmarks=[benchmark_record(us_organic_now=0)]))
        self.assertEqual(out["scenarios"]["base"]["total"], 0.0)
        self.assertIsNone(out["benchmark_fraction_needed"])

    def test_no_clean_benchmark_refused(self):
        with self.assertRaisesRegex(BenchError, "干净标杆"):
            M.compute(model_record(benchmarks=[benchmark_record(clean=False)]))

    def test_milestones_use_curve_then_linear(self):
        rec = model_record(benchmarks=[benchmark_record(us_organic_m12=20000)])
        model = M.compute(rec)
        ms = M.milestones(rec, model, {"3": 2000, "6": 8000, "12": None})
        self.assertEqual(ms["3"], {"expected_clicks": 1000, "basis": "标杆曲线"})
        self.assertEqual(ms["6"]["expected_clicks"], 4000)
        self.assertEqual(ms["12"], {"expected_clicks": 10000, "basis": "第 12 个月即基准情景"})
        self.assertEqual(M.milestones(rec, model, {})["3"], {"expected_clicks": 2500, "basis": "线性补"})
        self.assertEqual(ms["stop_line_m6"], 1000)


if __name__ == "__main__":
    unittest.main()
