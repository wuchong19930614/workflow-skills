import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qualification as Q
import registrar as R
import screen_index as S


def observation():
    return {
        "schema_version": 3, "slug": "report", "observed_at": "2026-09-07T00:00:00+00:00",
        "stage": "qualify", "points": ["按次报告交付有实际需求；自然查询存在未覆盖的导出任务"],
        "source_urls": ["https://example.com/serp"],
        "gates": {"G6": "pass", "G7": "pass", "G8": "pass"},
        "g6_lines": {"subscription": "veto", "paid_report": "pass", "advertising": "N/A",
                     "lead_generation": "inconclusive", "affiliate": "inconclusive", "transaction": "inconclusive"},
        "income_score": 18,
        "assessment": {"evidence_gaps": [], "scores": {"trigger": 14, "task": 12,
            "language": 7, "competition": 25, "alignment": 14, "income": 18}, "risks": [],
            "seo": {"query": "report export", "gap": "既有结果缺对象批量导出",
                    "source_urls": ["https://example.com/serp"]}},
    }


class QualificationTest(unittest.TestCase):
    def test_one_off_report_can_qualify_with_other_lines_unknown(self):
        result = Q.assess(observation())
        self.assertEqual(result, {"outcome": "qualified", "score": 90,
                                 "income_score": 18, "g6_passed_lines": ["paid_report"]})

    def test_dimension_risk_is_not_subtracted_twice(self):
        obs = observation()
        obs["assessment"]["risks"] = [{"id": "cost", "charged_to": "income", "deduction": 2,
                                        "reason": "交付成本已体现在收入分"}]
        self.assertEqual(Q.assess(obs)["score"], 90)
        obs["assessment"]["risks"].append({"id": "official", "charged_to": "red_team",
                                            "deduction": 11, "reason": "新增独立替代风险"})
        self.assertEqual(Q.assess(obs)["outcome"], "disqualified")
        self.assertEqual(Q.assess(obs)["score"], 79)

    def test_duplicate_risk_rejected_across_dimension_and_red_team(self):
        obs = observation()
        obs["assessment"]["risks"] = [{"id": "cost", "charged_to": "income", "deduction": 2, "reason": "r"},
            {"id": " COST ", "charged_to": "red_team", "deduction": 2, "reason": "r"}]
        with self.assertRaisesRegex(ValueError, "重复扣分"):
            Q.assess(obs)

    def test_missing_decisive_coverage_defers_without_score(self):
        obs = observation()
        obs["assessment"]["evidence_gaps"] = [{"item": "market", "kind": "coverage",
            "decisive": True, "resolved": False, "reason": "服务无覆盖，替代证据未取得"}]
        with self.assertRaisesRegex(ValueError, "不得产生分数"):
            Q.assess(obs)
        obs["assessment"].update(scores=None, seo=None)
        obs.pop("income_score")
        self.assertEqual(Q.assess(obs)["outcome"], "defer")
        obs["gates"] = {"G4": "veto"}
        self.assertEqual(Q.assess(obs)["outcome"], "disqualified")

    def test_proxy_resolves_decisive_gap_and_seo_must_be_sourced(self):
        obs = observation()
        obs["assessment"]["evidence_gaps"] = [{"item": "market", "kind": "coverage",
            "decisive": True, "resolved": True, "reason": "有直接客户案例与公开产品覆盖替代"}]
        self.assertEqual(Q.assess(obs)["outcome"], "qualified")
        obs["assessment"]["seo"]["source_urls"] = ["https://not-opened.example.com"]
        with self.assertRaisesRegex(ValueError, "SEO 来源"):
            Q.assess(obs)

    def test_registrar_validates_v3_and_keeps_v2_read_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "2026-09-07-qualify.json"
            obs = observation()
            p.write_text(json.dumps(obs))
            R._check_observation(p, p.name, "report")
            obs.pop("assessment")
            p.write_text(json.dumps(obs))
            with self.assertRaisesRegex(R.RegistrarError, "assessment"):
                R._check_observation(p, p.name, "report")
            obs["schema_version"] = 2
            obs["g6_lines"] = {k: "N/A" if v == "inconclusive" else v for k, v in obs["g6_lines"].items()}
            p.write_text(json.dumps(obs))
            R._check_observation(p, p.name, "report")

    def test_unknown_line_cannot_support_whole_candidate_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obs = observation()
            obs.pop("assessment"); obs.pop("income_score"); obs.pop("g6_lines")
            obs.update(stage="scan", gates={}, g6_tentative_lines=dict.fromkeys(Q.MONETIZATION_LINES, "tentative_veto"))
            obs["g6_tentative_lines"]["paid_report"] = "tentative_inconclusive"
            ref = "证据/report/2026-09-07-scan.json"
            p = root / ref; p.parent.mkdir(parents=True); p.write_text(json.dumps(obs))
            R._check_observation(p, ref, "report")
            self.assertFalse(R._has_no_applicable_tentative_g6(root, [ref], "new"))

    def test_formal_veto_cannot_bypass_six_line_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = observation()
            obs.pop("income_score")
            obs["assessment"].update(scores=None, seo=None)
            obs["gates"] = {"G6": "veto"}
            obs.pop("g6_lines")
            path = Path(tmp) / "2026-09-07-qualify.json"
            path.write_text(json.dumps(obs))
            with self.assertRaisesRegex(R.RegistrarError, "完整逐线证据"):
                R._check_observation(path, path.name, "report")
            obs["g6_lines"] = dict.fromkeys(Q.MONETIZATION_LINES, "veto")
            obs["g6_lines"]["paid_report"] = "inconclusive"
            path.write_text(json.dumps(obs))
            with self.assertRaisesRegex(R.RegistrarError, "未知不等于否决"):
                R._check_observation(path, path.name, "report")
            obs["gates"] = {"G3": "veto"}
            path.write_text(json.dumps(obs))
            with self.assertRaisesRegex(R.RegistrarError, "盈利线仍未知"):
                R._check_observation(path, path.name, "report")

    def test_serp_recheck_is_due_but_does_not_release_duplicate(self):
        rec = {"gate_version": S.GATE_VERSION, "gate": "G1", "date": "2026-08-08"}
        self.assertTrue(S.review_due(rec, today=date(2026, 9, 7)))
        self.assertFalse(S.review_due(rec, today=date(2026, 9, 6)))
        rec["gate"] = "G0"
        self.assertFalse(S.review_due(rec, today=date(2026, 9, 7)))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = {"term": "old report", "gate": "G1", "date": "2026-08-01",
                   "gate_version": "old", "reason": "old judgement"}
            S.append(root, [row])
            before = (root / S.INDEX_NAME).read_bytes()
            result = S.check(root, ["old report"])
            self.assertTrue(result["seen"][0]["review_due"])
            self.assertEqual(result["fresh"], [])
            self.assertEqual(before, (root / S.INDEX_NAME).read_bytes())

    def test_schema_accepts_v3_unknown_but_rejects_legacy_unknown(self):
        try:
            import jsonschema
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest("JSON Schema 引擎未安装")
        base = Path(__file__).resolve().parents[2] / "数据结构"
        schema = json.loads((base / "observation.schema.json").read_text())
        schema["$id"] = "https://xinci.local/observation.schema.json"
        resource = Resource.from_contents(json.loads((base / "assessment.schema.json").read_text()))
        registry = Registry().with_resource("https://xinci.local/assessment.schema.json", resource)
        validator = jsonschema.Draft7Validator(schema, registry=registry)
        obs = observation()
        self.assertEqual(list(validator.iter_errors(obs)), [])
        obs["schema_version"] = 2
        obs.pop("assessment")
        self.assertTrue(list(validator.iter_errors(obs)))
        obs["g6_lines"] = {k: "N/A" if v == "inconclusive" else v for k, v in obs["g6_lines"].items()}
        self.assertEqual(list(validator.iter_errors(obs)), [])

    def test_offline_audit_reports_review_candidates_without_mutation(self):
        import audit_rejections
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "账本").mkdir()
            path = root / "账本/候选账本.json"
            path.write_text(json.dumps({"schema_version": 1, "candidates": {"report": {
                "state": "disqualified", "score": 59, "evidence_refs": [],
                "history": [{"reason": "一次性报告"}]}}}))
            before = path.read_bytes()
            result = audit_rejections.build(root)
            self.assertEqual(result["groups"]["评分认定"]["count"], 1)
            self.assertEqual(result["groups"]["评分认定"]["samples"][0]["review_status"], "needs_review")
            self.assertEqual(before, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
