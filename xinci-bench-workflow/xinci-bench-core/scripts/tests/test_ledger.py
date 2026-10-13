import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import write_observation as W
from _common import BenchError, load_ledger
from helpers import TmpRoot, benchmark_record, cluster_record, demand_obs, scan_obs, setup_direction


class RegisterTest(unittest.TestCase):
    def test_register_copies_scan_readings(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs("example-bench.com"))
            rec = L.register(root, "example-county", "按地址查县", "tool", "example-bench.com", ref, "初核全过")
            b = rec["benchmarks"][0]
            self.assertEqual((b["authority_score"], b["us_organic_now"], b["clean"]), (11, 5400, None))
            self.assertEqual(rec["state"], "found")

    def test_register_refuses_failed_domain(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs(failing={"bad.com": {"B3": False, "B4": None, "B5": None}}))
            with self.assertRaisesRegex(BenchError, "B1–B5 全过"):
                L.register(root, "bad", "x", "tool", "bad.com", ref, "r")

    def test_same_benchmark_needs_confirm_distinct(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs("example-bench.com"))
            L.register(root, "a", "方向 A", "tool", "example-bench.com", ref, "r")
            with self.assertRaisesRegex(BenchError, "confirm-distinct"):
                L.register(root, "b", "方向 B", "tool", "example-bench.com", ref, "r")
            L.register(root, "b", "方向 B", "tool", "example-bench.com", ref, "r", confirm_distinct="B 是学区不是县")

    def test_duplicate_slug_and_bad_site_type(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs("example-bench.com"))
            L.register(root, "a", "x", "tool", "example-bench.com", ref, "r")
            with self.assertRaisesRegex(BenchError, "已存在"):
                L.register(root, "a", "x", "tool", "example-bench.com", ref, "r", confirm_distinct="y")
            with self.assertRaisesRegex(BenchError, "site_type"):
                L.register(root, "c", "x", "blog", "example-bench.com", ref, "r", confirm_distinct="y")


class UpdateRankTest(unittest.TestCase):
    def test_clean_requires_scan_pass_and_not_link_driven(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs("example-bench.com"))
            L.register(root, "a", "x", "tool", "example-bench.com", ref, "r")
            with self.assertRaisesRegex(BenchError, "外链驱动"):
                L.update(root, "a", {"benchmarks": [benchmark_record(link_driven=True)]})
            with self.assertRaisesRegex(BenchError, "B1–B5 全过"):
                L.update(root, "a", {"benchmarks": [benchmark_record(domain="other.com")]})

    def test_update_clears_model_and_adds_refs(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual(rec["evidence_refs"], refs)
            self.assertIsNone(rec["model"])
            with self.assertRaisesRegex(BenchError, "不可补"):
                L.update(root, slug, {"state": "go"})

    def test_update_rejects_other_directions_observation(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            other = W.write(root, demand_obs("someone-else"))
            with self.assertRaisesRegex(BenchError, "别的方向"):
                L.update(root, slug, {}, [other])

    def test_cluster_shape_checked(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            bad = cluster_record()
            del bad["counted"]
            with self.assertRaisesRegex(BenchError, "缺字段"):
                L.update(root, slug, {"clusters": [bad]})

    def test_rank_by_speed(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs("slow.com", "fast.com"))
            L.register(root, "slow", "x", "tool", "slow.com", ref, "r")
            L.register(root, "fast", "y", "tool", "fast.com", ref, "r")
            L.update(root, "fast", {"benchmarks": [benchmark_record(domain="fast.com", traffic_start="2026-08",
                                                                   us_organic_now=9000)]})
            rows = L.rank(root, on="2026-10-13")
            self.assertEqual([r["slug"] for r in rows], ["fast", "slow"])
            self.assertEqual(rows[0]["speed"], 4500.0)


class TransitionTest(unittest.TestCase):
    def test_illegal_and_gate_rules(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "gate"):
                L.transition(root, slug, "rejected", None, "r")
            with self.assertRaisesRegex(BenchError, "非法转移"):
                L.transition(root, slug, "found", None, "r")

    def test_transition_requires_settle_decision(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "settle"):
                L.transition(root, slug, "parked", None, "证据拿不到")


if __name__ == "__main__":
    unittest.main()
