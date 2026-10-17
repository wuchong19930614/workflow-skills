import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_quick_doc as BQ
import ledger
import quick_forecast
import quick_model as QM
import settle as S
import write_observation as W
from _common import load_ledger
from helpers import TmpRoot, forecast_payload, quick_volume_obs, setup_forecast, setup_quick, write_references

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

    def test_parked_pregame_doc_uses_forecast_layout_without_review_or_stop_line(self):
        with TmpRoot() as root:
            md = _pregame_md(root, "parked", brief=False)
            for needle in ("### 1. 即将开玩的游戏", "### 3. 任务与参照倍数", "### 6. 预判依据与风险", "10,800", "3 条参照",
                           "| US | 600,000 |", "**最大的未知：倍数只有 3 个参照。**", "没有复核日"):
                self.assertIn(needle, md)
            for needle in ("## 立即建站", "按当前量估算", "没有做到量级换算", "没有曲线读数", "没有首屏读数",
                           "2026-11-05 复核", "止损", "22,500", "推迟超过"):
                self.assertNotIn(needle, md)
            for block in md.split("\n### ")[1:]:
                first = [ln for ln in block.split("\n")[1:] if ln.strip()][0]
                self.assertTrue(first.startswith("**"), block.split("\n")[0])

    def test_parked_pregame_days_to_play_count_from_the_decision_date(self):
        with TmpRoot() as root:
            md = _pregame_md(root, "parked", brief=False)
            decided = load_ledger(root)["directions"]["mho-map"]["decision"]["decided_at"][:10]
            days = (date.fromisoformat("2026-10-29") - date.fromisoformat(decided)).days
            self.assertIn(f"离结算日 {decided} " + (f"还有 {days} 天" if days >= 0 else f"已过 {-days} 天"), md)

    def test_parked_pregame_without_model_says_not_measured_instead_of_tables(self):
        with TmpRoot() as root:
            _pregame_md(root, "parked", brief=False)
            rec = load_ledger(root)["directions"]["mho-map"]
            rec["model"] = None                                   # 搁置时预判测算被拒的情形
            md = BQ.render_md(root, rec)
            five = _section(md, "5. 预测访问与收入")
            self.assertIn("本方向没有完成测算", five)
            self.assertNotIn("| 情景 |", md)
            self.assertNotIn("两档结果", md)
            self.assertIn("### 6. 预判依据与风险", md)
            self.assertIn("**最大的未知：倍数只有 3 个参照。**", md)
            self.assertIn("| US | 600,000 |", md)                 # 对象名月量与参照倍数仍读自预判观察
            self.assertIn("3 条参照", md)

    def test_parked_pregame_whose_latest_forecast_observation_failed_still_builds(self):
        with TmpRoot() as root:
            slug, refs = setup_forecast(root, brief=False)
            payload = forecast_payload(slug=slug, object="Monster Hunter Outlanders", volume_ref=refs[1])
            payload["checks"]["P5"] = {"pass": False, "basis": "测试期已有专做本作的 wiki"}
            failed = W.write(root, quick_forecast.build_observation(root, payload, at="2026-10-13T09:00:00+00:00"))
            ledger.update(root, slug, {}, [failed])
            S.settle(root, slug, "parked", reason="首页已被占", biggest_unknown="开玩日会不会变", on=PRE_ON)
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn("本方向没有完成测算", _section(md, "5. 预测访问与收入"))
            self.assertIn("没有测出", _section(md, "2. 有人在等"))
            self.assertIn("P5 依据：测试期已有专做本作的 wiki", md)
            self.assertNotIn("按当前量估算", md)

    def test_parked_pregame_marks_skipped_countries_as_not_measured(self):
        # 最新预判观察只测了美国与几国、GB 没测(measure_rest)就搁置:没测的写"未测",测了读不出的仍写"读不出，记 0"
        import copy
        with TmpRoot() as root:
            slug, refs = setup_forecast(root, brief=False)
            obs = copy.deepcopy(W.read(root, refs[0]))
            obs["observed_at"] = "2026-10-13T09:00:00+00:00"
            obs["readings"]["skipped_geos"] = ["GB"]
            obs["readings"]["suggestion"] = QM.forecast_suggestion(90000, 120000, complete=False)      # measure_rest
            ledger.update(root, slug, {}, [W.write(root, obs)])
            S.settle(root, slug, "parked", reason="其余国家没测完", biggest_unknown="英国的量", on=PRE_ON)
            two = _section((root / "文档" / f"{slug}.md").read_text(encoding="utf-8"), "2. 有人在等")
            self.assertIn("| GB | 未测 |", two)
            self.assertIn("| CA | 读不出，记 0 |", two)
            self.assertIn("| US | 600,000 |", two)

    def test_forecast_basis_direction_with_current_basis_model_keeps_current_layout(self):
        with TmpRoot() as root:
            _pregame_md(root, "parked", brief=False)
            rec = load_ledger(root)["directions"]["mho-map"]
            rec["model"] = {k: v for k, v in rec["model"].items() if k != "basis"}   # 开玩后按现行路径复判出的模型
            md = BQ.render_md(root, rec)
            self.assertIn("### 6. 风险与最大未知", md)
            self.assertNotIn("预判依据与风险", md)

    def test_rebuilt_doc_reads_the_observations_own_params(self):
        # 假设表后来改了:重建的决策书仍按预判观察(min_references、aio_factor)与它引用的参照(窗口)自己记下的口径写
        a = dict(QM.QUICK_ASSUMPTIONS)
        far, near = a["reference_object_window"]
        with TmpRoot() as root:
            write_references(root, category="open_world_survival")      # 同类别 mmo_gacha 没有参照:倍数退到全部类别
            slug, _ = setup_forecast(root)
            S.settle(root, slug, "go", reason="r", biggest_unknown="u", on=PRE_ON)
            rec = load_ledger(root)["directions"][slug]
            changed = {"min_references": a["min_references"] + 1, "aio_factor": round(a["aio_factor"] / 2, 2),
                       "reference_object_window": (far + 1, near + 1), "reference_task_days": a["reference_task_days"] + 1,
                       "reference_task_span": a["reference_task_span"] - 10}
            with mock.patch.dict(QM.QUICK_ASSUMPTIONS, changed):
                md = BQ.render_md(root, rec)
            self.assertIn(f"同类别不足 {a['min_references']} 条，取全部类别", _section(md, "3. 任务与参照倍数"))
            self.assertIn(f"开玩前未知，按 {a['aio_factor']} 取系数", _section(md, "4. 首页现场"))
            self.assertIn(f"对象名取开玩日前第 {far} 到第 {near} 天，任务词取开玩后 {a['reference_task_span']} 天内"
                          f"最高的连续 {a['reference_task_days']} 天", _section(md, "6. 预判依据与风险"))
            for wrong in (f"同类别不足 {changed['min_references']} 条", f"按 {changed['aio_factor']} 取系数",
                          f"第 {far + 1} 到第 {near + 1} 天", f"开玩后 {changed['reference_task_span']} 天内",
                          f"连续 {changed['reference_task_days']} 天"):
                self.assertNotIn(wrong, md)

    def test_doc_without_references_has_no_window_line(self):
        # 最新预判观察六条没有全过、没引用参照:不写参照窗口(没有参照自己记的口径可写)
        with TmpRoot() as root:
            slug, refs = setup_forecast(root, brief=False)
            payload = forecast_payload(slug=slug, object="Monster Hunter Outlanders", volume_ref=refs[1])
            payload["checks"]["P5"] = {"pass": False, "basis": "测试期已有专做本作的 wiki"}
            failed = W.write(root, quick_forecast.build_observation(root, payload, at="2026-10-13T09:00:00+00:00"))
            ledger.update(root, slug, {}, [failed])
            S.settle(root, slug, "parked", reason="首页已被占", biggest_unknown="开玩日会不会变", on=PRE_ON)
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertNotIn("参照窗口", md)
            self.assertIn("没有复核日", md)

    def test_unreadable_reference_does_not_block_the_rebuild(self):
        # 结算后引用的参照坏了:重建决策书照常出,坏的参照不提供窗口;一条都读不出就不写窗口
        with TmpRoot() as root:
            slug, _ = setup_forecast(root)
            S.settle(root, slug, "go", reason="r", biggest_unknown="u", on=PRE_ON)
            rec = load_ledger(root)["directions"][slug]
            paths = sorted((root / "证据" / "_quick").glob("*-quick_reference.json"))
            paths[0].write_text("{not json", encoding="utf-8")
            self.assertIn("参照窗口", _section(BQ.render_md(root, rec), "6. 预判依据与风险"))     # 其余两条照常提供
            for path in paths[1:]:
                path.write_text("{not json", encoding="utf-8")
            md = BQ.render_md(root, rec)
            self.assertIn("### 6. 预判依据与风险", md)
            self.assertNotIn("参照窗口", md)

    def test_current_path_doc_has_no_forecast_sections(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            S.settle(root, slug, "go", None, "首页没人做", "新域名多久能排上去", on=ON)
            body = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            for needle in ("预判依据与风险", "即将开玩的游戏", "任务与参照倍数"):
                self.assertNotIn(needle, body)


if __name__ == "__main__":
    unittest.main()
