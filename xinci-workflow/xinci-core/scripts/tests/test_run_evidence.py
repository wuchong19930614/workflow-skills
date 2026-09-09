import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_controller as RC
import run_manifest as RM
import registrar as R
from formation_evidence import task_signal


class EvidenceRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = RC.start(self.root, max_rounds=2)
        self.id = self.run["run_id"]
        self.pre = {"controllable": True, "desktop": True, "region": "us", "logged_out": True}
        self.package = {"targets": ["https://example.com/release"], "completion": "读取来源并登记筛选结论"}
        self.capture = self.root / "capture.txt"
        self.capture.write_text("Skip to main content Search Results Sign in 独立浏览器桌面快照")
        self.payload = {"run_id": self.id, "executor_id": "worker", "observed_at": self.now(),
                        "capture_ref": "capture.txt", "observed": self.pre,
                        "query_url": "https://www.google.com/search?q=test&gl=us&hl=en&pws=0",
                        "privacy_context": "isolated_logged_out", "login_indicator": "Sign in",
                        "privacy_evidence": "独立会话，无共享账号状态", "observation": "桌面搜索及登录按钮可见"}
        self.save_payload()
        (self.root / "work.txt").write_text("独立来源的任务审计结果：只有版本修复，无新增任务")
        self.zeros = dict(extracted=0, rejected_zero_cost=0, rejected_g1=0, deep_audited=0, queued=0)

    def now(self):
        return datetime.now(timezone.utc).isoformat()

    def save_payload(self):
        (self.root / "preflight.json").write_text(json.dumps(self.payload))

    def begin(self):
        return RC.begin_round(self.root, self.id, "worker", "discovery", self.pre,
                              "preflight.json", self.package)

    def results(self, outcome="completed"):
        return [{"target": self.package["targets"][0], "outcome": outcome, "reason": "来源审计完成，零候选",
                 "evidence_refs": ["work.txt"], "observed_at": self.now()}]

    def test_requires_evidence_and_does_not_open_round_on_failure(self):
        with self.assertRaises(RC.RunControllerError):
            RC.begin_round(self.root, self.id, "worker", preflight=self.pre)
        self.assertIsNone(RC.load_session(self.root, self.id)["current_round"])

    def test_rejects_other_executor_stale_and_personalized_evidence(self):
        original = dict(self.payload)
        for changes in ({"executor_id": "other"},
                        {"observed_at": (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()},
                        {"query_url": "https://www.google.com/search?q=test&gl=us"},
                        {"privacy_context": "unknown"}):
            self.payload = {**original, **changes}
            self.save_payload()
            with self.assertRaises(RC.RunControllerError):
                self.begin()

    def test_empty_round_cannot_increment_degraded_or_budget(self):
        self.begin()
        with self.assertRaises(RC.RunControllerError):
            RC.record_round(self.root, self.id, funnel=self.zeros, results=[])
        with self.assertRaises(RC.RunControllerError):
            RC.record_round(self.root, self.id, funnel=self.zeros, results=self.results("blocked"))
        session = RC.abort_round(self.root, self.id, "通道未修复，本次仅尝试", "work.txt")
        self.assertEqual(session["rounds_completed"], 0)
        self.assertEqual(session["degraded_rounds"], 0)
        self.assertEqual(len(session["aborted_attempts"]), 1)
        with self.assertRaises(RC.RunControllerError):
            self.begin()

    def test_real_zero_yield_work_counts_and_pins_evidence(self):
        self.begin()
        RC.record_round(self.root, self.id, funnel=self.zeros, results=self.results())
        session = RC.load_session(self.root, self.id)
        self.assertEqual(session["rounds_completed"], 1)
        path, manifest = RM.find_run_manifest(self.root, self.id)
        self.assertEqual(manifest["rounds"][0]["work_package"], self.package)
        self.capture.write_text("changed")
        errors = RM.validate_manifest(manifest, path=path, session=session)
        self.assertTrue(errors)

    def test_g1_rejects_changed_capture(self):
        self.begin()
        self.capture.write_text("changed")
        with self.assertRaises(R.RegistrarError):
            R._check_run_g1_preflight(self.root, "xinci-run", self.id, {"G1": "pass"})

    def test_legacy_v3_session_remains_readable(self):
        RC.finish(self.root, self.id, "cancelled", "测试结束")
        old = RC.start(self.root, max_rounds=1, schema_version=3)
        RC.begin_round(self.root, old["run_id"])
        RC.record_round(self.root, old["run_id"], funnel=self.zeros)
        self.assertEqual(RC.load_session(self.root, old["run_id"])["rounds_completed"], 1)


class FormationEvidenceTest(unittest.TestCase):
    def observation(self, scope):
        return {"stage": "track", "gates": {"G1": "pass"}, "naming_status": "stabilized",
                "formation_signals": ["autocomplete"], "source_urls": ["https://example.com"],
                "formation_evidence": [{"signal": "autocomplete", "scope": scope,
                                        "query": "task query", "source_url": "https://example.com",
                                        "task_match": "制造商逐机型判定"}]}

    def test_topic_only_does_not_establish_formation(self):
        self.assertFalse(task_signal(self.observation("topic")))
        self.assertTrue(task_signal(self.observation("task")))

    def test_cannot_mix_g1_and_signal_across_observations(self):
        obs = self.observation("task")
        obs["gates"] = {}
        self.assertFalse(task_signal(obs))

    def test_unopened_signal_source_rejected(self):
        obs = self.observation("task")
        obs["source_urls"] = []
        with self.assertRaises(ValueError):
            task_signal(obs)
