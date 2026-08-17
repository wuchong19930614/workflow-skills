# registrar 契约测试:断言与实现计划附录 A(合法转移表)、附录 B(证据要求)一一对应。
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import registrar as R


def mk_evidence(root: Path, slug: str, name: str) -> str:
    d = root / "证据" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("{}", encoding="utf-8")
    return f"证据/{slug}/{name}"


def mk_decision(root: Path, slug: str, with_html: bool = True) -> str:
    d = root / "决策书"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text("# 决策书", encoding="utf-8")
    if with_html:
        (d / f"{slug}.html").write_text("<html></html>", encoding="utf-8")
    return f"决策书/{slug}.md"


GATES_15 = {"G1": "pass", "G2": "pass", "G3": "pass", "G4": "pass", "G5": "pass"}
GATES_678 = {"G6": "pass", "G7": "pass", "G8": "pass"}


class RegistrarTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # ---- 流程推进辅助 ----

    def register(self, slug="demo-term"):
        ev = mk_evidence(self.root, slug, "2026-08-17-scan.json")
        R.register(self.root, slug=slug, term="demo term", source_url="https://example.com/t",
                   task="complete demo task", evidence=[ev])
        return slug

    def to_screened(self, slug):
        ev = mk_evidence(self.root, slug, "2026-08-17b-scan.json")
        R.transition(self.root, slug, to="screened", by="xinci-scan",
                     gates=dict(GATES_15), window_estimate="weeks", evidence=[ev])

    def to_tracking(self, slug):
        ev = mk_evidence(self.root, slug, "2026-08-17c-scan.json")
        R.transition(self.root, slug, to="tracking", by="xinci-scan",
                     expiry="2026-09-30", invalidation=["官方工具上线"], evidence=[ev])

    def to_formation(self, slug):
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-27-track.json")])
        ev = mk_evidence(self.root, slug, "2026-09-03-track.json")
        R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                     gates={"G1": "pass"}, evidence=[ev])

    def to_qualified(self, slug):
        ev = mk_evidence(self.root, slug, "2026-09-10-qualify.json")
        R.transition(self.root, slug, to="qualified", by="xinci-qualify",
                     score=80, gates=dict(GATES_678), evidence=[ev])

    def load(self, slug):
        ledger = json.loads((self.root / "账本" / "候选账本.json").read_text(encoding="utf-8"))
        return ledger["candidates"][slug]

    # ---- 用例 ----

    def test_register_creates_captured(self):
        slug = self.register()
        rec = self.load(slug)
        self.assertEqual(rec["state"], "captured")
        self.assertEqual(len(rec["history"]), 1)
        self.assertEqual(rec["history"][0]["to"], "captured")
        self.assertEqual(len(rec["evidence_refs"]), 1)

    def test_register_requires_evidence_file(self):
        with self.assertRaises(R.RegistrarError):
            R.register(self.root, slug="x", term="x", source_url="https://e.com",
                       task="t", evidence=["证据/x/不存在.json"])

    def test_illegal_jump_rejected(self):
        slug = self.register()
        mk_decision(self.root, slug)
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                         decision_ref=f"决策书/{slug}.md", play="single_domain")

    def test_screened_requires_all_five_gates(self):
        slug = self.register()
        gates = dict(GATES_15)
        del gates["G5"]
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="screened", by="xinci-scan",
                         gates=gates, window_estimate="weeks", evidence=[ev])
        self.to_screened(slug)
        self.assertEqual(self.load(slug)["state"], "screened")

    def test_tracking_requires_expiry_and_invalidation(self):
        slug = self.register()
        self.to_screened(slug)
        ev = mk_evidence(self.root, slug, "2026-08-19-scan.json")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="tracking", by="xinci-scan", evidence=[ev])
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="tracking", by="xinci-scan",
                         expiry="2026-09-30", invalidation=[], evidence=[ev])
        self.to_tracking(slug)
        self.assertEqual(self.load(slug)["state"], "tracking")

    def test_formation_needs_two_track_observations(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        ev = mk_evidence(self.root, slug, "2026-08-20-track.json")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                         gates={"G1": "pass"}, evidence=[ev])

    def test_qualified_requires_score_80(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        ev = mk_evidence(self.root, slug, "2026-09-10-qualify.json")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="qualified", by="xinci-qualify",
                         score=79, gates=dict(GATES_678), evidence=[ev])
        self.to_qualified(slug)
        self.assertEqual(self.load(slug)["state"], "qualified")

    def test_build_ready_requires_dual_format(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        self.to_qualified(slug)
        ref = mk_decision(self.root, slug, with_html=False)
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                         decision_ref=ref, play="single_domain")
        mk_decision(self.root, slug, with_html=True)
        R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                     decision_ref=ref, play="single_domain")
        self.assertEqual(self.load(slug)["state"], "build_ready")

    def test_no_site_forbids_decision_ref(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        self.to_qualified(slug)
        ref = mk_decision(self.root, slug)
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="no_site", by="xinci-decide",
                         reason="簇撑不起独立站", decision_ref=ref)
        R.transition(self.root, slug, to="no_site", by="xinci-decide", reason="簇撑不起独立站")
        self.assertEqual(self.load(slug)["state"], "no_site")

    def test_fast_grab_only_from_screened(self):
        slug = self.register()
        ref = mk_decision(self.root, slug)
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                         decision_ref=ref, expiry="2026-08-25", play="fast_grab")
        self.to_screened(slug)
        R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                     decision_ref=ref, expiry="2026-08-25", play="fast_grab")
        self.assertEqual(self.load(slug)["state"], "fast_grab_ready")

    def test_terminal_states_have_no_exit(self):
        slug = self.register()
        R.transition(self.root, slug, to="rejected", by="xinci-scan", reason="G1 否决:原生组件直接完成任务")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="tracking", by="xinci-scan",
                         expiry="2026-09-30", invalidation=["x"])

    def test_superseded_requires_existing_slug(self):
        slug = self.register()
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="superseded", by="xinci-scan", superseded_by="ghost")
        other = "better-wording"
        ev = mk_evidence(self.root, other, "2026-08-17-scan.json")
        R.register(self.root, slug=other, term="better wording", source_url="https://e.com",
                   task="same task", evidence=[ev])
        R.transition(self.root, slug, to="superseded", by="xinci-scan", superseded_by=other)
        rec = self.load(slug)
        self.assertEqual(rec["state"], "superseded")
        self.assertEqual(rec["superseded_by"], other)

    def test_checked_updates_last_checked_at_without_state_change(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        before = self.load(slug)
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])
        after = self.load(slug)
        self.assertEqual(after["state"], "tracking")
        self.assertGreaterEqual(after["last_checked_at"], before["last_checked_at"])
        self.assertIn(f"证据/{slug}/2026-08-20-track.json", after["evidence_refs"])

    def test_history_append_only(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        rec = self.load(slug)
        self.assertEqual([h["to"] for h in rec["history"]], ["captured", "screened", "tracking"])
        self.assertEqual(rec["history"][1]["from"], "captured")
        for h in rec["history"]:
            self.assertIn("at", h)
            self.assertIn("by", h)


if __name__ == "__main__":
    unittest.main()
