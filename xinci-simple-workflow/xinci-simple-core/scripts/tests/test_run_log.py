# run_log:写 运行/<日期>-<skill>[-HHMM].json;同名拒绝覆盖;字段齐全。
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_log as R
from helpers import TmpRoot


class RunLogTest(unittest.TestCase):
    def test_writes_manifest(self):
        with TmpRoot() as root:
            p = R.record(root, date="2026-09-10", skill="xinci-simple-scan",
                         sources_opened=["https://a", "https://a", "https://b"],
                         candidates_touched=["x"], billable_calls=3, notes=["词根 Converter"])
            self.assertEqual(p.name, "2026-09-10-xinci-simple-scan.json")
            d = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(d["sources_opened"], ["https://a", "https://b"])
            self.assertEqual(d["billable_calls"], 3)
            self.assertEqual(d["skill"], "xinci-simple-scan")

    def test_refuses_overwrite_without_suffix(self):
        with TmpRoot() as root:
            R.record(root, date="2026-09-10", skill="xinci-simple-scan", sources_opened=[],
                     candidates_touched=[], billable_calls=0, notes=[])
            with self.assertRaises(R.RunLogError):
                R.record(root, date="2026-09-10", skill="xinci-simple-scan", sources_opened=[],
                         candidates_touched=[], billable_calls=0, notes=[])
            p = R.record(root, date="2026-09-10", skill="xinci-simple-scan", sources_opened=[],
                         candidates_touched=[], billable_calls=0, notes=[], suffix="1530")
            self.assertEqual(p.name, "2026-09-10-xinci-simple-scan-1530.json")

    def test_rejects_unknown_skill_and_bad_calls(self):
        with TmpRoot() as root:
            with self.assertRaises(R.RunLogError):
                R.record(root, date="2026-09-10", skill="xinci-scan", sources_opened=[],
                         candidates_touched=[], billable_calls=0, notes=[])
            with self.assertRaises(R.RunLogError):
                R.record(root, date="2026-09-10", skill="xinci-simple-verify", sources_opened=[],
                         candidates_touched=[], billable_calls=-1, notes=[])

class ProgressTest(unittest.TestCase):
    def record(self, root, skill='xinci-simple-scan', **overrides):
        progress = dict(run_id='test-run', round=1, max_rounds=2, source_kind='root', seed_value='Generator', outcome='completed', next_step='verify')
        progress.update(overrides)
        return R.record(root, date='2026-09-10', skill=skill, sources_opened=[], candidates_touched=[], billable_calls=0, notes=[], progress=progress)

    def test_resume_after_scan_and_after_verify(self):
        with TmpRoot() as root:
            self.record(root)
            self.assertEqual(R.plan(root)['resume']['round'], 1)
            self.assertEqual(R.plan(root)['action'], 'verify')
            self.record(root, skill='xinci-simple-verify', next_step='scan')
            self.assertEqual(R.plan(root)['resume']['round'], 2)
            self.assertEqual(R.plan(root)['next_source'], 'small_site')
            self.assertEqual(R.plan(root)['last_completed_root'], 'Generator')

    def test_budget_and_duplicate_completion_guard(self):
        with TmpRoot() as root:
            self.record(root)
            with self.assertRaises(R.RunLogError):
                self.record(root)
            with self.assertRaises(R.RunLogError):
                self.record(root, round=2, max_rounds=3)
            with self.assertRaises(R.RunLogError):
                self.record(root, round=3)

    def test_blocker_retains_phase(self):
        with TmpRoot() as root:
            self.record(root, outcome='blocked', next_step='scan')
            self.assertEqual(R.plan(root)['action'], 'scan')
            self.assertEqual(R.plan(root)['resume']['run_id'], 'test-run')

    def test_last_round_finishes_and_skip_does_not_rotate(self):
        with TmpRoot() as root:
            self.record(root, outcome='skipped', max_rounds=1)
            self.assertEqual(R.plan(root)['next_source'], 'root')
            self.assertIsNone(R.plan(root)['last_completed_root'])
            self.record(root, skill='xinci-simple-verify', max_rounds=1, next_step='done')
            self.assertIsNone(R.plan(root)['resume'])

    def test_backlog_prefers_verify_without_scanning(self):
        from helpers import register_candidate
        with TmpRoot() as root:
            for i in range(5):
                register_candidate(root, 'term-' + str(i))
            self.assertEqual(R.plan(root)['action'], 'scan')
            self.assertEqual(R.plan(root)['scan_outcome'], 'skipped')

    def test_invalid_next_step_cannot_finish_early(self):
        with TmpRoot() as root:
            with self.assertRaises(R.RunLogError):
                self.record(root, skill='xinci-simple-verify', next_step='done')


if __name__ == "__main__":
    unittest.main()
