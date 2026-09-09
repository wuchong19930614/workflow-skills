# md → html 单向生成:照 xinci 的模式(md 是唯一事实来源、内嵌源 SHA、永不手改)。
import hashlib
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_report as B
import build_report_html as H
import ledger as L
from helpers import revenue_for, VERIFY_OBS, TmpRoot, write_obs, CLUSTER, SEED, PROXY, REVENUE, VERIFY_OBS


def verified_md(root, slug="wire-size", volume=600000):
    ev = write_obs(root, slug, "2026-09-10-scan.json", semrush_preview={
        "queried_at": "2026-09-10", "filters": "US, phrase", "note": "前 50 行"})
    L.register(root, slug=slug, primary_keyword="wire size",
               cluster=dict(CLUSTER, total_volume=volume), seed=SEED,
               proxy=dict(PROXY, rank_score=0.71), evidence=[ev], by="t", reason="r")
    vev = write_obs(root, slug, "2026-09-11-verify.json", **VERIFY_OBS)
    L.transition(root, slug, to="verified", evidence=[vev], by="t", reason="r",
                 form="tool", revenue=revenue_for(root, slug, [vev]))
    return B.build(root, slug)


class ReportHtmlTest(unittest.TestCase):
    def test_md_carries_narrative_section_first(self):
        with TmpRoot() as root:
            text = verified_md(root).read_text(encoding="utf-8")
            self.assertIn("## 为什么是这个词", text)
            # 叙述节必须排在数据节之前
            self.assertLess(text.index("## 为什么是这个词"), text.index("## 1. 主关键词与簇"))

    def test_html_generated_next_to_md_with_source_sha(self):
        with TmpRoot() as root:
            md = verified_md(root)
            out = H.build(md)
            self.assertEqual(out, md.with_suffix(".html"))
            doc = out.read_text(encoding="utf-8")
            sha = hashlib.sha256(md.read_bytes()).hexdigest()
            self.assertIn(f'content="{sha}"', doc)
            self.assertTrue(doc.startswith("<!doctype html>"))
            self.assertIn("<title>", doc)
            self.assertIn("勿手改", doc)

    def test_html_converts_headings_tables_bold_code(self):
        with TmpRoot() as root:
            doc = H.build(verified_md(root)).read_text(encoding="utf-8")
            self.assertIn("<h2", doc)
            self.assertIn("<h3", doc)
            self.assertIn("<table>", doc)
            self.assertIn("<th", doc)
            self.assertIn("<strong>", doc)
            self.assertIn("<code>", doc)
            self.assertNotIn("| --- |", doc)     # 表格分隔行不得漏进正文
            self.assertNotIn("**", doc)          # 粗体标记必须被消化

    def test_data_sections_are_folded_away(self):
        """打开就是一页人话:九节数据表格折进 details,不占正文视线。"""
        with TmpRoot() as root:
            doc = H.build(verified_md(root)).read_text(encoding="utf-8")
            self.assertIn("完整数据与证据", doc)
            # 叙述节的小标题必须在正文里直接可见
            self.assertIn("<h3>有人在搜吗</h3>", doc)
            # 数据节的标题必须落在 details 之后
            self.assertLess(doc.index("完整数据与证据"), doc.index("主关键词与簇"))
            self.assertGreaterEqual(doc.count("<details"), 2)

    def test_no_sidebar_toc(self):
        """内容短了就不需要侧边目录,单栏更清晰。"""
        with TmpRoot() as root:
            doc = H.build(verified_md(root)).read_text(encoding="utf-8")
            self.assertNotIn('class="toc"', doc)

    def test_field_notes_collapsed(self):
        """机器化的现场要点折起来,不占正文视线。"""
        with TmpRoot() as root:
            doc = H.build(verified_md(root)).read_text(encoding="utf-8")
            self.assertIn("<details>", doc)
            self.assertIn("<summary>", doc)

    def test_deterministic(self):
        with TmpRoot() as root:
            md = verified_md(root)
            self.assertEqual(H.render(md), H.render(md))

    def test_rejects_non_md(self):
        with TmpRoot() as root:
            self.assertEqual(H.main([str(root / "账本" / "候选账本.json")]), 2)

    def test_build_report_also_writes_html(self):
        """build_report.py 出 md 时同批出 html,不留只有 md 的中间态。"""
        with TmpRoot() as root:
            md = verified_md(root)
            self.assertTrue(md.with_suffix(".html").is_file())


if __name__ == "__main__":
    unittest.main()
