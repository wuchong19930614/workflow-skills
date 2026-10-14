# xinci-bench 新词快道实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按快道设计稿在 `xinci-bench-workflow/` 里加一条"新词快道"：新 skill `xinci-bench-quick`（暗号 `xinci_bench_quick_run`）、新增 4 个脚本、改 9 个现有脚本（账本、结算、校验、运行清单、看板等按道分派），抓近 90 天冒出、首页还没人做、会反复被搜的新词，判 go 时四处强推用户建站并跟进到上线验收。

**Architecture:** 快道与标杆道共用账本、观察只追加、结算先复核再写入并可回滚、决策书 md→html、运行清单与看板；方向记录新增 `lane`（bench/quick），每条道有自己的合法转移、否决门和复核规则，快道多一个 `watching` 状态。快道判据只写在契约第 10 节，数值常量在 `quick_model.QUICK_ASSUMPTIONS`，由文档一致性测试锁住两边。唯一联网的脚本 `suggest_snapshot.py` 取数函数可注入，测试不联网。

**Tech Stack:** Python 3 标准库（零第三方依赖）、unittest、Markdown、symlink。

**Spec:** [docs/superpowers/specs/2026-10-13-xinci-bench-quick-lane-design.md](../specs/2026-10-13-xinci-bench-quick-lane-design.md)；底座见 [标杆道设计稿](../specs/2026-10-13-xinci-bench-workflow-design.md)。

**计划里的代码全部来自 scratchpad 原型，并且逐任务模拟执行过**：生成计划时从仓库 HEAD 导出干净的树，按任务顺序套用本计划里的改动，每个任务的 Step 2 与 Step 4 都真实跑了测试，下面的 Expected 就是当时的输出；全部做完与原型逐字节一致，151 个测试通过（原有 93 个 + 新增 58 个）。另用命令行在临时数据区把"扫信号 → 原料池 → 速判 → 登记 → 量级与简报 → 预览 → 结算 go → 看板置顶 → 跟进 → 校验"走过一遍（0 个错误），并对真实的自动补全接口取过一次数。照抄即可，不要凭记忆改写。

## 目录

