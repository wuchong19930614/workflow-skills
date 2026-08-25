import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import stage_checkpoint as SC
import run_controller as RC


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

    def test_outcome_cannot_be_overwritten(self):
        SC.start(self.root, self.run_id, 1, ["alpha"])
        SC.mark(self.root, self.run_id, 1, "alpha", "dedup")
        with self.assertRaisesRegex(SC.StageCheckpointError, "不可覆盖"):
            SC.mark(self.root, self.run_id, 1, "alpha", "queued")


if __name__ == "__main__":
    unittest.main()
