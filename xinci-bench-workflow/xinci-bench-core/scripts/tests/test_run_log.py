import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_log as R
import seeds
from _common import BenchError
from helpers import TmpRoot, setup_direction


def start(root, run_id="run-a", rnd=1, max_rounds=2, source="legacy"):
    return R.record(root, skill="xinci-bench-scan", progress={
        "run_id": run_id, "round": rnd, "max_rounds": max_rounds, "source_kind": source,
        "seed_value": "种子池 legacy 前 16 个", "outcome": "started", "next_step": "scan"})


def start_assess(root, run_id="run-a", rnd=1, max_rounds=2, source="legacy"):
    return R.record(root, skill="xinci-bench-assess", progress={
        "run_id": run_id, "round": rnd, "max_rounds": max_rounds, "source_kind": source,
        "seed_value": "rank 前 2", "outcome": "started", "next_step": "assess"})


class RunLogTest(unittest.TestCase):
    def test_full_round_then_done(self):
        with TmpRoot() as root:
            start(root)
            R.finish(root, run_id="run-a", semrush_calls=5)
            self.assertEqual(R.plan(root)["action"], "assess")
            start_assess(root)
            R.finish(root, run_id="run-a", semrush_calls=10)
            p = R.plan(root)
            self.assertEqual((p["action"], p["resume"]["round"]), ("scan", 2))
            start(root, rnd=2)
            R.finish(root, run_id="run-a", outcome="skipped")
            start_assess(root, rnd=2)
            R.finish(root, run_id="run-a")
            self.assertEqual(R.plan(root, "run-a")["action"], "done")
            p = R.plan(root)                      # 没有未完运行:可以开新运行
            self.assertEqual((p["action"], p["resume"]), ("scan", None))
            self.assertEqual(p["semrush_calls_total"], 15)

    def test_cannot_finish_twice_or_skip_assess(self):
        with TmpRoot() as root:
            start(root)
            R.finish(root, run_id="run-a")
            with self.assertRaisesRegex(BenchError, "finish"):
                R.finish(root, run_id="run-a")
            start_assess(root)
            with self.assertRaisesRegex(BenchError, "跳过"):
                R.finish(root, run_id="run-a", outcome="skipped")

    def test_new_run_blocked_while_another_active(self):
        with TmpRoot() as root:
            start(root)
            with self.assertRaisesRegex(BenchError, "未完成运行"):
                start(root, run_id="run-b")

    def test_new_run_must_start_with_scan_round_1(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "第 1 轮 scan"):
                start_assess(root)

    def test_blocked_keeps_position_and_source(self):
        with TmpRoot() as root:
            start(root, source="serp")
            R.finish(root, run_id="run-a", outcome="blocked", notes=["Semrush 额度用完"])
            p = R.plan(root)
            self.assertEqual((p["action"], p["next_source"]), ("scan", "serp"))
            R.finish(root, run_id="run-a")
            self.assertEqual(R.plan(root)["action"], "assess")

    def test_source_rotation(self):
        with TmpRoot() as root:
            self.assertEqual(R.plan(root)["next_source"], "sibling")
            seeds.add(root, "a.com", "legacy", "旧证据")
            self.assertEqual(R.plan(root)["next_source"], "legacy")
            seeds.mark_checked(root, ["a.com"])
            start(root, source="serp")
            R.finish(root, run_id="run-a")
            self.assertEqual(R.plan(root)["next_source"], "geo")

    def test_skipped_when_three_found(self):
        with TmpRoot() as root:
            for slug in ("d0", "d1"):
                setup_direction(root, slug=slug)
            self.assertIsNone(R.plan(root)["scan_outcome"])
            setup_direction(root, slug="d2")
            self.assertEqual(R.plan(root)["scan_outcome"], "skipped")

    def test_budget_cannot_change(self):
        with TmpRoot() as root:
            start(root)
            R.finish(root, run_id="run-a")
            with self.assertRaisesRegex(BenchError, "预算"):
                start_assess(root, max_rounds=5)


def start_quick(root, run_id="quick-a"):
    return R.record(root, skill="xinci-bench-quick", progress={
        "run_id": run_id, "round": 1, "max_rounds": 1, "source_kind": "quick",
        "seed_value": "自动补全与 Trends 飙升", "outcome": "started", "next_step": "quick"})


class QuickRunLogTest(unittest.TestCase):
    def test_quick_found_does_not_skip_bench_scan(self):
        from helpers import setup_quick
        with TmpRoot() as root:
            for s in ("q-one", "q-two", "q-three"):
                setup_quick(root, slug=s)
            p = R.plan(root)
            self.assertEqual((p["found_count"], p["scan_outcome"]), (0, None))

    def test_quick_lifecycle(self):
        with TmpRoot() as root:
            self.assertEqual(R.plan(root, lane="quick")["action"], "quick")
            start_quick(root)
            p = R.plan(root, lane="quick")
            self.assertEqual((p["resume"]["run_id"], p["active_run_ids"]), ("quick-a", ["quick-a"]))
            R.finish(root, run_id="quick-a", outcome="blocked", notes=["Trends 429"])
            R.finish(root, run_id="quick-a", semrush_calls=1)
            self.assertEqual(R.plan(root, "quick-a", lane="quick")["action"], "done")

    def test_lanes_do_not_block_each_other(self):
        with TmpRoot() as root:
            start(root)                     # 标杆道运行未完成
            start_quick(root)               # 快道照样能开
            self.assertEqual(R.plan(root)["resume"]["run_id"], "run-a")
            self.assertEqual(R.plan(root, lane="quick")["resume"]["run_id"], "quick-a")
            with self.assertRaisesRegex(BenchError, "这条道"):
                start_quick(root, run_id="quick-b")

    def test_quick_run_shape(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "max_rounds"):
                R.record(root, skill="xinci-bench-quick", progress={
                    "run_id": "q", "round": 1, "max_rounds": 2, "source_kind": "quick",
                    "seed_value": "x", "outcome": "started", "next_step": "quick"})
            with self.assertRaisesRegex(BenchError, "source_kind"):
                R.record(root, skill="xinci-bench-scan", progress={
                    "run_id": "b", "round": 1, "max_rounds": 1, "source_kind": "quick",
                    "seed_value": "x", "outcome": "started", "next_step": "scan"})


if __name__ == "__main__":
    unittest.main()
