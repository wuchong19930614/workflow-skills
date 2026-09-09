import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_index as E


class EvidenceIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "账本").mkdir()
        (self.root / "证据/report").mkdir(parents=True)
        self.ledger = self.root / "账本/候选账本.json"

    def obs(self, name, stage, at, version=1, **extra):
        ref = f"证据/report/{name}.json"
        (self.root / ref).write_text(json.dumps(dict(
            slug="report", stage=stage, observed_at=at, schema_version=version,
            points=["旧事实，不因新观察自动失效"], **extra)))
        return ref

    def register(self, refs):
        self.ledger.write_text(json.dumps({"candidates": {"report": {
            "state": "formation_confirmed", "lane": "mature", "gates": {"G1": "pass"},
            "evidence_refs": refs, "history": [{"reason": "补录早期证据"}],
            "qualify_pending": {"pending_evidence": ["付费证据"], "pending_until": "2026-10-01"}
        }}}))

    def test_navigation_preserves_old_facts_and_does_not_write(self):
        scan = self.obs("old-scan", "scan", "2026-08-01T00:00:00+00:00")
        latest = self.obs("z-track", "track", "2026-09-08T00:00:00+00:00", 2)
        late_filed = self.obs("a-track", "track", "2026-09-01T00:00:00+00:00", 2)
        self.obs("unregistered-qualify", "qualify", "2026-09-09T00:00:00+00:00", 3)
        self.register([scan, latest, late_filed])
        before = {str(p): p.read_bytes() for p in self.root.rglob("*.json")}
        result = E.build(self.root, "report")
        self.assertEqual(set(result["start_refs"]), {scan, latest, late_filed})
        self.assertEqual(len(result["observations"]), 3)
        self.assertEqual(result["gates"], {"G1": "pass"})
        self.assertEqual(result["qualify_pending"]["pending_evidence"], ["付费证据"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*.json")})

    def test_equal_instants_preserve_both_observations_and_deduplicate_refs(self):
        a = self.obs("a-track", "track", "2026-09-08T08:00:00+08:00")
        b = self.obs("b-track", "track", "2026-09-08T00:00:00+00:00", 3)
        old = self.obs("old-scan", "scan", "2026-09-07T00:00:00+00:00")
        self.register([a, b, a, old])
        result = E.build(self.root, "report")
        self.assertEqual(set(result["start_refs"]), {a, b, old})
        self.assertEqual(len(result["observations"]), 3)

    def test_missing_invalid_and_foreign_observations_are_reported(self):
        mismatch = self.obs("foreign-scan", "scan", "2026-09-01T00:00:00+00:00")
        path = self.root / mismatch
        obs = json.loads(path.read_text()); obs["slug"] = "other"
        path.write_text(json.dumps(obs))
        naive = self.obs("naive-track", "track", "2026-09-01T00:00:00")
        self.register([mismatch, naive, "证据/report/missing.json", "../../secret.json"])
        result = E.build(self.root, "report")
        self.assertEqual(len(result["errors"]), 4)
        self.assertEqual(result["start_refs"], [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(E.main(["report", "--data-root", str(self.root)]), 2)

    def test_symlink_cannot_read_outside_data_root(self):
        with tempfile.TemporaryDirectory() as outside:
            secret = Path(outside) / "source.json"
            secret.write_text('{"private": "do not read"}')
            ref = "证据/report/link.json"
            (self.root / ref).symlink_to(secret)
            self.register([ref])
            result = E.build(self.root, "report")
            self.assertEqual(result["observations"], [])
            self.assertIn("越界", result["errors"][0]["reason"])

    def test_unknown_candidate_fails_without_creating_files(self):
        self.register([])
        with self.assertRaisesRegex(ValueError, "没有候选"):
            E.build(self.root, "unknown")

    def test_new_unknowns_require_g3_review_without_erasing_history(self):
        scan = self.obs("old-scan", "scan", "2026-08-01T00:00:00+00:00", gates={"G3": "pass"})
        track = self.obs("new-track", "track", "2026-09-08T00:00:00+00:00", 3,
                         g6_tentative_lines={"subscription": "tentative_inconclusive"})
        self.register([scan, track])
        result = E.build(self.root, "report")
        self.assertEqual(result["review_required_gates"], {"G3": track})
        self.assertEqual(result["unknown_income_lines"], {"subscription": track})
        qualified = self.obs("new-qualify", "qualify", "2026-09-09T00:00:00+00:00", 3,
                             gates={"G3": "pass"}, g6_lines={"subscription": "pass"})
        self.register([scan, track, qualified])
        self.assertEqual(E.build(self.root, "report")["review_required_gates"], {})

    def test_legacy_observations_in_candidate_subdirectories_remain_readable(self):
        flat = self.obs("old-scan", "scan", "2026-08-01T00:00:00+00:00")
        ref = "证据/report/archive/2026-08-01-scan.json"
        path = self.root / ref
        path.parent.mkdir()
        obs = json.loads((self.root / flat).read_text())
        obs.pop("schema_version")
        path.write_text(json.dumps(obs))
        self.register([ref])
        result = E.build(self.root, "report")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["start_refs"], [ref])
        self.assertEqual(result["observations"][0]["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
