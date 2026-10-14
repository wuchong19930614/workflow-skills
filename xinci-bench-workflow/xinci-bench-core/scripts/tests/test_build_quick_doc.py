import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import settle as S
from helpers import TmpRoot, quick_volume_obs, setup_quick

ON = "2026-10-20"


class BuildQuickDocTest(unittest.TestCase):
    def test_go_doc_has_launch_block_brief_and_bold_leads(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            S.settle(root, slug, "go", None, "首页没人做", "新域名多久能排上去", on=ON)
            body = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            for h in ("## 立即建站", "## 结论", "### 5. 预计访问与收入", "## 第二部分 最小版本建站简报",
                      "### 6. 验收与止损", "## 附：证据清单"):
                self.assertIn(h, body)
            self.assertIn("建议最晚 2026-10-27 上线", body)
            self.assertIn("月点击低于 2,500 就止损", body)
            for block in body.split("\n### ")[1:]:
                first = [ln for ln in block.split("\n")[1:] if ln.strip()][0]
                self.assertTrue(first.startswith("**"), block.split("\n")[0])

    def test_watching_doc_has_no_launch_block(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root, volume=quick_volume_obs("gag2-calculator", anchor_volume=9900, new_mean=50.0,
                                                                anchor_mean=99.0))
            S.settle(root, slug, "watching", None, "量不够在涨", "能否涨到 5 万", on=ON)
            body = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertNotIn("立即建站", body)
            self.assertNotIn("建站简报", body)
            self.assertIn("2026-11-19 到期", body)

    def test_html_highlights_launch_block(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            html = (root / "文档" / f"{slug}.html").read_text(encoding="utf-8")
            start = html.index("<h2>立即建站</h2>")
            self.assertTrue(html[start:].split("</h2>", 1)[1].startswith('<div class="lede">'))


if __name__ == "__main__":
    unittest.main()
