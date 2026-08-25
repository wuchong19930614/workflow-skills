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

    def test_official_trigger_is_not_candidate_until_approved(self):
        row = self.add(); state = TP.current(self.root)[row["trigger_id"]]
        self.assertEqual(state["status"], "pending")
        with self.assertRaisesRegex(TP.TriggerPoolError, "商业预检"):
            TP.approve(self.root, row["trigger_id"], query="filing checker",
                       search_evidence_urls=[], payer="firm", repeat_unit="filing",
                       self_serve_path="upload", base_case_source="https://example.com/base",
                       reason="task language seen")
        TP.approve(self.root, row["trigger_id"], query="filing rule checker",
                   search_evidence_urls=["https://forum.example/questions/filing-checker"],
                   payer="small firm", repeat_unit="each filing", self_serve_path="upload and check",
                   base_case_source="https://agency.example/impact", reason="repeated compliance task")
        self.assertEqual(TP.current(self.root)[row["trigger_id"]]["status"], "approved")

    def test_terminal_trigger_cannot_be_reopened(self):
        row = self.add(); TP.discard(self.root, row["trigger_id"], reason="no owned task")
        with self.assertRaisesRegex(TP.TriggerPoolError, "pending"):
            TP.discard(self.root, row["trigger_id"], reason="again")


if __name__ == "__main__": unittest.main()
