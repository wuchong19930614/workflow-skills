import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_model as QM
import settle as S
from helpers import TmpRoot, quick_volume_obs, setup_forecast, setup_quick

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
            self.assertIn("次英文区访问", body)
            self.assertNotIn("美区访问", body)
            self.assertIn("| 国家 | 锚词 | 锚词月量 | 比值 | 换算月搜索量 |", body)
            self.assertIn("| GB | 读不出 |", body)
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


PRE_ON = "2026-10-14"


def _pregame_md(root, verdict="go", **kw):
    slug, _ = setup_forecast(root, **kw)
    S.settle(root, slug, verdict, reason="开玩前预测过线", biggest_unknown="倍数只有 3 个参照", on=PRE_ON)
    return (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")


def _section(md, head):
    """取 `### head` 这一节的正文(到下一个 ### 或 ## 为止)。"""
    body = md.split(f"### {head}", 1)[1]
    return body.split("\n### ", 1)[0].split("\n## ", 1)[0]


class PregameDocTest(unittest.TestCase):
    def test_go_doc_has_forecast_sections(self):
        with TmpRoot() as root:
            md = _pregame_md(root)
            for needle in ("## 立即建站", "建议最晚 2026-10-28（开玩日 2026-10-29 前 1 天）上线",
                           "### 1. 即将开玩的游戏", "### 3. 任务与参照倍数", "### 6. 预判依据与风险",
                           "下四分位", "中位数", "10,800", "3 条参照", "2026-11-05 复核",
                           "**最大的未知：倍数只有 3 个参照。**", "## 第二部分 最小版本建站简报"):
                self.assertIn(needle, md)
            self.assertNotIn("当前月搜索量", md)

    def test_watching_doc_has_no_go_block(self):
        with TmpRoot() as root:
            md = _pregame_md(root, "watching", object_us=450000)
            self.assertNotIn("## 立即建站", md)
            self.assertNotIn("建站简报", md)
            self.assertIn("### 6. 预判依据与风险", md)
            self.assertIn("2026-11-05 复核", md)

    def test_every_forecast_section_opens_with_bold_plain_sentence(self):
        for verdict, kw in (("go", {}), ("watching", {"object_us": 450000})):
            with TmpRoot() as root:
                md = _pregame_md(root, verdict, **kw)
                heads = [b.split("\n")[0] for b in md.split("\n### ")[1:]]
                self.assertEqual(["1. 即将开玩的游戏", "2. 有人在等", "3. 任务与参照倍数", "4. 首页现场",
                                  "5. 预测访问与收入", "6. 预判依据与风险"], heads[:6])
                for block in md.split("\n### ")[1:]:
                    first = [ln for ln in block.split("\n")[1:] if ln.strip()][0]
                    self.assertTrue(first.startswith("**"), block.split("\n")[0])

    def test_go_block_numbers_come_from_the_record(self):
        with TmpRoot() as root:
            md = _pregame_md(root, playable_at="2026-11-02")
            block = md.split("## 立即建站", 1)[1].split("\n## ", 1)[0]
            self.assertIn("建议最晚 2026-11-01（开玩日 2026-11-02 前 1 天）上线", block)
            self.assertIn("- 保守：约 5,400 次访问、$21.60/月", block)
            self.assertIn("- 基准：约 10,800 次访问、$43.20/月", block)
            self.assertIn("- 乐观：约 16,200 次访问、$64.80/月", block)
            self.assertNotIn("单站就能到 $100", block)          # 基准 $43.20,不到 $100
            self.assertIn("中位数倍数下基准约 14,400 次访问、$57.60/月", block)
            self.assertIn("2026-11-09 复核", _section(md, "6. 预判依据与风险"))   # 开玩日 + 7 天
            self.assertIn("最小版本要做的页面：`/` grow a garden 2 calculator", block)

    def test_game_and_volume_sections_show_dates_and_per_country_volume(self):
        with TmpRoot() as root:
            md = _pregame_md(root)
            one = _section(md, "1. 即将开玩的游戏")
            self.assertIn("Monster Hunter Outlanders", one)
            self.assertIn("2026-10-29", one)
            self.assertIn("还有 15 天", one)                      # 结算日 2026-10-14 → 开玩日 2026-10-29
            self.assertIn("https://example.org/mho", one)
            self.assertIn("P1 依据", one)
            two = _section(md, "2. 有人在等")
            self.assertIn("600,000", two)
            self.assertIn("| US | 600,000 |", two)
            self.assertIn("| GB | 读不出", two)
            self.assertIn("P2 依据", two)

    def test_task_table_lists_term_references_and_both_multipliers(self):
        with TmpRoot() as root:
            three = _section(_pregame_md(root), "3. 任务与参照倍数")
            self.assertIn("| 任务 | 说法 | 参照条数 | 下四分位倍数 | 中位数倍数 | 取自 |", three)
            self.assertIn("| map | mho map | 3 条参照 | 0.15 | 0.2 |", three)
            self.assertIn("同类别", three)
            self.assertIn("mmo_gacha", three)

    def test_serp_section_summarises_both_queries_and_marks_aio_unknown(self):
        with TmpRoot() as root:
            four = _section(_pregame_md(root), "4. 首页现场")
            self.assertIn("monster hunter outlanders map", four)
            self.assertIn("monster hunter outlanders wiki", four)
            self.assertIn("reddit.com", four)
            self.assertIn("开玩前未知，按 0.6", four)
            self.assertIn("P5 依据", four)

    def test_forecast_tables_show_both_tiers(self):
        with TmpRoot() as root:
            five = _section(_pregame_md(root), "5. 预测访问与收入")
            self.assertEqual(2, five.count("| 情景 | 首发份额 | 预计月访问 | 预计月收入（AdSense） |"))
            self.assertIn("| 基准 | 20% | 10,800 | $43.20 |", five)         # 下四分位
            self.assertIn("| 基准 | 20% | 14,400 | $57.60 |", five)         # 中位数
            self.assertIn("90,000", five)
            self.assertIn("120,000", five)
            self.assertIn("600,000", five)

    def test_risk_section_has_stop_line_review_date_and_slip_rule_from_assumptions(self):
        a = QM.QUICK_ASSUMPTIONS
        with TmpRoot() as root:
            six = _section(_pregame_md(root), "6. 预判依据与风险")
            stop = f"{90000 * a['review_stop_ratio']:,.0f}"                  # 预测下四分位 × 止损比例
            self.assertIn(f"低于 {stop}", six)
            self.assertIn(f"推迟超过 {a['forecast_slip_days']} 天", six)
            self.assertIn("map 3 条参照", six)
            self.assertIn("第 9 到第 3 天", six)                              # 参照窗口写死:对象名
            self.assertIn(f"连续 {a['reference_task_days']} 天", six)         # 任务词
            self.assertIn("游戏热度可能回落", six)                            # 简报素材里的风险照列

    def test_forecast_html_highlights_launch_block(self):
        with TmpRoot() as root:
            slug, _ = setup_forecast(root)
            S.settle(root, slug, "go", reason="r", biggest_unknown="u", on=PRE_ON)
            html = (root / "文档" / f"{slug}.html").read_text(encoding="utf-8")
            start = html.index("<h2>立即建站</h2>")
            self.assertTrue(html[start:].split("</h2>", 1)[1].startswith('<div class="lede">'))

    def test_parked_pregame_doc_still_builds_without_forecast_block(self):
        with TmpRoot() as root:
            md = _pregame_md(root, "parked", brief=False)
            self.assertNotIn("## 立即建站", md)
            self.assertNotIn("### 6. 预判依据与风险", md)

    def test_current_path_doc_has_no_forecast_sections(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            S.settle(root, slug, "go", None, "首页没人做", "新域名多久能排上去", on=ON)
            body = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            for needle in ("预判依据与风险", "即将开玩的游戏", "任务与参照倍数"):
                self.assertNotIn(needle, body)


if __name__ == "__main__":
    unittest.main()
