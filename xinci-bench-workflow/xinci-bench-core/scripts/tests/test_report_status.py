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
            self.assertEqual(st["counts"], {"found": 0, "go": 1, "rejected": 0, "parked": 1, "watching": 0})
            self.assertEqual(st["go"][0]["base_total"], 160.0)
            self.assertTrue(st["parked"][0]["overdue"])

    def test_empty_workspace(self):
        with TmpRoot() as root:
            st = RS.status(root)
            self.assertEqual(st["semrush_calls_total"], 0)
            self.assertEqual(st["found_ranked"], [])


class QuickStatusTest(unittest.TestCase):
    def test_upcoming_listed_with_run_window(self):
        import quick_pool
        with TmpRoot() as root:
            row = {"source": "wikipedia", "object": "Soon Game", "term": None, "url": "https://en.wikipedia.org/x",
                   "seen_at": "2026-10-14", "playable_at": "2026-10-20", "stage": "Early access"}
            quick_pool.add_items(root, [row], "证据/_quick/20261014T080000000000Z-abcd1234-quick_signal.json")
            q = RS.status(root, on="2026-10-14")["quick"]
            self.assertEqual(q["pool_pending"], 0)                    # 还没开玩,不算待看
            self.assertEqual(q["upcoming"], [{"object": "Soon Game", "stage": "Early access", "playable_at": "2026-10-20",
                                              "run_from": "2026-10-20", "run_to": "2026-10-23"}])


    def test_pending_go_on_top_and_milestones(self):
        import ledger
        from helpers import setup_quick
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            settle.settle(root, slug, "go", None, "r", "u", on="2026-10-20")
            q = RS.status(root, on="2026-10-28")["quick"]
            self.assertEqual(q["pending_go"][0]["slug"], slug)
            self.assertTrue(q["pending_go"][0]["overdue"])            # 建议 10-27 前上线
            ledger.follow_up(root, slug, "started", domain="x.com", on="2026-10-28")
            ledger.follow_up(root, slug, "launched", on="2026-11-01")
            q = RS.status(root, on="2026-12-01")["quick"]
            self.assertEqual(q["pending_go"], [])
            self.assertEqual([m["day"] for m in q["milestones_due"]], [14, 30])

    def test_banner_is_first_line_with_formatted_numbers(self):
        import contextlib
        import io
        from helpers import setup_quick
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            settle.settle(root, slug, "go", None, "r", "u")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                RS.main(["--data-root", str(root)])
            first = buf.getvalue().splitlines()[0]
            self.assertTrue(first.startswith(f"【立即建站】{slug}:基准约 10,000 次访问、$40.00/月"), first)



class SemrushTodayLineTest(unittest.TestCase):
    def test_board_shows_today_usage(self):
        import contextlib
        import io
        with TmpRoot() as root:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                RS.main(["--data-root", str(root)])
            self.assertIn("今天 Semrush 已用 0/100 次", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
