import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import trigger_pool as TP


class TriggerPoolTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.root = Path(self._tmp.name)

    def tearDown(self): self._tmp.cleanup()

    def add(self):
        return TP.add(self.root, observed_date="2026-08-25", title="Official Filing Rule 2026",
                      source_url="https://agency.example/rule", source_family="agency",
                      task_hypothesis="small firms must prepare a filing")

    def test_approve_needs_task_query_and_hypotheses_not_search_evidence(self):
        """approve 现在只是给原料配任务措辞与商业假设,不再是进入漏斗的门槛。

        旧前置要求"已有独立搜索语言证据 URL",而那份证据只有跑了 G1 才拿得到,
        当门槛用就成了"筛选前先完成筛选"(实测 290 条里 267 弃、仅 20 批准)。
        """
        row = self.add()
        self.assertEqual(TP.current(self.root)[row["trigger_id"]]["status"], "pending")
        with self.assertRaisesRegex(TP.TriggerPoolError, "任务措辞或商业假设"):
            TP.approve(self.root, row["trigger_id"], query="checker",  # 单词措辞不算任务
                       payer="firm", repeat_unit="filing", self_serve_path="upload",
                       base_case_source="https://example.com/base", reason="r")
        with self.assertRaisesRegex(TP.TriggerPoolError, "任务措辞或商业假设"):
            TP.approve(self.root, row["trigger_id"], query="filing rule checker",
                       payer="", repeat_unit="filing", self_serve_path="upload",
                       base_case_source="https://example.com/base", reason="r")
        # 不带搜索语言证据也能批准:那一步交给后面的 G1
        TP.approve(self.root, row["trigger_id"], query="which filing rule applies to my firm",
                   payer="small firm", repeat_unit="each filing",
                   self_serve_path="upload and check",
                   base_case_source="https://agency.example/impact",
                   reason="repeated compliance task")
        self.assertEqual(TP.current(self.root)[row["trigger_id"]]["status"], "approved")

    def test_terminal_trigger_cannot_be_reopened(self):
        row = self.add(); TP.discard(self.root, row["trigger_id"], reason="no owned task")
        with self.assertRaisesRegex(TP.TriggerPoolError, "未废弃"):
            TP.discard(self.root, row["trigger_id"], reason="again")

    def _approve(self, tid, query="filing rule checker"):
        TP.approve(self.root, tid, query=query,
                   search_evidence_urls=["https://forum.example/questions/filing-checker"],
                   payer="small firm", repeat_unit="each filing",
                   self_serve_path="upload and check",
                   base_case_source="https://agency.example/impact",
                   reason="repeated compliance task")

    def test_approved_trigger_can_be_discarded_after_gate_veto(self):
        """批准只表示可进 G0。方向随后被闸门否决(典型是 G1 实测 veto)时要能作废,
        否则死方向会永远挂在 approved 上被下一次运行反复提取。"""
        row = self.add(); tid = row["trigger_id"]
        self._approve(tid)
        TP.discard(self.root, tid, reason="G1 实测 veto:首屏 AI Overview 已列全逐国矩阵")
        state = TP.current(self.root)[tid]
        self.assertEqual(state["status"], "discarded")
        self.assertEqual(state["query"], "filing rule checker")  # 批准时的字段仍可追溯

    def test_approved_trigger_cannot_be_approved_twice(self):
        row = self.add(); tid = row["trigger_id"]
        self._approve(tid)
        with self.assertRaisesRegex(TP.TriggerPoolError, "pending"):
            self._approve(tid, query="second attempt")


if __name__ == "__main__": unittest.main()
