import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import browser_preflight as BP
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

    def ready(self):
        BP.record(self.root, self.run["run_id"], channel="chrome", controllable=True,
                  desktop=True, region="us", logged_out=True)

    def test_missing_browser_preflight_forces_trigger_only(self):
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertEqual(policy["mode"], "trigger_only")
        self.assertFalse(policy["formal_admission"])

    def test_hard_backlog_gate_forces_debt_only(self):
        self.ready(); self.seed_backlog(21)
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertEqual(policy["mode"], "debt_only")
        self.assertFalse(policy["formal_admission"])
        self.assertEqual(policy["carryover_quota"], 10)

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

    def test_source_family_over_40_percent_stops_that_harvest(self):
        self.ready()
        RC.begin_round(self.root, self.run["run_id"])
        for i in range(5):
            TP.add(self.root, observed_date="2026-08-25", title=f"Agency rule {i}",
                   source_url=f"https://agency.example/rule-{i}", source_family="agency",
                   task_hypothesis="repeated filing", actor="xinci-run",
                   run_id=self.run["run_id"])
        policy = RP.evaluate(self.root, self.run["run_id"])
        self.assertTrue(policy["source_rotation_due"])
        self.assertFalse(policy["trigger_harvest"])

    def test_trigger_origin_must_bind_approved_query(self):
        self.ready(); RC.begin_round(self.root, self.run["run_id"])
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
