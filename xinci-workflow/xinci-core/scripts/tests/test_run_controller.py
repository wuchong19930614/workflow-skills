import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_controller as RC
import run_manifest as RM
import trigger_pool as TP


class RunControllerTest(unittest.TestCase):
    ZEROS = {"extracted": 0, "rejected_zero_cost": 0,
             "rejected_g1": 0, "deep_audited": 0, "queued": 0}
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def snapshot(self):
        """运行会话、运行清单与账本的原文快照,用来断言被拒绝的写入什么都没改。"""
        out = {}
        for d in (self.root / RC.SESSION_DIR, self.root / "运行", self.root / "账本"):
            if d.is_dir():
                for path in sorted(d.glob("*.json")):
                    out[str(path.relative_to(self.root))] = path.read_text(encoding="utf-8")
        return out

    def _is_blank_manifest(self, rel):
        obj = json.loads((self.root / rel).read_text(encoding="utf-8"))
        return not obj.get("rounds") and not obj.get("termination")

    @contextmanager
    def refused(self, error=None):
        """断言写入被拒绝(抛 RunControllerError 或指定异常)且数据区没有实质变化。
        record_round / finish 在校验前会先确保本 run 的清单文件存在,一份新出现的空清单
        (无 rounds、无 termination)不算写入;其余任何字节变化都算。
        断言的是行为而不是某句中文措辞,改文案不该让用例变红。"""
        before = self.snapshot()
        with self.assertRaises(error or RC.RunControllerError):
            yield
        after = self.snapshot()
        for rel in set(after) - set(before):
            if rel.startswith("运行/") and self._is_blank_manifest(rel):
                after.pop(rel)
        self.assertEqual(after, before)

    def seed_candidate(self, slug="demo", state="captured", gates=None, history=None):
        d = self.root / "账本"
        d.mkdir(parents=True, exist_ok=True)
        (d / "候选账本.json").write_text(json.dumps({
            "schema_version": 1,
            "candidates": {slug: {
                "slug": slug, "state": state, "gates": gates or {},
                "history": history or [],
            }},
        }), encoding="utf-8")

    def seed_manifest(self, run_id, rounds=None, candidates_touched=None, name="2026-08-20-xinci-run.json"):
        d = self.root / "运行"
        d.mkdir(parents=True, exist_ok=True)
        seeded_rounds = list(rounds or [])
        (d / name).write_text(json.dumps({
            "date": "2026-08-20", "skill": "xinci-run", "run_id": run_id,
            "rounds": seeded_rounds,
            "candidates_touched": list(candidates_touched or []),
        }), encoding="utf-8")

    def test_start_round_resume_finish(self):
        run = RC.start(self.root, max_rounds=1)
        self.assertEqual(run["status"], "active")
        RC.begin_round(self.root, run["run_id"])
        resumed = RC.load_session(self.root, run["run_id"])
        self.assertEqual(resumed["current_round"], 1)
        RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        done = RC.finish(self.root, run["run_id"], "budget_reached", "测试预算命中")
        self.assertEqual(done["status"], "budget_reached")
        _, manifest = RC.find_run_manifest(self.root, run["run_id"])
        self.assertEqual(manifest["termination"]["status"], "budget_reached")
        self.assertEqual(manifest["termination"]["rounds_completed"], 1)

    def test_finish_rejects_unproven_terminal_statuses(self):
        run = RC.start(self.root, max_rounds=2)
        with self.refused():
            RC.finish(self.root, run["run_id"], "budget_reached", "提前收尾")
        with self.refused():
            RC.finish(self.root, run["run_id"], "quota_exhausted", "声称额度耗尽")
        with self.refused():
            RC.finish(self.root, run["run_id"], "calibration_triggered", "声称校准")
        self.assertEqual(RC.load_session(self.root, run["run_id"])["status"], "active")

    def test_quota_finish_persists_evidence(self):
        run = RC.start(self.root)
        ref = "证据/运行/semrush-quota.txt"
        path = self.root / ref
        path.parent.mkdir(parents=True)
        path.write_text("Semrush UI quota exhausted", encoding="utf-8")
        done = RC.finish(self.root, run["run_id"], "quota_exhausted",
                         "网页版实际显示额度耗尽", [ref])
        self.assertEqual(done["status"], "quota_exhausted")
        _, manifest = RC.find_run_manifest(self.root, run["run_id"])
        self.assertEqual(manifest["termination"]["evidence_refs"], [ref])

    def test_record_round_separates_trigger_funnel_and_read_only_reviews(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"])
        self.seed_candidate()
        trigger = TP.add(self.root, observed_date="2026-08-31", title="New official rule",
                         source_url="https://agency.example/new-rule", source_family="agency",
                         task_hypothesis="firms may need a task", actor="xinci-run",
                         run_id=run["run_id"])
        TP.discard(self.root, trigger["trigger_id"], reason="no repeat paid task",
                   actor="xinci-run", run_id=run["run_id"])
        reviewed = [{"slug": "demo", "outcome": "reviewed_no_transition",
                     "reason": "existing evidence still current", "evidence_refs": []}]
        result = RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS),
                                 candidates_reviewed=reviewed)
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["rounds"][0]["candidates_touched"], [])
        self.assertEqual(manifest["rounds"][0]["candidates_reviewed"], reviewed)
        self.assertEqual(manifest["rounds"][0]["trigger_funnel"]["harvested"], 1)
        self.assertEqual(manifest["rounds"][0]["trigger_funnel"]["discarded_preapproval"], 1)

    def test_record_round_rejects_missing_review_evidence(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"])
        self.seed_candidate()
        reviewed = [{"slug": "demo", "outcome": "awaiting_external_evidence",
                     "reason": "等待复核", "evidence_refs": ["证据/demo/missing.json"]}]
        with self.refused():
            RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS),
                            candidates_reviewed=reviewed)

    def test_record_round_rejects_unknown_reviewed_slug(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"])
        self.seed_candidate()
        reviewed = [{"slug": "ghost", "outcome": "not_due", "reason": "不存在的候选"}]
        with self.refused():
            RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS),
                            candidates_reviewed=reviewed)

    def test_record_round_rejects_unbalanced_funnel_via_manifest_contract(self):
        """record_round 不再自校验;漏斗加总等契约由 validate_manifest 一处把关。"""
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"])
        with self.refused():
            RC.record_round(self.root, run["run_id"],
                            funnel=dict(self.ZEROS, extracted=2, rejected_zero_cost=1))
        with self.refused():
            RC.record_round(self.root, run["run_id"], funnel=None)
        with self.refused():
            RC.record_round(self.root, run["run_id"], billable_calls=-1,
                            funnel=dict(self.ZEROS))
        self.assertEqual(RC.load_session(self.root, run["run_id"])["rounds_completed"], 0)

    def test_record_single_manifest_is_atomic_and_non_overwriting(self):
        path, obj = RM.record_single(
            self.root, run_date="2026-08-31", skill="xinci-track",
            notes=["完成一次复查"])
        self.assertTrue(path.is_file())
        self.assertEqual(obj["skill"], "xinci-track")
        with self.refused(RM.RunManifestError):
            RM.record_single(self.root, run_date="2026-08-31", skill="xinci-track")

    def test_trigger_funnel_is_derived_from_pool_events(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"])
        pending = TP.add(self.root, observed_date="2026-08-31", title="Pending trigger",
                         source_url="https://agency.example/pending", source_family="agency",
                         task_hypothesis="possible task", actor="xinci-run", run_id=run["run_id"])
        approved = TP.add(self.root, observed_date="2026-08-31", title="Approved trigger",
                          source_url="https://agency.example/approved", source_family="agency",
                          task_hypothesis="possible task", actor="xinci-run", run_id=run["run_id"])
        TP.approve(self.root, approved["trigger_id"], query="approved trigger checker",
                   search_evidence_urls=["https://forum.example/q"], payer="firm",
                   repeat_unit="filing", self_serve_path="upload", reason="repeat task",
                   base_case_source="https://agency.example/impact",
                   actor="xinci-run", run_id=run["run_id"])
        result = RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        self.assertEqual(result["round"]["trigger_funnel"],
                         {"harvested": 2, "discarded_preapproval": 0,
                          "discarded_postapproval": 0, "pending": 1, "approved": 1})
        self.assertNotIn("metrics", result["round"])
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        self.assertNotIn("metrics_summary", manifest)
        del pending

    def test_new_round_rejects_legacy_pooled_sink(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"])
        with self.refused():
            RC.record_round(self.root, run["run_id"],
                            funnel=dict(self.ZEROS, extracted=2, pooled=2))

    def test_funnel_pooled_is_optional_for_legacy_manifests(self):
        """新轮次不需要 pooled 字段。"""
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"])
        RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        self.assertEqual(RC.load_session(self.root, run["run_id"])["rounds_completed"], 1)

    def test_only_one_active_session(self):
        run = RC.start(self.root)
        self.assertEqual(RC.list_sessions(self.root)["active"], [run["run_id"]])
        with self.assertRaises(RC.RunControllerError):
            RC.start(self.root)

    def test_chinese_status_alias_and_human_rendering(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"])
        RC.record_round(self.root, run["run_id"], funnel={
            "extracted": 0, "rejected_zero_cost": 0, "rejected_g1": 0,
            "deep_audited": 0, "queued": 0,
        })
        done = RC.finish(self.root, run["run_id"], "运行预算已用完", "一轮预算已用完")
        self.assertEqual(done["status"], "budget_reached")
        rendered = RC.render_human_result("show", done)
        self.assertIn("运行状态：运行预算已用完", rendered)
        self.assertNotIn("budget_reached", rendered)

    def test_historical_reason_is_localized_without_mutation(self):
        obj = {
            "run_id": "run-20260820T000000Z-1234abcd",
            "status": "budget_reached",
            "rounds_completed": 6,
            "max_rounds": 6,
            "finish_reason": "max_rounds=6; 无GO; SERP unusual traffic",
        }
        rendered = RC.render_human_result("show", obj)
        self.assertIn("最大轮次=6", rendered)
        self.assertIn("无可交付", rendered)
        self.assertIn("搜索结果页 异常流量提示", rendered)
        self.assertNotIn("max_rounds", rendered)

    def test_round_budget_is_enforced(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"])
        RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        with self.assertRaises(RC.RunControllerError):
            RC.begin_round(self.root, run["run_id"])

    def test_ten_discovery_rounds_force_completed_calibration(self):
        run = RC.start(self.root, max_rounds=2)
        original = RC._discovery_rounds_since_calibration
        try:
            RC._discovery_rounds_since_calibration = lambda _: 10
            with self.refused():
                RC.begin_round(self.root, run["run_id"], round_type="discovery")
            RC.begin_round(self.root, run["run_id"], round_type="calibration")
        finally:
            RC._discovery_rounds_since_calibration = original

    def test_calibration_round_requires_evidenced_audit(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"], round_type="calibration")
        with self.assertRaisesRegex(RC.RunControllerError, "false_negative_audit"):
            RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))

    def test_calibration_round_records_evidenced_audit_and_metrics(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"], round_type="calibration")
        evidence = self.root / "证据" / "calibration.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("{}", encoding="utf-8")
        samples = []
        for gate, target in RM.CALIBRATION_TARGETS.items():
            for index in range(target):
                samples.append({"term": f"old term {gate} {index}", "gate": gate,
                                "outcome": "valid_reject", "reason": "复核后原否决仍成立",
                                "evidence_refs": ["证据/calibration.json"]})
        audit = {"status": "completed", "reason": "完成默认分层复核", "untested_gates": [],
                 "samples": samples}
        result = RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS),
                                 false_negative_audit=audit)
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["rounds"][0]["false_negative_audit"]["samples"]), 35)
        self.assertEqual(manifest["rounds"][0]["round_type"], "calibration")

    def test_completed_calibration_rejects_short_sample_and_wrong_untested_gates(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"], round_type="calibration")
        evidence = self.root / "证据" / "calibration.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("{}", encoding="utf-8")
        audit = {"status": "completed", "reason": "错误地声称完成", "untested_gates": [],
                 "samples": [{"term": "one", "gate": "G1", "outcome": "valid_reject",
                              "reason": "仍成立", "evidence_refs": ["证据/calibration.json"]}]}
        with self.refused():
            RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS),
                            false_negative_audit=audit)

    def test_confirmation_is_write_once(self):
        run = RC.start(self.root)
        RC.begin_round(self.root, run["run_id"])
        self.seed_candidate(gates={"G3": "veto_window_bet"})
        RC.confirm_window_bet(self.root, run["run_id"], "demo")
        confirmation = RC.load_session(self.root, run["run_id"])["confirmations"]["demo"]
        self.assertEqual(set(confirmation), {"risk", "confirmed_at"})
        with self.refused():
            RC.confirm_window_bet(self.root, run["run_id"], "demo")

    def test_confirmation_cannot_be_precreated(self):
        run = RC.start(self.root)
        with self.refused():
            RC.confirm_window_bet(self.root, run["run_id"], "ghost")
        self.seed_candidate(gates={"G3": "pass"})
        with self.assertRaisesRegex(RC.RunControllerError, "G3=veto_window_bet"):
            RC.confirm_window_bet(self.root, run["run_id"], "demo")

    def test_go_finish_requires_candidate_produced_by_this_run(self):
        run = RC.start(self.root)
        self.seed_manifest(run["run_id"])
        with self.refused():
            RC.finish(self.root, run["run_id"], "go", "声称成功")
        self.seed_candidate(state="build_ready", history=[{
            "at": "2026-08-20T00:00:00+00:00", "from": "qualified",
            "to": "build_ready", "by": "xinci-run", "run_id": "run-other",
        }])
        with self.refused():
            RC.finish(self.root, run["run_id"], "go", "不是本次产出")
        self.seed_candidate(state="build_ready", history=[{
            "at": "2026-08-20T00:00:00+00:00", "from": "qualified",
            "to": "build_ready", "by": "xinci-run", "run_id": run["run_id"],
        }])
        self.seed_manifest(run["run_id"], candidates_touched=["demo"])
        done = RC.finish(self.root, run["run_id"], "go", "本次产出")
        self.assertEqual(done["go_candidates"], ["demo"])

    def test_finish_rejects_non_sequential_manifest_rounds(self):
        run = RC.start(self.root)
        RC.begin_round(self.root, run["run_id"])
        result = RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        path = Path(result["manifest"])
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["rounds"][0]["round"] = 99
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.refused():
            RC.finish(self.root, run["run_id"], "cancelled", "测试")

    def test_finish_rejects_candidate_missing_from_manifest(self):
        run = RC.start(self.root)
        self.seed_candidate(history=[{
            "at": "2026-08-20T00:00:00+00:00", "from": None,
            "to": "captured", "by": "xinci-run", "run_id": run["run_id"],
        }])
        self.seed_manifest(run["run_id"])
        with self.assertRaisesRegex(RC.RunControllerError, "candidates_touched"):
            RC.finish(self.root, run["run_id"], "cancelled", "测试")

    def test_finish_rejects_manifest_schema_drift(self):
        run = RC.start(self.root)
        self.seed_manifest(run["run_id"])
        path = self.root / "运行" / "2026-08-20-xinci-run.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest.pop("date")
        manifest["evil"] = True
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.refused():
            RC.finish(self.root, run["run_id"], "cancelled", "测试")
        self.assertEqual(RC.load_session(self.root, run["run_id"])["status"], "active")

    def test_record_round_derives_candidates_and_aggregates_manifest(self):
        run = RC.start(self.root)
        RC.begin_round(self.root, run["run_id"])
        self.seed_candidate(history=[{
            "at": "2026-08-20T00:00:00+00:00", "from": None, "to": "captured",
            "by": "xinci-run", "run_id": run["run_id"], "round": 1,
            "gates": {"G0": "pass", "G4": "pass", "G5": "pass"},
            "expiry": "2026-08-27",
        }])
        result = RC.record_round(
            self.root, run["run_id"], sources_opened=["https://e.com/source"],
            sources_blocked=["https://e.com/blocked(CAPTCHA)"], billable_calls=2,
            notes=["本轮事实"], funnel=dict(self.ZEROS, queued=1, extracted=1))
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["rounds"][0]["candidates_touched"], ["demo"])
        self.assertEqual(manifest["candidates_touched"], ["demo"])
        self.assertEqual(manifest["billable_calls"], 2)
        self.assertEqual(RC.load_session(self.root, run["run_id"])["rounds_completed"], 1)

    def test_record_round_retries_after_session_write_failure(self):
        run = RC.start(self.root)
        RC.begin_round(self.root, run["run_id"])
        with patch.object(RC, "_save", side_effect=OSError("模拟 session 写入中断")):
            with self.assertRaises(OSError):
                RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        self.assertEqual(RC.load_session(self.root, run["run_id"])["current_round"], 1)
        result = RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["rounds"]), 1)

    def test_finish_retries_after_session_write_failure(self):
        run = RC.start(self.root)
        with patch.object(RC, "_save", side_effect=OSError("模拟 session 写入中断")):
            with self.assertRaises(OSError):
                RC.finish(self.root, run["run_id"], "cancelled", "测试重试")
        self.assertEqual(RC.load_session(self.root, run["run_id"])["status"], "active")
        done = RC.finish(self.root, run["run_id"], "cancelled", "测试重试")
        self.assertEqual(done["status"], "cancelled")

    def test_structurally_corrupt_session_fails_on_load(self):
        run = RC.start(self.root)
        path = self.root / RC.SESSION_DIR / f"{run['run_id']}.json"
        body = json.loads(path.read_text(encoding="utf-8"))
        body["rounds_completed"] = body["max_rounds"] + 1
        path.write_text(json.dumps(body), encoding="utf-8")
        with self.assertRaisesRegex(RC.RunControllerError, "max_rounds/rounds_completed"):
            RC.load_session(self.root, run["run_id"])

    def test_record_round_rejects_unpersisted_queued_claim(self):
        run = RC.start(self.root)
        RC.begin_round(self.root, run["run_id"])
        self.seed_candidate(history=[{
            "at": "2026-08-20T00:00:00+00:00", "from": None, "to": "captured",
            "by": "xinci-run", "run_id": run["run_id"], "round": 1,
        }])
        funnel = dict(self.ZEROS, queued=1, extracted=1)
        with self.refused():
            RC.record_round(self.root, run["run_id"], funnel=funnel)

    def test_candidate_touched_again_is_recorded_in_later_round(self):
        run = RC.start(self.root, max_rounds=2)
        RC.begin_round(self.root, run["run_id"])
        self.seed_candidate(gates={"G0": "pass"}, history=[{
            "at": "2026-08-20T00:00:00+00:00", "from": None, "to": "captured",
            "by": "xinci-run", "run_id": run["run_id"], "round": 1,
            "gates": {"G0": "pass"}, "expiry": "2026-08-27",
        }])
        RC.record_round(self.root, run["run_id"],
                        funnel=dict(self.ZEROS, queued=1, extracted=1))
        RC.begin_round(self.root, run["run_id"])
        ledger_path = self.root / "账本" / "候选账本.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["candidates"]["demo"]["history"].append({
            "at": "2026-08-20T01:00:00+00:00", "from": "captured", "to": "captured",
            "by": "xinci-run", "run_id": run["run_id"], "round": 2,
        })
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
        result = RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["rounds"][1]["candidates_touched"], ["demo"])

    def test_corrupt_session_fails_closed(self):
        d = self.root / RC.SESSION_DIR
        d.mkdir(parents=True)
        (d / "run-20260820T000000Z-deadbeef.json").write_text("{坏", encoding="utf-8")
        with self.refused():
            RC.active_sessions(self.root)

    def test_begin_round_echoes_preflight_verdict(self):
        """开轮的中文回显要直接说本轮预检是否满足 G1 前置,不必再跑 run_policy 才知道。"""
        run = RC.start(self.root, max_rounds=2)
        ok = RC.begin_round(self.root, run["run_id"], executor_id="e1",
                            preflight={"controllable": True, "desktop": True,
                                       "region": "us", "logged_out": True})
        text = RC.render_human_result("begin-round", ok)
        self.assertIn("浏览器预检", text)
        self.assertTrue(ok["current_round_preflight"]["g1_ready"])
        self.assertNotIn("不满足", text)

    def test_begin_round_echo_names_failing_preflight_items(self):
        """不达标时要点名是哪几项,否则执行者得自己回去比对四个参数。"""
        run = RC.start(self.root, max_rounds=2)
        bad = RC.begin_round(self.root, run["run_id"], executor_id="e1",
                             preflight={"controllable": True, "desktop": False,
                                        "region": "other", "logged_out": True})
        text = RC.render_human_result("begin-round", bad)
        self.assertFalse(bad["current_round_preflight"]["g1_ready"])
        self.assertIn("不满足", text)
        self.assertIn("桌面", text)
        self.assertIn("美区", text)
        self.assertNotIn("未登录", text.split("不满足", 1)[1])

    def test_begin_round_without_preflight_echoes_absence(self):
        """库级调用可省预检;回显要说明本轮没有预检,而不是沉默。"""
        run = RC.start(self.root, max_rounds=2)
        obj = RC.begin_round(self.root, run["run_id"], executor_id="e1")
        text = RC.render_human_result("begin-round", obj)
        self.assertIn("浏览器预检", text)
        self.assertIn("未提交", text)

    def test_correct_note_appends_without_touching_existing_record(self):
        """清单是审计轨迹:更正只能追加,原备注与轮次数据一字不动。"""
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"], executor_id="e1")
        RC.record_round(self.root, run["run_id"], notes=["原始判断(后被证明有误)"],
                        funnel=dict(self.ZEROS))
        RC.finish(self.root, run["run_id"], status="budget_reached", reason="预算命中")
        path, before = RM.find_run_manifest(self.root, run["run_id"])
        path2, after = RM.correct_note(self.root, run["run_id"], "更正:原判断有误,实际结论相反")
        self.assertEqual(path2, path)
        self.assertEqual(after["rounds"], before["rounds"])
        self.assertEqual(after["termination"], before["termination"])
        self.assertEqual(after["notes"][:len(before["notes"])], before["notes"])
        self.assertEqual(len(after["notes"]), len(before["notes"]) + 1)
        self.assertIn("更正", after["notes"][-1])
        self.assertIn("原判断有误", after["notes"][-1])
        self.assertEqual(after["rounds"][0]["notes"], ["原始判断(后被证明有误)"])
        self.assertEqual(RM.validate_runs(self.root), [])

    def test_correct_note_rejects_unknown_run(self):
        with self.refused(RM.RunManifestError):
            RM.correct_note(self.root, "run-20260820T000000Z-deadbeef", "无处可追加")

    def test_correct_note_rejects_blank_text(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"], executor_id="e1")
        RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        RC.finish(self.root, run["run_id"], status="budget_reached", reason="预算命中")
        with self.refused(RM.RunManifestError):
            RM.correct_note(self.root, run["run_id"], "   ")


if __name__ == "__main__":
    unittest.main()
