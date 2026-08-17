# validate_ledger 不变式测试:registrar 之外的改动(手工编辑损坏)必须被校验捕获。
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import registrar as R
import validate_ledger as V
from test_registrar import mk_evidence, mk_decision, GATES_SCREEN, GATES_678


class ValidateLedgerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # ---- 辅助 ----

    def build_chain(self, slug="demo-term", until="tracking", window="weeks"):
        ev = mk_evidence(self.root, slug, "2026-08-17-scan.json")
        R.register(self.root, slug=slug, term="demo term", source_url="https://e.com",
                   task="t", evidence=[ev])
        if until == "captured":
            return slug
        R.transition(self.root, slug, to="screened", by="xinci-scan",
                     gates=dict(GATES_SCREEN), window_estimate=window,
                     evidence=[mk_evidence(self.root, slug, "2026-08-17b-scan.json")])
        if until == "screened":
            return slug
        if until == "fast_grab_ready":
            ref = mk_decision(self.root, slug)
            R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                         decision_ref=ref, expiry="2026-08-25", play="fast_grab")
            return slug
        R.transition(self.root, slug, to="tracking", by="xinci-scan",
                     expiry="2026-09-30", invalidation=["官方工具上线"],
                     evidence=[mk_evidence(self.root, slug, "2026-08-17c-scan.json")])
        if until == "tracking":
            return slug
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-27-track.json")])
        R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                     gates={"G1": "pass"},
                     evidence=[mk_evidence(self.root, slug, "2026-09-03-track.json")])
        if until == "formation_confirmed":
            return slug
        R.transition(self.root, slug, to="qualified", by="xinci-qualify", score=85,
                     gates=dict(GATES_678),
                     evidence=[mk_evidence(self.root, slug, "2026-09-10-qualify.json")])
        if until == "qualified":
            return slug
        ref = mk_decision(self.root, slug)
        R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                     decision_ref=ref, play="single_domain")
        return slug

    def corrupt(self, slug, **fields):
        p = self.root / "账本" / "候选账本.json"
        ledger = json.loads(p.read_text(encoding="utf-8"))
        ledger["candidates"][slug].update(fields)
        p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    def errors(self):
        errs, _ = V.validate(self.root)
        return errs

    # ---- 用例 ----

    def test_clean_full_chain_passes(self):
        self.build_chain(until="build_ready")
        self.build_chain(slug="fast-one", until="fast_grab_ready", window="days")
        self.assertEqual(self.errors(), [])

    def test_detects_missing_window_on_screened(self):
        slug = self.build_chain(until="screened")
        self.corrupt(slug, window_estimate=None)
        self.assertTrue(any("window_estimate" in e for e in self.errors()))

    def test_detects_missing_expiry_on_tracking(self):
        slug = self.build_chain(until="tracking")
        self.corrupt(slug, expiry=None)
        self.assertTrue(any("expiry" in e for e in self.errors()))

    def test_detects_fast_grab_invariants(self):
        slug = self.build_chain(until="fast_grab_ready", window="days")
        self.corrupt(slug, expiry=None, play="single_domain", score=90)
        errs = self.errors()
        self.assertTrue(any("expiry" in e for e in errs))
        self.assertTrue(any("play" in e for e in errs))
        self.assertTrue(any("score" in e for e in errs))

    def test_detects_low_score_on_qualified(self):
        slug = self.build_chain(until="qualified")
        self.corrupt(slug, score=79)
        self.assertTrue(any("score" in e for e in self.errors()))

    def test_detects_bad_play_on_build_ready(self):
        slug = self.build_chain(until="build_ready")
        self.corrupt(slug, play="fast_grab")
        self.assertTrue(any("play" in e for e in self.errors()))

    def test_detects_broken_history_chain(self):
        slug = self.build_chain(until="tracking")
        p = self.root / "账本" / "候选账本.json"
        ledger = json.loads(p.read_text(encoding="utf-8"))
        ledger["candidates"][slug]["history"][1]["from"] = "tracking"  # 应为 captured
        p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertTrue(any("history" in e and "断链" in e for e in self.errors()))

    def test_detects_evidence_path_escape(self):
        slug = self.build_chain(until="captured")
        self.corrupt(slug, evidence_refs=["../外部文件.json"])
        self.assertTrue(any("相对路径" in e for e in self.errors()))


if __name__ == "__main__":
    unittest.main()
