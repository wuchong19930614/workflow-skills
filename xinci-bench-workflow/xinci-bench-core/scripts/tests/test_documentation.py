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
import suggest_discover as D
import upstream_fetch as U
import validate_ledger as V
import write_observation as W
from helpers import TmpRoot

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
                       f"每款游戏最多预判 {a['forecast_max_per_object']} 次",
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

    def test_quick_rounds_documented(self):
        skill = (WORKFLOW / "xinci-bench-quick" / "SKILL.md").read_text(encoding="utf-8")
        for t in (text("选站契约.md"), text("命令与观察.md"), skill):
            self.assertIn("quick_signal_due", t)
            self.assertNotIn("quick_new_round_allowed", t)

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

    def test_object_volume_lag_documented(self):
        # 对象名量的时效:契约 10.6 写数值(由测试锁住),10.9 与命令手册 7.7 引用
        lag = QM.QUICK_ASSUMPTIONS["forecast_volume_max_lag_days"]
        c = text("选站契约.md")
        table = c.split("### 10.6 ", 1)[1].split("### 10.7 ", 1)[0]
        self.assertIn(f"| 预判对象名量的时效 | 对象名量级观察须在预判当天或之前 {lag} 天内测", table)
        self.assertIn("预判对象名量的时效", c.split("### 10.9 ", 1)[1])
        self.assertIn("预判对象名量的时效", text("命令与观察.md").split("### 7.7 上线前预判", 1)[1])

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

    def test_pregame_decisions_documented(self):
        # 2026-10-17 拍板的三条(设计稿第 14 节):重做规则、搁置方向开玩后判 go、观察按自己记下的口径校验
        doc, skill, c = text("命令与观察.md"), skill_text("xinci-bench-quick"), text("选站契约.md")
        for needle in ("\"params\"", "\"assumptions_version\"", "\"reforecast\"", "口径已变"):
            self.assertIn(needle, doc)
        for needle in ("new", "due", "开玩前 9–3 天"):
            self.assertIn(needle, skill)
        for needle in ("口径已变", "开玩后 14 天内"):
            self.assertIn(needle, c)
        # 上面的数字也跟假设表对一遍:改了假设表,文档里这几处会跟着失败
        a = QM.QUICK_ASSUMPTIONS
        far, near = a["reference_object_window"]
        self.assertIn(f"开玩前 {far}–{near} 天", skill)
        self.assertIn(f"每款游戏最多预判 {a['forecast_max_per_object']} 次", skill)
        self.assertIn(f"开玩后 {a['new_days_game']} 天内", c)
        self.assertIn(f"开玩后 {a['new_days_game']} 天内", skill)

    def test_parked_forecast_window_documented(self):
        # 看板"预判后搁置的方向已开玩"提醒:命令手册 7.7.7 写 JSON 键与文字版,快道 SKILL 第 2 步列出
        sec = text("命令与观察.md").split("#### 7.7.7 看板提醒", 1)[1]
        self.assertIn('"forecast_parked_window"', sec)
        self.assertIn("预判后搁置的 <方向> 已开玩 N 天", sec)
        self.assertIn("预判后搁置的方向已开玩", skill_text("xinci-bench-quick"))

    def test_tables_of_contents_list_every_heading(self):
        for name, body in (("选站契约.md", text("选站契约.md")), ("命令与观察.md", text("命令与观察.md")),
                           ("数据采集.md", text("数据采集.md")), ("设计稿", SPEC.read_text(encoding="utf-8"))):
            toc, want = toc_entries(body), headings(body)
            self.assertEqual([t for t, _ in toc], want, f"{name} 的目录与标题不一致")
            self.assertEqual([a for _, a in toc], [anchor(h) for h in want], f"{name} 的目录锚点有误")


class SignalSourcesDocTest(unittest.TestCase):
    """飙升词种子轮换、补全字母展开、非游戏上游(用户 2026-10-19 定):规程、命令手册、SKILL 都要跟代码对得上。"""

    def test_rising_seed_pools_documented(self):
        coll, skill = text("数据采集.md"), skill_text("xinci-bench-quick")
        for needle in ("、".join(f"`{w}`" for w in QM.RISING_FIXED), "、".join(QM.RISING_GAME_POOL),
                       "、".join(QM.RISING_OTHER_POOL), f"游戏任务词 {QM.RISING_GAME_PER_DAY} 个", f"`cat: {QM.GAME_CAT}`",
                       "`rising_seeds`"):
            self.assertIn(needle, coll)
        self.assertIn("`rising_seeds`", skill)
        for body in (coll, skill, text("命令与观察.md")):
            self.assertNotIn("3–4 个任务词", body)          # 旧口径:人自己挑任务词

    def test_discover_and_upstream_documented(self):
        coll, skill = text("数据采集.md"), skill_text("xinci-bench-quick")
        for p in D.DISCOVER_PATTERNS:
            self.assertIn(f"`{p['prefix']} a`", coll)
        extra = U.UPSTREAM_TASK_WORDS[len(QM.TASK_WORDS):]
        for needle in ("suggest_discover.py", "upstream_fetch.py", f"points>{U.HN_MIN_POINTS}", f"近 {U.WINDOW_DAYS} 天",
                       f"每个源最多 {U.LIMIT} 个", "、".join(extra)):
            self.assertIn(needle, coll)
        for needle in ("suggest_discover.py", "upstream_fetch.py"):
            self.assertIn(needle, skill)

    def test_derivative_words_documented(self):
        coll, doc, skill = text("数据采集.md"), text("命令与观察.md"), skill_text("xinci-bench-quick")
        words = " / ".join(QM.DERIVATIVE_WORDS)
        self.assertIn(f"<站名> {words}", coll)
        self.assertIn("suggest_snapshot.py --derivative", doc)
        self.assertIn("suggest_snapshot.py --derivative", skill)

    def test_command_doc_lists_every_output_field(self):
        doc = text("命令与观察.md").split("### 7.2 扫信号与原料池", 1)[1].split("### 7.3 ", 1)[0]
        for needle in ("suggest_discover.py --output", "upstream_fetch.py --output", '"rising_seeds"'):
            self.assertIn(needle, doc)
        with TmpRoot() as root:
            D.discover(root, lambda q: [], sleeper=lambda s: None, at="2026-10-18T08:00:00+00:00", letters="a",
                       patterns=D.DISCOVER_PATTERNS[:1])
            d = D.discover(root, lambda q: ["tier list abyss world roblox"], sleeper=lambda s: None,
                           at="2026-10-19T08:00:00+00:00", letters="a", patterns=D.DISCOVER_PATTERNS[:1])
            gh = '{"items": [{"name": "deskpet", "html_url": "https://g/x", "created_at": "2026-10-18T00:00:00Z"}]}'
            fr = '{"results": [{"title": "Rule A", "html_url": "https://f/x", "publication_date": "2026-10-18"}]}'
            u = U.fetch_all(root, on="2026-10-19", text_fetcher=lambda url: gh if "github" in url else fr,
                            suggest_fetcher=lambda q: ["deskpet tracker"], sleeper=lambda s: None,
                            sources=("github", "policy"))
            u_err = U.fetch_all(root, on="2026-10-19", text_fetcher=lambda url: 1 / 0, suggest_fetcher=lambda q: [],
                                sleeper=lambda s: None, sources=("github",))
        keys = set(d) | set(d["items"][0]) | set(u) | set(u["items"][0]) | set(u["sources"]["github"])
        keys |= set(u_err["sources"]["github"]) | {k for c in u["candidates"] for k in c}
        for k in sorted(keys):
            self.assertIn(f'"{k}"', doc, k)


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
