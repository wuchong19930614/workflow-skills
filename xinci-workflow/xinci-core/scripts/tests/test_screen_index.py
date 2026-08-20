# screen_index 测试:去重是广度扫描的地基——漏判会重复烧一整轮,误判会永久丢掉真机会。
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import screen_index as S
import dedup_decisions as DD


class SimilarTest(unittest.TestCase):
    """三种命中方式,以及必须【不】命中的边界。"""

    def test_exact_after_normalize(self):
        self.assertTrue(S.similar("PPWR Empty Space Ratio", "ppwr empty space ratio"))
        self.assertTrue(S.similar("claude watermark(检测)", "Claude Watermark（检测）"))

    def test_substring_covers_chinese(self):
        # 中文无空格分词,靠子串命中
        self.assertTrue(S.similar("纯品牌名发布", "扫描中遇到的纯品牌名发布方向"))

    def test_token_overlap_covers_wording_drift(self):
        # 真实案例:待查词与索引条目措辞不同但指同一方向
        self.assertTrue(S.similar("qwen 3.8 27b vram requirements",
                                  "Qwen 3.8 27B(vram/quantization 等衍生任务)"))

    def test_different_directions_do_not_match(self):
        # "app store creative assets" 与 "app store connect" 共享 2 词,
        # 但占较短方 2/3 < 0.75,不该判重——否则真机会会被永久误杀
        self.assertFalse(S.similar("app store creative assets", "app store connect"))
        self.assertFalse(S.similar("ppwr empty space ratio", "cloudflare injects analytics"))

    def test_uninformative_tokens_do_not_match(self):
        # 纯数字/过短词的交集不算数,否则 "api"、"3" 会把一切匹上
        self.assertFalse(S.similar("api", "significant change api"))
        self.assertFalse(S.similar("3", "gpt 3"))

    def test_adjacent_directions_stay_distinct(self):
        # 只差一个词的相邻方向必须分开——误判会把真机会永久筛掉
        self.assertFalse(S.similar("ios 18 screen time budget", "ios 19 parental report export"))
        self.assertFalse(S.similar("distinct direction number one",
                                   "distinct direction number seven"))

    def test_programming_language_symbols_are_meaningful(self):
        self.assertFalse(S.similar("C++ migration tool", "C# migration tool"))

    def test_empty_is_never_similar(self):
        self.assertFalse(S.similar("", "anything"))
        self.assertFalse(S.similar("anything", "   "))


class ScreenIndexTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def seed_index(self, *records):
        S.append(self.root, list(records))

    def seed_ledger(self, slug, term, state="rejected", aliases=None):
        d = self.root / "账本"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "候选账本.json"
        ledger = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {
            "schema_version": 1, "candidates": {}}
        ledger["candidates"][slug] = {
            "slug": slug, "term": term, "state": state,
            "aliases": list(aliases or []), "first_observed_at": "2026-08-18T00:00:00+00:00"}
        p.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    # ---- check ----

    def test_check_hits_index(self):
        self.seed_index({"date": "2026-08-17", "term": "Qwen 3.8 27B(vram 等衍生任务)",
                         "gate": "G5", "reason": "陷阱类别一"})
        r = S.check(self.root, ["qwen 3.8 27b vram requirements"])
        self.assertEqual(r["fresh"], [])
        self.assertEqual(r["seen"], [])
        self.assertEqual(r["review"][0]["gate"], "G5")

    def test_probable_resolution_closes_review_loop(self):
        known = "Qwen 3.8 27B vram quantization"
        term = "qwen 3.8 27b vram requirements"
        self.seed_index({"date": "2026-08-17", "term": known, "gate": "G5", "reason": "x"})
        self.assertEqual(len(S.check(self.root, [term])["review"]), 1)
        DD.resolve(self.root, term, known, "distinct", "任务一个算显存,一个列硬件要求",
                   actor="user", term_task="列硬件要求", matched_task="计算量化显存",
                   term_evidence_urls=["https://e.com/requirements"],
                   matched_evidence_urls=["https://e.com/quantization"])
        self.assertEqual(S.check(self.root, [term])["fresh"], [term])

    def test_same_resolution_turns_probable_into_seen(self):
        known = "Qwen 3.8 27B vram quantization"
        term = "qwen 3.8 27b vram requirements"
        self.seed_index({"date": "2026-08-17", "term": known, "gate": "G5", "reason": "x"})
        DD.resolve(self.root, term, known, "same", "同一任务", actor="user",
                   term_task="估算显存", matched_task="估算显存",
                   term_evidence_urls=["https://e.com/requirements"],
                   matched_evidence_urls=["https://e.com/quantization"])
        result = S.check(self.root, [term])
        self.assertEqual(len(result["seen"]), 1)
        self.assertEqual(result["review"], [])

    def test_wrong_dedup_ruling_has_append_only_revision(self):
        known = "Qwen 3.8 27B vram quantization"
        term = "qwen 3.8 27b vram requirements"
        first = DD.resolve(self.root, term, known, "same", "初判同一任务", actor="user",
                           term_task="估算显存", matched_task="估算显存",
                           term_evidence_urls=["https://e.com/new"],
                           matched_evidence_urls=["https://e.com/old"])
        with self.assertRaises(DD.DedupDecisionError):
            DD.resolve(self.root, term, known, "distinct", "发现任务不同", actor="user",
                       term_task="列硬件要求", matched_task="生成量化文件",
                       term_evidence_urls=["https://e.com/new"],
                       matched_evidence_urls=["https://e.com/old"])
        revised = DD.resolve(self.root, term, known, "distinct", "复核后发现任务不同",
                             actor="user", term_task="列硬件要求", matched_task="生成量化文件",
                             term_evidence_urls=["https://e.com/new"],
                             matched_evidence_urls=["https://e.com/old"],
                             supersedes=first["decision_id"])
        self.assertEqual(revised["supersedes"], first["decision_id"])
        self.assertEqual(DD.find(self.root, term, known)["decision"], "distinct")

    def test_forged_run_actor_requires_real_session(self):
        path = self.root / DD.FILE_NAME
        path.write_text(json.dumps({
            "decision_id": "dd-0123456789abcdef",
            "term": "qwen 3.8 27b vram requirements",
            "matched": "Qwen 3.8 27B vram quantization",
            "decision": "distinct", "reason": "伪造", "actor": "xinci-run",
            "run_id": "run-20260820T000000Z-deadbeef",
            "term_task": "列硬件要求", "matched_task": "计算量化显存",
            "term_evidence_urls": ["https://e.com/new"],
            "matched_evidence_urls": ["https://e.com/old"],
            "decided_at": "2026-08-20T00:00:00+00:00",
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(DD.DedupDecisionError, "run_id 无效"):
            DD.find(self.root, "qwen 3.8 27b vram requirements",
                    "Qwen 3.8 27B vram quantization")

    def test_forged_duplicate_decision_id_fails_on_load(self):
        base = {
            "decision_id": "dd-0123456789abcdef", "decision": "distinct",
            "reason": "伪造", "actor": "user", "term_task": "任务 A",
            "matched_task": "任务 B", "term_evidence_urls": ["https://e.com/a"],
            "matched_evidence_urls": ["https://e.com/b"],
            "decided_at": "2026-08-20T00:00:00+00:00",
        }
        rows = [dict(base, term="alpha tool setup", matched="alpha setup tool"),
                dict(base, term="beta tool setup", matched="beta setup tool")]
        (self.root / DD.FILE_NAME).write_text(
            "\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(DD.DedupDecisionError, "全局重复"):
            DD.load(self.root)

    def test_dedup_requires_independent_urls_and_distinct_tasks(self):
        with self.assertRaisesRegex(DD.DedupDecisionError, "不可复用"):
            DD.resolve(self.root, "alpha tool setup", "alpha setup tool", "distinct", "不同",
                       actor="user", term_task="任务 A", matched_task="任务 B",
                       term_evidence_urls=["https://e.com/shared"],
                       matched_evidence_urls=["https://e.com/shared"])
        with self.assertRaisesRegex(DD.DedupDecisionError, "两个不同"):
            DD.resolve(self.root, "alpha tool setup", "alpha setup tool", "distinct", "不同",
                       actor="user", term_task="同一任务", matched_task="同一任务",
                       term_evidence_urls=["https://e.com/a"],
                       matched_evidence_urls=["https://e.com/b"])

    def test_check_hits_ledger(self):
        # 走到 G1 之后被否决的候选只在账本、不在索引,只查索引会漏判
        self.seed_ledger("ppwr-empty-space-ratio", "ppwr empty space ratio")
        r = S.check(self.root, ["ppwr empty space ratio"])
        self.assertEqual(r["fresh"], [])
        self.assertEqual(r["seen"][0]["gate"], "账本")
        self.assertIn("rejected", r["seen"][0]["reason"])

    def test_check_hits_ledger_alias(self):
        self.seed_ledger("x-term", "official name", aliases=["community nickname here"])
        self.assertEqual(S.check(self.root, ["community nickname here"])["fresh"], [])

    def test_check_reports_fresh(self):
        self.seed_index({"date": "2026-08-17", "term": "cloudflare injects analytics",
                         "gate": "G7", "reason": "一次性任务"})
        r = S.check(self.root, ["某个全新方向", "another fresh direction here"])
        self.assertEqual(len(r["fresh"]), 2)
        self.assertEqual(r["seen"], [])
        self.assertEqual(r["review"], [])

    def test_check_on_empty_workspace(self):
        r = S.check(self.root, ["anything at all"])
        self.assertEqual(r["fresh"], ["anything at all"])

    # ---- append ----

    def test_append_preserves_probable_but_nonexact_direction(self):
        self.seed_index({"date": "2026-08-17", "term": "Qwen 3.8 27B(vram 等衍生任务)",
                         "gate": "G5", "reason": "陷阱类别一"})
        n = S.append(self.root, [{"date": "2026-08-18", "term": "qwen 3.8 27b vram requirements",
                                  "gate": "G5", "reason": "换个说法的同一方向"}])
        self.assertEqual(n, 1)
        self.assertEqual(len(S.load(self.root)), 2)

    def test_append_skips_normalized_exact_duplicate(self):
        self.seed_index({"date": "2026-08-17", "term": "PPWR Empty-Space Ratio",
                         "gate": "G3", "reason": "x"})
        n = S.append(self.root, [{"date": "2026-08-18", "term": "ppwr empty space ratio",
                                  "gate": "G3", "reason": "same"}])
        self.assertEqual(n, 0)

    def test_append_skips_duplicates_within_batch(self):
        # 回归:existing 由 set 改 list 后 .add() 未同步改成 .append(),
        # 同批出现新条目时会 AttributeError
        n = S.append(self.root, [
            {"date": "2026-08-18", "term": "fresh direction alpha", "gate": "G0", "reason": "x"},
            {"date": "2026-08-18", "term": "fresh direction alpha", "gate": "G0", "reason": "重复"},
            {"date": "2026-08-18", "term": "another distinct beta", "gate": "G4", "reason": "y"},
        ])
        self.assertEqual(n, 2)
        self.assertEqual(len(S.load(self.root)), 2)

    def test_append_ignores_blank_terms(self):
        self.assertEqual(S.append(self.root, [{"term": "  "}, {"term": ""}]), 0)

    def test_append_is_additive_across_calls(self):
        S.append(self.root, [{"date": "2026-08-18", "term": "first direction one", "gate": "G0"}])
        S.append(self.root, [{"date": "2026-08-18", "term": "second direction two", "gate": "G4"}])
        self.assertEqual(len(S.load(self.root)), 2)

    # ---- stats / 归并 ----

    def test_stats_flags_merge_threshold(self):
        pat = "厂商已占位的 B2B 强制任务"
        terms = ["ppwr empty space ratio", "app store creative assets", "significant change api"]
        for term in terms[:S.MERGE_THRESHOLD]:
            S.append(self.root, [{"date": "2026-08-18", "term": term,
                                  "gate": "G3", "reason": "同型", "pattern": pat}])
        s = S.stats(self.root)
        self.assertEqual(s["total"], S.MERGE_THRESHOLD)
        self.assertIn(pat, s["merge_due"])

    def test_stats_below_threshold_is_not_flagged(self):
        S.append(self.root, [{"date": "2026-08-18", "term": "only one direction here",
                              "gate": "G3", "pattern": "某模式"}])
        self.assertEqual(S.stats(self.root)["merge_due"], [])

    # ---- 健壮性 ----

    def test_load_skips_corrupt_lines(self):
        p = self.root / S.INDEX_NAME
        p.write_text('{"term": "good direction one", "gate": "G0"}\n坏行\n\n'
                     '{"term": "good direction two", "gate": "G4"}\n', encoding="utf-8")
        self.assertEqual(len(S.load(self.root)), 2)

    def test_check_survives_corrupt_ledger(self):
        d = self.root / "账本"
        d.mkdir(parents=True)
        (d / "候选账本.json").write_text("{坏", encoding="utf-8")
        self.assertEqual(S.check(self.root, ["some direction"])["fresh"], ["some direction"])


if __name__ == "__main__":
    unittest.main()
