import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import false_negative_sample as F
import screen_index as S


class FalseNegativeSampleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_stratifies_index_and_ledger_without_writes(self):
        S.append(self.root, [{"date": "2026-08-01", "term": "old-g1", "gate": "G1",
                              "reason": "old", "gate_version": "2026-01"}])
        ledger = {"schema_version": 1, "candidates": {"deep": {
            "slug": "deep", "term": "deep-g3", "state": "rejected",
            "first_observed_at": "2026-08-02T00:00:00+00:00", "gates": {"G3": "veto"},
            "evidence_refs": ["证据/deep/a.json"]}}}
        path = self.root / "账本" / "候选账本.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(ledger), encoding="utf-8")
        before = (self.root / S.INDEX_NAME).read_bytes()
        result = F.build_sample(self.root, {"G1": 1, "G3": 1})
        self.assertEqual({x["gate"] for x in result["samples"]}, {"G1", "G3"})
        self.assertEqual(before, (self.root / S.INDEX_NAME).read_bytes())


if __name__ == "__main__":
    unittest.main()
