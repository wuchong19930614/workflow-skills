import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import write_observation as W
from _common import BenchError
from helpers import (TmpRoot, benchmark_obs, brief_obs, deep, delivery_obs, demand_obs, diff_obs,
                     scan_obs, serp_obs)


class WriteObservationTest(unittest.TestCase):
    def test_every_kind_round_trips(self):
        with TmpRoot() as root:
            for obs in (scan_obs("a.com"), benchmark_obs("s"), demand_obs("s"), serp_obs("s"),
                        diff_obs("s"), delivery_obs("s"), brief_obs("s")):
                ref = W.write(root, obs)
                self.assertEqual(W.read(root, ref)["kind"], obs["kind"])
                folder = "_scan" if obs["kind"] == "scan" else "s"
                self.assertTrue(ref.startswith(f"证据/{folder}/") and ref.endswith(f"-{obs['kind']}.json"))

    def test_never_overwrites(self):
        with TmpRoot() as root:
            refs = {W.write(root, demand_obs("s")) for _ in range(5)}
            self.assertEqual(len(refs), 5)

    def test_missing_reading_rejected(self):
        obs = benchmark_obs("s")
        del obs["readings"]["curve"]
        with self.assertRaisesRegex(BenchError, "缺字段"):
            W.validate(obs)

    def test_scan_null_only_after_a_failure(self):
        ok = scan_obs(failing={"x.com": {"B3": False, "B4": None, "B5": None}})
        W.validate(ok)
        bad = scan_obs(failing={"x.com": {"B4": None}})
        with self.assertRaisesRegex(BenchError, "null"):
            W.validate(bad)

    def test_numeric_limits_enforced_on_pass(self):
        old = scan_obs("old.com")
        old["readings"]["domains"][0]["registered_at"] = "2024-09-01"     # 25 个月前
        with self.assertRaisesRegex(BenchError, "24 个月"):
            W.validate(old)
        old["readings"]["domains"][0]["aged_domain"] = True              # 老域名重新起量,允许
        W.validate(old)
        high = scan_obs("high.com")
        high["readings"]["domains"][0]["authority_score"] = 31
        with self.assertRaisesRegex(BenchError, "AS"):
            W.validate(high)
        small = scan_obs("small.com")
        small["readings"]["domains"][0].update(us_organic_now=4999, en_organic_now=4999)
        with self.assertRaisesRegex(BenchError, "5000"):
            W.validate(small)

    def test_serp_needs_passing_preflight(self):
        obs = serp_obs("s")
        obs["browser_preflight"]["logged_out"] = False
        with self.assertRaisesRegex(BenchError, "preflight"):
            W.validate(obs)

    def test_observed_at_must_be_iso(self):
        obs = demand_obs("s")
        obs["observed_at"] = "2026-10-13 下午"
        with self.assertRaisesRegex(BenchError, "observed_at"):
            W.validate(obs)

    def test_stage_must_match_kind(self):
        obs = deep(demand_obs("s"))
        obs["stage"] = "scan"
        with self.assertRaisesRegex(BenchError, "stage"):
            W.validate(obs)

    def test_differentiation_needs_gaps_unless_copy_only(self):
        W.validate(diff_obs("s", copy_only=True))
        obs = diff_obs("s")
        obs["readings"]["gaps"] = []
        with self.assertRaisesRegex(BenchError, "gaps"):
            W.validate(obs)

    def test_competitor_traffic_needs_basis(self):
        obs = demand_obs("s")
        obs["readings"]["competitor_traffic"] = [{"domain": "a.com", "traffic": 10}]
        with self.assertRaisesRegex(BenchError, "basis"):
            W.validate(obs)

    def test_read_refuses_paths_outside_evidence(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "证据/"):
                W.read(root, "账本/方向账本.json")



class EnglishRegionTest(unittest.TestCase):
    def test_b3_uses_english_region_total(self):
        obs = scan_obs("uk-heavy.com")
        d = obs["readings"]["domains"][0]
        d.update(us_organic_now=3000, en_organic_now=6000,
                 country_traffic={"US": 3000, "GB": 2000, "CA": 500, "AU": 500, "NZ": 0, "IE": 0})
        W.validate(obs)                                  # 美国只有 3,000,英文区合计 6,000 照样过 B3
        d.update(en_organic_now=4000, country_traffic={"US": 3000, "GB": 1000, "CA": 0, "AU": 0, "NZ": 0, "IE": 0})
        with self.assertRaisesRegex(BenchError, "英文区"):
            W.validate(obs)

    def test_en_must_follow_country_ratio(self):
        obs = scan_obs("a.com")
        d = obs["readings"]["domains"][0]
        d.update(en_organic_now=9000, country_traffic={"US": 6000, "GB": 3000, "CA": 0, "AU": 0, "NZ": 0, "IE": 0})
        with self.assertRaisesRegex(BenchError, "en_organic_now"):          # 应为 5400 × 1.5 = 8100
            W.validate(obs)
        d["country_traffic"]["XX"] = 1
        with self.assertRaisesRegex(BenchError, "6 国"):
            W.validate(obs)

    def test_us_zero_takes_direct_reading(self):
        obs = scan_obs("uk-only.co.uk")
        d = obs["readings"]["domains"][0]
        d.update(us_organic_now=0, en_organic_now=6500,
                 country_traffic={"US": 0, "GB": 7000, "CA": 0, "AU": 0, "NZ": 0, "IE": 0})
        W.validate(obs)                                  # 美国为 0 时不能按比例换算,按逐国实测填

    def test_benchmark_and_demand_en_checked(self):
        b = benchmark_obs("x", us_organic_now=4000, us_organic_m12=8000, en_organic_now=5000, en_organic_m12=10000,
                          country_traffic={"US": 4000, "GB": 1000, "CA": 0, "AU": 0, "NZ": 0, "IE": 0})
        W.validate(b)
        b["readings"]["en_organic_m12"] = 9000
        with self.assertRaisesRegex(BenchError, "en_organic_m12"):
            W.validate(b)
        dm = demand_obs("x")
        c = dm["readings"]["clusters"][0]
        c.update(en_volume=125000, seed_country_volume={"US": 80000, "GB": 20000, "CA": 0, "AU": 0, "NZ": 0, "IE": 0})
        W.validate(dm)
        c["en_volume"] = 100000
        with self.assertRaisesRegex(BenchError, "en_volume"):
            W.validate(dm)


if __name__ == "__main__":
    unittest.main()
