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
    def test_submission_proposals_preserve_verdict_evidence_and_mode(self):
        import argparse
        import copy
        ref = "证据/report/2026-09-07-qualify.json"
        for outcome in ("qualified", "low_score", "veto", "defer"):
            with self.subTest(outcome=outcome):
                obs = observation()
                if outcome == "low_score":
                    obs["assessment"]["scores"]["competition"] = 10
                if outcome in {"veto", "defer"}:
                    obs.pop("income_score")
                    obs["assessment"].update(scores=None, seo=None)
                    if outcome == "veto":
                        obs["gates"] = {"G4": "veto"}
                    else:
                        obs["assessment"]["evidence_gaps"] = [{"item": "market", "kind": "coverage",
                            "decisive": True, "resolved": False, "reason": "缺决定性证据"}]
                before = copy.deepcopy(obs)
                proposal = Q.submission_proposal(obs, ref, "xinci-run", "run-test", current_state="formation_confirmed")
                argv = proposal["registrar_argv"]
                parser = argparse.ArgumentParser()
                for flag, options in R.CLI_SPEC[argv[0]][1]:
                    parser.add_argument(flag, **options)
                supplied = argv[1:]
                for flag in proposal["missing_arguments"]:
                    supplied += [flag, "2026-10-01" if flag == "--pending-until" else "现场依据"]
                args = parser.parse_args(supplied)
                self.assertEqual(args.evidence, [ref])
                self.assertEqual(args.by, "xinci-run")
                self.assertEqual(args.run_id, "run-test")
                if outcome in {"qualified", "low_score"}:
                    self.assertEqual(args.score, Q.assess(obs)["score"])
                    self.assertEqual(args.g6_passed_lines, "paid_report")
                elif outcome == "veto":
                    self.assertIsNone(args.score)
                    self.assertEqual(args.gates, "G4=veto")
                else:
                    self.assertEqual(args.pending_evidence, ["market"])
                self.assertFalse(proposal["executed"])
                self.assertEqual(obs, before)

    def test_submission_proposal_rejects_unsafe_reference_and_incomplete_mode(self):
        for ref, by, run_id in [("../x.json", "xinci-qualify", None),
                                ("/tmp/x.json", "xinci-qualify", None),
                                ("证据/other/2026-09-07-qualify.json", "xinci-qualify", None),
                                ("证据/report/2026-09-07-qualify.json", "xinci-run", None),
                                ("证据/report/2026-09-07-qualify.json", "xinci-qualify", "run-test")]:
            with self.subTest(ref=ref, by=by), self.assertRaises(ValueError):
                Q.submission_proposal(observation(), ref, by, run_id, current_state="formation_confirmed")

    def test_cli_proposal_reads_live_state_and_does_not_mutate_ledger(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = "证据/report/2026-09-07-qualify.json"
            path = root / ref
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(observation()))
            ledger = root / "账本/候选账本.json"
            ledger.parent.mkdir()
            for state in ("formation_confirmed", "hold", "rejected"):
                ledger.write_text(json.dumps({"candidates": {"report": {"state": state}}}))
                before = ledger.read_bytes()
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = Q.main([str(path), "--evidence-ref", ref, "--data-root", str(root)])
                self.assertEqual(ledger.read_bytes(), before)
                if state == "rejected":
                    self.assertEqual(code, 2)
                else:
                    self.assertEqual(code, 0, stderr.getvalue())
                    result = json.loads(stdout.getvalue())
                    self.assertEqual(result["current_state"], state)
                    self.assertEqual(bool(result["registrar_argv"]), state == "formation_confirmed")

    def test_hold_proposal_only_transitions_on_disqualification(self):
        ref = "证据/report/2026-09-07-qualify.json"
        obs = observation()
        passed = Q.submission_proposal(obs, ref, current_state="hold")
        self.assertEqual(passed["registrar_argv"], [])
        self.assertIn("xinci-decide", passed["next_action"])
        obs["assessment"]["scores"]["competition"] = 10
        failed = Q.submission_proposal(obs, ref, current_state="hold")
        self.assertEqual(failed["registrar_argv"][failed["registrar_argv"].index("--to") + 1], "disqualified")
        obs.pop("income_score")
        obs["assessment"].update(scores=None, seo=None, evidence_gaps=[{
            "item": "market", "kind": "coverage", "decisive": True,
            "resolved": False, "reason": "缺决定性证据"}])
        pending = Q.submission_proposal(obs, ref, current_state="hold")
        self.assertEqual(pending["registrar_argv"], [])
        self.assertEqual(pending["missing_arguments"], [])
        for state in ("captured", "qualified", "disqualified", None):
            with self.subTest(state=state), self.assertRaises(ValueError):
                Q.submission_proposal(obs, ref, current_state=state)

    def test_low_income_score_does_not_imply_total_below_threshold(self):
        obs = observation()
        obs["assessment"]["scores"] = dict(Q.WEIGHTS, income=1)
        obs["income_score"] = 1
        self.assertEqual(Q.assess(obs)["score"], 81)
        self.assertEqual(Q.assess(obs)["outcome"], "qualified")

    def test_scan_and_track_cannot_publish_formal_g6_but_legacy_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            for stage in ("scan", "track"):
                with self.subTest(stage=stage):
                    obs = observation()
                    obs.pop("assessment")
                    obs.pop("income_score")
                    obs.update(stage=stage, gates={"G6": "pass"})
                    obs["g6_lines"] = {k: "N/A" if v == "inconclusive" else v
                                       for k, v in obs["g6_lines"].items()}
                    path = Path(tmp) / f"2026-09-07-{stage}.json"
                    path.write_text(json.dumps(obs))
                    with self.assertRaisesRegex(R.RegistrarError, "不得产生正式 G6"):
                        R._check_observation(path, path.name, "report")
                    obs["schema_version"] = 2
                    path.write_text(json.dumps(obs))
                    R._check_observation(path, path.name, "report")
                    obs["schema_version"] = 3
                    obs["g6_tentative_lines"] = {k: "N/A" if v == "N/A" else "tentative_" + v
                                                 for k, v in obs.pop("g6_lines").items()}
                    obs["gates"] = {"G3": "pass"}
                    path.write_text(json.dumps(obs))
                    R._check_observation(path, path.name, "report")

    def test_missing_advertising_estimate_can_defer_or_allow_other_line(self):
        obs = observation()
        obs["g6_lines"]["advertising"] = "inconclusive"
        self.assertEqual(Q.assess(obs)["outcome"], "qualified")
        obs["g6_lines"]["paid_report"] = "veto"
        obs["gates"] = {"G7": "pass", "G8": "pass"}
        obs.pop("income_score")
        obs["assessment"].update(scores=None, seo=None, evidence_gaps=[{
            "item": "advertising estimate", "kind": "coverage", "decisive": True,
            "resolved": False, "reason": "量级来源未取得，尚不能证明广告收入达标或不足"}])
        self.assertEqual(Q.assess(obs)["outcome"], "defer")

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
        for stage in ("scan", "track"):
            obs["stage"] = stage
            self.assertEqual(list(validator.iter_errors(obs)), [])  # v2 remains readable
            obs["schema_version"] = 3
            self.assertTrue(list(validator.iter_errors(obs)))
            obs["schema_version"] = 2

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
