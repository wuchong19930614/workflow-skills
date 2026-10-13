import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import settle as S
import validate_ledger as V
import write_observation as W
from _common import BenchError, load_ledger, sha256_file
from helpers import TmpRoot, cluster_record, serp_obs, setup_direction

ON = "2026-10-20"


class SettleTest(unittest.TestCase):
    def test_go_builds_doc_with_brief_and_validates(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            rec = S.settle(root, slug, "go", None, "标杆 9 个月到 2 万", "Journey 实际 RPM", on=ON)
            self.assertEqual(rec["state"], "go")
            self.assertEqual(len(rec["bindings"]["files"]), len(refs))
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn("## 第二部分 建站简报", md)
            self.assertIn("第 6 个月 Search Console 点击低于", md)
            self.assertEqual(V.check_all(root), [])

    def test_revenue_reject_has_no_brief(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root, us_organic_m12=5400)
            with self.assertRaisesRegex(BenchError, "模型结论"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            rec = S.settle(root, slug, "rejected", "revenue", "基准只有 $10.80", "标杆是否还会涨", on=ON)
            self.assertEqual(rec["state"], "rejected")
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertNotIn("建站简报", md)
            self.assertIn("收入不足", md)

    def test_go_refuses_stale_clusters(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root, stale=True)
            with self.assertRaisesRegex(BenchError, "90 天"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            self.assertEqual(load_ledger(root)["directions"][slug]["state"], "found")

    def test_answered_requires_all_clusters_and_serp(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "所有簇"):
                S.settle(root, slug, "rejected", "answered", "r", "u", on=ON)
            ref = W.write(root, serp_obs(slug, answered=True))
            L.update(root, slug, {"clusters": [cluster_record(answered=True)]}, [ref])
            rec = S.settle(root, slug, "rejected", "answered", "AI 概览直接给县名", "定位后是否仍答", on=ON)
            self.assertEqual(rec["state"], "rejected")

    def test_scope_needs_hit(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "命中项"):
                S.settle(root, slug, "rejected", "scope", "r", "u", on=ON)
            rec = S.settle(root, slug, "rejected", "scope", "克隆受版权游戏", "无", scope_hit="infringement", on=ON)
            self.assertEqual(rec["decision"]["scope_hit"], "infringement")

    def test_recovery_rebuilds_docs_without_new_history(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            (root / "文档" / f"{slug}.html").unlink()
            n = len(load_ledger(root)["directions"][slug]["history"])
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            self.assertEqual(len(load_ledger(root)["directions"][slug]["history"]), n)
            self.assertTrue((root / "文档" / f"{slug}.html").is_file())
            with self.assertRaisesRegex(BenchError, "不一致"):
                S.settle(root, slug, "go", "revenue", "r", "u", on=ON)

    def test_parked_then_go_archives_old_doc(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            S.settle(root, slug, "parked", None, "曲线读不出", "Semrush 域名模块恢复后的读数", on=ON)
            S.settle(root, slug, "go", None, "补到曲线后过线", "Journey RPM", on=ON)
            self.assertEqual(len(list((root / "文档" / "历史").glob(f"{slug}-*.md"))), 1)
            self.assertEqual(V.check_all(root), [])


    def test_deleted_observation_gives_clear_refusal(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            (root / refs[3]).unlink()
            with self.assertRaisesRegex(BenchError, "观察不存在"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)


class ValidateTest(unittest.TestCase):
    def test_detects_tampering(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            md = root / "文档" / f"{slug}.md"
            md.write_text(md.read_text(encoding="utf-8") + "手改\n", encoding="utf-8")
            self.assertTrue(any("md/html" in e for e in V.check_all(root)))

    def test_detects_changed_observation(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            p = root / refs[2]
            p.write_text(p.read_text(encoding="utf-8").replace("Organic Research", "Organic  Research"), encoding="utf-8")
            self.assertTrue(any("绑定观察已变动" in e for e in V.check_all(root)))

    def test_detects_bad_recheck(self):
        with TmpRoot() as root:
            import json
            from _common import REJECTS_REL
            (root / REJECTS_REL).write_text(json.dumps({"schema_version": 1, "domains": {
                "a.com": {"failed": ["B2"], "readings": "x", "at": "2026-10-13", "recheck_after": "2027-01-11",
                          "observation": "证据/_scan/x.json"}}}), encoding="utf-8")
            self.assertTrue(any("复查" in e for e in V.check_all(root)))


if __name__ == "__main__":
    unittest.main()
