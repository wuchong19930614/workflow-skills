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
        self.assertIn("expiry 已过且非终态", text)
        self.assertIn("- overdue-one", text)

    def test_terminal_overdue_not_listed(self):
        past = (date.today() - timedelta(days=2)).isoformat()
        self._mk("was-tracked", state="tracking", expiry=past)
        R.transition(self.root, "was-tracked", to="expired", by="xinci-track",
                     reason="expiry 已过,用户确认")
        report = S.build_report(self.root)
        self.assertEqual(report["expired_unhandled"], [])


if __name__ == "__main__":
    unittest.main()
