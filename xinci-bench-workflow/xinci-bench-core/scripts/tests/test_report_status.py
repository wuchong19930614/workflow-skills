import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import report_status as RS
import settle
from helpers import TmpRoot, setup_direction


class ReportStatusTest(unittest.TestCase):
    def test_counts_go_and_parked(self):
        with TmpRoot() as root:
            setup_direction(root, slug="good")
            settle.settle(root, "good", "go", None, "r", "u", on="2026-10-20")
            setup_direction(root, slug="later")
            settle.settle(root, "later", "parked", None, "曲线读不出", "u", on="2026-10-20")
            st = RS.status(root, on="2027-02-01")
            self.assertEqual(st["counts"], {"found": 0, "go": 1, "rejected": 0, "parked": 1})
            self.assertEqual(st["go"][0]["base_total"], 160.0)
            self.assertTrue(st["parked"][0]["overdue"])

    def test_empty_workspace(self):
        with TmpRoot() as root:
            st = RS.status(root)
            self.assertEqual(st["semrush_calls_total"], 0)
            self.assertEqual(st["found_ranked"], [])


if __name__ == "__main__":
    unittest.main()
