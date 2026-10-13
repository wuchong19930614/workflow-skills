import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import seeds as S
from _common import BenchError, REJECTS_REL, load_json
from helpers import TmpRoot

OBS = "证据/_scan/20261013T080000000000Z-abcd1234-scan.json"


class SeedsTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(S.normalize_domain("https://www.Example.com/a?b=1"), "example.com")
        self.assertEqual(S.normalize_domain("sub.example.co.uk"), "sub.example.co.uk")
        self.assertEqual(S.normalize_domain("Example.COM.:443"), "example.com")
        with self.assertRaises(BenchError):
            S.normalize_domain("not a domain")

    def test_add_take_and_dedup(self):
        with TmpRoot() as root:
            self.assertTrue(S.add(root, "a.com", "serp", "查询 x 的首页"))
            self.assertFalse(S.add(root, "www.a.com", "serp", "重复"))
            S.add(root, "b.com", "serp", "查询 y")
            S.add(root, "c.com", "geo", "AI 概览推荐")
            self.assertEqual([s["domain"] for s in S.take(root, "serp")], ["a.com", "b.com"])
            S.mark_checked(root, ["a.com"])
            self.assertEqual([s["domain"] for s in S.take(root, "serp")], ["b.com"])

    def test_reject_sets_recheck_only_for_b3(self):
        with TmpRoot() as root:
            only_b3 = S.reject(root, "a.com", ["B3"], "美区 2,100", OBS, on="2026-10-13")
            self.assertEqual(only_b3["recheck_after"], "2027-01-11")
            mixed = S.reject(root, "b.com", ["B2", "B3"], "AS 45", OBS, on="2026-10-13")
            self.assertIsNone(mixed["recheck_after"])
            self.assertFalse(S.add(root, "a.com", "serp", "淘汰过的不重复登记"))

    def test_requeue_due(self):
        with TmpRoot() as root:
            S.add(root, "a.com", "serp", "x")
            S.reject(root, "a.com", ["B3"], "美区 2,100", OBS, on="2026-10-13")
            self.assertEqual(S.requeue(root, on="2027-01-10"), [])
            self.assertEqual(S.requeue(root, on="2027-01-11"), ["a.com"])
            self.assertEqual([s["domain"] for s in S.take(root, "serp")], ["a.com"])
            self.assertEqual(load_json(root / REJECTS_REL)["domains"], {})

    def test_reject_needs_scan_observation(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "scan 观察"):
                S.reject(root, "a.com", ["B3"], "x", "证据/s/a.json")

    def test_stats(self):
        with TmpRoot() as root:
            S.add(root, "a.com", "serp", "x")
            S.add(root, "b.com", "legacy", "y", role="sibling")
            S.reject(root, "c.com", ["B3"], "z", OBS, on="2026-01-01")
            st = S.stats(root, on="2026-10-13")
            self.assertEqual(st["pending"], {"serp/benchmark": 1, "legacy/sibling": 1})
            self.assertEqual(st["recheck_due"], 1)


if __name__ == "__main__":
    unittest.main()
