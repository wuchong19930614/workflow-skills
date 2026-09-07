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

    def test_reports_formation_eligible_date_from_earliest_track_observation(self):
        """看板要直接回答"何时可推进",锚点与 registrar 判据同源。

        提醒(3/7/14 天)按进入 tracking 起算,形成跨度按最早 -track 观察起算,
        两者此前各说各话,导致"3 日提醒逾期"被误读成可以推进。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obs = root / "证据" / "demo"
            obs.mkdir(parents=True)
            (obs / "2026-08-31-track.json").write_text(json.dumps(
                {"slug": "demo", "observed_at": "2026-08-31T04:10:00+00:00",
                 "stage": "track", "points": ["x"]}), encoding="utf-8")
            path = root / "账本" / "候选账本.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"candidates": {"demo": {
                "lane": "new", "state": "tracking",
                "first_observed_at": "2026-08-30T00:00:00+00:00",
                "history": [{"from": "screened", "to": "tracking",
                             "at": "2026-08-31T02:32:00+00:00"}],
                "evidence_refs": ["证据/demo/2026-08-31-track.json"]}}}),
                encoding="utf-8")
            row = T.build(root, date(2026, 9, 6))["formation"][0]
            self.assertEqual(row["earliest_track_day"], "2026-08-31")
            self.assertEqual(row["formation_eligible_date"], "2026-09-07")
            self.assertFalse(row["formation_eligible"])
            self.assertEqual(T.build(root, date(2026, 9, 7))["formation_eligible_now"], ["demo"])


if __name__ == "__main__":
    unittest.main()
