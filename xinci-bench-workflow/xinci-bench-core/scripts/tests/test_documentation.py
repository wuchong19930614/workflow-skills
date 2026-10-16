# 文档与代码的数值、字段、代码表必须一致:改一边忘了另一边时这里会失败。
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bench_model as M
import ledger as L
import quick_forecast as QF
import quick_model as QM
import quick_reference as QR
import seed_import as I
import validate_ledger as V
import write_observation as W

CORE = Path(__file__).resolve().parents[2]
WORKFLOW = CORE.parent


def text(name):
    return (CORE / name).read_text(encoding="utf-8")


def skill_text(name):
    return (WORKFLOW / name / "SKILL.md").read_text(encoding="utf-8")


SPEC = WORKFLOW.parent / "docs" / "superpowers" / "specs" / "2026-10-16-xinci-bench-quick-pregame-go-design.md"


def headings(body):
    """文档里的二到六级标题(跳过代码块和"目录"本身)。"""
    out, fence = [], False
    for line in body.splitlines():
        if line.startswith("```"):
            fence = not fence
        elif not fence:
            m = re.match(r"#{2,6} (.+)$", line)
            if m and m.group(1).strip() != "目录":
                out.append(m.group(1).strip())
    return out


def toc_entries(body):
    """目录里的 (标题, 锚点);目录从"## 目录"到下一个二级标题。"""
    block = body.split("\n## 目录\n", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\s*- \[(.+?)\]\(#(.+?)\)\s*$", block, re.M)


def anchor(heading):
    """GitHub 式锚点:转小写,只留字母数字(含汉字)、空格、连字符、下划线,空格换连字符。"""
    return "".join(c for c in heading.lower() if c.isalnum() or c in " -_").replace(" ", "-")


class ContractTest(unittest.TestCase):
    def test_contract_numbers_match_code(self):
        c = text("选站契约.md")
        a = M.ASSUMPTIONS
        self.assertIn(f"**{a['version']}**", c)
        self.assertIn(f"{W.LIMITS['max_age_months']} 个月", c)
        self.assertIn(f"≤ {W.LIMITS['max_authority_score']}", c)
        self.assertIn(f"≥ {W.LIMITS['min_en_organic']:,}/月", c)
        self.assertIn(f"{a['coef']['low']} / {a['coef']['base']} / {a['coef']['high']}", c)
        self.assertIn(f"{a['crowded_base_coef']}（crowding ≥ {a['crowded_at']}）", c)
        self.assertIn(f"{a['share_cap']:.0%}", c)
        self.assertIn(f"{a['journey_min_visits']:,}", c)
        self.assertIn(f"${a['rpm']['adsense']:.0f}", c)
        self.assertIn(f"${a['rpm']['mediavine_journey']:.0f}", c)
        self.assertIn(f"其他英文国家 AdSense ${a['rpm_other_en']['adsense']:.0f}、Journey ${a['rpm_other_en']['mediavine_journey']:.0f}", c)
        p = a["paid_conversion"]
        self.assertIn(f"{p['low']:.1%} / {p['base']:.1%} / {p['high']:.1%}", c)
        self.assertIn(f"${a['threshold']:.0f}", c)

    def test_contract_lists_every_gate_and_scope_code(self):
        c = text("选站契约.md")
        for code in L.GATES + L.SCOPE_ITEMS:
            self.assertIn(f"`{code}`", c)

    def test_platform_blacklist_documented(self):
        doc = text("数据采集.md")
        for d in I.PLATFORMS:
            self.assertIn(d, doc)


class SchemaTest(unittest.TestCase):
    def test_observation_schema_matches_validator(self):
        s = json.loads(text("数据结构/observation.schema.json"))
        self.assertEqual(tuple(s["properties"]["kind"]["enum"]), W.KINDS)
        self.assertEqual({k: tuple(v) for k, v in s["readings_required"].items()}, W.REQUIRED)

    def test_direction_schema_matches_ledger(self):
        s = json.loads(text("数据结构/direction.schema.json"))
        self.assertEqual(tuple(s["required"]), V.REQUIRED)
        self.assertEqual(tuple(s["properties"]["benchmarks"]["items"]["required"]), L.BENCH_KEYS)
        self.assertEqual(tuple(s["properties"]["clusters"]["items"]["required"]), L.CLUSTER_KEYS)
        self.assertEqual(tuple(s["properties"]["site_type"]["enum"]), L.SITE_TYPES)



class QuickContractTest(unittest.TestCase):
    def test_quick_numbers_match_code(self):
        c, a = text("选站契约.md"), QM.QUICK_ASSUMPTIONS
        s = a["share"]
        lo, hi = a["anchor_ratio"]
        for needle in (f"**{a['version']}**", f"{s['low']:.0%} / {s['base']:.0%} / {s['high']:.0%}",
                       f"×{a['aio_factor']}", f"{a['threshold_visits']:,} 访问", f"基准预计月收入 ≥ ${a['single_site_revenue']:.0f}",
                       f"美国 ${a['rpm_adsense']:.0f}/千访问", f"其他英文国家 ${a['rpm_other_en']:.0f}/千访问",
                       "、".join(a["countries"]), f"≤ {a['new_days']} 天", f"游戏 ≤ {a['new_days_game']} 天", f"| 观察期 | {a['watch_days']} 天 |",
                       f"峰值 × {a['oneoff_ratio']:.0%}", f"前 7 天 × {a['trend_floor']:.0%}", f"{lo}–{hi:g}",
                       f"| 原料保留 | {a['pool_days']} 天 |", f"{a['max_serp_per_run']} 个词", f"判 go 后 {a['launch_days']} 天",
                       " / ".join(str(m) for m in a["milestones"]) + " 天", f"基准预计 × {a['stop_ratio']:.0%}"):
            self.assertIn(needle, c)

    def test_pregame_numbers_match_code(self):
        c, a = text("选站契约.md"), QM.QUICK_ASSUMPTIONS
        lo, hi = a["forecast_days"]
        far, near = a["reference_object_window"]
        for needle in (f"今天之后 {lo}–{hi} 天", f"每轮最多预判 {a['forecast_per_run']} 个", f"参照至少 {a['min_references']} 条",
                       "下四分位", f"开玩日前 {a['forecast_launch_lead']} 天", f"开玩日 + {a['review_days']} 天",
                       f"预测 × {a['review_stop_ratio']:.0%}", f"门槛 × {a['us_only_cutoff']:.0%}",
                       f"开玩日前第 {far} 到第 {near} 天", f"开玩后 {a['reference_task_span']} 天内最高的连续 {a['reference_task_days']} 天",
                       f"推迟超过 {a['forecast_slip_days']} 天", *QM.GAME_CATEGORIES):
            self.assertIn(needle, c)

    def test_task_words_and_quick_gates_documented(self):
        c = text("选站契约.md")
        self.assertIn("、".join(QM.TASK_WORDS), c)
        for g in L.QUICK_GATES:
            self.assertIn(f"`{g}`", c)

    def test_quick_rounds_per_day_documented(self):
        import run_log as R
        self.assertIn(f"每天最多跑 {R.QUICK_ROUNDS_PER_DAY} 轮", text("选站契约.md"))

    def test_object_types_documented(self):
        s = json.loads(text("数据结构/direction.schema.json"))
        self.assertEqual(tuple(s["properties"]["object"]["properties"]["type"]["enum"]), L.OBJECT_TYPES)
        self.assertIn("type", s["properties"]["object"]["required"])

    def test_trends_tools_documented(self):
        js, doc = text("scripts/trends_fetch.js"), text("命令与观察.md")
        for fn in ("xinciTrends", "xinciTrendsRising", "xinciTrendsFirstSeen"):
            self.assertIn(f"async function {fn}(", js)
            self.assertIn(f"{fn}(", doc)

    def test_direction_schema_quick_required(self):
        s = json.loads(text("数据结构/direction.schema.json"))
        self.assertEqual(tuple(s["quick_required"]), V.REQUIRED_QUICK)


class PregameDocTest(unittest.TestCase):
    """上线前预判的文档:命令、字段、流程步骤与目录都要跟代码对得上。"""

    def test_pregame_tools_documented(self):
        doc, coll, skill = text("命令与观察.md"), text("数据采集.md"), skill_text("xinci-bench-quick")
        for needle in ("quick_reference.py time-range", "quick_reference.py build", "quick_reference.py summary",
                       "quick_forecast.py --input", "ledger.py review-forecast", "\"basis\": \"forecast\"",
                       "\"skipped_geos\"", "\"scope\""):
            self.assertIn(needle, doc)
        self.assertIn("xinciTrends(", coll)
        self.assertIn("quick_reference.py time-range", coll)
        for needle in ("quick_forecast.py", "review-forecast", f"每轮最多预判 {QM.QUICK_ASSUMPTIONS['forecast_per_run']} 个"):
            self.assertIn(needle, skill)

    def test_command_doc_lists_every_pregame_field(self):
        sec = text("命令与观察.md").split("### 7.7 上线前预判", 1)[1]
        keys = set(W.REQUIRED["quick_reference"]) | set(W.REQUIRED["quick_forecast"]) | set(L.FORECAST_KEYS)
        keys |= set(QR.PAYLOAD_KEYS) | set(QF.PAYLOAD_KEYS) | set(QF.RATE_KEYS)
        keys |= set(QR.summary([{"task": "map", "category": "mmo_gacha", "r": 0.1}])[0])
        for k in sorted(keys):
            self.assertIn(f'"{k}"', sec, f"7.7 的 JSON 里没写字段 {k}")
        for needle in ("forecast_window", "forecast_reviews_due", "forecast_warnings", "forecast_slipped",
                       "references_due", "measure_rest", "watching", "skip", "\"review\"", "--dry-run"):
            self.assertIn(needle, sec)

    def test_contract_has_pregame_section_and_step(self):
        c = text("选站契约.md")
        self.assertIn("### 10.9 上线前预判", c)
        sec, steps = c.split("### 10.9 上线前预判", 1)[1], c.split("### 10.2 ", 1)[1].split("### 10.3 ", 1)[0]
        self.assertEqual(re.findall(r"^\d+\. ([^：]+)：", steps, re.M),
                         ["先提醒", "复查观察中", "扫信号", "上线前预判", "零成本速判", "首屏速判", "登记、测算、结算", "推荐与汇报"])
        self.assertIn("### 10.2 一次运行的八步", c)
        for code in ("P1", "P2", "P3", "P4", "P5", "P6"):
            self.assertIn(f"**{code} ", sec)
        for needle in ("10.6", "飙升词 > 复核到期 > 预判 > 补参照", "不能否决", "review-forecast", "update"):
            self.assertIn(needle, sec)

    def test_skill_steps_are_numbered_and_cover_pregame(self):
        body = skill_text("xinci-bench-quick")
        nums = [int(n) for n in re.findall(r"^(\d+)\. ", body, re.M)]
        self.assertEqual(nums, list(range(1, len(nums) + 1)))
        for needle in ("forecast_window", "quick_forecast.py", "register-quick", "`forecast` 键", "review-forecast",
                       "watch-check", "开玩日前 1 天", "quick_reference.py", "references_due", "不能 `rejected`",
                       "不能用 `ledger.py quick-preview`"):
            self.assertIn(needle, body)

    def test_spec_marked_implemented_with_rulings(self):
        body = SPEC.read_text(encoding="utf-8")
        self.assertIn("- 状态：已批准，已实施", body)
        sec = body.split("## 13. 实施时补的口径", 1)[1]
        self.assertEqual([int(n) for n in re.findall(r"^(\d+)\. ", sec, re.M)], list(range(1, 11)))

    def test_tables_of_contents_list_every_heading(self):
        for name, body in (("选站契约.md", text("选站契约.md")), ("命令与观察.md", text("命令与观察.md")),
                           ("数据采集.md", text("数据采集.md")), ("设计稿", SPEC.read_text(encoding="utf-8"))):
            toc, want = toc_entries(body), headings(body)
            self.assertEqual([t for t, _ in toc], want, f"{name} 的目录与标题不一致")
            self.assertEqual([a for _, a in toc], [anchor(h) for h in want], f"{name} 的目录锚点有误")


class SkillTest(unittest.TestCase):
    def test_skills_named_and_point_to_contract(self):
        for name in ("xinci-bench-scan", "xinci-bench-assess", "xinci-bench-status", "xinci-bench-run",
                     "xinci-bench-quick"):
            body = (WORKFLOW / name / "SKILL.md").read_text(encoding="utf-8")
            m = re.match(r"---\nname: (\S+)\ndescription: '(.+)'\n---\n", body)
            self.assertIsNotNone(m, name)
            self.assertEqual(m.group(1), name)
            if name != "xinci-bench-status":
                self.assertIn("选站契约.md", body)

if __name__ == "__main__":
    unittest.main()
