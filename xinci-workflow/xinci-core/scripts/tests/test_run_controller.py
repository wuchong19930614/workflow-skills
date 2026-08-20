import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_controller as RC


class RunControllerTest(unittest.TestCase):
    ZEROS = {"extracted": 0, "rejected_zero_cost": 0,
             "rejected_g1": 0, "deep_audited": 0, "queued": 0}
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

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
        (d / name).write_text(json.dumps({
            "date": "2026-08-20", "skill": "xinci-run", "run_id": run_id,
            "rounds": list(rounds or []),
            "candidates_touched": list(candidates_touched or []),
        }), encoding="utf-8")

    def test_start_round_resume_finish(self):
        run = RC.start(self.root, max_rounds=2)
        self.assertEqual(run["status"], "active")
        RC.begin_round(self.root, run["run_id"])
        resumed = RC.load_session(self.root, run["run_id"])
        self.assertEqual(resumed["current_round"], 1)
        RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        done = RC.finish(self.root, run["run_id"], "budget_reached", "测试预算命中")
        self.assertEqual(done["status"], "budget_reached")

    def test_only_one_active_session(self):
        run = RC.start(self.root)
        self.assertEqual(RC.list_sessions(self.root)["active"], [run["run_id"]])
        with self.assertRaises(RC.RunControllerError):
            RC.start(self.root)

    def test_round_budget_is_enforced(self):
        run = RC.start(self.root, max_rounds=1)
        RC.begin_round(self.root, run["run_id"])
        RC.record_round(self.root, run["run_id"], funnel=dict(self.ZEROS))
        with self.assertRaises(RC.RunControllerError):
            RC.begin_round(self.root, run["run_id"])

    def test_confirmation_is_single_use(self):
        run = RC.start(self.root)
        RC.begin_round(self.root, run["run_id"])
        self.seed_candidate(gates={"G3": "veto_window_bet"})
        RC.confirm_window_bet(self.root, run["run_id"], "demo")
        RC.consume_window_bet_confirmation(self.root, run["run_id"], "demo")
        with self.assertRaises(RC.RunControllerError):
            RC.consume_window_bet_confirmation(self.root, run["run_id"], "demo")
        with self.assertRaisesRegex(RC.RunControllerError, "不可覆盖或重新激活"):
            RC.confirm_window_bet(self.root, run["run_id"], "demo")

    def test_confirmation_cannot_be_precreated(self):
        run = RC.start(self.root)
        with self.assertRaisesRegex(RC.RunControllerError, "已写入账本"):
            RC.confirm_window_bet(self.root, run["run_id"], "ghost")
        self.seed_candidate(gates={"G3": "pass"})
        with self.assertRaisesRegex(RC.RunControllerError, "G3=veto_window_bet"):
            RC.confirm_window_bet(self.root, run["run_id"], "demo")

    def test_go_finish_requires_candidate_produced_by_this_run(self):
        run = RC.start(self.root)
        self.seed_manifest(run["run_id"])
        with self.assertRaisesRegex(RC.RunControllerError, "GO 候选"):
            RC.finish(self.root, run["run_id"], "go", "声称成功")
        self.seed_candidate(state="build_ready", history=[{
            "at": "2026-08-20T00:00:00+00:00", "from": "qualified",
            "to": "build_ready", "by": "xinci-run", "run_id": "run-other",
        }])
        with self.assertRaisesRegex(RC.RunControllerError, "本次 run_id"):
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
        with self.assertRaisesRegex(RC.RunControllerError, "从 1 开始连续"):
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
        with self.assertRaisesRegex(RC.RunControllerError, "完整校验"):
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

    def test_end_round_is_fail_closed(self):
        run = RC.start(self.root)
        RC.begin_round(self.root, run["run_id"])
        with self.assertRaisesRegex(RC.RunControllerError, "record-round"):
            RC.end_round(self.root, run["run_id"])

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
        with self.assertRaisesRegex(RC.RunControllerError, "缺 gates 或 expiry"):
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
        with self.assertRaisesRegex(RC.RunControllerError, "防止授权绕过"):
            RC.active_sessions(self.root)


if __name__ == "__main__":
    unittest.main()
