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


if __name__ == "__main__":
    unittest.main()