- [与设计稿的差异（本计划补的，最后一个任务写回设计稿 §15）](#与设计稿的差异本计划补的最后一个任务写回设计稿-15)
- [Global Constraints](#global-constraints)
- [Review Focus](#review-focus)
- [文件结构](#文件结构)
- [任务](#任务)
  - [Task 1: 快道测算模型 quick_model](#task-1-快道测算模型-quick_model)
  - [Task 2: 快道观察与数据区](#task-2-快道观察与数据区)
  - [Task 3: 原料池与自动补全快照](#task-3-原料池与自动补全快照)
  - [Task 4: 快道账本——lane、登记、复查与建站跟进](#task-4-快道账本lane登记复查与建站跟进)
  - [Task 5: 快道结算、校验与决策书](#task-5-快道结算校验与决策书)
  - [Task 6: 运行清单与看板](#task-6-运行清单与看板)
  - [Task 7: 契约、采集规程与命令手册加快道](#task-7-契约采集规程与命令手册加快道)
  - [Task 8: 快道 skill、README 与双环境接入](#task-8-快道-skillreadme-与双环境接入)
  - [Task 9: 真实数据区、真实接口验收与设计稿写回](#task-9-真实数据区真实接口验收与设计稿写回)

## 与设计稿的差异（本计划补的，最后一个任务写回设计稿 §15）

1. 自动补全的"新建议"指以前所有快照里都没出现过的建议：同一查询隔几秒请求，返回的建议也不一样（2026-10-13 实测），只和上一次比会把波动当成新词；第一次快照只作基线。快照文件名为 `<规范化查询>-<查询 SHA-1 前 8 位>.json`，防止不同查询规范化后重名。
2. 运行清单的 `source_kind` 固定为 `quick`，本次用了哪些来源写在 `seed_value`。
3. `settle.py` 在任何写入之前先核对否决门属于该方向所在的道（快道不能用 `revenue` 等标杆道的门），不符直接拒收。
4. 速判 Q5 不过、占位的是小站时，用 `quick_pool.py reject --seed-domain <域名>` 在记淘汰的同时登记为标杆道种子（来源 serp）；已登记方向结算为 `occupied` 时仍用 `seeds.py add`。
5. 登记时速判观察里的词须是登记的说法之一（大小写与空格不计）；同一说法不能属于两个方向。
6. 量级观察额外校验：`ratio_7d` 须等于两条曲线 7 天均值之比，`estimate_7d` 须等于锚词月量 × 比值（允许取整误差 1），曲线至少 14 个非负数（Trends 显示 "<1" 的点记 0）。
7. 快道方向用 `ledger.py update` 只能改 `title`、`site_type`、`terms` 和追加观察引用，标杆道字段一律拒收。
8. 建站跟进的日期须为 YYYY-MM-DD，开建不早于判 go，上线不早于开建。
9. 原料池每行多记 `observation`（来自哪份 `quick_signal` 观察）与 `updated_at`；淘汰记录在顺带登记种子时多记 `seed`、`seed_added`。
10. 决策书把设计稿 §8.1 的第 3–8 项归在"第一部分 决策"（### 1–6）下，简报为"第二部分 最小版本建站简报"（### 1–6）。
11. 测试新增 58 个（设计稿估约 40 个），合计 151 个。
12. 工作流说明 html 与发布页（设计稿 §13 第 4 条）不在本计划里：放到实施与整体审查完成之后单独更新，因为测试数、脚本数要以最终代码为准。

## Global Constraints

- 只用 Python 3 标准库与 unittest，不加第三方依赖；与 xinci、xinci-simple 零运行时依赖。
- 标杆道的判据、假设表 `2026-10-13.1`、状态与流程不变；原有 93 个测试保持通过，唯一改动的旧断言是看板 `counts` 多一个 `"watching": 0`。
- 快道假设表 `2026-10-13.q1`：首发份额 10% / 20% / 30%；AI 概览在场但没答完 ×0.6；go 门槛基准 ≥ 10,000 访问（上线 90 天内单月）；≥ 25,000 标"单站就能到 $100"；收入按 AdSense $4/千访问展示；真新 ≤ 90 天；观察期 30 天；冲高回落 = 最近 7 天均值 < 近 30 天峰值 × 30%；趋势不降 = 最近 7 天 ≥ 前 7 天 × 80%；锚词比值 0.2–5；锚词测量须在 90 天内；原料保留 7 天；每次运行首屏最多 10 个词；建议最晚上线 = 判 go 后 7 天；验收节点 14 / 30 / 90 天；止损 = 第 30 天月点击 < 基准预计 × 25%。
- 任务词固定 10 个：calculator、codes、tracker、tier list、map、checker、generator、converter、build、value。
- 快道只能用暗号 `xinci_bench_quick_run` 手动触发，不建定时任务；Steam、Roblox 不走 GitHub Actions 绕道。
- 冒烟测试只用 `XINCI_BENCH_DATA_ROOT=<临时目录>` 或 `--data-root <临时目录> --no-save`；跑完确认 `.xinci-data-root`、`.xinci-simple-data-root`、`.xinci-bench-data-root` 三个指针文件都没被改。
- 注释、文档、提交信息用中文；代码标识符用英文；文档目录列出所有层级标题。
- 在已有分支 `xinci-bench-workflow` 上做，每个 Task 提交一次；只 `git add` 明确路径；不碰用户未提交的 `xinci-simple-workflow/xinci-simple-core/选词契约.md` 和未入库的 `xinci-bench-workflow/工作流说明.html`；不 push。

## Review Focus

- 用户口述跟进日期时写成 "10/25"，或上线日期早于开建日期：应拒收并说明格式与先后，而不是存进账本、等看板算验收节点时崩溃（Task 5 `test_dates_checked`）。
- 速判观察里的词和登记的说法对不上（拿别的词的首页结果给这个方向背书）：应拒收（Task 4 `test_screen_must_be_about_a_registered_term`）。
- 同一说法只差大小写或空格（"A  Term" 与 "a term"）：应视为同一个词，不能登记到两个方向（Task 4 `test_term_match_ignores_case_and_spaces`）。
- Trends 曲线里低量点显示为 "<1"，执行者原样抄进 `series_30d`：应拒收并提示记 0（Task 2 `test_trends_less_than_one_marker_refused`）。
- SteamCharts、Apple 榜单这类来源只给对象、还没有任务说法（`term` 为 null）：原料池应按对象名去重，不能每次运行都重复登记同一个新游戏（Task 3 `test_object_only_items_dedup_by_object`）。

---

## 文件结构

```
xinci-bench-workflow/
├── README.md                          加 quick 一行、快道设计稿链接、软链清单加 xinci-bench-quick
├── xinci-bench-quick/SKILL.md          新增:快道流程,暗号 xinci_bench_quick_run
├── xinci-bench-{scan,assess,run,status}/SKILL.md   末尾各加一行:汇报前先读看板"【立即建站】"行
└── xinci-bench-core/
    ├── 选站契约.md                     加第 10 节 新词快道(10.1–10.8)
    ├── 数据采集.md                     加第 7 节 快道数据来源(7.1–7.5)
    ├── 命令与观察.md                   加第 7 节 新词快道(7.1–7.6)
    ├── 数据结构/observation.schema.json  四类快道观察
    ├── 数据结构/direction.schema.json    lane、watching、quick_required 与快道字段
    └── scripts/
        ├── quick_model.py        新增:快道假设表、锚词换算、趋势、三档访问、判定建议
        ├── quick_pool.py         新增:原料池(去重、7 天过期)与快道淘汰记录
        ├── suggest_snapshot.py   新增:自动补全快照与"从没出现过"的新建议(唯一联网脚本)
        ├── build_quick_doc.py    新增:快道决策书(立即建站 + 决策 + 最小版本简报)
        ├── _common.py            加快道三个路径常量
        ├── init_workspace.py     建快道目录与空文件
        ├── write_observation.py  四类快道观察的校验
        ├── ledger.py             lane、快道登记/复核/复查/跟进
        ├── settle.py             按道分派复核与文档,快道 go 初始化跟进
        ├── validate_ledger.py    按道校验,快道模型重算、观察期到期、跟进合法
        ├── build_doc_html.py     立即建站一节加底色
        ├── run_log.py            快道单阶段运行,两条道互不阻塞
        ├── report_status.py      看板置顶立即建站、观察中、验收节点
        └── tests/                helpers 追加快道数据;新增 7 个测试文件,改 3 个
```

数据区新增（`init_workspace.py` 幂等创建）：`证据/_quick/`、`快道/原料.jsonl`、`快道/淘汰.json`、`快道/补全快照/`。

所有命令在仓库根 `/Users/vito.wu/IdeaProjects/workflow-skills` 执行，测试命令固定为：

```bash
python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q
```

**开工前**：确认在分支 `xinci-bench-workflow`（`git branch --show-current`），工作区只有用户原有的 `选词契约.md` 改动和未入库的 `工作流说明.html`；跑一次测试命令，Expected: `Ran 93 tests` 与 `OK`。

## 任务

### Task 1: 快道测算模型 quick_model

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/quick_model.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_model.py`

**Interfaces:**
- Consumes: `_common.BenchError/load_json/load_ledger/require`、`data_root.resolve_or_exit`（均已存在）
- Produces: `quick_model.QUICK_ASSUMPTIONS`（版本 `2026-10-13.q1`，键见 Global Constraints）、`TASK_WORDS`（10 个任务词）、`SCENARIOS=('low','base','high')`、`ratio_ok(ratio)->bool`、`anchor_estimate(anchor_volume, new_series, anchor_series, window=7)->{new_mean, anchor_mean, ratio, estimate, ratio_ok}`、`trend(series)->{last7, prev7, peak30, non_declining, spike_decay}`（至少 14 个点）、`aio_factor(serp)->float`、`searches_needed(factor)->int`、`compute(record)->{assumptions_version, searches, aio_factor, scenarios{low,base,high:{share,visits,revenue}}, passes, single_site_100, threshold_visits, searches_needed, suggestion}`（suggestion 为 go / watching / rejected:volume / rejected:oneoff）、`add_days(day, n)->str`、`milestones(launched_at)->[{day, date}]`、`stop_line(model)->int`；CLI `--direction <slug>` 或 `--input <记录 JSON>`

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_model.py`（新建）：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_model as Q
from _common import BenchError


def rec(estimate, aio=False, series=None):
    return {"volume": {"estimate_7d": estimate, "trend": Q.trend(series or list(range(20, 50)))},
            "serp": {"aio_present": aio, "aio_completes": False}}


class QuickModelTest(unittest.TestCase):
    def test_anchor_estimate(self):
        out = Q.anchor_estimate(60000, [0] * 23 + [50] * 7, [0] * 23 + [60] * 7)
        self.assertEqual((out["ratio"], out["estimate"], out["ratio_ok"]), (0.8333, 50000, True))
        far = Q.anchor_estimate(74000, [5] * 7, [72] * 7)
        self.assertFalse(far["ratio_ok"])          # 2026-10-13 实测那次约 1/15,应换锚词

    def test_anchor_zero_refused(self):
        with self.assertRaisesRegex(BenchError, "锚词"):
            Q.anchor_estimate(1000, [1] * 7, [0] * 7)

    def test_trend_rules(self):
        self.assertTrue(Q.trend(list(range(20, 50)))["non_declining"])
        self.assertFalse(Q.trend([50] * 23 + [30] * 7)["non_declining"])     # 30 < 50 × 0.8
        self.assertTrue(Q.trend([0] * 23 + [5] * 7)["non_declining"])       # 前 7 天为 0,刚起量
        self.assertTrue(Q.trend([0] * 10 + [100] + [5] * 19)["spike_decay"])
        self.assertFalse(Q.trend([0] * 30)["non_declining"])

    def test_threshold_edge(self):
        self.assertTrue(Q.compute(rec(50000))["passes"])
        out = Q.compute(rec(49995))
        self.assertEqual(out["scenarios"]["base"]["visits"], 9999)
        self.assertFalse(out["passes"])

    def test_aio_factor_and_searches_needed(self):
        out = Q.compute(rec(50000, aio=True))
        self.assertEqual((out["aio_factor"], out["scenarios"]["base"]["visits"], out["searches_needed"]), (0.6, 6000, 83334))
        self.assertEqual(Q.compute(rec(50000))["searches_needed"], 50000)

    def test_revenue_and_single_site(self):
        out = Q.compute(rec(125000))
        self.assertEqual(out["scenarios"]["base"], {"share": 0.2, "visits": 25000, "revenue": 100.0})
        self.assertTrue(out["single_site_100"])
        self.assertFalse(Q.compute(rec(124995))["single_site_100"])

    def test_answered_refused(self):
        r = rec(50000)
        r["serp"]["aio_completes"] = True
        with self.assertRaisesRegex(BenchError, "答完"):
            Q.compute(r)

    def test_suggestion(self):
        self.assertEqual(Q.compute(rec(5000))["suggestion"], "watching")
        self.assertEqual(Q.compute(rec(5000, series=[50] * 23 + [30] * 7))["suggestion"], "rejected:volume")
        self.assertEqual(Q.compute(rec(90000, series=[0] * 10 + [100] + [5] * 19))["suggestion"], "rejected:oneoff")
        self.assertEqual(Q.compute(rec(60000))["suggestion"], "go")

    def test_milestones_and_stop_line(self):
        self.assertEqual([m["date"] for m in Q.milestones("2026-11-01")], ["2026-11-15", "2026-12-01", "2027-01-30"])
        self.assertEqual(Q.stop_line(Q.compute(rec(50000))), 2500)
        self.assertEqual(Q.add_days("2026-10-20", 7), "2026-10-27")


if __name__ == "__main__":
    unittest.main()
```


- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `FAILED (errors=1)`，首个报错 `ModuleNotFoundError: No module named 'quick_model'`（本任务的模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/quick_model.py`（新建）：

```python
#!/usr/bin/env python3
"""新词快道测算:锚词换算、趋势判断、上线 90 天内单月访问三档。纯函数 + CLI。

预计月访问 = floor(当前月搜索量 × 首发份额 × AI 概览系数);按当前量,不外推增长。
假设表只由用户改(改时升版本)。
"""
import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import data_root
from _common import BenchError, load_json, load_ledger, require

QUICK_ASSUMPTIONS = {
    "version": "2026-10-13.q1",
    "share": {"low": 0.10, "base": 0.20, "high": 0.30},
    "aio_factor": 0.6,
    "threshold_visits": 10000,
    "single_site_visits": 25000,
    "rpm_adsense": 4.0,
    "new_days": 90,
    "watch_days": 30,
    "oneoff_ratio": 0.3,
    "trend_floor": 0.8,
    "anchor_ratio": (0.2, 5.0),
    "anchor_fresh_days": 90,
    "pool_days": 7,
    "max_serp_per_run": 10,
    "launch_days": 7,
    "milestones": (14, 30, 90),
    "stop_ratio": 0.25,
}
TASK_WORDS = ("calculator", "codes", "tracker", "tier list", "map", "checker", "generator",
              "converter", "build", "value")
SCENARIOS = ("low", "base", "high")


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def ratio_ok(ratio, a=QUICK_ASSUMPTIONS) -> bool:
    lo, hi = a["anchor_ratio"]
    return lo <= ratio <= hi


def anchor_estimate(anchor_volume, new_series, anchor_series, window=7) -> dict:
    """同一次 Trends 查询里的两条曲线 → 新词当前月搜索量。窗口取序列末尾 window 个点。"""
    require(anchor_volume > 0, "锚词月搜索量须为正数")
    require(len(new_series) == len(anchor_series) and len(new_series) >= window,
            "两条曲线须等长且不短于窗口")
    new_mean, anchor_mean = _mean(new_series[-window:]), _mean(anchor_series[-window:])
    require(anchor_mean > 0, "锚词在窗口内热度为 0,换一个锚词")
    ratio = new_mean / anchor_mean
    return {"new_mean": round(new_mean, 4), "anchor_mean": round(anchor_mean, 4),
            "ratio": round(ratio, 4), "estimate": round(anchor_volume * ratio),
            "ratio_ok": ratio_ok(ratio)}


def trend(series, a=QUICK_ASSUMPTIONS) -> dict:
    """最近 7 天 vs 前 7 天看趋势;最近 7 天 vs 近 30 天峰值看冲高回落。"""
    require(len(series) >= 14, "曲线至少要 14 个点")
    last7, prev7, peak = _mean(series[-7:]), _mean(series[-14:-7]), max(series)
    non_declining = last7 > 0 and (prev7 == 0 or last7 >= a["trend_floor"] * prev7)
    spike_decay = peak > 0 and last7 < a["oneoff_ratio"] * peak
    return {"last7": round(last7, 2), "prev7": round(prev7, 2), "peak30": peak,
            "non_declining": non_declining, "spike_decay": spike_decay}


def aio_factor(serp, a=QUICK_ASSUMPTIONS) -> float:
    return a["aio_factor"] if serp.get("aio_present") and not serp.get("aio_completes") else 1.0


def searches_needed(factor, a=QUICK_ASSUMPTIONS) -> int:
    return math.ceil(a["threshold_visits"] / (a["share"]["base"] * factor))


def compute(record: dict, a=QUICK_ASSUMPTIONS) -> dict:
    """record 须有 volume(estimate_7d、trend)与 serp(aio_present、aio_completes)。"""
    vol, serp = record.get("volume") or {}, record.get("serp") or {}
    require(isinstance(vol.get("estimate_7d"), (int, float)) and vol["estimate_7d"] >= 0, "缺当前月搜索量 estimate_7d")
    require("aio_present" in serp, "缺首屏读数 serp.aio_present")
    require(not serp.get("aio_completes"), "AI 概览已答完,不能测算(应按 answered 否决)")
    factor = aio_factor(serp, a)
    scenarios = {}
    for s in SCENARIOS:
        v = math.floor(vol["estimate_7d"] * a["share"][s] * factor)
        scenarios[s] = {"share": a["share"][s], "visits": v, "revenue": round(v * a["rpm_adsense"] / 1000, 2)}
    base = scenarios["base"]["visits"]
    tr = vol.get("trend") or {}
    passes = base >= a["threshold_visits"]
    if tr.get("spike_decay"):
        suggestion = "rejected:oneoff"
    elif passes:
        suggestion = "go"
    elif tr.get("non_declining"):
        suggestion = "watching"
    else:
        suggestion = "rejected:volume"
    return {"assumptions_version": a["version"], "searches": vol["estimate_7d"], "aio_factor": factor,
            "scenarios": scenarios, "passes": passes, "single_site_100": base >= a["single_site_visits"],
            "threshold_visits": a["threshold_visits"], "searches_needed": searches_needed(factor, a),
            "suggestion": suggestion}


def add_days(day: str, n: int) -> str:
    return (date.fromisoformat(day[:10]) + timedelta(days=n)).isoformat()


def milestones(launched_at: str, a=QUICK_ASSUMPTIONS) -> list:
    return [{"day": d, "date": add_days(launched_at, d)} for d in a["milestones"]]


def stop_line(model: dict, a=QUICK_ASSUMPTIONS) -> int:
    return math.floor(model["scenarios"]["base"]["visits"] * a["stop_ratio"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--direction", help="读账本里该快道方向")
    g.add_argument("--input", help="读一个方向记录 JSON 文件")
    a = ap.parse_args(argv)
    try:
        if a.direction:
            rec = load_ledger(data_root.resolve_or_exit(a.data_root))["directions"].get(a.direction)
            require(rec and rec.get("lane") == "quick", f"账本里没有快道方向 {a.direction}")
        else:
            rec = load_json(Path(a.input))
        print(json.dumps(compute(rec), ensure_ascii=False, indent=2))
    except (BenchError, OSError, ValueError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```


- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 102 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_model.py" "xinci-bench-workflow/xinci-bench-core/scripts/quick_model.py"
git commit -m "xinci-bench 快道:测算模型——锚词换算、趋势与冲高回落、三档访问与判定建议" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 快道观察与数据区

**Files:**
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/_common.py`（加三个路径常量）
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py`（建快道目录与空文件）
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/write_observation.py`（整份替换：四类快道观察的校验）
- Modify: `xinci-bench-workflow/xinci-bench-core/数据结构/observation.schema.json`（整份替换）
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/tests/helpers.py`（末尾追加快道测试数据）
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_observation.py`

**Interfaces:**
- Consumes: `quick_model.QUICK_ASSUMPTIONS/ratio_ok`（Task 1）
- Produces: `_common.QUICK_POOL_REL='快道/原料.jsonl'`、`QUICK_REJECTS_REL='快道/淘汰.json'`、`SUGGEST_DIR_REL='快道/补全快照'`；`init_workspace` 额外建 `证据/_quick`、`快道/补全快照`、`快道/淘汰.json`（`{schema_version:1, terms:{}}`）与空的 `快道/原料.jsonl`；`write_observation.QUICK_KINDS=('quick_signal','quick_screen','quick_volume','quick_brief')`（并入 `KINDS`）、`QUICK_CHECKS=('Q1'..'Q6')`、`QUICK_SOURCES`（15 个来源代码）、`REQUIRED` 增四类、`_DATE`（YYYY-MM-DD 正则）；快道观察 `stage='quick'`，`quick_signal` 的 slug 为 null、写到 `证据/_quick/`，其余写到 `证据/<slug>/`
- Produces（测试用）: `helpers.QUICK_BASE`、`OBJ`、`quick_signal_obs(*terms)`、`quick_screen_obs(slug, term=..., fail=None, aio=False, occupied_by=None, preflight=True)`、`rising_series()`、`quick_volume_obs(slug, anchor_volume=60000, new_mean=50.0, anchor_mean=60.0, series=None, measured='2026-10-08')`（默认恰好 5 万月搜索量 → 基准 1 万访问）、`quick_brief_obs(slug, build_days=2, data_available=True)`、`setup_quick(root, slug='gag2-calculator', volume=None, brief=True, screen=None)->(slug, refs)`。`setup_quick` 在函数体内 import ledger，要到 Task 4 才能用

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/helpers.py`：把

```python
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
```

替换为

```python
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- 新词快道

QUICK_BASE = {**BASE, "stage": "quick"}
OBJ = {"name": "Grow a Garden 2", "first_public": "2026-09-28", "date_source": "https://example.org/launch"}


def quick_signal_obs(*terms):
    items = [{"source": "autocomplete", "object": OBJ["name"], "term": t,
              "url": "https://suggestqueries.google.com/complete/search?q=grow", "seen_at": "2026-10-13"}
             for t in (terms or ("grow a garden 2 calculator",))]
    return {**QUICK_BASE, "slug": None, "kind": "quick_signal", "readings": {"items": items}}


def quick_screen_obs(slug, term="grow a garden 2 calculator", fail=None, aio=False, occupied_by=None, preflight=True):
    """六条默认全过;fail={"Q5": False} 让指定项不过。"""
    checks = {k: {"pass": True, "basis": f"{k} 依据"} for k in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")}
    for k, v in (fail or {}).items():
        checks[k] = {"pass": v, "basis": f"{k} 读数"}
    obs = {**QUICK_BASE, "slug": slug, "kind": "quick_screen",
           "readings": {"term": term, "checks": checks,
                        "ai_overview": {"present": aio, "completes_task": False, "cited_domains": []},
                        "top10": [{"pos": 1, "domain": "reddit.com", "type": "forum", "completes_task": False}],
                        "occupied_by": occupied_by}}
    if preflight:
        obs["browser_preflight"] = dict(PREFLIGHT)
    return obs


def rising_series():
    return list(range(20, 50))          # 30 个点,最近 7 天均值 46 ≥ 前 7 天 39 × 0.8,峰值 49 无回落


def quick_volume_obs(slug, anchor_volume=60000, new_mean=50.0, anchor_mean=60.0, series=None, measured="2026-10-08"):
    """默认 60000 × 50/60 = 50000 月搜索量 → 基准 1 万访问(恰好过线)。"""
    ratio = new_mean / anchor_mean
    return {**QUICK_BASE, "slug": slug, "kind": "quick_volume",
            "source_urls": ["https://trends.google.com/trends/explore?geo=US&q=grow"],
            "readings": {"anchor_term": "anchor term", "anchor_volume": anchor_volume, "anchor_source": "lexicon",
                         "anchor_measured_at": measured, "window_days": 7,
                         "new_mean_7d": new_mean, "anchor_mean_7d": anchor_mean,
                         "new_mean_30d": new_mean, "anchor_mean_30d": anchor_mean,
                         "ratio_7d": round(ratio, 4), "estimate_7d": round(anchor_volume * ratio),
                         "estimate_30d": round(anchor_volume * ratio),
                         "series_30d": series if series is not None else rising_series()}}


def quick_brief_obs(slug, build_days=2, data_available=True):
    return {**QUICK_BASE, "slug": slug, "kind": "quick_brief",
            "readings": {"positioning": "输入作物与天气,算出售价",
                         "pages": [{"path": "/", "target_query": "grow a garden 2 calculator",
                                    "deliverable": "按作物与突变算价格"}],
                         "data_sources": ["社区 wiki 价格表"], "license": "事实数据,自行整理",
                         "update_frequency": "随游戏更新", "build_days": build_days,
                         "data_available": data_available, "hosting": "Cloudflare Pages 免费版",
                         "risks": ["游戏热度可能回落"]}}


def setup_quick(root, slug="gag2-calculator", volume=None, brief=True, screen=None):
    """快道方向:速判全过 → 登记 → 量级(默认恰好过线)与简报素材。返回 (slug, 引用列表)。"""
    import ledger
    import write_observation as W
    term = f"{slug} term"
    screen_ref = W.write(root, screen or quick_screen_obs(slug, term=term))
    ledger.register_quick(root, slug, "新游戏计算器", "tool", dict(OBJ),
                          [{"term": term, "source": "autocomplete", "first_seen": "2026-10-13"}], screen_ref, "速判全过")
    refs = [W.write(root, volume or quick_volume_obs(slug))]
    if brief:
        refs.append(W.write(root, quick_brief_obs(slug)))
    ledger.update(root, slug, {}, refs)
    return slug, [screen_ref] + refs
```

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_observation.py`（新建）：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import init_workspace
import write_observation as W
from _common import QUICK_POOL_REL, QUICK_REJECTS_REL, SUGGEST_DIR_REL, BenchError, load_json
from helpers import (TmpRoot, quick_brief_obs, quick_screen_obs, quick_signal_obs, quick_volume_obs)


class QuickObservationTest(unittest.TestCase):
    def test_round_trip_and_folders(self):
        with TmpRoot() as root:
            sig = W.write(root, quick_signal_obs())
            self.assertTrue(sig.startswith("证据/_quick/") and sig.endswith("-quick_signal.json"))
            for obs in (quick_screen_obs("q"), quick_volume_obs("q"), quick_brief_obs("q")):
                self.assertTrue(W.write(root, obs).startswith("证据/q/"))

    def test_ratio_out_of_range_rejected(self):
        with self.assertRaisesRegex(BenchError, "0.2–5"):
            W.validate(quick_volume_obs("q", anchor_volume=74000, new_mean=5.0, anchor_mean=72.0))

    def test_estimate_must_match(self):
        obs = quick_volume_obs("q")
        obs["readings"]["estimate_7d"] = 90000
        with self.assertRaisesRegex(BenchError, "estimate_7d"):
            W.validate(obs)

    def test_serp_conclusion_needs_preflight(self):
        with self.assertRaisesRegex(BenchError, "preflight"):
            W.validate(quick_screen_obs("q", preflight=False))
        early = quick_screen_obs("q", fail={"Q1": False, "Q5": None, "Q6": None}, preflight=False)
        W.validate(early)                      # Q1 已不过,没看首页,不需要预检

    def test_occupied_needs_domain(self):
        with self.assertRaisesRegex(BenchError, "occupied_by"):
            W.validate(quick_screen_obs("q", fail={"Q5": False}))
        W.validate(quick_screen_obs("q", fail={"Q5": False}, occupied_by="small-tool.com"))

    def test_stage_must_be_quick(self):
        obs = quick_brief_obs("q")
        obs["stage"] = "assess"
        with self.assertRaisesRegex(BenchError, "stage"):
            W.validate(obs)

    def test_trends_less_than_one_marker_refused(self):
        obs = quick_volume_obs("q", series=["<1"] * 5 + list(range(20, 45)))
        with self.assertRaisesRegex(BenchError, "非负数"):
            W.validate(obs)

    def test_signal_source_checked(self):
        obs = quick_signal_obs()
        obs["readings"]["items"][0]["source"] = "twitter"
        with self.assertRaisesRegex(BenchError, "来源"):
            W.validate(obs)



class QuickWorkspaceTest(unittest.TestCase):
    def test_init_creates_quick_area(self):
        with TmpRoot() as root:
            self.assertTrue((root / "证据" / "_quick").is_dir())
            self.assertTrue((root / SUGGEST_DIR_REL).is_dir())
            self.assertEqual(load_json(root / QUICK_REJECTS_REL), {"schema_version": 1, "terms": {}})
            self.assertEqual((root / QUICK_POOL_REL).read_text(encoding="utf-8"), "")
            self.assertEqual(init_workspace.init_workspace(root), [])


if __name__ == "__main__":
    unittest.main()
```


- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `FAILED (errors=1)`，首个报错 `ImportError: cannot import name 'QUICK_POOL_REL' from '_common'`（write_observation 还不认识快道四类观察，数据区也没有快道目录）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/_common.py`：把

```python
LEXICON_REL = "词库/旧词库.json"
VERDICTS_REL = "词库/旧裁决.json"

SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
```

替换为

```python
LEXICON_REL = "词库/旧词库.json"
VERDICTS_REL = "词库/旧裁决.json"
QUICK_POOL_REL = "快道/原料.jsonl"
QUICK_REJECTS_REL = "快道/淘汰.json"
SUGGEST_DIR_REL = "快道/补全快照"

SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
```

`xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py`：把

```python

import data_root
from _common import (LEDGER_REL, MANUAL_SEEDS_REL, REJECTS_REL, SEEDS_REL,
                     atomic_save)

SUBDIRS = ("账本", "种子", "淘汰索引", "词库", "证据/_scan", "文档/历史", "运行", "反馈")
EMPTY_FILES = {
    LEDGER_REL: {"schema_version": 1, "directions": {}},
```

替换为

```python

import data_root
from _common import (LEDGER_REL, MANUAL_SEEDS_REL, QUICK_POOL_REL, QUICK_REJECTS_REL, REJECTS_REL,
                     SEEDS_REL, SUGGEST_DIR_REL, atomic_save)

SUBDIRS = ("账本", "种子", "淘汰索引", "词库", "证据/_scan", "证据/_quick", "文档/历史", "运行", "反馈",
           SUGGEST_DIR_REL)
EMPTY_FILES = {
    LEDGER_REL: {"schema_version": 1, "directions": {}},
```

`xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py`：把

```python
    MANUAL_SEEDS_REL: {"schema_version": 1, "seeds": []},
    REJECTS_REL: {"schema_version": 1, "domains": {}},
}

```

替换为

```python
    MANUAL_SEEDS_REL: {"schema_version": 1, "seeds": []},
    REJECTS_REL: {"schema_version": 1, "domains": {}},
    QUICK_REJECTS_REL: {"schema_version": 1, "terms": {}},
}

```

`xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py`：把

```python
            atomic_save(p, empty)
            created.append(str(p))
    return created

```

替换为

```python
            atomic_save(p, empty)
            created.append(str(p))
    pool = root / QUICK_POOL_REL          # 原料池是 jsonl,空文件即可
    if not pool.is_file():
        pool.parent.mkdir(parents=True, exist_ok=True)
        pool.write_text("", encoding="utf-8")
        created.append(str(pool))
    return created

```

`xinci-bench-workflow/xinci-bench-core/scripts/write_observation.py`（整份替换）：

```python
#!/usr/bin/env python3
"""观察只追加:按 kind 校验必填读数,文件名带时间与随机后缀,永不覆盖旧文件。"""
import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

import data_root
import quick_model as QM
from _common import SLUG_RE, BenchError, load_json, require, stamp

QUICK_KINDS = ("quick_signal", "quick_screen", "quick_volume", "quick_brief")
KINDS = ("scan", "benchmark", "demand", "serp", "differentiation", "delivery", "brief") + QUICK_KINDS
CHECKS = ("B1", "B2", "B3", "B4", "B5")
QUICK_CHECKS = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")
QUICK_SOURCES = ("autocomplete", "trends_rising", "trends_rss", "steamcharts", "apple", "itunes",
                 "google_play", "producthunt", "github", "hackernews", "youtube", "wikipedia",
                 "policy", "reddit", "other")
# 初核数值门槛(选站契约 §3.2);标"通过"但数字不达标的观察直接拒收
LIMITS = {"max_age_months": 24, "max_authority_score": 30, "min_us_organic": 5000}
# 每个 kind 的 readings 必填键;值的类型在 _check_<kind> 里再细查
REQUIRED = {
    "scan": ("domains",),
    "benchmark": ("domain", "traffic_start", "us_organic_now", "us_organic_m12", "curve",
                  "referring_domains", "anchor_summary", "link_driven", "algo_risk",
                  "update_readings", "ads_txt", "pricing"),
    "demand": ("clusters", "competitor_traffic", "crowding", "new_sites"),
    "serp": ("query", "cluster_id", "answered", "answered_basis", "ai_overview",
             "benchmark_position", "top10"),
    "differentiation": ("copy_only", "gaps"),
    "delivery": ("data_sources", "license", "hours", "cash_first_year", "monthly_hours",
                 "feasible", "basis"),
    "brief": ("positioning", "pages", "tech_hosting", "monetization_plan", "seo_notes",
              "geo_notes", "risks"),
    "quick_signal": ("items",),
    "quick_screen": ("term", "checks", "ai_overview", "top10", "occupied_by"),
    "quick_volume": ("anchor_term", "anchor_volume", "anchor_source", "anchor_measured_at", "window_days",
                     "new_mean_7d", "anchor_mean_7d", "new_mean_30d", "anchor_mean_30d", "ratio_7d",
                     "estimate_7d", "estimate_30d", "series_30d"),
    "quick_brief": ("positioning", "pages", "data_sources", "license", "update_frequency", "build_days",
                    "data_available", "hosting", "risks"),
}
_YM = re.compile(r"\d{4}-\d{2}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso(ts):
    try:
        datetime.fromisoformat(ts)
        return True
    except (TypeError, ValueError):
        return False


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


def _check_scan(r, observed_at):
    require(isinstance(r["domains"], list) and r["domains"], "scan.domains 须为非空列表")
    for d in r["domains"]:
        require(isinstance(d.get("domain"), str) and d["domain"], "scan.domains[].domain 缺失")
        checks = d.get("checks") or {}
        require(set(checks) == set(CHECKS), f"{d['domain']}: checks 须恰好含 B1–B5")
        verdicts = []
        for k in CHECKS:
            c = checks[k]
            require(c.get("pass") in (True, False, None), f"{d['domain']}.{k}.pass 须为 true/false/null")
            require(isinstance(c.get("basis"), str) and c["basis"].strip(), f"{d['domain']}.{k}.basis 缺失")
            verdicts.append(c["pass"])
        # null 只表示"前面已不过、为省额度没查",全过时不允许有 null
        require(False in verdicts or None not in verdicts, f"{d['domain']}: 没有不过项时 B1–B5 不能留 null")
        _check_limits(d, observed_at)


def _months_between(earlier, later):
    a, b = date.fromisoformat(earlier[:10]), date.fromisoformat(later[:10])
    return (b.year - a.year) * 12 + b.month - a.month - (b.day < a.day)


def _check_limits(d, observed_at):
    c, name = d["checks"], d["domain"]
    if c["B1"]["pass"] is True and not d.get("aged_domain"):
        reg = d.get("registered_at")
        require(isinstance(reg, str) and _DATE.fullmatch(reg[:10]),
                f"{name}: B1 判通过须有 registered_at,或标 aged_domain=true 并在 basis 写 24 个月前流量≈0 的依据")
        require(_months_between(reg, observed_at) <= LIMITS["max_age_months"],
                f"{name}: 注册已超过 {LIMITS['max_age_months']} 个月,B1 不能判通过")
    if c["B2"]["pass"] is True:
        a = d.get("authority_score")
        require(_num(a) and a <= LIMITS["max_authority_score"], f"{name}: AS 须 ≤ {LIMITS['max_authority_score']} 才能判 B2 通过")
    if c["B3"]["pass"] is True:
        t = d.get("us_organic_now")
        require(_num(t) and t >= LIMITS["min_us_organic"],
                f"{name}: 去品牌词与定位词后的美区自然流量须 ≥ {LIMITS['min_us_organic']} 才能判 B3 通过")


def _check_benchmark(r):
    require(isinstance(r["domain"], str) and r["domain"], "benchmark.domain 缺失")
    require(r["traffic_start"] is None or _YM.fullmatch(str(r["traffic_start"])), "traffic_start 须为 YYYY-MM 或 null")
    require(_num(r["us_organic_now"]), "us_organic_now 须为非负数")
    require(r["us_organic_m12"] is None or _num(r["us_organic_m12"]), "us_organic_m12 须为非负数或 null")
    curve = r["curve"]
    require(isinstance(curve, dict) and set(curve) == {"3", "6", "12"}, "curve 须恰好含键 3/6/12")
    require(all(v is None or _num(v) for v in curve.values()), "curve 值须为非负数或 null")
    require(r["referring_domains"] is None or _num(r["referring_domains"]), "referring_domains 须为非负数或 null")
    for k in ("link_driven", "algo_risk"):
        require(isinstance(r[k], bool), f"{k} 须为布尔")
    for k in ("anchor_summary", "update_readings", "ads_txt"):
        require(isinstance(r[k], str) and r[k].strip(), f"{k} 须为非空文字")


def _check_demand(r):
    require(isinstance(r["clusters"], list) and r["clusters"], "demand.clusters 须为非空列表")
    for c in r["clusters"]:
        require(isinstance(c.get("id"), str) and SLUG_RE.fullmatch(c["id"]), "cluster.id 无效")
        require(isinstance(c.get("seed_term"), str) and c["seed_term"].strip(), f"{c['id']}: seed_term 缺失")
        require(_num(c.get("volume")), f"{c['id']}: volume 须为非负数")
        require(_DATE.fullmatch(str(c.get("measured_at"))), f"{c['id']}: measured_at 须为 YYYY-MM-DD")
        require(c.get("coverage") in ("benchmark", "ours"), f"{c['id']}: coverage 须为 benchmark/ours")
        require(isinstance(c.get("near_me"), bool), f"{c['id']}: near_me 须为布尔")
    require(isinstance(r["competitor_traffic"], list), "competitor_traffic 须为列表")
    for t in r["competitor_traffic"]:
        require(isinstance(t, dict) and isinstance(t.get("domain"), str) and _num(t.get("traffic"))
                and isinstance(t.get("basis"), str) and t["basis"].strip(),
                "competitor_traffic[] 须含 domain、traffic(非负数)、basis(按网址筛选的依据)")
    require(isinstance(r["crowding"], int) and r["crowding"] >= 1, "crowding 须为 ≥1 的整数(含标杆本身)")
    require(isinstance(r["new_sites"], list), "new_sites 须为列表")


def _check_serp(r):
    require(isinstance(r["query"], str) and r["query"].strip(), "serp.query 缺失")
    require(isinstance(r["cluster_id"], str) and r["cluster_id"], "serp.cluster_id 缺失")
    require(isinstance(r["answered"], bool), "serp.answered 须为布尔")
    require(isinstance(r["answered_basis"], str) and r["answered_basis"].strip(), "answered_basis 缺失")
    aio = r["ai_overview"]
    require(isinstance(aio, dict) and {"present", "completes_task", "cited_domains", "recommends_tools"} <= set(aio),
            "ai_overview 须含 present/completes_task/cited_domains/recommends_tools")
    require(r["benchmark_position"] is None or (isinstance(r["benchmark_position"], int) and r["benchmark_position"] >= 1),
            "benchmark_position 须为 ≥1 的整数或 null")
    require(isinstance(r["top10"], list), "top10 须为列表")


def _check_differentiation(r):
    require(isinstance(r["copy_only"], bool), "copy_only 须为布尔")
    require(isinstance(r["gaps"], list), "gaps 须为列表")
    if r["copy_only"]:
        return
    require(r["gaps"], "copy_only=false 时 gaps 不能为空")
    for g in r["gaps"]:
        for k in ("benchmark_now", "ours", "evidence"):
            require(isinstance(g.get(k), str) and g[k].strip(), f"gap.{k} 缺失")


def _check_delivery(r):
    require(isinstance(r["data_sources"], list), "data_sources 须为列表")
    require(isinstance(r["license"], str) and r["license"].strip(), "license 缺失")
    h = r["hours"]
    require(isinstance(h, dict) and set(h) == {"dev", "data", "content"} and all(_num(v) for v in h.values()),
            "hours 须恰好含 dev/data/content 三个非负数")
    require(_num(r["cash_first_year"]) and _num(r["monthly_hours"]), "cash_first_year/monthly_hours 须为非负数")
    require(isinstance(r["feasible"], bool), "feasible 须为布尔")
    require(isinstance(r["basis"], str) and r["basis"].strip(), "basis 缺失")


def _check_brief(r):
    require(isinstance(r["positioning"], str) and r["positioning"].strip(), "positioning 缺失")
    require(isinstance(r["pages"], list) and r["pages"], "pages 须为非空列表")
    for p in r["pages"]:
        for k in ("path", "target_query", "page_type", "deliverable"):
            require(isinstance(p.get(k), str) and p[k].strip(), f"page.{k} 缺失")
        require(_num(p.get("volume")), "page.volume 须为非负数")
    for k in ("tech_hosting", "monetization_plan"):
        require(isinstance(r[k], str) and r[k].strip(), f"{k} 缺失")
    for k in ("seo_notes", "geo_notes", "risks"):
        require(isinstance(r[k], list), f"{k} 须为列表")


def _check_null_rule(checks, keys, label):
    """pass 为 true/false/null;null 只表示"前项已不过、为省额度没查"。"""
    require(isinstance(checks, dict) and set(checks) == set(keys), f"{label}: checks 须恰好含 {keys}")
    verdicts = []
    for k in keys:
        c = checks[k]
        require(isinstance(c, dict) and c.get("pass") in (True, False, None), f"{label}.{k}.pass 须为 true/false/null")
        require(isinstance(c.get("basis"), str) and c["basis"].strip(), f"{label}.{k}.basis 缺失")
        verdicts.append(c["pass"])
    require(False in verdicts or None not in verdicts, f"{label}: 没有不过项时不能留 null")


def _check_quick_signal(r):
    require(isinstance(r["items"], list) and r["items"], "quick_signal.items 须为非空列表")
    for it in r["items"]:
        require(it.get("source") in QUICK_SOURCES, f"原料来源须为 {QUICK_SOURCES}")
        require(isinstance(it.get("object"), str) and it["object"].strip(), "原料 object 缺失")
        require(it.get("term") is None or (isinstance(it["term"], str) and it["term"].strip()), "原料 term 须为文字或 null")
        require(isinstance(it.get("url"), str) and it["url"].strip(), "原料 url 缺失(写实际取回的网址)")
        require(_DATE.fullmatch(str(it.get("seen_at"))), "原料 seen_at 须为 YYYY-MM-DD")


def _check_quick_screen(r):
    require(isinstance(r["term"], str) and r["term"].strip(), "quick_screen.term 缺失")
    _check_null_rule(r["checks"], QUICK_CHECKS, r["term"])
    aio = r["ai_overview"]
    require(isinstance(aio, dict) and {"present", "completes_task", "cited_domains"} <= set(aio),
            "ai_overview 须含 present/completes_task/cited_domains")
    require(isinstance(r["top10"], list), "top10 须为列表")
    if r["checks"]["Q5"]["pass"] is False:
        require(isinstance(r["occupied_by"], str) and r["occupied_by"].strip(), "Q5 不过时 occupied_by 须写完整做了任务的页面域名")


def _check_quick_volume(r):
    require(isinstance(r["anchor_term"], str) and r["anchor_term"].strip(), "anchor_term 缺失")
    require(_num(r["anchor_volume"]) and r["anchor_volume"] > 0, "anchor_volume 须为正数")
    require(r["anchor_source"] in ("lexicon", "semrush"), "anchor_source 须为 lexicon/semrush")
    require(_DATE.fullmatch(str(r["anchor_measured_at"])), "anchor_measured_at 须为 YYYY-MM-DD")
    require(r["window_days"] == 7, "window_days 固定为 7(同时报 30 天对照)")
    for k in ("new_mean_7d", "anchor_mean_7d", "new_mean_30d", "anchor_mean_30d", "estimate_7d", "estimate_30d"):
        require(_num(r[k]), f"{k} 须为非负数")
    require(r["anchor_mean_7d"] > 0 and r["anchor_mean_30d"] > 0, "锚词热度为 0,换一个锚词")
    ratio = r["new_mean_7d"] / r["anchor_mean_7d"]
    require(abs(ratio - r["ratio_7d"]) < 0.001, "ratio_7d 须等于 new_mean_7d ÷ anchor_mean_7d")
    require(QM.ratio_ok(ratio), "锚词与新词热度比须在 0.2–5 之间,换一个量级更接近的锚词")
    require(abs(r["estimate_7d"] - r["anchor_volume"] * ratio) <= 1, "estimate_7d 须等于 anchor_volume × ratio_7d(取整)")
    s = r["series_30d"]
    require(isinstance(s, list) and len(s) >= 14 and all(_num(v) for v in s),
            "series_30d 须为至少 14 个非负数(Trends 显示 \"<1\" 的点记 0)")


def _check_quick_brief(r):
    require(isinstance(r["positioning"], str) and r["positioning"].strip(), "positioning 缺失")
    require(isinstance(r["pages"], list) and r["pages"], "pages 须为非空列表")
    for p in r["pages"]:
        for k in ("path", "target_query", "deliverable"):
            require(isinstance(p.get(k), str) and p[k].strip(), f"page.{k} 缺失")
    for k in ("license", "update_frequency", "hosting"):
        require(isinstance(r[k], str) and r[k].strip(), f"{k} 缺失")
    require(isinstance(r["data_sources"], list) and isinstance(r["risks"], list), "data_sources/risks 须为列表")
    require(_num(r["build_days"]), "build_days 须为非负数")
    require(isinstance(r["data_available"], bool), "data_available 须为布尔")


def _expected_stage(kind):
    return "scan" if kind == "scan" else ("quick" if kind in QUICK_KINDS else "assess")


def _preflight_ok(pf):
    pf = pf or {}
    return (all(pf.get(k) is True for k in ("controllable", "desktop", "logged_out")) and pf.get("region") == "us"
            and isinstance(pf.get("evidence"), str) and bool(pf["evidence"].strip()))


def validate(obs: dict) -> None:
    kind, stage = obs.get("kind"), obs.get("stage")
    require(kind in KINDS, f"kind 须为 {KINDS}")
    require(stage == _expected_stage(kind), "kind=scan 时 stage=scan;快道四类 stage=quick;其余 stage=assess")
    if kind in ("scan", "quick_signal"):
        require(obs.get("slug") is None, f"{kind} 批次观察 slug 须为 null")
    else:
        require(isinstance(obs.get("slug"), str) and SLUG_RE.fullmatch(obs["slug"]), "slug 无效")
    require(isinstance(obs.get("observed_at"), str) and _iso(obs["observed_at"]),
            "observed_at 须为 ISO 时间;写观察前先取系统时间,不要估")
    urls = obs.get("source_urls")
    require(isinstance(urls, list) and urls and all(isinstance(u, str) and u for u in urls), "source_urls 须为非空列表")
    require(isinstance(obs.get("semrush_calls"), int) and obs["semrush_calls"] >= 0, "semrush_calls 须为非负整数")
    require(isinstance(obs.get("points"), list), "points 须为列表")
    if kind == "serp":
        require(_preflight_ok(obs.get("browser_preflight")),
                "serp 观察须有通过的 browser_preflight(可控、桌面、美区、未登录、依据)")
    r = obs.get("readings")
    require(isinstance(r, dict), "readings 须为对象")
    missing = [k for k in REQUIRED[kind] if k not in r]
    require(not missing, f"{kind}.readings 缺字段: {missing}")
    if kind == "scan":
        _check_scan(r, obs["observed_at"])
    else:
        globals()[f"_check_{kind}"](r)
    if kind == "quick_screen" and (r["checks"]["Q5"]["pass"] is not None or r["checks"]["Q6"]["pass"] is not None):
        require(_preflight_ok(obs.get("browser_preflight")), "Q5/Q6 有结论时须有通过的 browser_preflight")


def write(root, obs: dict) -> str:
    validate(obs)
    folder = {"scan": "_scan", "quick_signal": "_quick"}.get(obs["kind"], obs["slug"])
    ref = f"证据/{folder}/{stamp()}-{uuid.uuid4().hex[:8]}-{obs['kind']}.json"
    path = Path(root) / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(obs, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return ref


def read(root, ref: str) -> dict:
    """读回并重新校验;路径必须在 证据/ 下。"""
    require(ref.startswith("证据/") and ".." not in ref, f"观察路径须在 证据/ 下: {ref}")
    p = Path(root) / ref
    require(p.is_file(), f"观察不存在: {ref}")
    obs = load_json(p)
    validate(obs)
    return obs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--input", required=True, help="观察 JSON 文件")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        print(write(root, json.loads(Path(a.input).read_text(encoding="utf-8"))))
    except (BenchError, OSError, ValueError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`xinci-bench-workflow/xinci-bench-core/数据结构/observation.schema.json`（整份替换）：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "xinci-bench 观察文件",
  "description": "说明性 schema;强制校验在 write_observation.py。kind=scan 时 stage=scan、slug=null;快道四类 stage=quick(quick_signal 的 slug=null);其余 stage=assess。",
  "type": "object",
  "required": ["slug", "observed_at", "stage", "kind", "source_urls", "semrush_calls", "points", "readings"],
  "properties": {
    "slug": {"type": ["string", "null"]},
    "observed_at": {"type": "string", "description": "ISO 时间,写之前先取系统时间"},
    "stage": {"enum": ["scan", "assess", "quick"]},
    "kind": {"enum": ["scan", "benchmark", "demand", "serp", "differentiation", "delivery", "brief", "quick_signal", "quick_screen", "quick_volume", "quick_brief"]},
    "source_urls": {"type": "array", "minItems": 1, "items": {"type": "string"}},
    "semrush_calls": {"type": "integer", "minimum": 0},
    "points": {"type": "array", "items": {"type": "string"}},
    "browser_preflight": {"description": "kind=serp 时必填;quick_screen 的 Q5/Q6 有结论时必填;四项须通过", "required": ["controllable", "desktop", "region", "logged_out", "evidence"]},
    "readings": {"type": "object"}
  },
  "readings_required": {
    "scan": ["domains"],
    "benchmark": ["domain", "traffic_start", "us_organic_now", "us_organic_m12", "curve", "referring_domains", "anchor_summary", "link_driven", "algo_risk", "update_readings", "ads_txt", "pricing"],
    "demand": ["clusters", "competitor_traffic", "crowding", "new_sites"],
    "serp": ["query", "cluster_id", "answered", "answered_basis", "ai_overview", "benchmark_position", "top10"],
    "differentiation": ["copy_only", "gaps"],
    "delivery": ["data_sources", "license", "hours", "cash_first_year", "monthly_hours", "feasible", "basis"],
    "brief": ["positioning", "pages", "tech_hosting", "monetization_plan", "seo_notes", "geo_notes", "risks"],
    "quick_signal": ["items"],
    "quick_screen": ["term", "checks", "ai_overview", "top10", "occupied_by"],
    "quick_volume": ["anchor_term", "anchor_volume", "anchor_source", "anchor_measured_at", "window_days", "new_mean_7d", "anchor_mean_7d", "new_mean_30d", "anchor_mean_30d", "ratio_7d", "estimate_7d", "estimate_30d", "series_30d"],
    "quick_brief": ["positioning", "pages", "data_sources", "license", "update_frequency", "build_days", "data_available", "hosting", "risks"]
  }
}
```


- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 111 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/helpers.py" "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_observation.py" "xinci-bench-workflow/xinci-bench-core/scripts/_common.py" "xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py" "xinci-bench-workflow/xinci-bench-core/scripts/write_observation.py" "xinci-bench-workflow/xinci-bench-core/数据结构/observation.schema.json"
git commit -m "xinci-bench 快道:四类观察的校验与数据区快道目录" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 原料池与自动补全快照

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/quick_pool.py`
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/suggest_snapshot.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pool.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_suggest_snapshot.py`

**Interfaces:**
- Consumes: `_common.QUICK_POOL_REL/QUICK_REJECTS_REL/SUGGEST_DIR_REL/LEDGER_REL/VERDICTS_REL`（Task 2）、`quick_model.QUICK_ASSUMPTIONS/TASK_WORDS`（Task 1）、`seeds.add/normalize_domain`（已存在）
- Produces: `quick_pool.STATUSES=('pending','used','expired')`、`QUICK_GATES=('scope','not_new','oneoff','occupied','answered','volume')`、`normalize_term(text)->str`（小写、压空格）、`add_items(root, items, observation)->{added, skipped}`（与原料池、快道淘汰、已有方向的 terms、旧裁决主词去重；只有对象时按对象名去重）、`pending(root)->list`、`mark(root, ids, status)`、`expire(root, on=None)->list[id]`（超过 7 天）、`reject_term(root, term, gate, observation, on=None, seed_domain=None)->dict`（`seed_domain` 只在 occupied 时可用，顺带 `seeds.add(..., 'serp', ...)`）；`suggest_snapshot.ENDPOINT`、`fetch(query)->list`、`snapshot_path(root, query)->Path`、`snapshot(root, query, fetcher=fetch, at=None)->{query, suggestions, new_suggestions, gap_days, first_time}`（取数失败返回 error、不写快照）、`expand(root, obj, fetcher=fetch, sleeper=time.sleep, interval=1.0, at=None)->list`（对象名 + 空格与 10 个任务词，共 11 次）

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pool.py`（新建）：

```python
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_pool as P
from _common import LEDGER_REL, SEEDS_REL, VERDICTS_REL, BenchError, load_json
from helpers import TmpRoot, write_json

OBS = "证据/_quick/20261013T080000000000Z-abcd1234-quick_signal.json"


def item(term, seen="2026-10-13"):
    return {"source": "autocomplete", "object": "Grow a Garden 2", "term": term,
            "url": "https://suggestqueries.google.com/x", "seen_at": seen}


class QuickPoolTest(unittest.TestCase):
    def test_add_and_dedup(self):
        with TmpRoot() as root:
            out = P.add_items(root, [item("Grow A Garden 2  Calculator"), item("grow a garden 2 calculator")], OBS)
            self.assertEqual(len(out["added"]), 1)
            self.assertEqual(out["skipped"][0]["reason"], "已在原料池")
            self.assertEqual(len(P.pending(root)), 1)

    def test_skip_rejected_existing_and_old_verdicts(self):
        with TmpRoot() as root:
            P.reject_term(root, "old news term", "oneoff", "证据/q/x.json")
            write_json(root / LEDGER_REL, {"schema_version": 1, "directions": {"gag2": {"lane": "quick", "terms": [
                {"term": "gag2 term", "source": "autocomplete", "first_seen": "2026-10-13"}]}}})
            write_json(root / VERDICTS_REL, {"schema_version": 1, "candidates": {
                "tide-chart": {"primary_keyword": "tide chart", "state": "parked", "gate": None, "reason": "x"}}})
            out = P.add_items(root, [item("old news term"), item("gag2 term"), item("tide chart"), item("fresh one")], OBS)
            self.assertEqual([r["term"] for r in out["added"]], ["fresh one"])
            reasons = {s["term"]: s["reason"] for s in out["skipped"]}
            self.assertIn("快道淘汰过", reasons["old news term"])
            self.assertIn("已有方向 gag2", reasons["gag2 term"])
            self.assertIn("旧裁决 tide-chart", reasons["tide chart"])

    def test_object_only_items_dedup_by_object(self):
        with TmpRoot() as root:
            obj = {"source": "steamcharts", "object": "New Game", "term": None,
                   "url": "https://steamcharts.com/top", "seen_at": "2026-10-13"}
            out = P.add_items(root, [obj, dict(obj, object="NEW  game")], OBS)
            self.assertEqual((len(out["added"]), out["skipped"][0]["reason"]), (1, "已在原料池"))

    def test_expire_after_seven_days(self):
        with TmpRoot() as root:
            P.add_items(root, [item("a", seen="2026-10-01"), item("b", seen="2026-10-12")], OBS)
            self.assertEqual(len(P.expire(root, on="2026-10-13")), 1)
            self.assertEqual([r["term"] for r in P.pending(root)], ["b"])

    def test_mark(self):
        with TmpRoot() as root:
            row = P.add_items(root, [item("a")], OBS)["added"][0]
            P.mark(root, [row["id"]], "used")
            self.assertEqual(P.pending(root), [])
            with self.assertRaisesRegex(BenchError, "没有"):
                P.mark(root, ["nope"], "used")

    def test_reject_gate_checked(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "gate"):
                P.reject_term(root, "x", "revenue", "证据/q/x.json")

    def test_occupied_small_site_becomes_bench_seed(self):
        with TmpRoot() as root:
            P.reject_term(root, "gag2 calculator", "occupied", "证据/q/x.json", seed_domain="https://www.GAG2calc.com/")
            seed = load_json(root / SEEDS_REL)["seeds"]["gag2calc.com"]
            self.assertEqual((seed["source"], seed["role"]), ("serp", "benchmark"))
            self.assertIn("gag2 calculator", seed["source_ref"])
            with self.assertRaisesRegex(BenchError, "occupied"):
                P.reject_term(root, "other", "scope", "证据/q/y.json", seed_domain="z.com")

    def test_needs_signal_observation(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "quick_signal"):
                P.add_items(root, [item("a")], "证据/q/x.json")


if __name__ == "__main__":
    unittest.main()
```

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_suggest_snapshot.py`（新建）：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_model as Q
import suggest_snapshot as S
from helpers import TmpRoot


def fake(answers):
    calls = []

    def f(q):
        calls.append(q)
        return answers.pop(0)
    f.calls = calls
    return f


class SuggestSnapshotTest(unittest.TestCase):
    def test_first_snapshot_is_baseline(self):
        with TmpRoot() as root:
            out = S.snapshot(root, "grow a garden 2 ", fake([["a", "b"]]), at="2026-10-13T08:00:00+00:00")
            self.assertEqual((out["first_time"], out["new_suggestions"], out["gap_days"]), (True, [], None))
            self.assertTrue(S.snapshot_path(root, "grow a garden 2 ").is_file())

    def test_new_means_never_seen_before(self):
        with TmpRoot() as root:
            f = fake([["a", "b"], ["b", "c"], ["a", "c", "d"]])
            S.snapshot(root, "q", f, at="2026-10-01T00:00:00+00:00")
            S.snapshot(root, "q", f, at="2026-10-05T00:00:00+00:00")
            out = S.snapshot(root, "q", f, at="2026-10-13T00:00:00+00:00")
            self.assertEqual((out["new_suggestions"], out["gap_days"]), (["d"], 8))   # a 在第一次出现过,不算新

    def test_fetch_failure_writes_nothing(self):
        with TmpRoot() as root:
            def boom(q):
                raise OSError("HTTP 429")
            out = S.snapshot(root, "q", boom)
            self.assertIn("429", out["error"])
            self.assertFalse(S.snapshot_path(root, "q").exists())

    def test_expand_uses_task_words_and_interval(self):
        with TmpRoot() as root:
            f, slept = fake([["x"]] * 11), []
            out = S.expand(root, "Grow a Garden 2", f, sleeper=slept.append, interval=1.0)
            self.assertEqual(len(out), 1 + len(Q.TASK_WORDS))
            self.assertEqual(f.calls[0], "Grow a Garden 2 ")
            self.assertIn("Grow a Garden 2 tier list", f.calls)
            self.assertEqual(slept, [1.0] * len(Q.TASK_WORDS))

    def test_snapshot_path_stable_and_safe(self):
        with TmpRoot() as root:
            a = S.snapshot_path(root, "Grow  A Garden/2 ")
            self.assertEqual(a, S.snapshot_path(root, "grow a garden/2"))
            self.assertNotIn("/2", a.name)


if __name__ == "__main__":
    unittest.main()
```


- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `FAILED (errors=2)`，首个报错 `ModuleNotFoundError: No module named 'quick_pool'`（本任务的两个模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/quick_pool.py`（新建）：

```python
#!/usr/bin/env python3
"""快道原料池与淘汰记录:登记原料(去重)、取待看原料、标记已用或过期、记速判不过的词。"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import data_root
import quick_model as QM
import seeds
from _common import (LEDGER_REL, QUICK_POOL_REL, QUICK_REJECTS_REL, VERDICTS_REL, BenchError,
                     atomic_save, load_json, now, require, today)

STATUSES = ("pending", "used", "expired")
QUICK_GATES = ("scope", "not_new", "oneoff", "occupied", "answered", "volume")


def normalize_term(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    require(t, "原料词不能为空")
    return t


def _key(item) -> str:
    return normalize_term(item.get("term") or item["object"])


def _read_pool(root) -> list:
    p = Path(root) / QUICK_POOL_REL
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_pool(root, rows) -> None:
    p = Path(root) / QUICK_POOL_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(p)


def _rejects(root) -> dict:
    p = Path(root) / QUICK_REJECTS_REL
    return load_json(p) if p.is_file() else {"schema_version": 1, "terms": {}}


def _known_terms(root) -> dict:
    """已有快道方向的说法、旧裁决的主词 → 去重来源。"""
    known = {}
    ledger_p = Path(root) / LEDGER_REL
    if ledger_p.is_file():
        for slug, rec in load_json(ledger_p)["directions"].items():
            for t in rec.get("terms") or []:
                known[normalize_term(t["term"])] = f"已有方向 {slug}"
    ver_p = Path(root) / VERDICTS_REL
    if ver_p.is_file():
        for slug, v in load_json(ver_p)["candidates"].items():
            if v.get("primary_keyword"):
                known.setdefault(normalize_term(v["primary_keyword"]), f"旧裁决 {slug}({v.get('state')})")
    return known


def add_items(root, items, observation) -> dict:
    """登记一批原料;已在池里、被快道淘汰过、已有方向或旧裁决的跳过,返回新增与跳过原因。"""
    require(isinstance(observation, str) and observation.startswith("证据/_quick/"), "observation 须为 quick_signal 观察路径")
    rows, rejects, known = _read_pool(root), _rejects(root)["terms"], _known_terms(root)
    seen = {_key(r) for r in rows}
    added, skipped = [], []
    for it in items:
        k = _key(it)
        reason = ("已在原料池" if k in seen else
                  f"快道淘汰过({rejects[k]['gate']})" if k in rejects else known.get(k))
        if reason:
            skipped.append({"term": k, "reason": reason})
            continue
        row = {"id": hashlib.sha1(k.encode("utf-8")).hexdigest()[:12], "source": it["source"],
               "object": it["object"], "term": it.get("term"), "url": it["url"], "seen_at": it["seen_at"],
               "status": "pending", "observation": observation}
        rows.append(row)
        seen.add(k)
        added.append(row)
    _write_pool(root, rows)
    return {"added": added, "skipped": skipped}


def pending(root) -> list:
    return [r for r in _read_pool(root) if r["status"] == "pending"]


def mark(root, ids, status) -> None:
    require(status in STATUSES, f"status 须为 {STATUSES}")
    rows = _read_pool(root)
    want = set(ids)
    found = {r["id"] for r in rows if r["id"] in want}
    require(found == want, f"原料池里没有: {sorted(want - found)}")
    for r in rows:
        if r["id"] in want:
            r["status"] = status
            r["updated_at"] = now()
    _write_pool(root, rows)


def expire(root, on=None) -> list:
    """待看原料超过 7 天(拿不到"有人在搜"的证据)标 expired。"""
    on = date.fromisoformat(on or today())
    rows, gone = _read_pool(root), []
    for r in rows:
        if r["status"] == "pending" and (on - date.fromisoformat(r["seen_at"])).days > QM.QUICK_ASSUMPTIONS["pool_days"]:
            r["status"] = "expired"
            gone.append(r["id"])
    if gone:
        _write_pool(root, rows)
    return gone


def reject_term(root, term, gate, observation, on=None, seed_domain=None) -> dict:
    """速判不过的词进快道淘汰记录,同词不再看;首页被小站做了(occupied)时顺带把它登记为标杆道种子。"""
    require(gate in QUICK_GATES, f"gate 须为 {QUICK_GATES}")
    require(isinstance(observation, str) and observation.startswith("证据/"), "observation 须为速判观察路径")
    require(seed_domain is None or gate == "occupied", "只有 occupied 才能顺带登记标杆种子")
    t = normalize_term(term)
    entry = {"gate": gate, "at": on or today(), "observation": observation}
    if seed_domain:
        entry["seed"] = seeds.normalize_domain(seed_domain)
        entry["seed_added"] = seeds.add(root, seed_domain, "serp", f"快道速判 {t} 首页({observation})")
    data = _rejects(root)
    data["terms"][t] = entry
    atomic_save(Path(root) / QUICK_REJECTS_REL, data)
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("add")
    a1.add_argument("--observation", required=True, help="quick_signal 观察路径,原料取自它的 items")
    sub.add_parser("pending")
    m = sub.add_parser("mark")
    m.add_argument("--id", action="append", required=True)
    m.add_argument("--status", required=True, choices=STATUSES)
    sub.add_parser("expire")
    r = sub.add_parser("reject")
    r.add_argument("--term", required=True)
    r.add_argument("--gate", required=True, choices=QUICK_GATES)
    r.add_argument("--observation", required=True)
    r.add_argument("--seed-domain", help="occupied 且占位的是小站时,登记为标杆道种子(来源 serp)")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "add":
            obs = load_json(Path(root) / a.observation)
            require(obs.get("kind") == "quick_signal", "--observation 须为 quick_signal 观察")
            out = add_items(root, obs["readings"]["items"], a.observation)
        elif a.cmd == "pending":
            out = pending(root)
        elif a.cmd == "mark":
            mark(root, a.id, a.status)
            out = {"marked": a.id, "status": a.status}
        elif a.cmd == "expire":
            out = {"expired": expire(root)}
        else:
            out = reject_term(root, a.term, a.gate, a.observation, seed_domain=a.seed_domain)
    except (BenchError, OSError, ValueError, KeyError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`xinci-bench-workflow/xinci-bench-core/scripts/suggest_snapshot.py`（新建）：

```python
#!/usr/bin/env python3
"""Google 自动补全快照:取建议、按查询存快照、和以前所有快照比,找出从没出现过的建议。

快道里唯一会联网的脚本;取数函数可注入,测试不联网。取数失败不写快照(不能当作"没有新建议")。
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import data_root
import quick_model as QM
from _common import SUGGEST_DIR_REL, BenchError, atomic_save, load_json, now, require

ENDPOINT = "https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=us&q="
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"


def fetch(query: str) -> list:
    req = urllib.request.Request(ENDPOINT + urllib.parse.quote(query), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    require(isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list), "自动补全返回格式不对")
    return [str(s) for s in data[1]]


def snapshot_path(root, query: str) -> Path:
    norm = re.sub(r"\s+", " ", query.strip().lower())
    name = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")[:70] or "q"
    return Path(root) / SUGGEST_DIR_REL / f"{name}-{hashlib.sha1(norm.encode('utf-8')).hexdigest()[:8]}.json"


def snapshot(root, query: str, fetcher=fetch, at=None) -> dict:
    """取一次建议并追加快照;返回全部建议、新冒出的建议、与上一次快照的间隔天数。

    同一查询隔几秒请求两次,返回的建议也会不同(2026-10-13 实测),所以"新"指以前所有快照里都没出现过。
    """
    at = at or now()
    try:
        current = fetcher(query)
    except Exception as exc:          # 网络、限流、格式错误都不写快照
        return {"query": query, "error": f"{type(exc).__name__}: {exc}", "suggestions": [], "new_suggestions": [],
                "gap_days": None, "first_time": None}
    p = snapshot_path(root, query)
    history = load_json(p) if p.is_file() else []
    prev = history[-1] if history else None
    seen = {s for h in history for s in h["suggestions"]}
    new = [s for s in current if s not in seen]
    gap = (date.fromisoformat(at[:10]) - date.fromisoformat(prev["fetched_at"][:10])).days if prev else None
    history.append({"fetched_at": at, "query": query, "suggestions": current})
    atomic_save(p, history)
    return {"query": query, "suggestions": current, "new_suggestions": new if prev else [],
            "gap_days": gap, "first_time": prev is None}


def expand(root, obj: str, fetcher=fetch, sleeper=time.sleep, interval=1.0, at=None) -> list:
    """对象名 + 空格,以及对象名 + 每个任务词;请求之间间隔 interval 秒。"""
    require(isinstance(obj, str) and obj.strip(), "对象名不能为空")
    queries = [obj.strip() + " "] + [f"{obj.strip()} {w}" for w in QM.TASK_WORDS]
    out = []
    for i, q in enumerate(queries):
        if i:
            sleeper(interval)
        out.append(snapshot(root, q, fetcher, at))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--object", help="对象名,按任务词展开")
    g.add_argument("--query", help="单条查询")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        out = expand(root, a.object) if a.object else [snapshot(root, a.query)]
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if all(r.get("error") for r in out) else 0


if __name__ == "__main__":
    raise SystemExit(main())
```


- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 124 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pool.py" "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_suggest_snapshot.py" "xinci-bench-workflow/xinci-bench-core/scripts/quick_pool.py" "xinci-bench-workflow/xinci-bench-core/scripts/suggest_snapshot.py"
git commit -m "xinci-bench 快道:原料池去重与过期、快道淘汰记录、自动补全快照比对" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 快道账本——lane、登记、复查与建站跟进

**Files:**
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/ledger.py`（整份替换）
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_ledger.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py`（看板 counts 断言加 `"watching": 0`）

**Interfaces:**
- Consumes: `quick_model.compute/trend/add_days/QUICK_ASSUMPTIONS`、`quick_pool.normalize_term/QUICK_GATES`、`write_observation.read/QUICK_CHECKS/QUICK_SOURCES/_DATE`
- Produces: `ledger.STATES` 加 `watching`、`LANES=('bench','quick')`、`LEGAL_BY_LANE`（quick：found→go/rejected/parked/watching，watching→go/rejected，parked→go/rejected）、`LEGAL`（=bench，不变）、`GATES`（bench，不变）、`QUICK_GATES`、`GATES_BY_LANE`、`QUICK_GATE_CHECK={'not_new':'Q1','oneoff':'Q3','scope':'Q4','occupied':'Q5','answered':'Q6'}`、`QUICK_PATCHABLE=('title','site_type','terms')`、`FOLLOW_UP_STATUSES=('pending','started','launched','abandoned')`；`register(...)` 记录多写 `lane='bench'`；`update` 按 lane 区分可补字段；`rank` 只排标杆道；`precheck(root, rec, to, gate, on, scope_hit=None)` 按 lane 分派；`register_quick(root, slug, title, site_type, obj, terms, screen_ref, reason, by='xinci-bench-quick')->dict`；`derive_quick(root, rec)->{volume, serp}`；`watch_check(root, slug, refs=(), on=None)->dict`（只给建议、记一次复查）；`follow_up(root, slug, status, domain=None, on=None, reason=None)->dict`；`transition` 按 lane 查合法转移与否决门。CLI 新增 `register-quick --input`、`quick-preview --slug`、`watch-check --slug [--ref]`、`follow-up --slug --status [--domain] [--date] [--reason]`

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_ledger.py`（新建）：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import write_observation as W
from _common import BenchError
from helpers import OBJ, TmpRoot, quick_screen_obs, setup_direction, setup_quick

ON = "2026-10-20"


def term(slug):
    return [{"term": f"{slug} term", "source": "autocomplete", "first_seen": "2026-10-13"}]


class RegisterQuickTest(unittest.TestCase):
    def test_needs_all_six_pass(self):
        with TmpRoot() as root:
            ref = W.write(root, quick_screen_obs("q", term="q term", fail={"Q5": False}, occupied_by="x.com"))
            with self.assertRaisesRegex(BenchError, "六条"):
                L.register_quick(root, "q", "t", "tool", dict(OBJ), term("q"), ref, "r")

    def test_object_must_be_new(self):
        with TmpRoot() as root:
            ref = W.write(root, quick_screen_obs("q", term="q term"))
            old = dict(OBJ, first_public="2026-06-01")
            with self.assertRaisesRegex(BenchError, "90 天"):
                L.register_quick(root, "q", "t", "tool", old, term("q"), ref, "r")
            future = dict(OBJ, first_public="2026-11-01")
            with self.assertRaisesRegex(BenchError, "未来"):
                L.register_quick(root, "q", "t", "tool", future, term("q"), ref, "r")

    def test_term_cannot_belong_to_two_directions(self):
        with TmpRoot() as root:
            setup_quick(root, slug="a")
            ref = W.write(root, quick_screen_obs("b", term="a term"))
            with self.assertRaisesRegex(BenchError, "已属于方向 a"):
                L.register_quick(root, "b", "t", "tool", dict(OBJ), term("a"), ref, "r")

    def test_term_match_ignores_case_and_spaces(self):
        with TmpRoot() as root:
            setup_quick(root, slug="a")
            ref = W.write(root, quick_screen_obs("b", term="A  Term"))
            loud = [{"term": "A  Term", "source": "autocomplete", "first_seen": "2026-10-13"}]
            with self.assertRaisesRegex(BenchError, "已属于方向 a"):
                L.register_quick(root, "b", "t", "tool", dict(OBJ), loud, ref, "r")

    def test_screen_must_be_about_a_registered_term(self):
        with TmpRoot() as root:
            ref = W.write(root, quick_screen_obs("b", term="something else"))
            with self.assertRaisesRegex(BenchError, "速判的词"):
                L.register_quick(root, "b", "t", "tool", dict(OBJ), term("b"), ref, "r")

    def test_rank_and_update_by_lane(self):
        with TmpRoot() as root:
            setup_direction(root, slug="bench-one")
            slug, _ = setup_quick(root)
            self.assertEqual([r["slug"] for r in L.rank(root, on=ON)], ["bench-one"])
            with self.assertRaisesRegex(BenchError, "不可补"):
                L.update(root, slug, {"benchmarks": []})


if __name__ == "__main__":
    unittest.main()
```

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py`：把

```python
            settle.settle(root, "later", "parked", None, "曲线读不出", "u", on="2026-10-20")
            st = RS.status(root, on="2027-02-01")
            self.assertEqual(st["counts"], {"found": 0, "go": 1, "rejected": 0, "parked": 1})
            self.assertEqual(st["go"][0]["base_total"], 160.0)
            self.assertTrue(st["parked"][0]["overdue"])
```

替换为

```python
            settle.settle(root, "later", "parked", None, "曲线读不出", "u", on="2026-10-20")
            st = RS.status(root, on="2027-02-01")
            self.assertEqual(st["counts"], {"found": 0, "go": 1, "rejected": 0, "parked": 1, "watching": 0})
            self.assertEqual(st["go"][0]["base_total"], 160.0)
            self.assertTrue(st["parked"][0]["overdue"])
```


- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `FAILED (failures=1, errors=6)`，首个报错 `AttributeError: module 'ledger' has no attribute 'register_quick'`（ledger 还没有 register_quick，rank 也不分道）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/ledger.py`（整份替换）：

```python
#!/usr/bin/env python3
"""方向账本:两条道(标杆道 bench、新词快道 quick)的登记、补数、排序、转移前的最小证据复核。

账本只由本脚本写;状态只经 settle.py 转移。快道比标杆道多一个 watching(观察中)状态。
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import bench_model
import data_root
import quick_model as QM
import quick_pool
import write_observation as W
from _common import SLUG_RE, BenchError, load_json, load_ledger, now, require, save_ledger, sha256_file, today

STATES = ("found", "go", "rejected", "parked", "watching")
LANES = ("bench", "quick")
LEGAL_BY_LANE = {
    "bench": {"found": {"go", "rejected", "parked"}, "parked": {"go", "rejected"}},
    "quick": {"found": {"go", "rejected", "parked", "watching"}, "watching": {"go", "rejected"},
              "parked": {"go", "rejected"}},
}
LEGAL = LEGAL_BY_LANE["bench"]
GATES = ("scope", "benchmark", "answered", "revenue")
QUICK_GATES = quick_pool.QUICK_GATES
GATES_BY_LANE = {"bench": GATES, "quick": QUICK_GATES}
# 快道否决门 → 速判观察里必须不过的那一条
QUICK_GATE_CHECK = {"not_new": "Q1", "oneoff": "Q3", "scope": "Q4", "occupied": "Q5", "answered": "Q6"}
QUICK_PATCHABLE = ("title", "site_type", "terms")
FOLLOW_UP_STATUSES = ("pending", "started", "launched", "abandoned")
SITE_TYPES = ("tool", "content", "game", "mixed")
SCOPE_ITEMS = ("ymyl", "brand_nav", "news", "adult_gambling", "infringement")
BENCH_KEYS = ("domain", "registered_at", "aged_domain", "traffic_start", "authority_score",
              "us_organic_now", "us_organic_m12", "covered_demand", "link_driven", "algo_risk",
              "monetization", "clean")
CLUSTER_KEYS = ("id", "seed_term", "volume", "measured_at", "coverage", "near_me", "answered", "counted")
PATCHABLE = ("title", "site_type", "benchmarks", "clusters", "crowding", "paid")
FRESH_DAYS = 90
# 账本里决定收入的字段必须等于绑定观察的读数(结算时核对)
BENCH_OBS_FIELDS = ("traffic_start", "us_organic_now", "us_organic_m12", "link_driven", "algo_risk")
CLUSTER_OBS_FIELDS = ("seed_term", "volume", "measured_at", "coverage", "near_me")


def _observations(root, refs):
    return [(ref, W.read(root, ref)) for ref in refs]


def _scan_domain(root, refs, domain):
    """在引用的 scan 观察里找该域名的初核记录;找不到返回 None。"""
    for _, obs in _observations(root, [r for r in refs if r.startswith("证据/_scan/")]):
        for d in obs["readings"]["domains"]:
            if d["domain"] == domain:
                return d
    return None


def _all_pass(item):
    return item is not None and all(item["checks"][k]["pass"] is True for k in W.CHECKS)


def register(root, slug, title, site_type, domain, scan_ref, reason, by="xinci-bench-scan",
             confirm_distinct=None) -> dict:
    require(isinstance(slug, str) and SLUG_RE.fullmatch(slug), "slug 须为小写字母数字连字符")
    require(isinstance(title, str) and title.strip(), "title 须写方向一句话")
    require(site_type in SITE_TYPES, f"site_type 须为 {SITE_TYPES}")
    require(isinstance(reason, str) and reason.strip(), "reason 不能为空")
    ledger = load_ledger(root)
    require(slug not in ledger["directions"], f"方向已存在: {slug}")
    W.read(root, scan_ref)
    item = _scan_domain(root, [scan_ref], domain)
    require(_all_pass(item), f"{domain} 在 {scan_ref} 里没有 B1–B5 全过的记录,不能登记")
    same = [s for s, r in ledger["directions"].items() if any(b["domain"] == domain for b in r["benchmarks"])]
    require(not same or (confirm_distinct or "").strip(),
            f"标杆 {domain} 已用于方向 {same};确属不同方向请用 --confirm-distinct 写理由")
    rec = {
        "slug": slug, "title": title.strip(), "site_type": site_type, "lane": "bench", "state": "found",
        "benchmarks": [{"domain": domain, "registered_at": item.get("registered_at"),
                        "aged_domain": bool(item.get("aged_domain", False)), "traffic_start": None,
                        "authority_score": item.get("authority_score"),
                        "us_organic_now": item.get("us_organic_now"), "us_organic_m12": None,
                        "covered_demand": None, "link_driven": None, "algo_risk": None,
                        "monetization": [], "clean": None}],
        "clusters": [], "crowding": None,
        "paid": {"applicable": False, "price_month": None, "evidence": None},
        "model": None, "decision": None, "evidence_refs": [scan_ref], "bindings": None,
        "history": [{"at": now(), "from": None, "to": "found", "by": by, "reason": reason.strip(),
                     **({"confirm_distinct": confirm_distinct.strip()} if same else {})}],
    }
    ledger["directions"][slug] = rec
    save_ledger(root, ledger)
    return rec


def _check_benchmarks(root, refs, benchmarks):
    require(isinstance(benchmarks, list) and benchmarks, "benchmarks 须为非空列表")
    for b in benchmarks:
        missing = [k for k in BENCH_KEYS if k not in b]
        require(not missing, f"标杆 {b.get('domain')} 缺字段 {missing}")
        require(b["clean"] in (True, False, None), "clean 须为 true/false/null")
        if b["clean"] is True:
            require(b["link_driven"] is False, f"{b['domain']}: 外链驱动的标杆不能标 clean")
            require(_all_pass(_scan_domain(root, refs, b["domain"])),
                    f"{b['domain']}: 引用的 scan 观察里没有 B1–B5 全过的记录,不能标 clean")


def _check_clusters(clusters):
    require(isinstance(clusters, list), "clusters 须为列表")
    ids = [c.get("id") for c in clusters]
    require(len(ids) == len(set(ids)), "簇 id 重复")
    for c in clusters:
        missing = [k for k in CLUSTER_KEYS if k not in c]
        require(not missing, f"簇 {c.get('id')} 缺字段 {missing}")
        require(c["coverage"] in ("benchmark", "ours"), f"簇 {c['id']}: coverage 须为 benchmark/ours")
        for k in ("near_me", "answered", "counted"):
            require(isinstance(c[k], bool), f"簇 {c['id']}: {k} 须为布尔")


def update(root, slug, patch: dict, refs=()) -> dict:
    """补数:标杆道只对 found/parked,改了输入就清掉旧模型结果;快道只能补标题、站型、说法与引用。"""
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    lane = rec.get("lane", "bench")
    open_states = ("found", "parked") if lane == "bench" else ("found", "parked", "watching")
    require(rec["state"] in open_states, f"{slug} 已是 {rec['state']},不能补数")
    allowed = PATCHABLE if lane == "bench" else QUICK_PATCHABLE
    bad = [k for k in patch if k not in allowed]
    require(not bad, f"不可补的字段: {bad}(可补: {allowed})")
    new_refs = list(rec["evidence_refs"])
    for ref in refs:
        obs = W.read(root, ref)
        require(obs["slug"] in (None, slug), f"{ref} 属于别的方向")
        if ref not in new_refs:
            new_refs.append(ref)
    if "site_type" in patch:
        require(patch["site_type"] in SITE_TYPES, f"site_type 须为 {SITE_TYPES}")
    if "terms" in patch:
        _check_terms(patch["terms"])
    if "benchmarks" in patch:
        _check_benchmarks(root, new_refs, patch["benchmarks"])
    if "clusters" in patch:
        _check_clusters(patch["clusters"])
    if "crowding" in patch:
        require(isinstance(patch["crowding"], int) and patch["crowding"] >= 1, "crowding 须为 ≥1 的整数")
    if "paid" in patch:
        p = patch["paid"]
        require(isinstance(p, dict) and isinstance(p.get("applicable"), bool), "paid.applicable 须为布尔")
        if p["applicable"]:
            require(isinstance(p.get("price_month"), (int, float)) and p["price_month"] > 0
                    and isinstance(p.get("evidence"), str) and p["evidence"].strip(),
                    "付费适用时须有正数 price_month 与有用户的 evidence")
    rec.update(patch)
    rec["evidence_refs"] = new_refs
    if lane == "bench":
        rec["model"] = None
    save_ledger(root, ledger)
    return rec


def _months_since(ym, on):
    y, m = map(int, ym.split("-")[:2])
    d = date.fromisoformat(on)
    return max((d.year - y) * 12 + d.month - m, 1)


def rank(root, on=None) -> list:
    """found 排序:起量速度(流量 ÷ 起量月数)降序,同分 AS 低的在前。只排序不否决。"""
    on = on or today()
    rows = []
    for slug, rec in load_ledger(root)["directions"].items():
        if rec["state"] != "found" or rec.get("lane", "bench") != "bench":
            continue
        best = None
        for b in rec["benchmarks"]:
            if b.get("link_driven") is True or b.get("us_organic_now") is None:
                continue
            start = b.get("traffic_start") or (b.get("registered_at") or "")[:7] or None
            months = _months_since(start, on) if start else 24
            speed = b["us_organic_now"] / months
            if best is None or speed > best[0]:
                best = (speed, b.get("authority_score") if b.get("authority_score") is not None else 99)
        if best:
            rows.append({"slug": slug, "speed": round(best[0], 1), "authority_score": best[1]})
    return sorted(rows, key=lambda r: (-r["speed"], r["authority_score"], r["slug"]))


def doc_paths(root, slug):
    base = Path(root) / "文档"
    return base / f"{slug}.md", base / f"{slug}.html"


def docs_consistent(root, slug) -> bool:
    md, html = doc_paths(root, slug)
    if not (md.is_file() and html.is_file()):
        return False
    return f'content="{sha256_file(md)}"' in html.read_text(encoding="utf-8")


def _latest(obs, kind, key=None, value=None):
    rows = [o for _, o in obs if o["kind"] == kind and (key is None or o["readings"].get(key) == value)]
    return rows[-1] if rows else None


def _check_against_observations(rec, obs):
    """账本里的标杆读数、簇量、拥挤度必须等于最新的对应观察;覆盖需求不能小于"标杆已做"的簇量合计。"""
    floor = sum(c["volume"] for c in rec["clusters"] if c["coverage"] == "benchmark")
    for b in rec["benchmarks"]:
        if b.get("clean") is not True:
            continue
        o = _latest(obs, "benchmark", "domain", b["domain"])
        require(o, f"干净标杆 {b['domain']} 没有 benchmark 观察")
        diff = [k for k in BENCH_OBS_FIELDS if b.get(k) != o["readings"][k]]
        require(not diff, f"标杆 {b['domain']} 的 {diff} 与最新 benchmark 观察不一致")
        require(isinstance(b.get("covered_demand"), (int, float)) and b["covered_demand"] >= floor,
                f"标杆 {b['domain']} 的 covered_demand 小于\"标杆已做\"的簇量合计 {floor}(分母偏小会抬高份额率)")
    d = _latest(obs, "demand")
    require(d, "缺 demand 观察")
    by_id = {c["id"]: c for c in d["readings"]["clusters"]}
    for c in rec["clusters"]:
        oc = by_id.get(c["id"])
        require(oc, f"簇 {c['id']} 不在最新 demand 观察里")
        diff = [k for k in CLUSTER_OBS_FIELDS if c[k] != oc[k]]
        require(not diff, f"簇 {c['id']} 的 {diff} 与最新 demand 观察不一致")
    require(rec.get("crowding") == d["readings"]["crowding"], "crowding 与最新 demand 观察不一致")


def precheck(root, rec, to, gate, on, scope_hit=None):
    """不依赖结算产物的证据复核;settle 在写任何东西之前先跑它,转移时再跑一遍。按道分派。"""
    if rec.get("lane", "bench") == "quick":
        return _precheck_quick(root, rec, to, gate, on, scope_hit)
    return _precheck_bench(root, rec, to, gate, on, scope_hit)


def _precheck_bench(root, rec, to, gate, on, scope_hit=None):
    obs = _observations(root, rec["evidence_refs"])
    kinds = {o["kind"] for _, o in obs}
    if to == "parked":
        return
    if to == "go":
        need = {"benchmark", "demand", "serp", "differentiation", "delivery", "brief"}
        require(need <= kinds, f"go 缺观察: {sorted(need - kinds)}")
        require(_latest(obs, "delivery")["readings"]["feasible"] is True,
                "交付依据不成立(最新 delivery.feasible=false)")
        stale = [c["id"] for c in rec["clusters"] if c["counted"]
                 and (date.fromisoformat(on) - date.fromisoformat(c["measured_at"])).days > FRESH_DAYS]
        require(not stale, f"计入需求的簇测量超过 {FRESH_DAYS} 天: {stale}")
        serps = [o["readings"] for _, o in obs if o["kind"] == "serp"]
        for c in rec["clusters"]:
            if not c["counted"] or c["answered"]:
                continue
            mine = [s for s in serps if s["cluster_id"] == c["id"]]
            require(mine, f"计入需求的簇 {c['id']} 没有 serp 观察")
            require(not any(s["answered"] for s in mine), f"簇 {c['id']} 在 serp 观察里已被首屏答完,不能计入需求")
    if to == "go" or gate == "revenue":
        _check_against_observations(rec, obs)
        require(bench_model.compute(rec)["passes"] is (to == "go"), "模型结论与转移方向不符")
    elif gate == "benchmark":
        require("benchmark" in kinds, "benchmark 否决须有起量手段观察")
    elif gate == "answered":
        require(rec["clusters"] and all(c["answered"] for c in rec["clusters"]),
                "answered 否决要求所有簇都被首屏答完")
        answered_ids = {o["readings"]["cluster_id"] for _, o in obs
                        if o["kind"] == "serp" and o["readings"]["answered"]}
        missing = [c["id"] for c in rec["clusters"] if c["id"] not in answered_ids]
        require(not missing, f"这些簇没有首屏答完的 serp 观察: {missing}")
    elif gate == "scope":
        require(scope_hit in SCOPE_ITEMS, f"scope 否决须写命中项 {SCOPE_ITEMS}")


def _require_evidence(root, rec, to, gate, on):
    dec = rec.get("decision") or {}
    require(dec.get("verdict") == to and dec.get("gate") == gate,
            "账本里的 decision 与本次转移不一致;请用 settle.py 结算")
    require(docs_consistent(root, rec["slug"]), "决策书 md/html 缺失或不一致;请用 settle.py 结算")
    precheck(root, rec, to, gate, on, dec.get("scope_hit"))
    if rec.get("lane", "bench") == "quick":
        if to in ("go", "watching") or gate == "volume":
            derived = derive_quick(root, rec)
            require(rec.get("volume") == derived["volume"] and rec.get("serp") == derived["serp"],
                    "账本里的量级与首屏读数须等于最新观察")
            require(rec.get("model") == QM.compute(rec), "账本里的模型结果与现场重算不一致")
        if to == "go":
            require((rec.get("follow_up") or {}).get("status") == "pending", "快道 go 须初始化建站跟进")
    elif to == "go" or gate == "revenue":
        require(rec.get("model") == bench_model.compute(rec), "账本里的模型结果与现场重算不一致")
    if to == "go":
        require(rec.get("bindings"), "go 须有绑定")


# ---------------------------------------------------------------- 新词快道

_DATE_RE = W._DATE


def _check_terms(terms):
    require(isinstance(terms, list) and terms, "terms 须为非空列表")
    for t in terms:
        require(isinstance(t.get("term"), str) and t["term"].strip(), "terms[].term 缺失")
        require(t.get("source") in W.QUICK_SOURCES, f"terms[].source 须为 {W.QUICK_SOURCES}")
        require(_DATE_RE.fullmatch(str(t.get("first_seen"))), "terms[].first_seen 须为 YYYY-MM-DD")


def _screen_all_pass(obs):
    return all(obs["readings"]["checks"][k]["pass"] is True for k in W.QUICK_CHECKS)


def register_quick(root, slug, title, site_type, obj, terms, screen_ref, reason, by="xinci-bench-quick") -> dict:
    """登记快道方向:须有本方向 Q1–Q6 全过的速判观察;对象首次公开须在 90 天内。"""
    require(isinstance(slug, str) and SLUG_RE.fullmatch(slug), "slug 须为小写字母数字连字符")
    require(isinstance(title, str) and title.strip(), "title 须写方向一句话")
    require(site_type in SITE_TYPES, f"site_type 须为 {SITE_TYPES}")
    require(isinstance(reason, str) and reason.strip(), "reason 不能为空")
    require(isinstance(obj, dict) and isinstance(obj.get("name"), str) and obj["name"].strip()
            and _DATE_RE.fullmatch(str(obj.get("first_public")))
            and isinstance(obj.get("date_source"), str) and obj["date_source"].strip(),
            "object 须含 name、first_public(YYYY-MM-DD)、date_source")
    _check_terms(terms)
    mine = {quick_pool.normalize_term(t["term"]) for t in terms}
    screen = W.read(root, screen_ref)
    require(screen["kind"] == "quick_screen" and screen["slug"] == slug, f"{screen_ref} 不是本方向的速判观察")
    require(quick_pool.normalize_term(screen["readings"]["term"]) in mine,
            f"速判的词 {screen['readings']['term']!r} 不在登记的说法里")
    require(_screen_all_pass(screen), "速判六条没有全过,不登记,应进快道淘汰记录")
    age = (date.fromisoformat(screen["observed_at"][:10]) - date.fromisoformat(obj["first_public"])).days
    require(0 <= age <= QM.QUICK_ASSUMPTIONS["new_days"],
            f"对象首次公开距速判 {age} 天,超出 {QM.QUICK_ASSUMPTIONS['new_days']} 天(或日期在未来)")
    ledger = load_ledger(root)
    require(slug not in ledger["directions"], f"方向已存在: {slug}")
    for other, r in ledger["directions"].items():
        clash = mine & {quick_pool.normalize_term(t["term"]) for t in r.get("terms") or []}
        require(not clash, f"说法 {sorted(clash)} 已属于方向 {other}")
    rec = {
        "slug": slug, "title": title.strip(), "site_type": site_type, "lane": "quick", "state": "found",
        "object": {k: obj[k] for k in ("name", "first_public", "date_source")}, "terms": terms,
        "volume": None, "serp": None, "watch": None, "follow_up": None,
        "model": None, "decision": None, "evidence_refs": [screen_ref], "bindings": None,
        "history": [{"at": now(), "from": None, "to": "found", "by": by, "reason": reason.strip()}],
    }
    ledger["directions"][slug] = rec
    save_ledger(root, ledger)
    return rec


def derive_quick(root, rec) -> dict:
    """从最新的量级观察与速判观察推导 volume、serp;结算时写进账本。"""
    obs = _observations(root, rec["evidence_refs"])
    v, s = _latest(obs, "quick_volume"), _latest(obs, "quick_screen")
    volume = None
    if v:
        r = v["readings"]
        volume = {"estimate_7d": r["estimate_7d"], "estimate_30d": r["estimate_30d"],
                  "anchor_term": r["anchor_term"], "anchor_volume": r["anchor_volume"],
                  "anchor_source": r["anchor_source"], "anchor_measured_at": r["anchor_measured_at"],
                  "ratio_7d": r["ratio_7d"], "trend": QM.trend(r["series_30d"])}
    serp = None
    if s:
        r = s["readings"]
        serp = {"aio_present": bool(r["ai_overview"]["present"]),
                "aio_completes": bool(r["ai_overview"]["completes_task"]), "occupied_by": r["occupied_by"]}
    return {"volume": volume, "serp": serp}


def _quick_model(root, rec):
    return QM.compute(dict(rec, **derive_quick(root, rec)))


def _precheck_quick(root, rec, to, gate, on, scope_hit=None):
    obs = _observations(root, rec["evidence_refs"])
    if to == "parked":
        return
    screen = _latest(obs, "quick_screen")
    require(screen, "缺速判观察 quick_screen")
    checks = screen["readings"]["checks"]
    vol = _latest(obs, "quick_volume")
    if to in ("go", "watching"):
        require(_screen_all_pass(screen), "最新速判观察六条须全过")
        require(vol, "缺量级观察 quick_volume")
        fresh = (date.fromisoformat(on) - date.fromisoformat(vol["readings"]["anchor_measured_at"])).days
        require(fresh <= QM.QUICK_ASSUMPTIONS["anchor_fresh_days"], f"锚词测量已过 {fresh} 天,须在 90 天内")
        model = _quick_model(root, rec)
        trend = QM.trend(vol["readings"]["series_30d"])
        require(not trend["spike_decay"], "曲线冲高回落,应按 oneoff 否决")
        if to == "go":
            brief = _latest(obs, "quick_brief")
            require(brief, "go 缺最小简报素材 quick_brief")
            require(brief["readings"]["data_available"] is True and brief["readings"]["build_days"] <= 3,
                    "最小版本须 3 天内能做出、数据拿得到")
            require(model["passes"], "基准预计不到 1 万访问,不能判 go")
        else:
            require(not model["passes"], "基准已过 1 万,应判 go")
            require(trend["non_declining"], "趋势在降,不能进观察中(应按 volume 否决)")
    elif to == "rejected" and gate not in QUICK_GATES:
        require(False, f"快道否决门须为 {QUICK_GATES}")
    elif gate in QUICK_GATE_CHECK:
        q = QUICK_GATE_CHECK[gate]
        spike = gate == "oneoff" and vol and QM.trend(vol["readings"]["series_30d"])["spike_decay"]
        require(checks[q]["pass"] is False or spike, f"{gate} 否决须有 {q} 不过的速判观察")
        if gate == "scope":
            require(scope_hit in SCOPE_ITEMS, f"scope 否决须写命中项 {SCOPE_ITEMS}")
    elif gate == "volume":
        require(vol, "volume 否决须有量级观察")
        model = _quick_model(root, rec)
        require(not model["passes"], "基准已过 1 万,不能按 volume 否决")
        watch = rec.get("watch") or {}
        expired = bool(watch) and on >= watch["expires_at"]
        declining = not QM.trend(vol["readings"]["series_30d"])["non_declining"]
        require(expired or declining, "volume 否决须观察到期,或趋势在降")


def watch_check(root, slug, refs=(), on=None) -> dict:
    """复查观察中的方向:加入新观察,算一次,记一条复查;只给建议,转移仍走 settle.py。"""
    on = on or today()
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec and rec.get("lane") == "quick" and rec["state"] == "watching", f"{slug} 不是观察中的快道方向")
    for ref in refs:
        obs = W.read(root, ref)
        require(obs["slug"] == slug, f"{ref} 属于别的方向")
        if ref not in rec["evidence_refs"]:
            rec["evidence_refs"].append(ref)
    obs = _observations(root, rec["evidence_refs"])
    screen, vol = _latest(obs, "quick_screen"), _latest(obs, "quick_volume")
    model = _quick_model(root, rec)
    trend = QM.trend(vol["readings"]["series_30d"])
    if screen["readings"]["checks"]["Q5"]["pass"] is False:
        suggestion = "rejected:occupied"
    elif model["passes"]:
        suggestion = "go"
    elif on >= rec["watch"]["expires_at"] or not trend["non_declining"]:
        suggestion = "rejected:volume"
    else:
        suggestion = "watching"
    check = {"at": on, "estimate_7d": vol["readings"]["estimate_7d"],
             "base_visits": model["scenarios"]["base"]["visits"], "non_declining": trend["non_declining"],
             "suggestion": suggestion}
    rec["watch"]["checks"].append(check)
    save_ledger(root, ledger)
    return {"slug": slug, "expires_at": rec["watch"]["expires_at"], **check}


def follow_up(root, slug, status, domain=None, on=None, reason=None) -> dict:
    """建站跟进:pending → started → launched 只能前进,任何时候可 abandoned;不改 state。"""
    require(status in FOLLOW_UP_STATUSES[1:], "status 须为 started/launched/abandoned")
    on = on or today()
    require(isinstance(on, str) and _DATE_RE.fullmatch(on), f"日期须为 YYYY-MM-DD(收到 {on!r})")
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec and rec.get("lane") == "quick" and rec["state"] == "go" and rec.get("follow_up"),
            f"{slug} 不是快道 go,没有建站跟进")
    fu = rec["follow_up"]
    order = {"pending": 0, "started": 1, "launched": 2}
    require(fu["status"] != "abandoned", "已放弃的方向不能再改跟进")
    if status == "abandoned":
        require(isinstance(reason, str) and reason.strip(), "放弃须写理由")
        fu.update(status="abandoned", reason=reason.strip())
    else:
        require(order[status] == order[fu["status"]] + 1, f"跟进只能按 pending → started → launched 前进(当前 {fu['status']})")
        if status == "started":
            require(isinstance(domain, str) and domain.strip(), "已开建须写域名")
            require(on >= fu["go_at"], f"开建日期 {on} 早于判 go 日期 {fu['go_at']}")
            fu.update(status="started", domain=domain.strip(), started_at=on)
        else:
            require(on >= fu["started_at"], f"上线日期 {on} 早于开建日期 {fu['started_at']}")
            fu.update(status="launched", launched_at=on)
    fu["updated_at"] = now()
    save_ledger(root, ledger)
    return fu


def transition(root, slug, to, gate=None, reason="", by="xinci-bench-assess", on=None) -> dict:
    on = on or today()
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    frm, lane = rec["state"], rec.get("lane", "bench")
    require(to in LEGAL_BY_LANE[lane].get(frm, set()), f"非法转移 {frm} → {to}({lane})")
    gates = GATES_BY_LANE[lane]
    require((gate in gates) if to == "rejected" else gate is None,
            f"rejected 须带 gate {gates};go/parked/watching 不带 gate")
    require(isinstance(reason, str) and reason.strip(), "reason 不能为空")
    _require_evidence(root, rec, to, gate, on)
    rec["state"] = to
    rec["history"].append({"at": now(), "from": frm, "to": to, "by": by, "reason": reason.strip(),
                           **({"gate": gate} if gate else {})})
    save_ledger(root, ledger)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    r.add_argument("--slug", required=True)
    r.add_argument("--title", required=True)
    r.add_argument("--site-type", required=True, choices=SITE_TYPES)
    r.add_argument("--domain", required=True)
    r.add_argument("--scan", required=True, help="scan 观察路径")
    r.add_argument("--reason", required=True)
    r.add_argument("--by", default="xinci-bench-scan")
    r.add_argument("--confirm-distinct")
    u = sub.add_parser("update")
    u.add_argument("--slug", required=True)
    u.add_argument("--patch", required=True, help="补数 JSON 文件")
    u.add_argument("--ref", action="append", default=[], help="新增引用的观察路径")
    sub.add_parser("rank")
    s = sub.add_parser("show")
    s.add_argument("--slug", required=True)
    rq = sub.add_parser("register-quick")
    rq.add_argument("--input", required=True, help="JSON:slug、title、site_type、object、terms、screen、reason")
    pv = sub.add_parser("quick-preview")
    pv.add_argument("--slug", required=True)
    wc = sub.add_parser("watch-check")
    wc.add_argument("--slug", required=True)
    wc.add_argument("--ref", action="append", default=[])
    fu = sub.add_parser("follow-up")
    fu.add_argument("--slug", required=True)
    fu.add_argument("--status", required=True, choices=FOLLOW_UP_STATUSES[1:])
    fu.add_argument("--domain")
    fu.add_argument("--date")
    fu.add_argument("--reason")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "register":
            out = register(root, a.slug, a.title, a.site_type, a.domain, a.scan, a.reason, a.by, a.confirm_distinct)
        elif a.cmd == "update":
            out = update(root, a.slug, load_json(Path(a.patch)), a.ref)
        elif a.cmd == "rank":
            out = rank(root)
        elif a.cmd == "register-quick":
            d = load_json(Path(a.input))
            out = register_quick(root, d["slug"], d["title"], d["site_type"], d["object"], d["terms"],
                                 d["screen"], d["reason"], d.get("by", "xinci-bench-quick"))
        elif a.cmd == "quick-preview":
            rec = load_ledger(root)["directions"].get(a.slug)
            require(rec and rec.get("lane") == "quick", f"没有快道方向 {a.slug}")
            out = {**derive_quick(root, rec), "model": _quick_model(root, rec)}
        elif a.cmd == "watch-check":
            out = watch_check(root, a.slug, a.ref)
        elif a.cmd == "follow-up":
            out = follow_up(root, a.slug, a.status, a.domain, a.date, a.reason)
        else:
            out = load_ledger(root)["directions"].get(a.slug)
            require(out, f"没有方向 {a.slug}")
    except (BenchError, OSError, ValueError, KeyError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```


- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 130 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_ledger.py" "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py" "xinci-bench-workflow/xinci-bench-core/scripts/ledger.py"
git commit -m "xinci-bench 快道:账本分道——快道登记、补数、观察中复查与建站跟进" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 快道结算、校验与决策书

**Files:**
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/settle.py`（整份替换）
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py`（整份替换）
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/build_quick_doc.py`
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/build_doc_html.py`（立即建站一节加底色）
- Modify: `xinci-bench-workflow/xinci-bench-core/数据结构/direction.schema.json`（整份替换）
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_settle.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_build_quick_doc.py`

**Interfaces:**
- Consumes: Task 4 的 `ledger.precheck/transition/derive_quick/LEGAL_BY_LANE/GATES_BY_LANE/doc_paths`、Task 1 的 `quick_model.compute/add_days/stop_line`、`build_doc._observations/_fmt/_money/_yn/_table/SEO_RULES/GEO_RULES`（已存在）
- Produces: `settle.VERDICTS` 加 `watching`；`settle.settle(...)` 签名不变，快道 go 初始化 `follow_up={status:'pending', go_at, launch_by=go_at+7 天, domain, started_at, launched_at, reason}`，watching 初始化 `watch={since, expires_at=+30 天, checks:[]}`，parked/watching 改判时旧决策书归档到 `文档/历史/`；`validate_ledger.REQUIRED` 加 `lane`、`REQUIRED_QUICK`、`check_direction(root, slug, rec, on=None)`、`check_quick_files(root)`、`check_all(root, on=None)`；`build_quick_doc.render_md(root, rec)->str`、`build(root, slug)->(md, html)`；决策书结构：go 时 `## 立即建站`、`## 结论`、`## 第一部分 决策`（### 1–6）、go 时 `## 第二部分 最小版本建站简报`（### 1–6）、`## 附：证据清单`

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_settle.py`（新建）：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import settle as S
import validate_ledger as V
import write_observation as W
from _common import BenchError, load_ledger, save_ledger
from helpers import TmpRoot, quick_brief_obs, quick_screen_obs, quick_volume_obs, setup_quick

ON = "2026-10-20"
WATCH_VOL = dict(anchor_volume=9900, new_mean=50.0, anchor_mean=99.0)     # 约 5,000 月搜索量 → 基准 1,000


class SettleQuickTest(unittest.TestCase):
    def test_go_initialises_follow_up_and_doc(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            rec = S.settle(root, slug, "go", None, "首页没人做,量够", "新域名多久能排上去", on=ON)
            self.assertEqual(rec["follow_up"]["status"], "pending")
            self.assertEqual(rec["follow_up"]["launch_by"], "2026-10-27")
            self.assertEqual(rec["model"]["scenarios"]["base"]["visits"], 10000)
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn("## 立即建站", md)
            self.assertIn("## 第二部分 最小版本建站简报", md)
            self.assertEqual(V.check_all(root, on=ON), [])

    def test_go_needs_brief_and_fast_build(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root, brief=False)
            with self.assertRaisesRegex(BenchError, "quick_brief"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            L.update(root, slug, {}, [W.write(root, quick_brief_obs(slug, build_days=5))])
            with self.assertRaisesRegex(BenchError, "3 天"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            self.assertIsNone(load_ledger(root)["directions"][slug]["decision"])

    def test_spike_refuses_go_and_allows_oneoff(self):
        with TmpRoot() as root:
            spike = quick_volume_obs("gag2-calculator", series=[0] * 10 + [100] + [5] * 19)
            slug, _ = setup_quick(root, volume=spike)
            with self.assertRaisesRegex(BenchError, "冲高回落"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            rec = S.settle(root, slug, "rejected", "oneoff", "冲高回落", "u", on=ON)
            self.assertEqual(rec["state"], "rejected")

    def test_watching_then_go(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root, volume=quick_volume_obs("gag2-calculator", **WATCH_VOL))
            with self.assertRaisesRegex(BenchError, "不到 1 万"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            rec = S.settle(root, slug, "watching", None, "量还不够,在涨", "能不能涨到 5 万", on=ON)
            self.assertEqual(rec["watch"]["expires_at"], "2026-11-19")
            self.assertEqual(V.check_all(root, on=ON), [])
            ref = W.write(root, quick_volume_obs(slug))                  # 复查时量涨到 5 万
            chk = L.watch_check(root, slug, [ref], on="2026-10-27")
            self.assertEqual(chk["suggestion"], "go")
            S.settle(root, slug, "go", None, "涨够了", "u", on="2026-10-27")
            self.assertEqual(len(list((root / "文档" / "历史").glob(f"{slug}-*.md"))), 1)
            self.assertEqual(V.check_all(root, on="2026-10-27"), [])

    def test_watching_expiry(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root, volume=quick_volume_obs("gag2-calculator", **WATCH_VOL))
            S.settle(root, slug, "watching", None, "r", "u", on=ON)
            with self.assertRaisesRegex(BenchError, "到期"):
                S.settle(root, slug, "rejected", "volume", "r", "u", on="2026-11-01")
            self.assertTrue(any("到期" in e for e in V.check_all(root, on="2026-11-20")))
            self.assertEqual(L.watch_check(root, slug, on="2026-11-19")["suggestion"], "rejected:volume")
            rec = S.settle(root, slug, "rejected", "volume", "30 天没涨够", "u", on="2026-11-19")
            self.assertEqual(rec["decision"]["gate"], "volume")
            self.assertEqual(V.check_all(root, on="2026-11-20"), [])

    def test_occupied_needs_failed_screen(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            with self.assertRaisesRegex(BenchError, "Q5"):
                S.settle(root, slug, "rejected", "occupied", "r", "u", on=ON)
            ref = W.write(root, quick_screen_obs(slug, term=f"{slug} term", fail={"Q5": False}, occupied_by="new-tool.com"))
            L.update(root, slug, {}, [ref])
            self.assertEqual(S.settle(root, slug, "rejected", "occupied", "有人做了", "u", on=ON)["state"], "rejected")

    def test_quick_gate_codes_only(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            with self.assertRaisesRegex(BenchError, "gate"):
                S.settle(root, slug, "rejected", "revenue", "r", "u", on=ON)


class FollowUpTest(unittest.TestCase):
    def test_only_forward(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            with self.assertRaisesRegex(BenchError, "前进"):
                L.follow_up(root, slug, "launched", on="2026-10-21")
            with self.assertRaisesRegex(BenchError, "域名"):
                L.follow_up(root, slug, "started", on="2026-10-21")
            L.follow_up(root, slug, "started", domain="gag2calc.com", on="2026-10-21")
            fu = L.follow_up(root, slug, "launched", on="2026-10-25")
            self.assertEqual((fu["status"], fu["launched_at"]), ("launched", "2026-10-25"))
            with self.assertRaisesRegex(BenchError, "理由"):
                L.follow_up(root, slug, "abandoned")
            self.assertEqual(V.check_all(root, on=ON), [])

    def test_dates_checked(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            with self.assertRaisesRegex(BenchError, "YYYY-MM-DD"):
                L.follow_up(root, slug, "started", domain="x.com", on="10/21")
            with self.assertRaisesRegex(BenchError, "早于"):
                L.follow_up(root, slug, "started", domain="x.com", on="2026-10-19")
            L.follow_up(root, slug, "started", domain="x.com", on="2026-10-22")
            with self.assertRaisesRegex(BenchError, "早于"):
                L.follow_up(root, slug, "launched", on="2026-10-21")

    def test_validate_catches_tampered_quick_model(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            ledger = load_ledger(root)
            ledger["directions"][slug]["model"]["scenarios"]["base"]["visits"] = 99999
            save_ledger(root, ledger)
            self.assertTrue(any("快道模型重算" in e for e in V.check_all(root, on=ON)))


if __name__ == "__main__":
    unittest.main()
```

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_build_quick_doc.py`（新建）：

```python
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
```


- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `FAILED (failures=1, errors=11)`，首个报错 `_common.BenchError: 没有干净标杆,不能测算`（settle 还不会结算快道方向，build_quick_doc 不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/settle.py`（整份替换）：

```python
#!/usr/bin/env python3
"""结算一个方向:重算模型 → 固定绑定 → 生成决策书 → 转移状态 → 校验。

中断后用同一条命令重跑即可恢复:已转移的只补文档与校验,不重复写 history。
"""
import argparse
import copy
import shutil
import sys
from pathlib import Path

import bench_model
import build_doc
import build_quick_doc
import data_root
import ledger as L
import quick_model as QM
import validate_ledger
import write_observation as W
from _common import BenchError, load_ledger, now, require, save_ledger, sha256_file, today


def _archive_docs(root, slug) -> list:
    """把旧决策书移到 文档/历史/,返回移过去的路径(回滚时删掉)。"""
    md, html = L.doc_paths(root, slug)
    if not md.is_file():
        return []
    tag = sha256_file(md)[:12]
    dest = Path(root) / "文档" / "历史"
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for p in (md, html):
        if p.is_file():
            target = dest / f"{slug}-{tag}{p.suffix}"
            shutil.move(str(p), str(target))
            moved.append(target)
    return moved


def _record_doc_sha(root, slug):
    """决策书生成后把 md 的 SHA 记进 decision,validate 用它发现手改。"""
    ledger = load_ledger(root)
    ledger["directions"][slug]["decision"]["doc_sha256"] = sha256_file(L.doc_paths(root, slug)[0])
    save_ledger(root, ledger)


VERDICTS = ("go", "rejected", "parked", "watching")


def _build(root, slug, lane):
    (build_quick_doc if lane == "quick" else build_doc).build(root, slug)


def _fill_quick(root, rec, verdict, gate, on):
    """快道结算:从最新观察写入量级与首屏读数,算模型;观察中写到期日,go 初始化建站跟进。"""
    rec.update(L.derive_quick(root, rec))
    try:
        rec["model"] = QM.compute(rec)
    except BenchError:
        require(verdict not in ("go", "watching") and gate != "volume", "go、观察中与 volume 否决必须能完成测算")
        rec["model"] = None
    if verdict == "watching":
        rec["watch"] = {"since": on, "expires_at": QM.add_days(on, QM.QUICK_ASSUMPTIONS["watch_days"]), "checks": []}
    if verdict == "go":
        rec["follow_up"] = {"status": "pending", "go_at": on,
                            "launch_by": QM.add_days(on, QM.QUICK_ASSUMPTIONS["launch_days"]),
                            "domain": None, "started_at": None, "launched_at": None, "reason": None}


def settle(root, slug, verdict, gate=None, reason="", biggest_unknown="", by="xinci-bench-assess",
           scope_hit=None, on=None) -> dict:
    require(verdict in VERDICTS, f"verdict 须为 {VERDICTS}")
    require(isinstance(biggest_unknown, str) and biggest_unknown.strip(), "biggest_unknown 须写最可能让结论翻转的一项")
    require(isinstance(reason, str) and reason.strip(), "reason 须写一句结论理由")
    on = on or today()
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    lane = rec.get("lane", "bench")
    if rec["state"] == verdict:            # 恢复:已转移,只补文档与校验
        dec = rec.get("decision") or {}
        require(dec.get("verdict") == verdict and dec.get("gate") == gate, "已结算的结论与本次参数不一致,不能覆盖")
        _build(root, slug, lane)           # 文档只由账本与绑定观察决定,重建是幂等的
        _record_doc_sha(root, slug)
    else:
        legal, gates = L.LEGAL_BY_LANE[lane], L.GATES_BY_LANE[lane]
        require(verdict in legal.get(rec["state"], set()), f"非法结算 {rec['state']} → {verdict}({lane})")
        require((gate in gates) if verdict == "rejected" else gate is None,
                f"{lane} 道 rejected 须带 gate {gates};go/parked/watching 不带 gate")
        for ref in rec["evidence_refs"]:      # 先确认引用的观察都在且合规,再算绑定
            W.read(root, ref)
        L.precheck(root, rec, verdict, gate, on, scope_hit)   # 证据不够在写任何东西之前就拒
        snapshot = copy.deepcopy(ledger)
        md, html = L.doc_paths(root, slug)
        saved = {p: p.read_bytes() for p in (md, html) if p.is_file()}
        archived = []
        try:
            if lane == "quick":
                _fill_quick(root, rec, verdict, gate, on)
            else:
                try:
                    rec["model"] = bench_model.compute(rec)
                except BenchError:
                    require(verdict != "go" and gate != "revenue", "go 与收入否决必须能完成测算")
                    rec["model"] = None
            rec["decision"] = {"verdict": verdict, "gate": gate, "reason": reason.strip(),
                               "biggest_unknown": biggest_unknown.strip(), "scope_hit": scope_hit,
                               "decided_at": now()}
            rec["bindings"] = {"bound_at": now(), "files": [
                {"ref": ref, "sha256": sha256_file(Path(root) / ref)} for ref in rec["evidence_refs"]]}
            save_ledger(root, ledger)
            if rec["state"] in ("parked", "watching"):
                archived = _archive_docs(root, slug)
            _build(root, slug, lane)
            _record_doc_sha(root, slug)
            L.transition(root, slug, verdict, gate, reason, by, on)
        except Exception:
            # 回滚:账本恢复结算前原样,删掉本次生成与归档的文档,放回原决策书
            save_ledger(root, snapshot)
            for p in archived + [md, html]:
                p.unlink(missing_ok=True)
            for p, data in saved.items():
                p.write_bytes(data)
            raise
    rec = load_ledger(root)["directions"][slug]
    errs = validate_ledger.check_direction(root, slug, rec)
    require(not errs, "结算后校验失败: " + "; ".join(errs))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--verdict", required=True, choices=VERDICTS)
    ap.add_argument("--gate", choices=tuple(dict.fromkeys(L.GATES + L.QUICK_GATES)))
    ap.add_argument("--scope-hit", choices=L.SCOPE_ITEMS)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--biggest-unknown", required=True)
    ap.add_argument("--by", default="xinci-bench-assess")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        rec = settle(root, a.slug, a.verdict, a.gate, a.reason, a.biggest_unknown, a.by, a.scope_hit)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    md, html = L.doc_paths(root, a.slug)
    print(f"{a.slug}: {rec['state']}\n决策书: {md}\n        {html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py`（整份替换）：

```python
#!/usr/bin/env python3
"""账本、种子池、淘汰索引、快道原料池的不变式校验;有错非零退出。单元测试通过不能代替它。"""
import argparse
import sys
from pathlib import Path

import bench_model
import data_root
import ledger as L
import quick_model as QM
import quick_pool
import write_observation as W
from _common import REJECTS_REL, SEEDS_REL, BenchError, load_json, load_ledger, sha256_file, today

REQUIRED = ("slug", "title", "site_type", "lane", "state", "benchmarks", "clusters", "crowding", "paid",
            "model", "decision", "evidence_refs", "bindings", "history")
REQUIRED_QUICK = ("slug", "title", "site_type", "lane", "state", "object", "terms", "volume", "serp", "watch",
                  "follow_up", "model", "decision", "evidence_refs", "bindings", "history")


def _history_errors(slug, rec):
    errs, hist = [], rec["history"]
    legal = L.LEGAL_BY_LANE[rec["lane"]]
    if not hist or hist[0].get("from") is not None or hist[0].get("to") != "found":
        return [f"{slug}: history 须以 null → found 开始"]
    for h in hist[1:]:
        if h.get("to") not in legal.get(h.get("from"), set()):
            errs.append(f"{slug}: history 含非法转移 {h.get('from')} → {h.get('to')}")
    if hist[-1]["to"] != rec["state"]:
        errs.append(f"{slug}: 状态 {rec['state']} 与 history 末条 {hist[-1]['to']} 不一致")
    return errs


def _quick_errors(slug, rec, on):
    errs, dec = [], rec.get("decision") or {}
    if rec["state"] in ("go", "watching") or dec.get("gate") == "volume":
        try:
            if QM.compute(rec) != rec.get("model"):
                errs.append(f"{slug}: 快道模型重算与账本不一致")
        except BenchError as exc:
            errs.append(f"{slug}: 快道模型无法重算: {exc}")
    if rec["state"] == "watching":
        w = rec.get("watch") or {}
        if not w.get("expires_at"):
            errs.append(f"{slug}: 观察中须有到期日")
        elif on > w["expires_at"]:
            errs.append(f"{slug}: 观察已于 {w['expires_at']} 到期,须按 go 或 volume 否决结算")
    if rec["state"] == "go":
        fu = rec.get("follow_up") or {}
        if fu.get("status") not in L.FOLLOW_UP_STATUSES or not fu.get("launch_by"):
            errs.append(f"{slug}: 快道 go 的建站跟进缺失或状态无效")
        elif fu["status"] == "launched" and not fu.get("launched_at"):
            errs.append(f"{slug}: 已上线须有上线日期")
    if dec.get("gate") and dec["gate"] not in L.QUICK_GATES:
        errs.append(f"{slug}: 快道否决门无效 {dec['gate']}")
    return errs


def check_direction(root, slug, rec, on=None) -> list:
    on = on or today()
    lane = rec.get("lane")
    if lane not in L.LANES:
        return [f"{slug}: 缺 lane 或取值无效(须为 {L.LANES})"]
    missing = [k for k in (REQUIRED if lane == "bench" else REQUIRED_QUICK) if k not in rec]
    if missing:
        return [f"{slug}: 缺字段 {missing}"]
    errs = []
    if rec["slug"] != slug:
        errs.append(f"{slug}: 记录里的 slug 是 {rec['slug']}")
    if rec["state"] not in L.STATES:
        errs.append(f"{slug}: 未知状态 {rec['state']}")
    errs += _history_errors(slug, rec)
    for ref in rec["evidence_refs"]:
        try:
            W.read(root, ref)
        except BenchError as exc:
            errs.append(f"{slug}: 观察不可用 {ref}: {exc}")
    if rec["state"] == "found":
        if rec.get("decision") is not None or rec.get("bindings") is not None:
            errs.append(f"{slug}: found 不应带 decision/bindings,说明结算未完成;用同一条 settle.py 命令重跑")
        return errs
    dec = rec.get("decision") or {}
    if dec.get("verdict") != rec["state"]:
        errs.append(f"{slug}: decision.verdict 与状态不一致")
    if not L.docs_consistent(root, slug):
        errs.append(f"{slug}: 决策书 md/html 缺失,或 html 内嵌的源 SHA 与 md 不符")
    elif sha256_file(L.doc_paths(root, slug)[0]) != dec.get("doc_sha256"):
        errs.append(f"{slug}: 决策书 md 与账本不一致(md 的 SHA 不等于结算时记录的 doc_sha256,疑似被手改);"
                    "事实没变时用同一条 settle.py 命令重跑重建")
    for f in (rec.get("bindings") or {}).get("files", []):
        p = Path(root) / f["ref"]
        if not p.is_file() or sha256_file(p) != f["sha256"]:
            errs.append(f"{slug}: 绑定观察已变动或丢失 {f['ref']}")
    if not rec.get("bindings"):
        errs.append(f"{slug}: 终态、搁置或观察中须有绑定")
    if lane == "quick":
        return errs + _quick_errors(slug, rec, on)
    if rec["state"] == "go" or dec.get("gate") == "revenue":
        try:
            model = bench_model.compute(rec)
            if model != rec.get("model"):
                errs.append(f"{slug}: 模型重算与账本不一致")
            elif model["passes"] is not (rec["state"] == "go"):
                errs.append(f"{slug}: 模型结论与状态不符")
        except BenchError as exc:
            errs.append(f"{slug}: 模型无法重算: {exc}")
    return errs


def check_seeds(root) -> list:
    errs = []
    pool = load_json(Path(root) / SEEDS_REL)
    for d, s in pool.get("seeds", {}).items():
        if s.get("source") not in ("legacy", "sibling", "serp", "geo", "community"):
            errs.append(f"种子 {d}: 来源无效")
        if s.get("role") not in ("benchmark", "sibling") or s.get("status") not in ("pending", "checked"):
            errs.append(f"种子 {d}: role 或 status 无效")
    rejects = load_json(Path(root) / REJECTS_REL)
    for d, e in rejects.get("domains", {}).items():
        if (e.get("recheck_after") is not None) != (e.get("failed") == ["B3"]):
            errs.append(f"淘汰 {d}: 只有单独 B3 不过才设复查日期")
        if not str(e.get("observation", "")).startswith("证据/_scan/"):
            errs.append(f"淘汰 {d}: 缺 scan 观察引用")
    return errs


def check_quick_files(root) -> list:
    errs = []
    for r in quick_pool._read_pool(root):
        if r.get("status") not in quick_pool.STATUSES:
            errs.append(f"原料 {r.get('id')}: status 无效")
    for term, e in quick_pool._rejects(root)["terms"].items():
        if e.get("gate") not in quick_pool.QUICK_GATES or not str(e.get("observation", "")).startswith("证据/"):
            errs.append(f"快道淘汰 {term}: gate 或观察引用无效")
    return errs


def check_all(root, on=None) -> list:
    ledger = load_ledger(root)
    errs = [] if ledger.get("schema_version") == 1 else ["账本 schema_version 须为 1"]
    for slug, rec in ledger.get("directions", {}).items():
        errs += check_direction(root, slug, rec, on)
    return errs + check_seeds(root) + check_quick_files(root)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    errs = check_all(root)
    for e in errs:
        print("错误: " + e)
    print(f"校验完成:{len(errs)} 个错误")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
```

`xinci-bench-workflow/xinci-bench-core/scripts/build_quick_doc.py`（新建）：

```python
#!/usr/bin/env python3
"""快道决策书(go 时含"立即建站"与最小版本建站简报):账本 + 绑定观察 → 文档/<slug>.md,再生成 html。

只读绑定的观察;每节第一句是加粗的大白话结论,数字都从结构化字段派生。
"""
import argparse
import sys
from pathlib import Path

import build_doc
import build_doc_html
import data_root
import quick_model as QM
import write_observation as W
from _common import BenchError, load_ledger, require

VERDICT_CN = {"go": "值得做（go）", "rejected": "否决", "parked": "搁置", "watching": "观察中"}
GATE_CN = {"scope": "范围排除", "not_new": "不是新的", "oneoff": "一次性或冲高回落", "occupied": "首页已有人做",
           "answered": "首屏已答完", "volume": "量不够"}
SCEN_CN = {"low": "保守", "base": "基准", "high": "乐观"}
_fmt, _money, _yn, _table = build_doc._fmt, build_doc._money, build_doc._yn, build_doc._table


def _latest(by_kind, kind):
    return by_kind[kind][-1][1]["readings"] if by_kind.get(kind) else None


def _go_block(rec, by_kind):
    m, fu, vol = rec["model"], rec["follow_up"], rec["volume"]
    base = m["scenarios"]["base"]
    brief = _latest(by_kind, "quick_brief")
    first_seen = min(t["first_seen"] for t in rec["terms"])
    lines = ["## 立即建站", "",
             f"**建议最晚 {fu['launch_by']} 上线：首页现在没人完整做这个任务，这个说法 {first_seen} 开始冒出来，"
             f"基准预计上线 90 天内单月约 {_fmt(base['visits'])} 次美区访问（模型估算）。**", ""]
    lines += [f"- {SCEN_CN[k]}：约 {_fmt(v['visits'])} 次访问、{_money(v['revenue'])}/月" for k, v in m["scenarios"].items()]
    if m["single_site_100"]:
        lines.append("- 基准预计 ≥ 2.5 万访问：单站就能到 $100/月")
    lines.append(f"- 当前月搜索量约 {_fmt(vol['estimate_7d'])}（Trends 换算）")
    lines.append("- 最小版本要做的页面：" + "；".join(f"`{p['path']}` {p['target_query']}" for p in brief["pages"]))
    return lines + [""]


def _part_one(rec, by_kind):
    obj, vol, serp, m = rec["object"], rec.get("volume"), rec.get("serp"), rec.get("model")
    screen = _latest(by_kind, "quick_screen")
    lines = ["## 第一部分 决策", "", "### 1. 新对象与新说法", "",
             f"**{obj['name']} 首次公开于 {obj['first_public']}，冒出 {len(rec['terms'])} 个任务说法。**"
             f"日期来源：{obj['date_source']}", ""]
    lines += _table(["说法", "来源", "首次看到"], [[t["term"], t["source"], t["first_seen"]] for t in rec["terms"]])
    lines += ["", "### 2. 有人在搜", ""]
    if vol:
        lines.append(f"**当前月搜索量约 {_fmt(vol['estimate_7d'])}（Trends 换算，锚词 {vol['anchor_term']} "
                     f"{_fmt(vol['anchor_volume'])}/月，比值 {vol['ratio_7d']}）。**")
        lines += ["", f"- 按 30 天算约 {_fmt(vol['estimate_30d'])}/月；锚词来自 {vol['anchor_source']}，测于 {vol['anchor_measured_at']}"]
    else:
        lines += ["**本方向没有做到量级换算这一步。**", ""]
    if screen:
        lines.append(f"- Q2 依据：{screen['checks']['Q2']['basis']}")
    lines += ["", "### 3. 不是一次性", ""]
    if vol:
        tr = vol["trend"]
        lines.append(f"**最近 7 天均值 {tr['last7']}、前 7 天 {tr['prev7']}、近 30 天峰值 {tr['peak30']}："
                     f"{'趋势不降' if tr['non_declining'] else '趋势在降'}，{'是' if tr['spike_decay'] else '不是'}冲高回落。**")
    else:
        lines.append("**本方向没有曲线读数。**")
    if screen:
        lines += ["", f"- Q3 依据：{screen['checks']['Q3']['basis']}"]
    lines += ["", "### 4. 首页现场与 GEO", ""]
    if screen:
        aio = screen["ai_overview"]
        aio_cn = "不在" if not aio["present"] else ("已答完" if aio["completes_task"] else "在场但没答完")
        occ = screen["occupied_by"]
        lines.append(f"**首页前 10 条{'有页面完整做了这个任务（' + occ + '）' if occ else '没有页面完整做了这个任务'}；AI 概览{aio_cn}。**")
        lines.append("")
        lines += _table(["位置", "域名", "类型", "完整做了任务"],
                        [[r.get("pos", "—"), r.get("domain", "—"), r.get("type", "—"), _yn(r.get("completes_task"))]
                         for r in screen["top10"]])
        if aio.get("cited_domains"):
            lines.append("")
            lines.append("- AI 概览引用：" + "、".join(aio["cited_domains"]))
    else:
        lines.append("**本方向没有首屏读数。**")
    lines += ["", "### 5. 预计访问与收入", ""]
    if m:
        base = m["scenarios"]["base"]
        lines.append(f"**基准情景上线 90 天内单月约 {_fmt(base['visits'])} 次美区访问、{_money(base['revenue'])}/月（模型估算），"
                     f"{'过' if m['passes'] else '不过'} {_fmt(m['threshold_visits'])} 访问门槛。**")
        lines.append("")
        lines += _table(["情景", "首发份额", "预计月访问", "预计月收入（AdSense）"],
                        [[SCEN_CN[k], f"{v['share']:.0%}", _fmt(v["visits"]), _money(v["revenue"])] for k, v in m["scenarios"].items()])
        lines += ["", f"- AI 概览系数 {m['aio_factor']}；基准过线需要月搜索量约 {_fmt(m['searches_needed'])}",
                  f"- 假设表版本 {m['assumptions_version']}；按当前量估算，不外推增长"]
    else:
        lines.append("**本方向没有完成测算。**")
    if rec.get("watch"):
        w = rec["watch"]
        lines += ["", f"- 观察中：{w['since']} 起，{w['expires_at']} 到期；已复查 {len(w['checks'])} 次"]
    lines += ["", "### 6. 风险与最大未知", "", f"**最大的未知：{rec['decision']['biggest_unknown']}。**", ""]
    risks = list((_latest(by_kind, "quick_brief") or {}).get("risks") or [])
    risks.append("首发份额是起点假设（10/20/30%），新域名多久能排上去未确认")
    lines += [f"- {x}" for x in risks]
    return lines + [""]


def _brief(rec, by_kind):
    b, m = _latest(by_kind, "quick_brief"), rec["model"]
    base = m["scenarios"]["base"]
    lines = ["## 第二部分 最小版本建站简报", "", "### 1. 做什么", "", f"**{b['positioning']}**", "",
             "- 1 个主页面完成核心任务，最多 2–3 个配套页覆盖同一对象的其他任务词", "",
             "### 2. 页面清单", "", f"**首版 {len(b['pages'])} 个页面，预计 {_fmt(b['build_days'])} 天做完。**", ""]
    lines += _table(["路径", "目标查询", "要交付的内容或功能"], [[p["path"], p["target_query"], p["deliverable"]] for p in b["pages"]])
    lines += ["", "### 3. 数据", "", f"**数据来自 {len(b['data_sources'])} 个来源，{b['update_frequency']}更新；授权：{b['license']}。**", ""]
    lines += [f"- {s}" for s in b["data_sources"]]
    lines += ["", "### 4. 上线清单", "", "**免费托管上线，当天提交 Search Console 和 sitemap。**", "", f"- 托管：{b['hosting']}"]
    lines += [f"- {x}" for x in build_doc.SEO_RULES + build_doc.GEO_RULES]
    lines += ["", "### 5. 预计访问与收入", "",
              f"**基准约 {_fmt(base['visits'])} 次访问、{_money(base['revenue'])}/月，按 AdSense $4/千访问估算。**", ""]
    lines += ["### 6. 验收与止损", "",
              f"**上线第 30 天月点击低于 {_fmt(QM.stop_line(m))} 就止损（基准预计的 25%）：不再加工时，站留着。**", ""]
    lines += _table(["上线后", "看什么", "结论"],
                    [["第 14 天", "主页面是否收录、有展现", "没有就先查收录"],
                     ["第 30 天", f"月点击是否低于 {_fmt(QM.stop_line(m))}", "低于即止损"],
                     ["第 90 天", f"单月是否 ≥ {_fmt(m['threshold_visits'])} 访问", "达到算成功"]])
    return lines + [""]


def render_md(root, rec) -> str:
    dec = rec.get("decision")
    require(dec, f"{rec['slug']} 还没有 decision;用 settle.py 结算")
    refs, by_kind = build_doc._observations(root, rec)
    verdict = VERDICT_CN[dec["verdict"]] + (f"（{GATE_CN[dec['gate']]}）" if dec.get("gate") else "")
    lines = [f"# {rec['title']}：快道决策书", "",
             f"- 方向 `{rec['slug']}` · 新词快道 · 站型 {rec['site_type']} · 结论 {verdict} · 决定于 {dec['decided_at']}", ""]
    if dec["verdict"] == "go":
        lines += _go_block(rec, by_kind)
    lines += ["## 结论", "", f"一句话：**{verdict}**。{dec['reason']}", ""]
    if rec.get("model"):
        base = rec["model"]["scenarios"]["base"]
        lines.append(f"- 基准情景上线 90 天内单月约 {_fmt(base['visits'])} 次访问、{_money(base['revenue'])}/月（模型估算）")
    lines += [f"- 最大的未知：{dec['biggest_unknown']}", ""]
    lines += _part_one(rec, by_kind)
    if dec["verdict"] == "go":
        lines += _brief(rec, by_kind)
    files = (rec.get("bindings") or {}).get("files") or [{"ref": r, "sha256": ""} for r in refs]
    lines += ["## 附：证据清单", ""]
    lines += _table(["观察文件", "SHA-256 前 12 位"], [[f"`{f['ref']}`", f["sha256"][:12] or "未绑定"] for f in files])
    return "\n".join(lines) + "\n"


def build(root, slug):
    rec = load_ledger(root)["directions"].get(slug)
    require(rec and rec.get("lane") == "quick", f"没有快道方向 {slug}")
    md = Path(root) / "文档" / f"{slug}.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_md(root, rec), encoding="utf-8")
    return md, build_doc_html.build(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--slug", required=True)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        md, html = build(root, a.slug)
    except (BenchError, KeyError, IndexError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(f"已生成: {md}\n已生成: {html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`xinci-bench-workflow/xinci-bench-core/scripts/build_doc_html.py`：把

```python

def _decorate(body: str) -> str:
    """html 独有的两处排版:开篇结论加底色;证据清单折起来(它是给人反查的)。"""
    body = re.sub(r"(<h2>结论</h2>)\s*(<p>一句话：.*?</p>)",
                  lambda m: f'{m.group(1)}<div class="lede">{m.group(2)}</div>',
```

替换为

```python

def _decorate(body: str) -> str:
    """html 独有的排版:快道"立即建站"整节加底色;开篇结论加底色;证据清单折起来(它是给人反查的)。"""
    m = re.search(r'(<span class="a" id="s\d+"></span><h2>立即建站</h2>)(.*?)(?=<span class="a" id="s\d+"></span><h2>)',
                  body, re.S)
    if m:
        body = body[:m.end(1)] + '<div class="lede">' + m.group(2) + "</div>" + body[m.end(2):]
    body = re.sub(r"(<h2>结论</h2>)\s*(<p>一句话：.*?</p>)",
                  lambda m: f'{m.group(1)}<div class="lede">{m.group(2)}</div>',
```

`xinci-bench-workflow/xinci-bench-core/数据结构/direction.schema.json`（整份替换）：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "xinci-bench 方向记录",
  "description": "说明性 schema;强制校验在 ledger.py 与 validate_ledger.py。账本结构 {schema_version: 1, directions: {slug: 本记录}}。lane=bench 的记录按 required,lane=quick 的按 quick_required。",
  "type": "object",
  "required": ["slug", "title", "site_type", "lane", "state", "benchmarks", "clusters", "crowding", "paid", "model", "decision", "evidence_refs", "bindings", "history"],
  "properties": {
    "slug": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
    "title": {"type": "string"},
    "site_type": {"enum": ["tool", "content", "game", "mixed"]},
    "lane": {"enum": ["bench", "quick"]},
    "state": {"enum": ["found", "go", "rejected", "parked", "watching"], "description": "watching 只对 lane=quick 合法"},
    "benchmarks": {"type": "array", "minItems": 1, "items": {"required": ["domain", "registered_at", "aged_domain", "traffic_start", "authority_score", "us_organic_now", "us_organic_m12", "covered_demand", "link_driven", "algo_risk", "monetization", "clean"]}},
    "clusters": {"type": "array", "items": {"required": ["id", "seed_term", "volume", "measured_at", "coverage", "near_me", "answered", "counted"]}},
    "crowding": {"type": ["integer", "null"], "minimum": 1},
    "paid": {"required": ["applicable", "price_month", "evidence"]},
    "model": {"type": ["object", "null"], "description": "bench_model.compute 的输出,结算时写入"},
    "decision": {"type": ["object", "null"], "required": ["verdict", "gate", "reason", "biggest_unknown", "scope_hit", "decided_at", "doc_sha256"]},
    "evidence_refs": {"type": "array", "items": {"type": "string"}},
    "bindings": {"type": ["object", "null"], "required": ["bound_at", "files"]},
    "history": {"type": "array", "minItems": 1},
    "object": {"required": ["name", "first_public", "date_source"], "description": "快道:催生新词的对象"},
    "terms": {"type": "array", "minItems": 1, "items": {"required": ["term", "source", "first_seen"]}},
    "volume": {"type": ["object", "null"], "description": "快道:结算时由最新 quick_volume 写入(estimate_7d、estimate_30d、锚词信息、trend)"},
    "serp": {"type": ["object", "null"], "description": "快道:结算时由最新 quick_screen 写入(aio_present、aio_completes、occupied_by)"},
    "watch": {"type": ["object", "null"], "required": ["since", "expires_at", "checks"]},
    "follow_up": {"type": ["object", "null"], "required": ["status", "go_at", "launch_by", "domain", "started_at", "launched_at", "reason"], "properties": {"status": {"enum": ["pending", "started", "launched", "abandoned"]}}}
  },
  "quick_required": ["slug", "title", "site_type", "lane", "state", "object", "terms", "volume", "serp", "watch", "follow_up", "model", "decision", "evidence_refs", "bindings", "history"]
}
```


- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 143 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_settle.py" "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_build_quick_doc.py" "xinci-bench-workflow/xinci-bench-core/scripts/settle.py" "xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py" "xinci-bench-workflow/xinci-bench-core/scripts/build_quick_doc.py" "xinci-bench-workflow/xinci-bench-core/scripts/build_doc_html.py" "xinci-bench-workflow/xinci-bench-core/数据结构/direction.schema.json"
git commit -m "xinci-bench 快道:结算与回滚按道分派、快道校验、快道决策书与立即建站一节" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 运行清单与看板

**Files:**
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/run_log.py`（整份替换）
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/report_status.py`（整份替换）
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_run_log.py`（加 `QuickRunLogTest`）
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py`（加 `QuickStatusTest`）

**Interfaces:**
- Consumes: Task 4 的 `ledger.STATES/doc_paths/rank`、Task 3 的 `quick_pool.pending`、Task 1 的 `quick_model.milestones`
- Produces: `run_log.SKILLS` 加 `xinci-bench-quick`、`STAGE`、`LANE_OF`、`SOURCE_KINDS=seeds.SOURCES+('quick',)`、`latest_runs(rows, lane=None)`、`plan(root, run_id=None, lane='bench')`（快道 action 为 quick 或 done）；快道运行 `round=max_rounds=1`、`source_kind='quick'`，两条道的未完成运行互不阻塞；`report_status.status(root, on=None)` 多出 `counts.watching` 与 `quick={pending_go:[{slug,title,base_visits,base_revenue,launch_by,overdue,doc}], watching:[{slug,days_left,expires_at,checks}], milestones_due:[{slug,day,date}], pool_pending}`；文本看板第一行是 `【立即建站】<slug>:基准约 10,000 次访问、$40.00/月,建议最晚 <日期> 上线 → <决策书>`

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_run_log.py`：把

```python


if __name__ == "__main__":
    unittest.main()
```

替换为

```python


def start_quick(root, run_id="quick-a"):
    return R.record(root, skill="xinci-bench-quick", progress={
        "run_id": run_id, "round": 1, "max_rounds": 1, "source_kind": "quick",
        "seed_value": "自动补全与 Trends 飙升", "outcome": "started", "next_step": "quick"})


class QuickRunLogTest(unittest.TestCase):
    def test_quick_lifecycle(self):
        with TmpRoot() as root:
            self.assertEqual(R.plan(root, lane="quick")["action"], "quick")
            start_quick(root)
            p = R.plan(root, lane="quick")
            self.assertEqual((p["resume"]["run_id"], p["active_run_ids"]), ("quick-a", ["quick-a"]))
            R.finish(root, run_id="quick-a", outcome="blocked", notes=["Trends 429"])
            R.finish(root, run_id="quick-a", semrush_calls=1)
            self.assertEqual(R.plan(root, "quick-a", lane="quick")["action"], "done")

    def test_lanes_do_not_block_each_other(self):
        with TmpRoot() as root:
            start(root)                     # 标杆道运行未完成
            start_quick(root)               # 快道照样能开
            self.assertEqual(R.plan(root)["resume"]["run_id"], "run-a")
            self.assertEqual(R.plan(root, lane="quick")["resume"]["run_id"], "quick-a")
            with self.assertRaisesRegex(BenchError, "这条道"):
                start_quick(root, run_id="quick-b")

    def test_quick_run_shape(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "max_rounds"):
                R.record(root, skill="xinci-bench-quick", progress={
                    "run_id": "q", "round": 1, "max_rounds": 2, "source_kind": "quick",
                    "seed_value": "x", "outcome": "started", "next_step": "quick"})
            with self.assertRaisesRegex(BenchError, "source_kind"):
                R.record(root, skill="xinci-bench-scan", progress={
                    "run_id": "b", "round": 1, "max_rounds": 1, "source_kind": "quick",
                    "seed_value": "x", "outcome": "started", "next_step": "scan"})


if __name__ == "__main__":
    unittest.main()
```

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py`：把

```python


if __name__ == "__main__":
    unittest.main()
```

替换为

```python


class QuickStatusTest(unittest.TestCase):
    def test_pending_go_on_top_and_milestones(self):
        import ledger
        from helpers import setup_quick
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            settle.settle(root, slug, "go", None, "r", "u", on="2026-10-20")
            q = RS.status(root, on="2026-10-28")["quick"]
            self.assertEqual(q["pending_go"][0]["slug"], slug)
            self.assertTrue(q["pending_go"][0]["overdue"])            # 建议 10-27 前上线
            ledger.follow_up(root, slug, "started", domain="x.com", on="2026-10-28")
            ledger.follow_up(root, slug, "launched", on="2026-11-01")
            q = RS.status(root, on="2026-12-01")["quick"]
            self.assertEqual(q["pending_go"], [])
            self.assertEqual([m["day"] for m in q["milestones_due"]], [14, 30])

    def test_banner_is_first_line_with_formatted_numbers(self):
        import contextlib
        import io
        from helpers import setup_quick
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            settle.settle(root, slug, "go", None, "r", "u")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                RS.main(["--data-root", str(root)])
            first = buf.getvalue().splitlines()[0]
            self.assertTrue(first.startswith(f"【立即建站】{slug}:基准约 10,000 次访问、$40.00/月"), first)


if __name__ == "__main__":
    unittest.main()
```


- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `FAILED (failures=1, errors=4)`，首个报错 `KeyError: 'total'`（run_log 还不认识 xinci-bench-quick，看板没有快道部分）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/run_log.py`（整份替换）：

```python
#!/usr/bin/env python3
"""运行清单:阶段进度只追加,保存预算、恢复位置与来源;--plan 推导下一步,--finish 结束阶段。"""
import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import data_root
import seeds
from _common import BenchError, atomic_save, load_json, load_ledger, require, today

SKILLS = ("xinci-bench-scan", "xinci-bench-assess", "xinci-bench-quick")
STAGE = {"xinci-bench-scan": "scan", "xinci-bench-assess": "assess", "xinci-bench-quick": "quick"}
LANE_OF = {"xinci-bench-scan": "bench", "xinci-bench-assess": "bench", "xinci-bench-quick": "quick"}
SOURCE_KINDS = seeds.SOURCES + ("quick",)
ROTATION = ("sibling", "serp", "geo", "community")
OUTCOMES = ("started", "completed", "blocked", "skipped")
FOUND_TARGET = 3


def records(root) -> list:
    rows = []
    for path in (Path(root) / "运行").glob("*.json"):
        row = load_json(path)
        row["_path"] = str(path)
        rows.append(row)
    return sorted(rows, key=lambda r: (r["recorded_at"], r["_path"]))


def latest_runs(rows, lane=None) -> dict:
    """每个运行编号的最新一条;给了 lane 就只看这条道的运行(两条道互不阻塞)。"""
    latest = {}
    for row in rows:
        if lane is None or LANE_OF[row["skill"]] == lane:
            latest[row["progress"]["run_id"]] = row
    return latest


def next_position(row):
    """该运行下一阶段的位置;运行已结束返回 None。"""
    p = row["progress"]
    if p["next_step"] == "done":
        return None
    if STAGE[row["skill"]] == "quick":
        return {"stage": "quick", "round": 1}
    bump = STAGE[row["skill"]] == "assess" and p["outcome"] == "completed"
    return {"stage": p["next_step"], "round": p["round"] + int(bump)}


def _expected_next(stage, outcome, rnd, max_rounds):
    if outcome in ("started", "blocked"):
        return stage
    if stage == "quick":
        return "done"
    if stage == "scan":
        return "assess"
    return "done" if rnd == max_rounds else "scan"


def record(root, *, skill, progress, sources_opened=(), directions_touched=(), semrush_calls=0, notes=()) -> Path:
    require(skill in SKILLS, f"skill 须为 {SKILLS}")
    keys = ("run_id", "round", "max_rounds", "source_kind", "seed_value", "outcome", "next_step")
    require(all(k in progress for k in keys), f"progress 须含 {keys}")
    p = progress
    require(re.fullmatch(r"[a-zA-Z0-9-]+", str(p["run_id"])), "run_id 只能用字母数字连字符")
    require(type(p["round"]) is int and type(p["max_rounds"]) is int and 1 <= p["round"] <= p["max_rounds"],
            "轮次或预算无效")
    require(p["source_kind"] in SOURCE_KINDS, f"source_kind 须为 {SOURCE_KINDS}")
    lane = LANE_OF[skill]
    require((p["source_kind"] == "quick") == (lane == "quick"), "快道运行的 source_kind 固定为 quick,标杆道不能用 quick")
    require(lane == "bench" or p["max_rounds"] == 1, "快道运行一次只走一遍,max_rounds 固定为 1")
    require(isinstance(p["seed_value"], str) and p["seed_value"].strip(), "seed_value 须写本阶段从哪取种子")
    require(p["outcome"] in OUTCOMES, f"outcome 须为 {OUTCOMES}")
    require(isinstance(semrush_calls, int) and semrush_calls >= 0, "semrush_calls 须为非负整数")
    stage = STAGE[skill]
    require(not (p["outcome"] == "skipped" and stage != "scan"), "只能跳过标杆道的发现阶段")
    require(p["next_step"] == _expected_next(stage, p["outcome"], p["round"], p["max_rounds"]),
            "next_step 与阶段、结果、轮次不一致")
    history = records(root)
    same = [r for r in history if r["progress"]["run_id"] == p["run_id"]]
    if same:
        cursor = next_position(same[-1])
        require(cursor is not None, "该运行已结束,不能追加")
        require(cursor == {"stage": stage, "round": p["round"]}, f"恢复位置应为 {cursor}")
        require(all(r["progress"]["max_rounds"] == p["max_rounds"] for r in same), "同一 run_id 的预算不能改")
        last = same[-1]["progress"]
        if last["outcome"] in ("started", "blocked"):
            require(p["outcome"] != "started", "该阶段已开始,结束请用 --finish")
    else:
        require(not any(next_position(r) for r in latest_runs(history, lane).values()),
                "这条道存在未完成运行,须先恢复;不能创建新 run_id")
        first = "quick" if lane == "quick" else "scan"
        require(p["round"] == 1 and stage == first and p["outcome"] == "started",
                f"新运行须从第 1 轮 {first} started 开始")
    path = Path(root) / "运行" / f"{today()}-{skill}-{p['run_id']}-r{p['round']}-{uuid.uuid4().hex[:8]}.json"
    # 微秒精度:同一秒内写多条时排序仍确定,恢复位置才不会读错
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    atomic_save(path, {"skill": skill, "recorded_at": recorded_at, "progress": dict(p),
                       "sources_opened": list(dict.fromkeys(sources_opened)),
                       "directions_touched": sorted(set(directions_touched)),
                       "semrush_calls": semrush_calls, "notes": list(notes)})
    return path


def _next_source(root, rows):
    if seeds.take(root, "legacy", 1):
        return "legacy", "旧数据导入的标杆种子还有待初核的,先用完"
    done = [r for r in rows if STAGE[r["skill"]] == "scan" and r["progress"]["outcome"] == "completed"
            and r["progress"]["source_kind"] in ROTATION]
    if not done:
        return ROTATION[0], "legacy 已用完,按固定轮换从 sibling 开始"
    last = done[-1]["progress"]["source_kind"]
    nxt = ROTATION[(ROTATION.index(last) + 1) % len(ROTATION)]
    return nxt, f"上次完成的发现来源是 {last},按固定轮换下一个是 {nxt}"


def _plan_quick(root, rows, run_id):
    latest = latest_runs(rows, "quick")
    active = {k: r for k, r in latest.items() if next_position(r)}
    require(run_id is None or run_id in latest, "指定的 run_id 不存在")
    conflict = run_id is None and len(active) > 1
    selected = latest.get(run_id) if run_id else (next(iter(active.values())) if len(active) == 1 else None)
    resume, action = None, "quick"
    if selected:
        if next_position(selected):
            resume = dict(selected["progress"], next_step="quick")
        else:
            action = "done"
    return {"lane": "quick", "action": None if conflict else action, "resume": resume, "conflict": conflict,
            "active_run_ids": sorted(active), "latest_log": selected["_path"] if selected else None,
            "semrush_calls_total": sum(r["semrush_calls"] for r in rows)}


def plan(root, run_id=None, lane="bench") -> dict:
    rows = records(root)
    if lane == "quick":
        return _plan_quick(root, rows, run_id)
    latest = latest_runs(rows, "bench")
    active = {k: r for k, r in latest.items() if next_position(r)}
    require(run_id is None or run_id in latest, "指定的 run_id 不存在")
    conflict = run_id is None and len(active) > 1
    selected = latest.get(run_id) if run_id else (next(iter(active.values())) if len(active) == 1 else None)
    found = sum(r["state"] == "found" for r in load_ledger(root)["directions"].values())
    source, reason = _next_source(root, rows)
    resume, action = None, "scan"
    if selected:
        cursor = next_position(selected)
        if cursor:
            resume = dict(selected["progress"], round=cursor["round"], next_step=cursor["stage"])
            action = cursor["stage"]
            if STAGE[selected["skill"]] == cursor["stage"]:
                source, reason = selected["progress"]["source_kind"], "恢复已开始的阶段,保持原来源与 seed_value"
        else:
            action = "done"
    return {"found_count": found, "action": None if conflict else action,
            "scan_outcome": "skipped" if action == "scan" and found >= FOUND_TARGET and not conflict else None,
            "resume": resume, "conflict": conflict, "active_run_ids": sorted(active),
            "next_source": source, "source_reason": reason,
            "latest_log": selected["_path"] if selected else None,
            "semrush_calls_total": sum(r["semrush_calls"] for r in rows)}


def finish(root, *, run_id, outcome="completed", sources_opened=(), directions_touched=(), semrush_calls=0,
           notes=()) -> Path:
    row = latest_runs(records(root)).get(run_id)
    require(row and row["progress"]["outcome"] in ("started", "blocked"),
            "finish 只针对 started/blocked 阶段;阶段已结束时不要重记调用数")
    require(outcome in ("completed", "blocked", "skipped"), "finish 的 outcome 须为 completed/blocked/skipped")
    p = dict(row["progress"], outcome=outcome)
    p["next_step"] = _expected_next(STAGE[row["skill"]], outcome, p["round"], p["max_rounds"])
    return record(root, skill=row["skill"], progress=p, sources_opened=sources_opened,
                  directions_touched=directions_touched, semrush_calls=semrush_calls, notes=notes)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--finish", action="store_true")
    ap.add_argument("--run-id")
    ap.add_argument("--lane", choices=("bench", "quick"), default="bench", help="--plan 看哪条道")
    ap.add_argument("--skill", choices=SKILLS)
    ap.add_argument("--round", type=int)
    ap.add_argument("--max-rounds", type=int)
    ap.add_argument("--source-kind", choices=SOURCE_KINDS)
    ap.add_argument("--seed-value")
    ap.add_argument("--outcome", choices=OUTCOMES)
    ap.add_argument("--next-step", choices=("scan", "assess", "quick", "done"))
    ap.add_argument("--source-opened", action="append", default=[])
    ap.add_argument("--direction-touched", action="append", default=[])
    ap.add_argument("--semrush-calls", type=int, default=0)
    ap.add_argument("--note", action="append", default=[])
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.plan:
            print(json.dumps(plan(root, a.run_id, a.lane), ensure_ascii=False, indent=2))
            return 0
        if a.finish:
            out = finish(root, run_id=a.run_id, outcome=a.outcome or "completed", sources_opened=a.source_opened,
                         directions_touched=a.direction_touched, semrush_calls=a.semrush_calls, notes=a.note)
        else:
            progress = {"run_id": a.run_id, "round": a.round, "max_rounds": a.max_rounds,
                        "source_kind": a.source_kind, "seed_value": a.seed_value,
                        "outcome": a.outcome, "next_step": a.next_step}
            require(all(v is not None for v in progress.values()) and a.skill,
                    "写清单须提供 --skill/--run-id/--round/--max-rounds/--source-kind/--seed-value/--outcome/--next-step")
            out = record(root, skill=a.skill, progress=progress, sources_opened=a.source_opened,
                         directions_touched=a.direction_touched, semrush_calls=a.semrush_calls, notes=a.note)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(f"已写 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`xinci-bench-workflow/xinci-bench-core/scripts/report_status.py`（整份替换）：

```python
#!/usr/bin/env python3
"""只读看板:置顶待开建的快道 go;各状态数、待深核排序、观察中剩余天数、搁置天数、go 的文档、
到期的验收节点、种子池与原料池余量、待复查淘汰、累计 Semrush 调用。"""
import argparse
import json
import sys
from datetime import date

import data_root
import ledger as L
import quick_model as QM
import quick_pool
import run_log
import seeds
from _common import BenchError, load_ledger, today

PARKED_WARN_DAYS = 90


def _quick_status(root, dirs, on) -> dict:
    pending, launched_due, watching = [], [], []
    for s, r in dirs.items():
        if r.get("lane") != "quick":
            continue
        if r["state"] == "watching":
            left = (date.fromisoformat(r["watch"]["expires_at"]) - date.fromisoformat(on)).days
            watching.append({"slug": s, "days_left": left, "expires_at": r["watch"]["expires_at"],
                             "checks": len(r["watch"]["checks"])})
        if r["state"] != "go":
            continue
        fu, base = r["follow_up"], r["model"]["scenarios"]["base"]
        if fu["status"] == "pending":
            pending.append({"slug": s, "title": r["title"], "base_visits": base["visits"],
                            "base_revenue": base["revenue"], "launch_by": fu["launch_by"],
                            "overdue": on > fu["launch_by"], "doc": str(L.doc_paths(root, s)[0])})
        elif fu["status"] == "launched":
            for m in QM.milestones(fu["launched_at"]):
                if m["date"] <= on:
                    launched_due.append({"slug": s, "day": m["day"], "date": m["date"]})
    return {"pending_go": pending, "watching": sorted(watching, key=lambda w: w["days_left"]),
            "milestones_due": launched_due, "pool_pending": len(quick_pool.pending(root))}


def status(root, on=None) -> dict:
    on = on or today()
    dirs = load_ledger(root)["directions"]
    counts = {s: sum(r["state"] == s for r in dirs.values()) for s in L.STATES}
    parked = []
    for slug, r in dirs.items():
        if r["state"] == "parked":
            days = (date.fromisoformat(on) - date.fromisoformat(r["history"][-1]["at"][:10])).days
            parked.append({"slug": slug, "days": days, "overdue": days > PARKED_WARN_DAYS,
                           "reason": r["history"][-1]["reason"]})
    go = [{"slug": s, "title": r["title"], "base_total": r["model"]["scenarios"]["base"]["total"],
           "doc": str(L.doc_paths(root, s)[0])} for s, r in dirs.items()
          if r["state"] == "go" and r.get("lane", "bench") == "bench"]
    quick = _quick_status(root, dirs, on)
    rejected = {}
    for r in dirs.values():
        if r["state"] == "rejected":
            g = r["decision"]["gate"]
            rejected[g] = rejected.get(g, 0) + 1
    return {"data_root": str(root), "counts": counts, "quick": quick, "found_ranked": L.rank(root, on),
            "parked": parked, "go": go, "rejected_by_gate": rejected, "seeds": seeds.stats(root, on),
            "semrush_calls_total": sum(r["semrush_calls"] for r in run_log.records(root))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        st = status(root)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    c, q = st["counts"], st["quick"]
    for g in q["pending_go"]:
        print(f"【立即建站】{g['slug']}:基准约 {g['base_visits']:,} 次访问、${g['base_revenue']:.2f}/月,"
              f"建议最晚 {g['launch_by']} 上线" + ("(已超期)" if g["overdue"] else "") + f" → {g['doc']}")
    for m in q["milestones_due"]:
        print(f"  验收节点到了:{m['slug']} 上线第 {m['day']} 天({m['date']}),去看 Search Console")
    print(f"数据区:{st['data_root']}")
    print(f"方向:found {c['found']} · go {c['go']} · rejected {c['rejected']} · parked {c['parked']} · 观察中 {c['watching']}")
    for w in q["watching"]:
        print(f"  观察中 {w['slug']}:还剩 {w['days_left']} 天({w['expires_at']} 到期),已复查 {w['checks']} 次")
    for row in st["found_ranked"]:
        print(f"  待深核 {row['slug']}:起量速度 {row['speed']}/月,AS {row['authority_score']}")
    for g in st["go"]:
        print(f"  go {g['slug']}:基准 ${g['base_total']}/月 → {g['doc']}")
    for p in st["parked"]:
        print(f"  搁置 {p['slug']}:{p['days']} 天" + (" (超过 90 天,请复核)" if p["overdue"] else ""))
    if st["rejected_by_gate"]:
        print("  否决按门:" + "、".join(f"{k} {v}" for k, v in st["rejected_by_gate"].items()))
    s = st["seeds"]
    print(f"种子池待初核:{s['pending'] or '无'};已初核 {s['checked']};淘汰 {s['rejected']}(到期可复查 {s['recheck_due']})")
    print(f"快道原料池待看:{q['pool_pending']}")
    print(f"累计 Semrush 调用:{st['semrush_calls_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```


- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 148 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_run_log.py" "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py" "xinci-bench-workflow/xinci-bench-core/scripts/run_log.py" "xinci-bench-workflow/xinci-bench-core/scripts/report_status.py"
git commit -m "xinci-bench 快道:运行清单单阶段与分道恢复、看板置顶立即建站与验收节点" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 契约、采集规程与命令手册加快道

**Files:**
- Modify: `xinci-bench-workflow/xinci-bench-core/选站契约.md`（目录、§0 一句、末尾加第 10 节）
- Modify: `xinci-bench-workflow/xinci-bench-core/数据采集.md`（目录、末尾加第 7 节）
- Modify: `xinci-bench-workflow/xinci-bench-core/命令与观察.md`（目录、末尾加第 7 节）
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py`（加 `QuickContractTest`）

**Interfaces:**
- Consumes: `quick_model.QUICK_ASSUMPTIONS/TASK_WORDS`、`ledger.QUICK_GATES`、`validate_ledger.REQUIRED_QUICK`、`direction.schema.json` 的 `quick_required`
- Produces: 契约第 10 节（10.1–10.8）为快道判据唯一来源；`数据采集.md` 第 7 节（7.1–7.5）为每个来源的取法；`命令与观察.md` 第 7 节（7.1–7.6）为命令与四类观察字段

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py`：把

```python
import bench_model as M
import ledger as L
import seed_import as I
import validate_ledger as V
```

替换为

```python
import bench_model as M
import ledger as L
import quick_model as QM
import seed_import as I
import validate_ledger as V
```

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py`：把

```python


class SkillTest(unittest.TestCase):
    def test_skills_named_and_point_to_contract(self):
```

替换为

```python


class QuickContractTest(unittest.TestCase):
    def test_quick_numbers_match_code(self):
        c, a = text("选站契约.md"), QM.QUICK_ASSUMPTIONS
        s = a["share"]
        lo, hi = a["anchor_ratio"]
        for needle in (f"**{a['version']}**", f"{s['low']:.0%} / {s['base']:.0%} / {s['high']:.0%}",
                       f"×{a['aio_factor']}", f"{a['threshold_visits']:,} 访问", f"{a['single_site_visits']:,} 访问",
                       f"${a['rpm_adsense']:.0f}/千访问", f"≤ {a['new_days']} 天", f"| 观察期 | {a['watch_days']} 天 |",
                       f"峰值 × {a['oneoff_ratio']:.0%}", f"前 7 天 × {a['trend_floor']:.0%}", f"{lo}–{hi:g}",
                       f"| 原料保留 | {a['pool_days']} 天 |", f"{a['max_serp_per_run']} 个词", f"判 go 后 {a['launch_days']} 天",
                       " / ".join(str(m) for m in a["milestones"]) + " 天", f"基准预计 × {a['stop_ratio']:.0%}"):
            self.assertIn(needle, c)

    def test_task_words_and_quick_gates_documented(self):
        c = text("选站契约.md")
        self.assertIn("、".join(QM.TASK_WORDS), c)
        for g in L.QUICK_GATES:
            self.assertIn(f"`{g}`", c)

    def test_direction_schema_quick_required(self):
        s = json.loads(text("数据结构/direction.schema.json"))
        self.assertEqual(tuple(s["quick_required"]), V.REQUIRED_QUICK)


class SkillTest(unittest.TestCase):
    def test_skills_named_and_point_to_contract(self):
```


- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `FAILED (failures=2)`，首个报错 `AssertionError: '**2026-10-13.q1**' not found in <选站契约.md 全文>`（契约里还没有快道假设表与任务词）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/选站契约.md`：把

```markdown
- [8. 决策书与建站简报](#8-决策书与建站简报)
- [9. 停机与错误](#9-停机与错误)

## 0. 定位与边界

从近 24 个月起量的低权重小站倒推建站方向，判断"上线后 12 个月内单站做到 $100/月"的把握；产出决策书，go 时附建站简报。

用户 2026-10-13 定的口径（改之前先问用户）：
```

替换为

```markdown
- [8. 决策书与建站简报](#8-决策书与建站简报)
- [9. 停机与错误](#9-停机与错误)
- [10. 新词快道](#10-新词快道)
  - [10.1 定位与口径](#101-定位与口径)
  - [10.2 一次运行的七步](#102-一次运行的七步)
  - [10.3 状态与否决门](#103-状态与否决门)
  - [10.4 速判六条](#104-速判六条)
  - [10.5 量级换算与判定](#105-量级换算与判定)
  - [10.6 快道假设表](#106-快道假设表)
  - [10.7 强烈推荐与建站跟进](#107-强烈推荐与建站跟进)
  - [10.8 快道决策书](#108-快道决策书)

## 0. 定位与边界

从近 24 个月起量的低权重小站倒推建站方向，判断"上线后 12 个月内单站做到 $100/月"的把握；产出决策书，go 时附建站简报。另有一条新词快道（第 10 节），专抓刚冒出来、还没人做的新词。

用户 2026-10-13 定的口径（改之前先问用户）：
```

`xinci-bench-workflow/xinci-bench-core/选站契约.md`：把

````markdown
- Google /sorry：两次请求间隔 ≥ 60 秒；已触发就静置约 1 小时，仍触发记 blocked。
- 数据区未配置：脚本退出码 2，先问用户，不猜位置。
````

替换为

````markdown
- Google /sorry：两次请求间隔 ≥ 60 秒；已触发就静置约 1 小时，仍触发记 blocked。
- 数据区未配置：脚本退出码 2，先问用户，不猜位置。

## 10. 新词快道

设计依据见 `docs/superpowers/specs/2026-10-13-xinci-bench-quick-lane-design.md`。快道记录 `lane=quick`；标杆道（`lane=bench`）的第 1–9 节不变。

### 10.1 定位与口径

专抓最近 1 周到 3 个月才出现、首页还没有专门页面、而且会反复被搜的新词：判断我们第一个做，上线 90 天内能否有一个月达到 10,000 美区访问；能就判 go 并强烈推荐用户建站，用户自己建。

用户 2026-10-13 定的口径（改之前先问用户）：暗号 `xinci_bench_quick_run` 手动触发，不做定时任务；门槛与首发份额见 10.6；Steam、Roblox 不绕道取数；go 时四处强推（10.7）。

### 10.2 一次运行的七步

1. 先提醒：跟进状态为"待开建"的快道 go 放汇报最前面再推荐一次；列出到期的验收节点。
2. 复查观察中：每个 watching 方向写新的量级与速判观察，`ledger.py watch-check` 记一次复查并给建议，按建议用 `settle.py` 转 go 或否决。
3. 扫信号：按 `数据采集.md` §7 取新对象与新说法，写一份 `quick_signal` 观察，`quick_pool.py add` 进原料池；与已有方向、旧裁决、快道淘汰记录去重。
4. 零成本速判：Q1–Q4（10.4），不花 Semrush、不看 Google。
5. 首屏速判：内置浏览器判 Q5、Q6，两次请求间隔 ≥ 60 秒，每次运行最多看 10 个词。
6. 登记、测算、结算：六条全过才 `ledger.py register-quick`（速判观察里的词须是登记的说法之一）；写量级观察与简报素材，按 10.5 判定，经 `settle.py` 结算。
7. 推荐与汇报：出 go 按 10.7 推荐；汇报各来源扫了多少、各步筛掉多少、观察中剩几个和剩余天数、Semrush 调用数。

### 10.3 状态与否决门

```
found    → go | rejected | parked | watching
watching → go | rejected
parked   → go | rejected
```

速判不过的词不登记，只进快道淘汰记录（`quick_pool.py reject`），同一个词不再看；Q5 不过且占位的是小站时加 `--seed-domain`，同时登记为标杆道种子（来源 serp）。已登记方向的否决门：

| 门 | 条件 | 最少证据 |
| --- | --- | --- |
| `scope` | 范围排除命中（同第 1 节） | 最新速判 Q4 不过，加 `--scope-hit` |
| `not_new` | 对象首次公开超过 90 天，或老东西换名 | 最新速判 Q1 不过 |
| `oneoff` | 新闻热点、一次性需求、冲高回落 | 最新速判 Q3 不过，或量级曲线冲高回落 |
| `occupied` | 首页已有页面完整做了这个任务 | 最新速判 Q5 不过（写 `occupied_by`）；那个站若是小站，用 `seeds.py add --source serp` 登记为标杆道种子 |
| `answered` | AI 概览或原生组件已答完 | 最新速判 Q6 不过 |
| `volume` | 观察 30 天到期仍不够，或量不够且趋势在降 | 最新量级观察，模型重算一致 |

`parked`：Trends 读不出、首页预检重试仍失败、对象发布日期查不到。

### 10.4 速判六条

前四条零成本，过了才看 Google 首页；前一条已不过时后面的填 null。

| 编号 | 条件 | 判法 |
| --- | --- | --- |
| Q1 真新 | 对象首次公开 ≤ 90 天 | 从对象自己的发布页、商店页、仓库首个版本读日期，不信来源的"新"标签；`register-quick` 按速判观察日期强制 90 天 |
| Q2 有人在搜 | 至少一项证据 | 自动补全出现该说法，或 Trends 曲线可读；没证据不否决，原料保留 7 天 |
| Q3 不是一次性 | 四项都满足 | 任务反复发生；不是新闻事件驱动；对象在涨或持平；不冲高回落（10.5） |
| Q4 范围 | 五条排除未命中 | 同第 1 节 |
| Q5 没人做 | 首页前 10 条无页面完整做了这个任务 | "完整做了"同第 4 节；新闻、论坛、视频、官方公告不算 |
| Q6 没被答完 | AI 概览或原生组件没答完 | 同 `数据采集.md` §4 |

任务词：calculator、codes、tracker、tier list、map、checker、generator、converter、build、value。

### 10.5 量级换算与判定

- **锚词换算**：同一次 Trends 查询放新词与锚词，取最近 7 天均值比值；`当前月搜索量 = 锚词月量 × 比值`，同时报 30 天。锚词优先旧词库里 90 天内测过、无季节性的词，没有再用 Semrush。**比值须在 0.2–5 之间**，否则换锚词（`write_observation.py` 拒收）。
- **预计月访问** = floor(当前月搜索量 × 首发份额 × AI 概览系数)，按当前量，不外推增长。
- **趋势不降**：最近 7 天均值 ≥ 前 7 天均值 × 80%；**冲高回落**：最近 7 天均值 < 近 30 天峰值 × 30%。

| 结论 | 条件 |
| --- | --- |
| go | 六条全过；基准 ≥ 10,000 访问；不冲高回落；简报素材写明 ≤ 3 天能做出、数据拿得到；锚词测量 ≤ 90 天 |
| watching | 六条全过；基准 < 10,000；趋势不降；不冲高回落 |
| rejected | 见 10.3 |

### 10.6 快道假设表

版本 **2026-10-13.q1**，数值写在 `quick_model.QUICK_ASSUMPTIONS`，两边必须一致。

| 项目 | 值 |
| --- | --- |
| 首发份额 保守/基准/乐观 | 10% / 20% / 30% |
| AI 概览在场未答完系数 | ×0.6 |
| go 门槛（基准，上线 90 天内单月） | 10,000 访问 |
| 单站就能到 $100 | 25,000 访问 |
| 收入展示 | AdSense $4/千访问 |
| 真新 | 对象首次公开 ≤ 90 天 |
| 观察期 | 30 天 |
| 冲高回落 | 最近 7 天均值 < 峰值 × 30% |
| 趋势不降 | 最近 7 天均值 ≥ 前 7 天 × 80% |
| 锚词比值区间 | 0.2–5 |
| 原料保留 | 7 天 |
| 每次运行首屏上限 | 10 个词 |
| 建议最晚上线 | 判 go 后 7 天 |
| 验收节点 | 上线后 14 / 30 / 90 天 |
| 止损 | 第 30 天月点击 < 基准预计 × 25% |

### 10.7 强烈推荐与建站跟进

判 go 当次，四处同时出现，直到跟进状态改为"已开建"或"放弃"：

1. 推送通知：方向、基准访问与收入、建议最晚上线日期。
2. 运行汇报第一行：以"【立即建站】"开头。
3. 决策书开头 `## 立即建站` 一节（html 加底色）。
4. 看板顶部常驻（`report_status.py` 第一屏）。

跟进状态 `follow_up.status`：pending（待开建）→ started（已开建，须写域名）→ launched（已上线，验收节点由上线日起算），任何时候可 abandoned（须写理由）；用 `ledger.py follow-up` 改，只能前进，日期写 YYYY-MM-DD，开建不早于判 go、上线不早于开建，不改 `state`。

验收节点：上线第 14 天看收录与展现；第 30 天月点击低于基准预计 25% 即止损（不再加工时，站留着）；第 90 天单月 ≥ 10,000 访问算成功。用户记录的点击与收入写进 `反馈/`。

### 10.8 快道决策书

只由 `build_quick_doc.py` 生成（`settle.py` 会调用），纪律同第 8 节。结构：立即建站（仅 go）、结论、第一部分决策（新对象与新说法、有人在搜、不是一次性、首页现场与 GEO、预计访问与收入、风险与最大未知）、第二部分最小版本建站简报（仅 go：做什么、页面清单、数据、上线清单、预计访问与收入、验收与止损）、证据清单。
````

`xinci-bench-workflow/xinci-bench-core/数据采集.md`：把

```markdown
- [5. 旧数据导入规则](#5-旧数据导入规则)
- [6. 已知的坑](#6-已知的坑)

## 1. 通道分工
```

替换为

```markdown
- [5. 旧数据导入规则](#5-旧数据导入规则)
- [6. 已知的坑](#6-已知的坑)
- [7. 快道数据来源](#7-快道数据来源)
  - [7.1 快道的通道分工](#71-快道的通道分工)
  - [7.2 搜索侧](#72-搜索侧)
  - [7.3 上游新对象](#73-上游新对象)
  - [7.4 现场](#74-现场)
  - [7.5 确认不可用](#75-确认不可用)

## 1. 通道分工
```

`xinci-bench-workflow/xinci-bench-core/数据采集.md`：把

```markdown
- 面板和 Chrome 的出口 IP 不在美国，部分站被 Cloudflare 拦。
- 写观察前先用 `date -u +%Y-%m-%dT%H:%M:%S+00:00` 取系统时间，不要估。
```

替换为

```markdown
- 面板和 Chrome 的出口 IP 不在美国，部分站被 Cloudflare 拦。
- 写观察前先用 `date -u +%Y-%m-%dT%H:%M:%S+00:00` 取系统时间，不要估。

## 7. 快道数据来源

2026-10-13 从本机逐个实测。未在本次运行实际取回的来源不得写"已检查"；实际打开的网址记进观察 `source_urls`。

### 7.1 快道的通道分工

| 通道 | 用于 |
| --- | --- |
| curl / 脚本 | 自动补全（`suggest_snapshot.py`）、Trends 热搜 RSS、各公开接口与订阅源 |
| 内置浏览器 | Trends 曲线与飙升词（在 trends 页面里调用内部接口）、Google 首页、Reddit（经 Google 搜索）、Google Play |
| 用户的 Chrome | 只在旧词库没有合适锚词时，用 Semrush 查锚词月量 |

社区类条目（Product Hunt、Reddit）有潜力的要在真实浏览器读原页，看人们怎么称呼它。

### 7.2 搜索侧

| 来源 | 获取方式 | 取什么 | 限制与实测 |
| --- | --- | --- | --- |
| Google 自动补全 | `suggest_snapshot.py --object "<对象名>"`：请求 `https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=us&q=<查询>`，返回 `[原查询, [≤10 条建议]]` | 对"对象名 + 空格"和"对象名 + 每个任务词"各取一次；快照存 `快道/补全快照/`，以前所有快照里都没出现过的才算新说法，并给出与上次的间隔天数 | 可用。**同一查询隔几秒请求两次结果也会不同**，所以只认"从没出现过"；频率上限未确认，脚本间隔 1 秒；取数失败不写快照 |
| Trends 曲线 | 内置浏览器打开 `https://trends.google.com/trends/explore?geo=US&q=<词>`，页内 `fetch('/trends/api/explore?hl=en-US&tz=0&req=<JSON>')`，切掉返回体前缀 `)]}'`，取 `TIMESERIES` 的 request 与 token，再请求 `/trends/api/widgetdata/multiline?req=…&token=…` | `timelineData[].value`；`now 7-d` 逐小时、`today 1-m` 逐日、`today 3-m` | 可用；两次请求间隔 ≥ 1.5 秒，curl 直接请求 429 |
| Trends 飙升词 | 同上，取 `RELATED_QUERIES` 的 request 与 token，请求 `/trends/api/widgetdata/relatedsearches` | `rankedList[0]` 热门、`rankedList[1]` 飙升（百分比或 Breakout）；对新对象查，也对任务词以 `now 7-d` 查 | 可用；如 "grow a garden 2 weather tracker" +200% |
| 锚词换算 | 同上，一次请求放新词与锚词两个 `comparisonItem`（`today 1-m`） | 两条曲线最近 7 天与 30 天均值 → `quick_model.anchor_estimate` | 比值须 0.2–5；低量词是噪声大的小整数 |
| Trends 热搜 RSS | `curl https://trends.google.com/trending/rss?geo=US` | `title`、`ht:approx_traffic`、`ht:news_item_title`、`ht:news_item_url` | 可用；基本是新闻，主要用来判 Q3 新闻热点 |
| Semrush | 用户 Chrome，Keyword Overview | 锚词月量 | 新词自身量多久出现未确认，首次运行时测 |

### 7.3 上游新对象

| 来源 | 获取方式 | 取什么 | 实测 |
| --- | --- | --- | --- |
| SteamCharts（代替 Steam） | `curl https://steamcharts.com/top`（HTML 表）；单款 `https://steamcharts.com/app/<id>` | app id、名称、当前在线人数；与上次比出新进榜；单款在线人数走势。无发布日期，Q1 改从 Wikipedia 或 Google 读 | 可用 |
| Roblox | 不直接取：用自动补全与 Trends 盯 "roblox" 加任务词的飙升，再看 YouTube | 新体验名与任务说法 | 官方与第三方统计站都取不到 |
| Apple 免费榜 | `curl https://rss.applemarketingtools.com/api/v2/us/apps/top-free/50/apps.json` | `name`、`releaseDate`、`url`（`genre` 过滤无效，游戏不能单独筛） | 可用 |
| iTunes 搜索 | `curl "https://itunes.apple.com/search?term=<词>&country=us&entity=software"` | `trackName`、`releaseDate`、`primaryGenreName`；核发布日期、看有没有配套 App | 可用 |
| Google Play | 内置浏览器读 `https://play.google.com/store/games?hl=en&gl=US` | 新上榜游戏名 | 未实测 |
| Product Hunt | `curl https://www.producthunt.com/feed`（Atom） | `title`、`link`、`published`、`content` | 可用 |
| GitHub | `curl "https://github.com/trending?since=daily"`；`gh api "search/repositories?q=created:>YYYY-MM-DD&sort=stars&order=desc"` | 仓库名、`created_at`、`stargazers_count` | 可用；未登录搜索每分钟 10 次 |
| Hacker News | `curl "https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&numericFilters=points>50"` | `title`、`url`、`points`、`created_at` | 可用 |
| YouTube 搜索 | `curl "https://www.youtube.com/results?search_query=<词>"` | 页面内视频条目数与发布时间（相对时间），看创作者是否跟进 | 可用但易碎，出口不在美国，页面为繁体中文（香港） |
| Wikipedia 浏览量 | `curl https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/<词条>/daily/<YYYYMMDD>/<YYYYMMDD>` | 每日 `views`，对象热度的绝对参照与持续性 | 可用 |
| 平台规则与政策 | `curl "https://www.federalregister.gov/api/v1/documents.json?order=newest"`；其他辖区见旧新词工作流 `数据采集指南.md` | `title`、`publication_date`、`type`、`abstract` | 可用 |

### 7.4 现场

- Google 首页：同第 4 节规程（美区三参、预检四项、请求间隔 ≥ 60 秒）。
- Reddit：接口返回 403；内置浏览器搜 Google `site:reddit.com "<对象>" (calculator OR tracker OR tool)`，加 `tbs=qdr:w` 只看过去一周。

### 7.5 确认不可用

Steam 官方接口（curl 连接失败、内置浏览器被拒、Chrome 错误页）、SteamSpy（Cloudflare 挑战）、Roblox 官网与接口（三条通道都打不开）、RoMonitor 与 RoTrends（curl 只得脚本外壳）、Reddit 接口（403）、Trends 接口直接 curl（429）、Google 搜索页直接 curl（脚本外壳）。Exploding Topics 等付费趋势工具没有账号，不用。
```

`xinci-bench-workflow/xinci-bench-core/命令与观察.md`：把

```markdown
- [5. 结算](#5-结算)
- [6. 看板与校验](#6-看板与校验)

## 1. 初始化与导入
```

替换为

```markdown
- [5. 结算](#5-结算)
- [6. 看板与校验](#6-看板与校验)
- [7. 新词快道](#7-新词快道)
  - [7.1 运行清单](#71-运行清单)
  - [7.2 扫信号与原料池](#72-扫信号与原料池)
  - [7.3 速判观察](#73-速判观察)
  - [7.4 登记](#74-登记)
  - [7.5 量级观察与简报素材](#75-量级观察与简报素材)
  - [7.6 结算、观察中与建站跟进](#76-结算观察中与建站跟进)

## 1. 初始化与导入
```

`xinci-bench-workflow/xinci-bench-core/命令与观察.md`：把

````markdown
python3 -m unittest discover -s $S/tests -t $S/tests -q
```
````

替换为

````markdown
python3 -m unittest discover -s $S/tests -t $S/tests -q
```

## 7. 新词快道

### 7.1 运行清单

```bash
python3 $S/run_log.py --plan --lane quick
python3 $S/run_log.py --skill xinci-bench-quick --run-id quick-20261014-a --round 1 --max-rounds 1 \
  --source-kind quick --seed-value "自动补全、Trends 飙升、SteamCharts、Product Hunt" --outcome started --next-step quick
python3 $S/run_log.py --finish --run-id quick-20261014-a --outcome completed --semrush-calls 1 --note "扫 40 条原料,登记 1 个"
```

快道一次运行只有一个阶段：`round` 与 `max-rounds` 固定为 1，`source-kind` 固定为 `quick`；受阻用 `--outcome blocked`，之后同一运行编号再 `--finish`。快道与标杆道的未完成运行互不阻塞。

### 7.2 扫信号与原料池

```bash
python3 $S/suggest_snapshot.py --object "Grow a Garden 2"          # 对象名 + 空格,以及对象名 + 10 个任务词
python3 $S/suggest_snapshot.py --query "grow a garden 2 calculator"
python3 $S/write_observation.py --input <quick_signal 观察文件>
python3 $S/quick_pool.py add --observation 证据/_quick/<文件名>
python3 $S/quick_pool.py pending
python3 $S/quick_pool.py expire                                     # 7 天没拿到"有人在搜"证据的标 expired
python3 $S/quick_pool.py mark --id <原料 id> --status used
python3 $S/quick_pool.py reject --term "<说法>" --gate occupied --observation 证据/<方向>/<速判观察> --seed-domain <占位小站>
```

快道观察的公共字段同 §3.1，`stage` 固定为 `quick`。`quick_signal` 一批一份，`slug` 为 null：

```json
{
  "kind": "quick_signal",
  "readings": {
    "items": [
      {
        "source": "autocomplete",               // autocomplete | trends_rising | trends_rss | steamcharts | apple | itunes | google_play | producthunt | github | hackernews | youtube | wikipedia | policy | reddit | other
        "object": "Grow a Garden 2",            // 催生新说法的对象
        "term": "grow a garden 2 calculator",   // 冒出的任务说法;只有对象时为 null
        "url": "https://suggestqueries.google.com/complete/search?q=grow%20a%20garden%202%20",  // 实际取回的网址
        "seen_at": "2026-10-14"                 // 看到日期
      }
    ]
  }
}
```

### 7.3 速判观察

每个拟登记方向一份，`slug` 写拟用的方向名；Q5、Q6 有结论时必须带通过的 `browser_preflight`。

```json
{
  "kind": "quick_screen",
  "readings": {
    "term": "grow a garden 2 calculator",
    "checks": {                                  // 恰好 Q1–Q6;pass 为 true/false/null(前项已不过才可 null)
      "Q1": {"pass": true, "basis": "官方发布页 2026-09-28"},
      "Q2": {"pass": true, "basis": "自动补全出现 grow a garden 2 calculator"},
      "Q3": {"pass": true, "basis": "每局都要算;Wikipedia 浏览量持平"},
      "Q4": {"pass": true, "basis": "游戏工具,不涉排除项"},
      "Q5": {"pass": true, "basis": "首页为 reddit、YouTube、官方 Discord"},
      "Q6": {"pass": true, "basis": "无 AI 概览"}
    },
    "ai_overview": {"present": false, "completes_task": false, "cited_domains": []},
    "top10": [{"pos": 1, "domain": "reddit.com", "type": "forum", "completes_task": false}],
    "occupied_by": null                          // Q5 不过时写完整做了任务的页面域名
  }
}
```

速判不过：`quick_pool.py reject` 记淘汰；Q5 不过且占位的是小站时加 `--seed-domain <域名>`，同时登记为标杆道种子（来源 serp），交给标杆道。`--seed-domain` 只在 `--gate occupied` 时可用。

### 7.4 登记

```json
{
  "slug": "gag2-calculator",
  "title": "Grow a Garden 2 价格计算器",
  "site_type": "tool",
  "object": {"name": "Grow a Garden 2", "first_public": "2026-09-28", "date_source": "<发布页网址>"},
  "terms": [{"term": "grow a garden 2 calculator", "source": "autocomplete", "first_seen": "2026-10-14"}],
  "screen": "证据/gag2-calculator/<速判观察文件名>",
  "reason": "速判六条全过"
}
```

```bash
python3 $S/ledger.py register-quick --input <上面的文件>
```

`screen` 指向的速判观察里的 `term` 须是 `terms` 之一（大小写与空格不计）；同一说法不能属于两个方向。

### 7.5 量级观察与简报素材

```json
{
  "kind": "quick_volume",
  "readings": {
    "anchor_term": "<旧词库里量级接近的词>",   // python3 $S/lexicon.py --match <词> 找
    "anchor_volume": 9900,
    "anchor_source": "lexicon",                 // lexicon | semrush
    "anchor_measured_at": "2026-10-08",         // 判 go 时须在 90 天内
    "window_days": 7,
    "new_mean_7d": 54.0, "anchor_mean_7d": 96.0,
    "new_mean_30d": 44.0, "anchor_mean_30d": 90.0,
    "ratio_7d": 0.5625,                          // 须等于 new_mean_7d ÷ anchor_mean_7d,且在 0.2–5 之间
    "estimate_7d": 5569,                         // anchor_volume × ratio_7d 取整
    "estimate_30d": 4840,
    "series_30d": [0, 0, 11, 13, 20]             // 30 天逐日新词值(至少 14 个点)
  }
}
```

```json
{
  "kind": "quick_brief",
  "readings": {
    "positioning": "输入作物与天气,算出售价",
    "pages": [{"path": "/", "target_query": "grow a garden 2 calculator", "deliverable": "按作物与突变算价格"}],
    "data_sources": ["社区 wiki 价格表"],
    "license": "事实数据,自行整理",
    "update_frequency": "随游戏更新",
    "build_days": 2,                             // 判 go 须 ≤ 3
    "data_available": true,                      // 判 go 须为 true
    "hosting": "Cloudflare Pages 免费版",
    "risks": ["游戏热度可能三个月内回落"]
  }
}
```

```bash
python3 $S/ledger.py update --slug gag2-calculator --patch <只含要改字段的 JSON,通常为 {}> --ref 证据/gag2-calculator/<量级观察> --ref ...
python3 $S/ledger.py quick-preview --slug gag2-calculator     # 结算前预览三档与建议
```

### 7.6 结算、观察中与建站跟进

```bash
python3 $S/settle.py --slug gag2-calculator --verdict go --reason "首页没人做,基准 1 万" --biggest-unknown "新域名多久能排上去"
python3 $S/settle.py --slug gag2-calculator --verdict watching --reason "量不够但在涨" --biggest-unknown "能否涨到 5 万"
python3 $S/ledger.py watch-check --slug gag2-calculator --ref 证据/gag2-calculator/<新量级观察>   # 复查,给建议
python3 $S/settle.py --slug gag2-calculator --verdict rejected --gate volume --reason "30 天没涨够" --biggest-unknown "无"
python3 $S/ledger.py follow-up --slug gag2-calculator --status started --domain gag2calc.com
python3 $S/ledger.py follow-up --slug gag2-calculator --status launched --date 2026-10-25
python3 $S/ledger.py follow-up --slug gag2-calculator --status abandoned --reason "热度回落"
```

`--date` 缺省为今天，须为 YYYY-MM-DD；开建日期不早于判 go 日期，上线日期不早于开建日期。
````


- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 151 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py" "xinci-bench-workflow/xinci-bench-core/选站契约.md" "xinci-bench-workflow/xinci-bench-core/数据采集.md" "xinci-bench-workflow/xinci-bench-core/命令与观察.md"
git commit -m "xinci-bench 快道:选站契约第 10 节、数据来源取法、命令与观察手册" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 快道 skill、README 与双环境接入

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-quick/SKILL.md`
- Modify: `xinci-bench-workflow/xinci-bench-scan/SKILL.md`、`xinci-bench-workflow/xinci-bench-assess/SKILL.md`、`xinci-bench-workflow/xinci-bench-run/SKILL.md`、`xinci-bench-workflow/xinci-bench-status/SKILL.md`（末尾各加一行：汇报前先读看板的立即建站行）
- Modify: `xinci-bench-workflow/README.md`
- Modify: `README.md`（仓库根）
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py`（`SkillTest` 名单加 `xinci-bench-quick`）

**Interfaces:**
- Consumes: 契约第 10 节与命令手册第 7 节的章节号（SKILL.md 按章节号引用）
- Produces: skill `xinci-bench-quick`（暗号 `xinci_bench_quick_run`），软链到 `~/.claude/skills/` 与 `~/.codex/skills/`

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py`：把

```python
class SkillTest(unittest.TestCase):
    def test_skills_named_and_point_to_contract(self):
        for name in ("xinci-bench-scan", "xinci-bench-assess", "xinci-bench-status", "xinci-bench-run"):
            body = (WORKFLOW / name / "SKILL.md").read_text(encoding="utf-8")
            m = re.match(r"---\nname: (\S+)\ndescription: '(.+)'\n---\n", body)
```

替换为

```python
class SkillTest(unittest.TestCase):
    def test_skills_named_and_point_to_contract(self):
        for name in ("xinci-bench-scan", "xinci-bench-assess", "xinci-bench-status", "xinci-bench-run",
                     "xinci-bench-quick"):
            body = (WORKFLOW / name / "SKILL.md").read_text(encoding="utf-8")
            m = re.match(r"---\nname: (\S+)\ndescription: '(.+)'\n---\n", body)
```


- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `FAILED (errors=1)`，首个报错 `FileNotFoundError: [Errno 2] No such file or directory: '/Users/vito.wu/IdeaProjects/workflow-skills/xinci-bench-workflow/xinci-bench-quick/SKILL.md'`（xinci-bench-quick/SKILL.md 还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-quick/SKILL.md`（新建）：

```markdown
---
name: xinci-bench-quick
description: '新词快道：暗号 xinci_bench_quick_run 或 /xinci-bench-quick。抓最近 1 周到 3 个月才冒出来、首页还没人做、会反复被搜的新词（新游戏、新产品、新规则带出的 calculator/codes/tracker 等任务），锚词换算 Trends 量级，预计上线 90 天内单月 ≥1 万美区访问就判 go 并强烈推荐建站。不是 xinci_bench_run（标杆道）。'
---

# 新词快道

行动前读 `xinci-bench-workflow/xinci-bench-core/选站契约.md` 第 10 节与第 1、7 节，`数据采集.md` 第 4、6、7 节；命令与观察字段见 `命令与观察.md` 第 7 节。脚本都在 `xinci-bench-workflow/xinci-bench-core/scripts/`。暗号即授权既定的观察、账本、原料池和清单写入，不重复确认。

1. `report_status.py` 确认数据区；未配置才问用户。`run_log.py --plan --lane quick`：有未完成的快道运行就恢复它；没有才写 started 清单（运行编号字母数字连字符）。
2. **先提醒**：看板里每个"【立即建站】"行原样放进汇报最前面；验收节点到了的一并提醒。
3. **复查观察中**：每个 watching 方向重测量级（必要时重看首页），写新观察，`ledger.py watch-check --slug <方向> --ref <新观察>`；建议是 go 或否决就用 `settle.py` 结算，建议是 watching 就继续观察。
4. **扫信号**：`quick_pool.py expire`；按 `数据采集.md` 第 7 节取上游新对象与 Trends 飙升词，对新对象跑 `suggest_snapshot.py --object`；把取回的对象与说法写成一份 `quick_signal` 观察，`quick_pool.py add`。没在本次实际取回的来源不写"已检查"。
5. **零成本速判** Q1–Q4，再对剩下的用内置浏览器看首页判 Q5、Q6（两次请求间隔 ≥ 60 秒，每次最多 10 个词）。每个词写一份 `quick_screen` 观察；不过的 `quick_pool.py reject`；Q5 不过且占位的是小站，加 `--seed-domain` 同时登记为标杆道种子。
6. **登记与测算**：六条全过的 `ledger.py register-quick`；挑量级接近的锚词（先 `lexicon.py`，没有再用 Semrush），在 Trends 页面做锚词换算，写 `quick_volume`；预计能过线的写 `quick_brief`；`ledger.py update --ref` 引用后 `ledger.py quick-preview` 看三档。
7. **结算**：按预览建议 `settle.py --verdict go|watching|rejected|parked`，`--reason` 一句理由，`--biggest-unknown` 写最可能让结论翻转的一项；全部结束后 `validate_ledger.py`，再 `run_log.py --finish`。
8. **出 go 时强烈推荐**（缺一不可）：
   - 调用推送通知工具，内容含方向、基准访问与收入、建议最晚上线日期；
   - 汇报第一行以"【立即建站】"开头，写方向、基准访问与收入、建议最晚上线日期、决策书路径；
   - 说明决策书开头的"立即建站"一节，以及之后每次运行都会再提醒，直到用户说已开建或放弃（用 `ledger.py follow-up` 记）。

汇报：各来源取回多少、原料去重后多少、各速判条不过多少、登记多少、go / 观察中 / 否决（按门）/ 搁置数、观察中剩余天数、Semrush 调用数。不建站、不改假设表；用户说已开建、已上线或放弃时，照用户说的用 `ledger.py follow-up` 记。
```

`xinci-bench-workflow/xinci-bench-scan/SKILL.md`：把

```markdown

不做深核与 SERP 现场；不改门槛；登录失效、额度用完或验证码时 `--finish --outcome blocked` 并报告现象。
```

替换为

```markdown

不做深核与 SERP 现场；不改门槛；登录失效、额度用完或验证码时 `--finish --outcome blocked` 并报告现象。

汇报前先跑 `report_status.py`：看板第一屏有"【立即建站】"行时，原样放在汇报最前面（新词快道的 go 在用户标已开建或放弃之前，每次都要再推荐一次）。
```

`xinci-bench-workflow/xinci-bench-assess/SKILL.md`：把

```markdown

不改门槛和假设表；取到"内容类/游戏类 RPM""Journey RPM""付费转化率"的证据时，写进观察 points 并在汇报里单独列出，由用户决定是否升版。建不建站由用户决定。
```

替换为

```markdown

不改门槛和假设表；取到"内容类/游戏类 RPM""Journey RPM""付费转化率"的证据时，写进观察 points 并在汇报里单独列出，由用户决定是否升版。建不建站由用户决定。

汇报前先跑 `report_status.py`：看板第一屏有"【立即建站】"行时，原样放在汇报最前面（新词快道的 go 在用户标已开建或放弃之前，每次都要再推荐一次）。
```

`xinci-bench-workflow/xinci-bench-run/SKILL.md`：把

```markdown

收尾汇报：k/N 轮、初核域名数与通过数、登记方向数、go/rejected（按 gate）/parked 数、每个 go 的方向与基准收入与决策书路径、取到的未确认假设证据、Semrush 累计调用、种子池余量、下次来源。建不建站由用户决定。
```

替换为

```markdown

收尾汇报：k/N 轮、初核域名数与通过数、登记方向数、go/rejected（按 gate）/parked 数、每个 go 的方向与基准收入与决策书路径、取到的未确认假设证据、Semrush 累计调用、种子池余量、下次来源。建不建站由用户决定。

汇报前先跑 `report_status.py`：看板第一屏有"【立即建站】"行时，原样放在汇报最前面（新词快道的 go 在用户标已开建或放弃之前，每次都要再推荐一次）。
```

`xinci-bench-workflow/xinci-bench-status/SKILL.md`：把

```markdown
2. 需要时再跑 `run_log.py --plan` 看恢复位置、下次来源；跑 `validate_ledger.py` 看账本是否有错。
3. 汇报时先给结论（有没有 go、下一步该做什么），再列数字；搁置超过 90 天的单独提醒；validator 有错时如实列出，不当作正常状态。
```

替换为

```markdown
2. 需要时再跑 `run_log.py --plan` 看恢复位置、下次来源；跑 `validate_ledger.py` 看账本是否有错。
3. 汇报时先给结论（有没有 go、下一步该做什么），再列数字；搁置超过 90 天的单独提醒；validator 有错时如实列出，不当作正常状态。

汇报前先跑 `report_status.py`：看板第一屏有"【立即建站】"行时，原样放在汇报最前面（新词快道的 go 在用户标已开建或放弃之前，每次都要再推荐一次）。
```

`xinci-bench-workflow/README.md`：把

```markdown
| [assess](xinci-bench-assess/SKILL.md) | 六步深核、标杆份额法测算、结算并生成决策书与建站简报 |
| [run](xinci-bench-run/SKILL.md) | `xinci_bench_run max_rounds=N`，默认 3 轮；出 go 不停，跑满预算 |
| [status](xinci-bench-status/SKILL.md) | 只读看板 |
| [选站契约](xinci-bench-core/选站契约.md) | 唯一判据；[数据采集](xinci-bench-core/数据采集.md)管通道与坑；[命令与观察](xinci-bench-core/命令与观察.md)管调用 |

设计稿：[docs/superpowers/specs/2026-10-13-xinci-bench-workflow-design.md](../docs/superpowers/specs/2026-10-13-xinci-bench-workflow-design.md)。

## 首次使用
```

替换为

```markdown
| [assess](xinci-bench-assess/SKILL.md) | 六步深核、标杆份额法测算、结算并生成决策书与建站简报 |
| [run](xinci-bench-run/SKILL.md) | `xinci_bench_run max_rounds=N`，默认 3 轮；出 go 不停，跑满预算 |
| [quick](xinci-bench-quick/SKILL.md) | 新词快道，暗号 `xinci_bench_quick_run`：找近 90 天冒出、首页还没人做的任务词，速判 Q1–Q6、锚词换算量级，go 时强推立即建站 |
| [status](xinci-bench-status/SKILL.md) | 只读看板 |
| [选站契约](xinci-bench-core/选站契约.md) | 唯一判据；[数据采集](xinci-bench-core/数据采集.md)管通道与坑；[命令与观察](xinci-bench-core/命令与观察.md)管调用 |

设计稿：[docs/superpowers/specs/2026-10-13-xinci-bench-workflow-design.md](../docs/superpowers/specs/2026-10-13-xinci-bench-workflow-design.md)；新词快道见 [docs/superpowers/specs/2026-10-13-xinci-bench-quick-lane-design.md](../docs/superpowers/specs/2026-10-13-xinci-bench-quick-lane-design.md)。

## 首次使用
```

`xinci-bench-workflow/README.md`：把

````markdown

```bash
for s in xinci-bench-scan xinci-bench-assess xinci-bench-status xinci-bench-run; do
  ln -sfn "$(pwd)/xinci-bench-workflow/$s" ~/.claude/skills/$s
  ln -sfn "$(pwd)/xinci-bench-workflow/$s" ~/.codex/skills/$s
````

替换为

````markdown

```bash
for s in xinci-bench-scan xinci-bench-assess xinci-bench-status xinci-bench-run xinci-bench-quick; do
  ln -sfn "$(pwd)/xinci-bench-workflow/$s" ~/.claude/skills/$s
  ln -sfn "$(pwd)/xinci-bench-workflow/$s" ~/.codex/skills/$s
````

`README.md`：把

```markdown
| [xinci-bench-status](xinci-bench-workflow/xinci-bench-status/SKILL.md) | 只读看板 |
| [xinci-bench-run](xinci-bench-workflow/xinci-bench-run/SKILL.md) | 连续运行驱动器，暗号 `xinci_bench_run max_rounds=N` |
| [xinci-bench-core](xinci-bench-workflow/xinci-bench-core/) | 选站契约、数据采集、命令与观察、schema、脚本 |

```

替换为

```markdown
| [xinci-bench-status](xinci-bench-workflow/xinci-bench-status/SKILL.md) | 只读看板 |
| [xinci-bench-run](xinci-bench-workflow/xinci-bench-run/SKILL.md) | 连续运行驱动器，暗号 `xinci_bench_run max_rounds=N` |
| [xinci-bench-quick](xinci-bench-workflow/xinci-bench-quick/SKILL.md) | 新词快道，暗号 `xinci_bench_quick_run`：抓近 90 天冒出、首页还没人做的任务词，go 时强推立即建站 |
| [xinci-bench-core](xinci-bench-workflow/xinci-bench-core/) | 选站契约、数据采集、命令与观察、schema、脚本 |

```


- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 151 tests` 与 `OK`

- [ ] **Step 5: 软链到两个环境并核对**

```bash
ln -sfn "$(pwd)/xinci-bench-workflow/xinci-bench-quick" ~/.claude/skills/xinci-bench-quick
ln -sfn "$(pwd)/xinci-bench-workflow/xinci-bench-quick" ~/.codex/skills/xinci-bench-quick
for s in xinci-bench-scan xinci-bench-assess xinci-bench-status xinci-bench-run xinci-bench-quick; do
  test "$(readlink -f ~/.claude/skills/$s/SKILL.md)" = "$(readlink -f ~/.codex/skills/$s/SKILL.md)" && echo "ok $s"
done
```

Expected: 五行 `ok`。

- [ ] **Step 6: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py" "xinci-bench-workflow/xinci-bench-quick/SKILL.md" "xinci-bench-workflow/xinci-bench-scan/SKILL.md" "xinci-bench-workflow/xinci-bench-assess/SKILL.md" "xinci-bench-workflow/xinci-bench-run/SKILL.md" "xinci-bench-workflow/xinci-bench-status/SKILL.md" "xinci-bench-workflow/README.md" "README.md"
git commit -m "xinci-bench 快道:xinci-bench-quick skill、四个旧 skill 汇报前读立即建站行、README 与接入" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 9: 真实数据区、真实接口验收与设计稿写回

**Files:**
- 数据区（不入库）：`/Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-bench/`（指针 `.xinci-bench-data-root` 已存在，不改）
- Modify: `docs/superpowers/specs/2026-10-13-xinci-bench-quick-lane-design.md`（目录加一行，末尾加 §15 实现时的调整）

**Interfaces:**
- Consumes: Task 1–8 的全部脚本
- Produces: 真实数据区出现快道目录；设计稿与实现一致

- [ ] **Step 1: 记录三个指针文件的当前内容（验收时对比）**

```bash
cat .xinci-data-root .xinci-simple-data-root .xinci-bench-data-root
```

Expected: 依次是 `/Users/vito.wu/IdeaProjects/keywords-macdownds/数据/新词工作流`、`/Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-simple`、`/Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-bench`。

- [ ] **Step 2: 在真实数据区补建快道目录（不带 --data-root，按指针解析，不改指针）**

```bash
python3 xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py
python3 xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py
```

Expected: 第一次的"已创建"列出 `证据/_quick`、`快道/补全快照`、`快道/淘汰.json`、`快道/原料.jsonl` 四项；第二次为"无(全部已存在)"。

- [ ] **Step 3: 对真实自动补全接口取一次数（设计稿 §13 第 2 条）**

```bash
python3 xinci-bench-workflow/xinci-bench-core/scripts/suggest_snapshot.py --object "grow a garden 2" > /tmp/xinci-bench-suggest.json; echo "exit $?"
python3 -c "import json;d=json.load(open('/tmp/xinci-bench-suggest.json'));print(len(d), sum(1 for r in d if r.get('error')), sum(len(r['suggestions']) for r in d))"
ls "$(cat .xinci-bench-data-root)/快道/补全快照" | wc -l
```

Expected: `exit 0`；第二行三个数依次为 11（对象名 + 空格与 10 个任务词）、失败数、建议总数——失败数为 0 时建议总数应 > 0；第三行等于 11 减失败数。失败数不为 0 时把报错原文写进提交说明，不要改脚本去重试；全部失败（`exit 1`）就停下报告网络现象。

- [ ] **Step 4: 全量验收**

```bash
python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q
python3 xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py
python3 xinci-bench-workflow/xinci-bench-core/scripts/report_status.py
python3 xinci-bench-workflow/xinci-bench-core/scripts/run_log.py --plan --lane quick
cat .xinci-data-root .xinci-simple-data-root .xinci-bench-data-root
git status --short
```

Expected：`Ran 151 tests` 与 `OK`；`校验完成:0 个错误`；看板第一行不是"【立即建站】"（还没有快道方向），出现"快道原料池待看:0"；`--plan --lane quick` 的 `action` 为 `quick`、`resume` 为 null；三个指针与 Step 1 一致；`git status` 只剩用户原有的 `选词契约.md` 改动与未入库的 `工作流说明.html`。

- [ ] **Step 5: 设计稿写回"实现时的调整"**

`docs/superpowers/specs/2026-10-13-xinci-bench-quick-lane-design.md`：把

```markdown
- [13. 验收标准](#13-验收标准)
- [14. 设计决策记录](#14-设计决策记录)

## 1. 为什么要加快道
```

替换为

```markdown
- [13. 验收标准](#13-验收标准)
- [14. 设计决策记录](#14-设计决策记录)
- [15. 实现时的调整](#15-实现时的调整)

## 1. 为什么要加快道
```

`docs/superpowers/specs/2026-10-13-xinci-bench-quick-lane-design.md`：把

```markdown
- **手动触发、不做定时任务**：用户选暗号 `xinci_bench_quick_run`；代价是自动补全按"上一次运行"比对，记录间隔天数。
- **强推四处 + 跟进状态**：旧新词工作流唯一的 go 因无人建站过期；go 必须持续提醒，直到用户明确处理。
```

替换为

```markdown
- **手动触发、不做定时任务**：用户选暗号 `xinci_bench_quick_run`；代价是自动补全按"上一次运行"比对，记录间隔天数。
- **强推四处 + 跟进状态**：旧新词工作流唯一的 go 因无人建站过期；go 必须持续提醒，直到用户明确处理。

## 15. 实现时的调整

实施计划 `docs/superpowers/plans/2026-10-14-xinci-bench-quick-lane.md` 相对本设计稿补的 12 处：

1. 自动补全的"新建议"指以前所有快照里都没出现过的建议：同一查询隔几秒请求，返回的建议也不一样（2026-10-13 实测），只和上一次比会把波动当成新词；第一次快照只作基线。快照文件名为 `<规范化查询>-<查询 SHA-1 前 8 位>.json`，防止不同查询规范化后重名。
2. 运行清单的 `source_kind` 固定为 `quick`，本次用了哪些来源写在 `seed_value`。
3. `settle.py` 在任何写入之前先核对否决门属于该方向所在的道（快道不能用 `revenue` 等标杆道的门），不符直接拒收。
4. 速判 Q5 不过、占位的是小站时，用 `quick_pool.py reject --seed-domain <域名>` 在记淘汰的同时登记为标杆道种子（来源 serp）；已登记方向结算为 `occupied` 时仍用 `seeds.py add`。
5. 登记时速判观察里的词须是登记的说法之一（大小写与空格不计）；同一说法不能属于两个方向。
6. 量级观察额外校验：`ratio_7d` 须等于两条曲线 7 天均值之比，`estimate_7d` 须等于锚词月量 × 比值（允许取整误差 1），曲线至少 14 个非负数（Trends 显示 "<1" 的点记 0）。
7. 快道方向用 `ledger.py update` 只能改 `title`、`site_type`、`terms` 和追加观察引用，标杆道字段一律拒收。
8. 建站跟进的日期须为 YYYY-MM-DD，开建不早于判 go，上线不早于开建。
9. 原料池每行多记 `observation`（来自哪份 `quick_signal` 观察）与 `updated_at`；淘汰记录在顺带登记种子时多记 `seed`、`seed_added`。
10. 决策书把 §8.1 的第 3–8 项归在"第一部分 决策"（### 1–6）下，简报为"第二部分 最小版本建站简报"（### 1–6）。
11. 测试新增 58 个（本稿估约 40 个），合计 151 个。
12. 工作流说明 html 与发布页（§13 第 4 条）放到实施与整体审查完成之后单独更新，因为测试数、脚本数要以最终代码为准。
```

- [ ] **Step 6: 提交**

```bash
git add "docs/superpowers/specs/2026-10-13-xinci-bench-quick-lane-design.md"
git commit -m "xinci-bench 快道:设计稿补实现时的调整;真实数据区已建快道目录并对自动补全接口验收" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

数据区在 `keywords-macdownds` 仓库里，本计划不提交那边。工作流说明 html 与发布页在整体审查修完后另行更新；分支是否合并进 main、是否 push，交给 superpowers:finishing-a-development-branch 按用户选择处理。
