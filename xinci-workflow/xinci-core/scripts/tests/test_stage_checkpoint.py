import sys
import tempfile
import unittest
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import stage_checkpoint as SC
import run_controller as RC
import trigger_pool as TP


class StageCheckpointTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.run_id = RC.start(self.root)["run_id"]
        RC.begin_round(self.root, self.run_id)

    def tearDown(self):
        self._tmp.cleanup()

    def test_resume_mark_and_finish(self):
        first = SC.start(self.root, self.run_id, 1, ["alpha", "beta", "alpha"])
        self.assertEqual(len(first["items"]), 2)
        resumed = SC.start(self.root, self.run_id, 1, ["ignored"])
        self.assertEqual(set(resumed["items"]), {"alpha", "beta"})
        SC.mark(self.root, self.run_id, 1, "alpha", "zero_cost")
        with self.assertRaisesRegex(SC.StageCheckpointError, "pending"):
            SC.finish(self.root, self.run_id, 1)
        SC.mark(self.root, self.run_id, 1, "beta", "queued", "待 G1")
        done = SC.finish(self.root, self.run_id, 1)
        self.assertEqual(done["status"], "completed")
        self.assertEqual(SC.list_open(self.root, self.run_id, 1), [])

    def test_pooled_is_rejected_for_new_checkpoint(self):
        SC.start(self.root, self.run_id, 1, ["gamma"])
        with self.assertRaisesRegex(SC.StageCheckpointError, "pooled 仅可读取历史"):
            SC.mark(self.root, self.run_id, 1, "gamma", "pooled", "错误混入正式漏斗")

    def test_outcome_cannot_be_overwritten(self):
        SC.start(self.root, self.run_id, 1, ["alpha"])
        SC.mark(self.root, self.run_id, 1, "alpha", "dedup")
        with self.assertRaisesRegex(SC.StageCheckpointError, "不可覆盖"):
            SC.mark(self.root, self.run_id, 1, "alpha", "queued")

    def test_trigger_checkpoint_must_match_real_trigger_state(self):
        trigger = TP.add(self.root, observed_date="2026-08-31", title="Official trigger",
                         source_url="https://agency.example/trigger", source_family="agency",
                         task_hypothesis="possible filing", actor="xinci-run", run_id=self.run_id)
        SC.start(self.root, self.run_id, 1, [trigger["trigger_id"]], stage="trigger")
        SC.mark(self.root, self.run_id, 1, trigger["trigger_id"],
                "trigger_approved", stage="trigger")
        with self.assertRaisesRegex(SC.StageCheckpointError, "状态不一致"):
            SC.finish(self.root, self.run_id, 1, stage="trigger")

    def test_trigger_outcome_cannot_be_used_in_scan_checkpoint(self):
        SC.start(self.root, self.run_id, 1, ["alpha"])
        with self.assertRaisesRegex(SC.StageCheckpointError, "只允许"):
            SC.mark(self.root, self.run_id, 1, "alpha", "trigger_pending")

    def test_loader_rejects_manually_forged_stage_outcome_pair(self):
        SC.start(self.root, self.run_id, 1, ["alpha"])
        path = SC.checkpoint_path(self.root, self.run_id, 1, "scan")
        obj = json.loads(path.read_text(encoding="utf-8"))
        obj["items"]["alpha"]["outcome"] = "trigger_pending"
        path.write_text(json.dumps(obj), encoding="utf-8")
        with self.assertRaisesRegex(SC.StageCheckpointError, "语义冲突"):
            SC.list_open(self.root)


if __name__ == "__main__":
    unittest.main()
