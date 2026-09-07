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

    def _manifest(self, samples):
        d = self.root / "运行"; d.mkdir(parents=True, exist_ok=True)
        (d / "2026-09-03-000000-aaaaaaaa-xinci-run.json").write_text(json.dumps({
            "date": "2026-09-03", "skill": "xinci-run",
            "run_id": "run-20260903T000000Z-aaaaaaaa",
            "rounds": [{"round": 1, "round_type": "calibration",
                        "false_negative_audit": {"status": "completed", "reason": "r",
                                                 "samples": samples, "untested_gates": []}}],
        }, ensure_ascii=False), encoding="utf-8")

    def test_skips_terms_already_audited_with_a_verdict(self):
        """已经复核出结论的词不再重复抽。

        实测(2026-09-03 与 2026-09-05 两个校准轮):old-gate-priority 使两次抽到完全
        相同的 35 条,第二轮等于把同一批词又核一遍,校准没有新增覆盖面。
        """
        for i in range(3):
            S.append(self.root, [{"date": "2026-08-01", "term": f"g1-{i}", "gate": "G1",
                                  "reason": "old", "gate_version": "2026-01"}])
        self._manifest([{"term": "g1-0", "gate": "G1", "outcome": "valid_reject",
                         "reason": "已核", "evidence_refs": ["证据/x/a.json"]},
                        {"term": "g1-1", "gate": "G1", "outcome": "inconclusive",
                         "reason": "无现场依据", "evidence_refs": ["证据/x/a.json"]}])
        result = F.build_sample(self.root, {"G1": 2})
        picked = [x["term"] for x in result["samples"]]
        # g1-0 已有结论,排到最后;g1-1 只是 inconclusive,仍应优先补测
        self.assertIn("g1-1", picked)
        self.assertIn("g1-2", picked)
        self.assertNotIn("g1-0", picked)
        self.assertEqual(result["coverage"]["G1"]["already_audited_deprioritised"], 1)


if __name__ == "__main__":
    unittest.main()
