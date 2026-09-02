import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tracking_schedule as T


class TrackingScheduleTest(unittest.TestCase):
    def test_read_only_due_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "账本" / "候选账本.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"candidates": {"demo": {
                "lane": "new", "state": "tracking",
                "first_observed_at": "2026-08-01T00:00:00+00:00",
                "history": [{"from": "screened", "to": "tracking",
                             "at": "2026-08-10T00:00:00+00:00"}],
                "evidence_refs": []}}}),
                encoding="utf-8")
            before = path.read_bytes()
            result = T.build(root, date(2026, 8, 17))
            self.assertEqual(result["counts"]["overdue"], 1)
            self.assertEqual(result["counts"]["due_now"], 1)
            self.assertEqual(result["checkpoints"][0]["due_date"], "2026-08-13")
            self.assertTrue(result["advisory_only"])
            self.assertEqual(before, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
