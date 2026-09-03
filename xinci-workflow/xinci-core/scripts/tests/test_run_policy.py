import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_controller as RC
import run_policy as RP
import trigger_pool as TP
import registrar as R


class RunPolicyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.root = Path(self._tmp.name)
        self.run = RC.start(self.root, max_rounds=5)

    def tearDown(self): self._tmp.cleanup()

    def seed_backlog(self, count):
        d = self.root / "账本"; d.mkdir(parents=True, exist_ok=True)
        rows = {f"c-{i}": {"slug": f"c-{i}", "lane": "new", "state": "captured", "history": []}
                for i in range(count)}
        (d / "候选账本.json").write_text(json.dumps({"candidates": rows}), encoding="utf-8")

    PREFLIGHT_OK = {"controllable": True, "desktop": True, "region": "us", "logged_out": True}

    def ready(self):
        """开始一轮并自报满足 G1 前置的浏览器预检(预检随 begin-round 写进 session)。"""
        RC.begin_round(self.root, self.run["run_id"], executor_id="worker",
                       preflight=dict(self.PREFLIGHT_OK))

    def seed_ledger(self, rows):
        d = self.root / "账本"; d.mkdir(parents=True, exist_ok=True)
        (d / "候选账本.json").write_text(json.dumps({"candidates": rows}), encoding="utf-8")

    def seed_track_obs(self, slug, day):
        ref = f"证据/{slug}/{day}-track.json"
        path = self.root / ref; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"slug": slug, "observed_at": f"{day}T00:00:00+00:00",
                                    "stage": "track", "points": ["x"]}), encoding="utf-8")
        return ref

    def test_ceiling_is_trigger_only_without_g1_environment(self):
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertEqual(policy["reachable_ceiling"]["state"], "trigger_only")

    def test_ceiling_is_tracking_when_no_candidate_can_reach_formation(self):
        """存量里只有刚进追踪的候选时,存量侧本次最远只能到 tracking。"""
        self.ready()
        ref = self.seed_track_obs("fresh", date.today().isoformat())
        self.seed_ledger({"fresh": {"slug": "fresh", "lane": "new", "state": "tracking",
                                    "evidence_refs": [ref], "history": []}})
        ceiling = RP.evaluate(self.root, self.run["run_id"])["reachable_ceiling"]
        self.assertEqual(ceiling["state"], "tracking")
        self.assertIn("快道", ceiling["why"])  # 不得被读成"本轮不必扫描"

    def test_ceiling_is_go_when_track_span_already_satisfied(self):
        """最早 -track 观察已满 7 天时,本次复查即可凑齐跨度,存量能一路走到 go。"""
        self.ready()
        old_day = (date.today() - timedelta(days=RP.MIN_TRACK_SPAN_DAYS)).isoformat()
        ref = self.seed_track_obs("ripe", old_day)
        self.seed_ledger({"ripe": {"slug": "ripe", "lane": "new", "state": "tracking",
                                   "evidence_refs": [ref], "history": []}})
        ceiling = RP.evaluate(self.root, self.run["run_id"])["reachable_ceiling"]
        self.assertEqual(ceiling["state"], "go")
        self.assertEqual(ceiling["enablers"], ["ripe"])

    def test_ceiling_is_go_for_days_window_screened_candidate(self):
        self.ready()
        self.seed_ledger({"fast": {"slug": "fast", "lane": "new", "state": "screened",
                                   "window_estimate": "days", "history": []}})
        ceiling = RP.evaluate(self.root, self.run["run_id"])["reachable_ceiling"]
        self.assertEqual(ceiling["state"], "go")
        self.assertEqual(ceiling["enablers"], ["fast"])

    def test_ceiling_includes_mature_after_formation_confirmed(self):
        self.ready()
        self.seed_ledger({"mature-ready": {
            "slug": "mature-ready", "lane": "mature",
            "state": "formation_confirmed", "history": []}})
        ceiling = RP.evaluate(self.root, self.run["run_id"])["reachable_ceiling"]
        self.assertEqual(ceiling["state"], "go")
        self.assertEqual(ceiling["enablers"], ["mature-ready"])

    def test_missing_browser_preflight_forces_trigger_only(self):
        # 轮次未开始:没有任何预检
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertEqual(policy["mode"], "trigger_only")
        self.assertFalse(policy["formal_admission"])
        # 轮次已开始但未自报预检(库级调用省略 preflight):同样按缺预检处理
        RC.begin_round(self.root, self.run["run_id"], executor_id="worker")
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertEqual(policy["mode"], "trigger_only")
        self.assertFalse(policy["g1_ready"])

    def test_preflight_not_meeting_g1_forces_trigger_only(self):
        RC.begin_round(self.root, self.run["run_id"], executor_id="worker",
                       preflight=dict(self.PREFLIGHT_OK, region="other"))
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertEqual(policy["mode"], "trigger_only")
        self.assertFalse(policy["g1_ready"])
        self.assertTrue(any("浏览器预检未满足" in r for r in policy["reasons"]))

    def test_preflight_is_bound_to_current_round(self):
        """预检只对本轮有效:record-round 清空它,下一轮必须在 begin-round 时重新自报。"""
        self.ready()
        self.assertEqual(RP.evaluate(self.root, self.run["run_id"])["mode"], "full")
        RC.record_round(self.root, self.run["run_id"], funnel={
            "extracted": 0, "rejected_zero_cost": 0, "rejected_g1": 0,
            "deep_audited": 0, "queued": 0})
        self.assertEqual(RP.evaluate(self.root, self.run["run_id"])["mode"], "trigger_only")

    def test_hard_backlog_gate_forces_debt_only(self):
        self.ready(); self.seed_backlog(21)
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertEqual(policy["mode"], "debt_only")
        self.assertFalse(policy["formal_admission"])
        self.assertEqual(policy["carryover_quota"], 10)

    def test_missing_g1_environment_takes_priority_over_hard_backlog(self):
        self.seed_backlog(21)
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertEqual(policy["mode"], "trigger_only")
        self.assertFalse(policy["g1_ready"])
        self.assertEqual(policy["new_captured_backlog"], 21)

    def test_queued_registration_is_not_decision_progress(self):
        self.ready()
        d = self.root / "账本"; d.mkdir(parents=True, exist_ok=True)
        candidate = {"slug": "demo", "lane": "new", "state": "captured", "history": [{
            "at": "2026-08-25T00:00:00+00:00", "from": None, "to": "captured",
            "by": "xinci-run", "run_id": self.run["run_id"], "round": 1}]}
        (d / "候选账本.json").write_text(json.dumps({"candidates": {"demo": candidate}}), encoding="utf-8")
        self.assertEqual(RP.decision_transitions_by_round(self.root, self.run["run_id"]), {})
        candidate["history"].append({"at": "2026-08-25T01:00:00+00:00", "from": "captured",
                                     "to": "screened", "by": "xinci-run",
                                     "run_id": self.run["run_id"], "round": 2})
        (d / "候选账本.json").write_text(json.dumps({"candidates": {"demo": candidate}}), encoding="utf-8")
        self.assertEqual(RP.decision_transitions_by_round(self.root, self.run["run_id"]), {2: 1})

    def test_stall_requires_net_backlog_growth(self):
        self.ready()
        rounds = []
        for number in range(1, 4):
            rounds.append({"round": number, "funnel": {
                "extracted": 1, "rejected_zero_cost": 0, "rejected_g1": 0,
                "deep_audited": 0, "queued": 1, "carryover_audited": 1}})
        d = self.root / "运行"; d.mkdir(parents=True, exist_ok=True)
        (d / "2026-08-31-xinci-run.json").write_text(json.dumps({
            "date": "2026-08-31", "skill": "xinci-run", "run_id": self.run["run_id"],
            "rounds": rounds}), encoding="utf-8")
        self.seed_ledger({})
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertEqual(policy["captured_backlog_delta_by_round"], {})
        self.assertEqual(policy["consecutive_decision_stall_rounds"], 0)

    def test_three_rounds_of_real_net_backlog_growth_trigger_stall(self):
        self.ready()
        rounds = [{"round": number, "funnel": {
            "extracted": 1, "rejected_zero_cost": 0, "rejected_g1": 0,
            "deep_audited": 0, "queued": 1}} for number in range(1, 4)]
        d = self.root / "运行"; d.mkdir(parents=True, exist_ok=True)
        (d / "2026-08-31-xinci-run.json").write_text(json.dumps({
            "date": "2026-08-31", "skill": "xinci-run", "run_id": self.run["run_id"],
            "rounds": rounds}), encoding="utf-8")
        rows = {f"new-{number}": {
            "slug": f"new-{number}", "lane": "new", "state": "captured",
            "history": [{"run_id": self.run["run_id"], "round": number,
                         "from": None, "to": "captured"}]}
            for number in range(1, 4)}
        self.seed_ledger(rows)
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertEqual(policy["captured_backlog_delta_by_round"], {1: 1, 2: 1, 3: 1})
        self.assertEqual(policy["consecutive_decision_stall_rounds"], 3)
        self.assertEqual(policy["mode"], "debt_only")

    def test_source_family_over_40_percent_stops_that_harvest(self):
        self.ready()
        for i in range(5):
            TP.add(self.root, observed_date="2026-08-25", title=f"Agency rule {i}",
                   source_url=f"https://agency.example/rule-{i}", source_family="agency",
                   task_hypothesis="repeated filing", actor="xinci-run",
                   run_id=self.run["run_id"])
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertTrue(policy["source_rotation_due"])
        self.assertTrue(policy["trigger_harvest"])
        self.assertEqual(policy["blocked_source_families"], ["agency"])
        with self.assertRaisesRegex(TP.TriggerPoolError, "轮换约束"):
            TP.add(self.root, observed_date="2026-08-25", title="Agency rule 6",
                   source_url="https://agency.example/rule-6", source_family="agency",
                   task_hypothesis="repeated filing", actor="xinci-run",
                   run_id=self.run["run_id"])
        TP.add(self.root, observed_date="2026-08-25", title="Platform rule",
               source_url="https://platform.example/rule", source_family="platform",
               task_hypothesis="repeated filing", actor="xinci-run",
               run_id=self.run["run_id"])

    def test_source_share_rule_waits_for_five_adds(self):
        self.ready()
        for i in range(4):
            TP.add(self.root, observed_date="2026-08-25", title=f"Agency early rule {i}",
                   source_url=f"https://agency.example/early-{i}", source_family="agency",
                   task_hypothesis="repeated filing", actor="xinci-run",
                   run_id=self.run["run_id"])
        rotation = TP.source_rotation_status(self.root, self.run["run_id"], current_round=1)
        self.assertEqual(rotation["dominant_share"], 1.0)
        self.assertEqual(rotation["blocked_source_families"], [])
        TP.add(self.root, observed_date="2026-08-25", title="Agency fifth rule",
               source_url="https://agency.example/early-4", source_family="agency",
               task_hypothesis="repeated filing", actor="xinci-run",
               run_id=self.run["run_id"])
        self.assertEqual(
            TP.source_rotation_status(self.root, self.run["run_id"], current_round=1)
            ["blocked_source_families"], ["agency"])

    def test_two_consecutive_dominant_rounds_block_only_that_family(self):
        for round_number in (1, 2):
            TP._append(self.root, {
                "trigger_id": TP._id(f"Agency round {round_number}",
                                      f"https://agency.example/round-{round_number}"),
                "event": "add", "at": "2026-09-01T00:00:00+00:00",
                "actor": "xinci-run", "run_id": self.run["run_id"],
                "round": round_number, "observed_date": "2026-09-01",
                "title": f"Agency round {round_number}",
                "source_url": f"https://agency.example/round-{round_number}",
                "source_family": "agency", "task_hypothesis": "repeated filing"})
        rotation = TP.source_rotation_status(self.root, self.run["run_id"], current_round=3)
        self.assertEqual(rotation["consecutive_family"], "agency")
        self.assertEqual(rotation["blocked_source_families"], ["agency"])

    def test_trigger_origin_must_bind_approved_query(self):
        self.ready()
        added = TP.add(self.root, observed_date="2026-08-25", title="Official filing rule",
                       source_url="https://agency.example/rule", source_family="agency",
                       task_hypothesis="firms check filings", actor="xinci-run",
                       run_id=self.run["run_id"])
        TP.approve(self.root, added["trigger_id"], query="filing rule checker",
                   search_evidence_urls=["https://forum.example/filing-checker"],
                   payer="firm", repeat_unit="filing", self_serve_path="upload and check",
                   base_case_source="https://agency.example/impact", reason="repeated task",
                   actor="xinci-run", run_id=self.run["run_id"])
        R.require_formal_admission(self.root, "xinci-run", self.run["run_id"],
                                   "filing rule checker", "trigger", added["trigger_id"])
        with self.assertRaisesRegex(R.RegistrarError, "trigger.query"):
            R.require_formal_admission(self.root, "xinci-run", self.run["run_id"],
                                       "official filing rule", "trigger", added["trigger_id"])


if __name__ == "__main__": unittest.main()
