# report_status:各状态计数、found 按 rank 排序、parked 停留天数与 90 天提醒、verified 报告路径。
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import report_status as S
from helpers import plan_candidate, revenue_for, VERIFY_OBS, TmpRoot, write_obs, CLUSTER, SEED, PROXY, REVENUE


def reg(root, slug, rank=None):
    ev = write_obs(root, slug, "2026-09-10-scan.json")
    proxy = dict(PROXY)
    if rank is not None:
        proxy["rank_score"] = rank
    L.register(root, slug=slug, primary_keyword=slug, cluster=CLUSTER, seed=SEED, proxy=proxy,
               evidence=[ev], by="t", reason="r")
    plan_candidate(root, slug)


class ReportStatusTest(unittest.TestCase):
    def test_counts_and_found_order(self):
        with TmpRoot() as root:
            reg(root, "low", rank=0.2)
            reg(root, "high", rank=0.9)
            reg(root, "none")
            rep = S.build_report(root)
            self.assertEqual(rep["counts"], {"found": 3})
            self.assertEqual([r["slug"] for r in rep["found"]], ["high", "low", "none"])

    def test_parked_days_and_stale_flag(self):
        with TmpRoot() as root:
            reg(root, "p")
            ev = write_obs(root, "p", "2026-09-10-verify.json", **VERIFY_OBS)
            L.transition(root, "p", to="parked", evidence=[ev], by="t", reason="季节性")
            ledger = L.load(root)
            old = (datetime.now(timezone.utc) - timedelta(days=95)).isoformat(timespec="seconds")
            ledger["candidates"]["p"]["history"][-1]["at"] = old
            L.save(root, ledger)
            rep = S.build_report(root)
            self.assertEqual(rep["parked"][0]["days"], 95)
            self.assertTrue(rep["parked"][0]["stale"])
            self.assertIn("超 90 天", S.render_text(rep))

    def test_verified_lists_report_path(self):
        with TmpRoot() as root:
            reg(root, "v")
            ev = write_obs(root, "v", "2026-09-10-verify.json", **VERIFY_OBS)
            L.transition(root, "v", to="verified", evidence=[ev], by="t", reason="r",
                         form="tool", revenue=revenue_for(root, "v", [ev]))
            rep = S.build_report(root)
            self.assertEqual(rep["verified"][0]["report"], "报告/v.md")
            self.assertFalse(rep["verified"][0]["report_exists"])
            (root / "报告" / "v.md").write_text("# v", encoding="utf-8")
            self.assertTrue(S.build_report(root)["verified"][0]["report_exists"])

    def test_render_text_mentions_all_sections(self):
        with TmpRoot() as root:
            reg(root, "a")
            text = S.render_text(S.build_report(root))
            for kw in ("各状态候选数", "待核验", "已验证", "已搁置"):
                self.assertIn(kw, text)


if __name__ == "__main__":
    unittest.main()
