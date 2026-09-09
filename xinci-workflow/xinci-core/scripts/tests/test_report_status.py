# report_status 测试:只读汇报的事实正确性(计数、年龄、expiry 余量、过期未处理清单)。
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import registrar as R
import report_status as S
from test_registrar import mk_evidence, GATES_SCREEN


class ReportStatusTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _mk(self, slug, state=None, expiry=None):
        ev = mk_evidence(self.root, slug, "2026-08-17-scan.json")
        R.register(self.root, slug=slug, term=slug, source_url="https://e.com",
                   task="t", evidence=[ev])
        if state == "rejected":
            R.transition(self.root, slug, to="rejected", by="xinci-scan",
                         gates={"G1": "veto"}, reason="G1 否决",
                         evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                               gates={"G1": "veto"})])
        elif state == "tracking":
            R.transition(self.root, slug, to="screened", by="xinci-scan",
                         gates=dict(GATES_SCREEN), window_estimate="weeks",
                         expiry=expiry,
                         evidence=[mk_evidence(self.root, slug, "2026-08-17b-scan.json",
                                               gates=dict(GATES_SCREEN))])
            R.transition(self.root, slug, to="tracking", by="xinci-scan",
                         expiry=expiry, invalidation=["官方工具上线"],
                         evidence=[mk_evidence(self.root, slug, "2026-08-17c-scan.json")])

    def test_tracking_rows_report_formation_eligible_date(self):
        """追踪中候选要直接给出"最早哪天能提交形成确认",与 registrar 判据同源。"""
        future = (date.today() + timedelta(days=30)).isoformat()
        self._mk("span-one", state="tracking", expiry=future)
        R.checked(self.root, "span-one", evidence=[mk_evidence(
            self.root, "span-one", "2026-08-20-track.json",
            observed_at="2026-08-20T04:10:00+00:00")])
        rows = {r["slug"]: r for r in S.build_report(self.root)["candidates"]}
        row = rows["span-one"]
        self.assertEqual(row["track_observations"], 1)
        self.assertEqual(row["formation_eligible_date"], "2026-08-27")
        text = S.render_text(S.build_report(self.root))
        self.assertIn("形成跨度", text)
        self.assertIn("时间达标", text)
        # 非 tracking 状态不算这一列,避免看板给出无意义的日期
        self._mk("dead-two", state="rejected")
        rows = {r["slug"]: r for r in S.build_report(self.root)["candidates"]}
        self.assertIsNone(rows["dead-two"]["formation_eligible_date"])

    def test_default_hides_terminal_details_but_preserves_counts_and_json_rows(self):
        self._mk("dead-one", state="rejected")
        self._mk("live-one")
        report = S.build_report(self.root)
        text = S.render_text(report)
        self.assertIn("live-one", text)
        self.assertNotIn("【已淘汰】dead-one", text)
        self.assertNotIn("dead-one —", text)
        self.assertIn("dead-one —", S.render_text(report, all_candidates=True))
        self.assertEqual(len(report["candidates"]), 2)
        self.assertEqual(report["counts"]["rejected"], 1)

    def test_pending_due_date_renders_without_forcing_a_verdict(self):
        self._mk("pending-one")
        report = S.build_report(self.root)
        for offset in (-1, 0, 1):
            report["candidates"][0]["qualify_pending"] = {
                "pending_until": (date.today() + timedelta(days=offset)).isoformat(),
                "pending_evidence": ["市场证据"]}
            text = S.render_text(report)
            self.assertIn("市场证据", text)
            self.assertNotIn("该按现有证据出结论", text)
            if offset <= 0:
                self.assertIn("仍不足可继续暂缓", text)

    def test_missing_ledger_raises(self):
        with self.assertRaises(FileNotFoundError):
            S.build_report(self.root / "不存在")

    def test_empty_ledger(self):
        (self.root / "账本").mkdir(parents=True)
        (self.root / "账本" / "候选账本.json").write_text(
            '{"schema_version": 1, "candidates": {}}', encoding="utf-8")
        report = S.build_report(self.root)
        self.assertEqual(report["counts"], {})
        self.assertEqual(report["candidates"], [])
        self.assertEqual(report["expired_unhandled"], [])
        self.assertIn("账本为空", S.render_text(report))

    def test_counts_ages_and_overdue(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        past = (date.today() - timedelta(days=3)).isoformat()
        self._mk("fresh-one", state="tracking", expiry=future)
        self._mk("overdue-one", state="tracking", expiry=past)
        self._mk("dead-one", state="rejected")
        report = S.build_report(self.root)
        self.assertEqual(report["counts"], {"tracking": 2, "rejected": 1})
        rows = {r["slug"]: r for r in report["candidates"]}
        self.assertEqual(rows["fresh-one"]["expiry_days_left"], 5)
        self.assertEqual(rows["overdue-one"]["expiry_days_left"], -3)
        self.assertEqual(rows["dead-one"]["expiry_days_left"], None)
        self.assertEqual(rows["fresh-one"]["age_days"], 0)
        self.assertEqual(rows["fresh-one"]["days_since_checked"], 0)
        # 过期未处理:只有非终态的 overdue-one;rejected 即使无 expiry 也不该出现
        self.assertEqual(report["expired_unhandled"], ["overdue-one"])
        text = S.render_text(report)
        self.assertIn("失效日已过且仍未终结", text)
        self.assertIn("- overdue-one", text)

    def test_human_output_uses_chinese_state_labels(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        self._mk("fresh-one", state="tracking", expiry=future)
        text = S.render_text(S.build_report(self.root))
        self.assertIn("追踪中：1", text)
        self.assertIn("【追踪中】", text)
        self.assertIn("失效日", text)
        self.assertNotIn("[tracking]", text)

    def test_terminal_overdue_not_listed(self):
        past = (date.today() - timedelta(days=2)).isoformat()
        self._mk("was-tracked", state="tracking", expiry=past)
        R.transition(self.root, "was-tracked", to="expired", by="xinci-track",
                     reason="expiry 已过,用户确认", expiry_trigger="date")
        report = S.build_report(self.root)
        self.assertEqual(report["expired_unhandled"], [])


if __name__ == "__main__":
    unittest.main()
