import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lexicon
import seed_import as I
from _common import BenchError, MANUAL_SEEDS_REL, SEEDS_REL, LEXICON_REL, VERDICTS_REL, load_json, sha256_file
from helpers import TmpRoot, write_json

LEDGER = {"schema_version": 1, "candidates": {
    "tide-chart": {"slug": "tide-chart", "primary_keyword": "tide chart", "state": "parked",
                   "seed": {"type": "root", "value": "Chart", "queried_at": "2026-09-10T03:00:00+00:00"},
                   "cluster": {"keywords": [{"term": "Tide Chart", "volume": 1000, "kd": 11},
                                            {"term": "tide times", "volume": 500}]},
                   "history": [{"to": "found", "from": None, "reason": "准入"},
                               {"to": "parked", "from": "found", "reason": "季节性"}]},
    "bus-schedule": {"slug": "bus-schedule", "primary_keyword": "bus schedule", "state": "rejected",
                     "seed": {"type": "small_site", "value": "transitapp.com(AS 63) 与 Example.org 反推",
                              "queried_at": "2026-09-11T03:00:00+00:00"},
                     "cluster": {"keywords": [{"term": "tide chart", "volume": 1200, "kd": 12}]},
                     "history": [{"to": "found", "from": None, "reason": "准入"},
                                 {"to": "rejected", "from": "found", "gate": "G3", "reason": "K=3"}]}}}


def legacy_root(tmp):
    root = Path(tmp)
    write_json(root / "账本" / "候选账本.json", LEDGER)
    rows = [
        {"url": "https://www.small-tool.com/a", "dr": 11, "type": "tool"},      # 保留
        {"domain": "unknown-as.com", "dr": 0, "type": "tool"},                    # 0 视为未测,保留
        {"domain": "big.com", "dr": 45, "type": "tool"},                          # AS 过高
        {"domain": "denvergov.org", "dr": 14, "type": "other"},                   # 政府
        {"domain": "city.gov", "dr": 10, "type": "tool"},                         # .gov
        {"domain": "pinterest.com", "dr": 0, "type": "other"},                    # 平台
        {"domain": "no-as.com", "dr": None, "type": "tool"},                      # 没有 AS 记录
        {"domain": "mixed.com", "dr": 12, "type": "tool"},
    ]
    write_json(root / "证据" / "tide-chart" / "a-verify.json", {"serp_top10": rows})
    write_json(root / "证据" / "bus-schedule" / "b-verify.json",
               {"serp_top10": [{"domain": "mixed.com", "dr": 12, "type": "official"}]})  # 出现过 official → 排除
    return root


class SeedImportTest(unittest.TestCase):
    def test_filters_and_counts(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            legacy = legacy_root(tmp)
            out = I.import_legacy(root, legacy)
            pool = load_json(root / SEEDS_REL)["seeds"]
            bench = sorted(d for d, s in pool.items() if s["role"] == "benchmark")
            self.assertEqual(bench, ["small-tool.com", "unknown-as.com"])
            self.assertIsNone(pool["unknown-as.com"]["as_recorded"])
            self.assertEqual(sorted(d for d, s in pool.items() if s["role"] == "sibling"),
                             ["example.org", "transitapp.com"])
            self.assertEqual(out["lexicon_words"], 2)
            self.assertEqual(out["verdicts"], 2)

    def test_lexicon_keeps_latest_and_verdict_gate(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            I.import_legacy(root, legacy_root(tmp))
            words = load_json(root / LEXICON_REL)["words"]
            self.assertEqual(words["tide chart"]["volume"], 1200)
            self.assertEqual(words["tide chart"]["slug"], "bus-schedule")
            ver = load_json(root / VERDICTS_REL)["candidates"]
            self.assertEqual(ver["bus-schedule"]["gate"], "G3")
            self.assertIsNone(ver["tide-chart"]["gate"])

    def test_idempotent_and_legacy_untouched(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            legacy = legacy_root(tmp)
            before = {p: sha256_file(p) for p in legacy.rglob("*.json")}
            I.import_legacy(root, legacy)
            again = I.import_legacy(root, legacy)
            self.assertEqual(again["seeds_added"], {"benchmark": 0, "sibling": 0, "manual": 0})
            self.assertEqual(before, {p: sha256_file(p) for p in legacy.rglob("*.json")})

    def test_manual_seeds_imported_first(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            write_json(root / MANUAL_SEEDS_REL, {"schema_version": 1, "seeds": [
                {"domain": "https://www.wisconsinpropertymap.com/", "note": "AS 11,9 个月到 5.4K"},
                {"domain": "geocodify.com", "role": "sibling", "note": "AS 38,只查同类站"}]})
            I.import_legacy(root, legacy_root(tmp))
            pool = load_json(root / SEEDS_REL)["seeds"]
            self.assertEqual(next(iter(pool)), "wisconsinpropertymap.com")
            self.assertEqual(pool["geocodify.com"]["role"], "sibling")
            write_json(root / MANUAL_SEEDS_REL, {"schema_version": 1, "seeds": [{"domain": "x.com", "role": "boss"}]})
            with self.assertRaisesRegex(BenchError, "role"):
                I.import_legacy(root, legacy_root(tmp))

    def test_corrupt_legacy_evidence_skipped(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            legacy = legacy_root(tmp)
            (legacy / "证据" / "tide-chart" / "broken.json").write_text("{坏的", encoding="utf-8")
            self.assertEqual(I.import_legacy(root, legacy)["benchmark_candidates"], 2)

    def test_missing_legacy_ledger(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(BenchError, "旧账本不存在"):
                I.import_legacy(root, tmp)

    def test_lexicon_match(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            I.import_legacy(root, legacy_root(tmp))
            out = lexicon.match(root, "tide")
            self.assertEqual([k["term"] for k in out["keywords"]], ["tide chart", "tide times"])
            self.assertEqual(out["volume_sum"], 1700)
            self.assertIn("tide-chart", out["verdicts"])


if __name__ == "__main__":
    unittest.main()
