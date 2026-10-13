import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bench_model
import build_doc as B
from _common import BenchError, load_ledger, save_ledger
from helpers import TmpRoot, setup_direction


def decide(root, slug, verdict, gate=None):
    """不经 settle,直接写 decision 与 model,只测文档生成。"""
    ledger = load_ledger(root)
    rec = ledger["directions"][slug]
    rec["model"] = bench_model.compute(rec)
    rec["decision"] = {"verdict": verdict, "gate": gate, "reason": "测试理由", "biggest_unknown": "测试未知",
                       "scope_hit": None, "decided_at": "2026-10-13T08:00:00+00:00"}
    save_ledger(root, ledger)


class BuildDocTest(unittest.TestCase):
    def test_go_doc_has_both_parts_and_bold_leads(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            decide(root, slug, "go")
            md, html = B.build(root, slug)
            body = md.read_text(encoding="utf-8")
            for h in ("## 结论", "## 第一部分 决策", "### 4. 12 个月流量与收入", "## 第二部分 建站简报",
                      "### 10. 里程碑与止损", "## 附：证据清单"):
                self.assertIn(h, body)
            self.assertIn("一句话：**值得做（go）**", body)
            # 每个三级标题后的第一段以粗体开头
            for block in body.split("\n### ")[1:]:
                first = [ln for ln in block.split("\n")[1:] if ln.strip()][0]
                self.assertTrue(first.startswith("**"), block.split("\n")[0])

    def test_html_embeds_md_sha_and_lede(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            decide(root, slug, "go")
            md, html = B.build(root, slug)
            h = html.read_text(encoding="utf-8")
            self.assertIn(hashlib.sha256(md.read_bytes()).hexdigest(), h)
            self.assertIn('<div class="lede">', h)
            self.assertIn("<details><summary>附：证据清单", h)

    def test_rejected_doc_has_no_brief(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root, us_organic_m12=5400)
            decide(root, slug, "rejected", "revenue")
            body = B.build(root, slug)[0].read_text(encoding="utf-8")
            self.assertIn("否决（收入不足）", body)
            self.assertNotIn("建站简报", body)

    def test_requires_decision(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "decision"):
                B.build(root, slug)


if __name__ == "__main__":
    unittest.main()
