# build_decision_html 测试:md→html 单向生成,覆盖决策书用到的 Markdown 子集。
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_decision_html as B

SAMPLE_MD = """# demo-term 建站决策书

**结论:build_ready**,base 情景 $320/月。

## 页面地图

| 页面 | 任务 |
| --- | --- |
| /calculator | 算 **VRAM** 需求 |
| /guide | 装机指南 |

## 失效条件

- 官方计算器上线
- 搜索语言迁移到 `new-term`

> 风险确认:这是窗口赌注。

1. 注册域名
2. 发布最小页面集

详见 [来源](https://example.com/thread)。

```bash
python3 registrar.py transition --to built
```

<script>alert('xss')</script>
"""


class BuildDecisionHtmlTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.md = Path(self._tmp.name) / "demo-term.md"
        self.md.write_text(SAMPLE_MD, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_generates_sibling_html(self):
        out = B.build(self.md)
        self.assertEqual(out, self.md.with_suffix(".html"))
        self.assertTrue(out.is_file())

    def test_html_structure_and_content(self):
        html = B.build(self.md).read_text(encoding="utf-8")
        self.assertIn("<title>demo-term 建站决策书</title>", html)
        self.assertIn("<h1>demo-term 建站决策书</h1>", html)
        self.assertIn("<h2>页面地图</h2>", html)
        self.assertIn("<th>页面</th>", html)
        self.assertIn("<td>算 <strong>VRAM</strong> 需求</td>", html)
        self.assertIn("<li>官方计算器上线</li>", html)
        self.assertIn("<code>new-term</code>", html)
        self.assertIn("<blockquote>", html)
        self.assertIn("<ol><li>注册域名</li><li>发布最小页面集</li></ol>", html)
        self.assertIn('<a href="https://example.com/thread">来源</a>', html)
        self.assertIn("<pre><code>python3 registrar.py transition --to built</code></pre>", html)
        self.assertIn("<strong>结论:build_ready</strong>", html)

    def test_raw_html_escaped(self):
        html = B.build(self.md).read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_single_file_no_external_refs(self):
        html = B.build(self.md).read_text(encoding="utf-8")
        for marker in ("<link", "src=\"http", "@import", "url(http"):
            self.assertNotIn(marker, html)

    def test_regeneration_is_deterministic(self):
        first = B.build(self.md).read_text(encoding="utf-8")
        second = B.build(self.md).read_text(encoding="utf-8")
        self.assertEqual(first, second)

    def test_cli_rejects_non_md(self):
        bogus = Path(self._tmp.name) / "x.txt"
        bogus.write_text("hi", encoding="utf-8")
        self.assertEqual(B.main([str(bogus)]), 2)
        self.assertEqual(B.main([str(self.md)]), 0)


if __name__ == "__main__":
    unittest.main()
