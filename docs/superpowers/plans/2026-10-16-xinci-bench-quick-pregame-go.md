# xinci-bench 快道"上线前预判 go"实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对开玩日在今天之后 3–21 天的游戏，按"一款游戏一个站、1–4 项任务合计"的预测量判 go，并在开玩后 7 天用实测量复核、止损、补参照库。

**Architecture:** 新增两类观察（`quick_reference` 参照、`quick_forecast` 预判），由两个新脚本从 Trends 曲线和参照库算出来（`quick_reference.py`、`quick_forecast.py`），不手算。预测数学放在 `quick_model.forecast()`，和现行 `compute()` 共用情景计算。账本方向多一个 `basis: "forecast"`，登记、结算、复查、复核、看板、决策书按它分派；现行"开玩后按当前量"的路径一行不改行为。

**Tech Stack:** Python 3 标准库、unittest、Markdown；Trends 取数沿用 `trends_fetch.js` 的 `xinciTrends`。

**Spec:** [docs/superpowers/specs/2026-10-16-xinci-bench-quick-pregame-go-design.md](../specs/2026-10-16-xinci-bench-quick-pregame-go-design.md)；底座是 [快道设计稿](../specs/2026-10-13-xinci-bench-quick-lane-design.md) 与契约 `xinci-bench-workflow/xinci-bench-core/选站契约.md` 第 10 节。

## 目录

- [与设计稿的差异（我替用户定的，最后一个任务写回设计稿）](#与设计稿的差异我替用户定的最后一个任务写回设计稿)
- [Global Constraints](#global-constraints)
- [Review Focus](#review-focus)
- [文件结构](#文件结构)
- [任务](#任务)
  - [Task 1: 假设表 q4 与预测模型](#task-1-假设表-q4-与预测模型)
  - [Task 2: 参照观察与量级观察的说法字段](#task-2-参照观察与量级观察的说法字段)
  - [Task 3: 参照库脚本 quick_reference.py](#task-3-参照库脚本-quick_referencepy)
  - [Task 4: 预判观察与 quick_forecast.py](#task-4-预判观察与-quick_forecastpy)
  - [Task 5: 预判登记](#task-5-预判登记)
  - [Task 6: 预判结算与账本校验](#task-6-预判结算与账本校验)
  - [Task 7: 预判决策书](#task-7-预判决策书)
  - [Task 8: 复核、预判观察复查与开玩日变化](#task-8-复核预判观察复查与开玩日变化)
  - [Task 9: 看板提醒](#task-9-看板提醒)
  - [Task 10: 契约、命令手册、采集规程、SKILL 与说明页](#task-10-契约命令手册采集规程skill-与说明页)

## 与设计稿的差异（我替用户定的，最后一个任务写回设计稿）

设计稿没写到、或前后有出入的地方，按下面执行；Task 10 写进设计稿新增的"13. 实施时补的口径"一节。

1. **参照取数不改 `trends_fetch.js`**：现有 `xinciTrends({geo, terms, time})` 接受 `"YYYY-MM-DD YYYY-MM-DD"` 形式的日期范围，两次调用（对象名 + 锚词、任务词 + 锚词）就够了；窗口和比值在 Python 里算（可测试）。设计稿 12 节列的"改 trends_fetch.js"由 `quick_reference.py time-range` 加文档替代。
2. **任务词窗口以 2a 为准**：设计稿 5.3 第一条写"任务词开玩后 0–13 天"，与同节第三条和 11 节 2a"开玩后 60 天内最高的连续 14 天"冲突，按后者。
3. **参照记录在开玩后 ≥ 14 天才写**：开玩后第 7 天复核时任务词只有 7 天，凑不满 14 天窗口。复核当天只做对账与止损；看板在开玩后第 14 天提醒"补参照"（`full_60_days: false`），第 60 天提醒"更新参照"。
4. **"美国单国不到门槛一半"用中位数倍数判**：用下四分位会把本可进观察中的对象提前砍掉。
5. **预判观察第一次复查时，到期日改为复查日 + 30 天**：设计稿 6.2 说到期日 = 开玩日 + 7，6.3 又说那天可"继续观察"；两者合起来就是：到复核日先复查，可以继续观察时再给 30 天（`watch_days`）。
6. **止损只对预判 go，对比下四分位预测**（判 go 的依据），单位都是英文区月搜索量。
7. **预判方向开玩前不能否决**：开玩前没有速判观察可作依据，只能结算 go、观察中或搁置；要否决，等复核日按现行路径。
8. **现行方向不写 `basis`**（不写即 current），已有记录和测试不动。
9. **观察字段比设计稿 7.2 多四项**：`quick_forecast` 加 `skipped_geos`（本次没测的国家）、`suggestion`、`serp`（两次首页的前 10）和 `tasks[].scope`（`category` 或 `task_type`，倍数取自同类别还是退到全部类别）；`quick_volume` 加可选的 `term`（测的是哪个词），用来区分对象名的量和任务词的量。
10. **开玩日变化**：`ledger.py update` 允许改预判方向的 `object.first_public`（只能改成今天之后的日期，须同时更新 `date_source`），自动顺延复核日、建议最晚上线日、观察到期日；累计推迟超过 7 天，看板提醒重新评估。

## Global Constraints

- 只用 Python 3 标准库与 unittest，不加依赖；测试不联网、只写 `TmpRoot` 临时数据区，不碰 `.xinci-bench-data-root`。
- 观察只追加、一律经 `write_observation.write()` 校验；账本只经脚本写；新判据的数值只从 `quick_model.QUICK_ASSUMPTIONS` 读，契约里的数字由文档一致性测试锁住。
- 现行快道路径行为不变：现有 213 个测试一个不改、全部通过。
- 拒收信息、注释、文档、提交信息用中文；提交信息末尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- 不提交、不改 `xinci-simple-workflow/xinci-simple-core/选词契约.md`（用户自己的未提交改动）；`git add` 只加本任务列出的文件。
- 不 push、不合并分支。
- 文档里的命令入参、出参用带逐字段注释的 JSON，不用表格；文档目录列出所有层级标题。
- 门槛不变：英文区单月 10,000 访问；首发份额 10% / 20% / 30%；预判一律按 AI 概览系数 0.6。
- 测试命令（在仓库根目录跑）：`python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`，下文记作 `<全部测试>`；单个文件把 `discover ...` 换成 `-k <测试类名>` 或直接 `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/<文件>.py`。

## Review Focus

1. **Trends 曲线不是逐日的**：日期范围超过约 270 天，Trends 会改按周返回；窗口函数必须拒收日期不连续的曲线，而不是拿周点去算 14 天均值（Task 3 `test_weekly_series_refused`）。
2. **同一款游戏的参照写了两次**（开玩后 14 天写一次、满 60 天再更新一次），分位数只能算最新的一条，否则倍数被重复样本拉偏（Task 3 `test_library_keeps_latest_per_object_task`）。
3. **对象名大小写、空格不同**：发售表写 "Wardogs"、Trends 查 "WARDOGS"，对象名的量级观察要按规范化后的名字认，换一款游戏的量级观察要拒收（Task 4 `test_object_volume_term_normalized` / `test_object_volume_other_object_refused`）。
4. **登记后隔几天才结算**：预判观察当天在 3–21 天窗口内，结算那天已经不到 3 天，必须拒收（Task 6 `test_pregame_settle_outside_window_refused`）。
5. **开玩日改到过去或今天**：说明游戏已经开玩，不该再顺延预判；必须拒收并提示按现行路径看首页（Task 8 `test_slip_to_past_refused`）。

---

## 文件结构

- 改 `xinci-bench-workflow/xinci-bench-core/scripts/quick_model.py`：q4 假设、游戏类别、参照窗口、`forecast()` 一族、`recompute()`；`compute()` 的情景计算抽成共用的 `_scenarios()`。
- 改 `scripts/write_observation.py`：`quick_reference`、`quick_forecast` 两类校验；`quick_volume` 可选 `term`。
- 改 `scripts/trends_volume.py`：`--term` 写进观察；导出 `SKIPPED_PREFIX`。
- 建 `scripts/quick_reference.py`：参照窗口、从两条 Trends 曲线写参照观察、读参照库、算分位倍数、`time-range` / `build` / `summary` 命令。
- 建 `scripts/quick_forecast.py`：从对象名量级观察 + 参照库写预判观察。
- 改 `scripts/ledger.py`：预判登记、按说法挑量级观察、`forecast_model()`、开玩前结算的复核、预判观察复查、`review_forecast()`、开玩日变化。
- 改 `scripts/settle.py`：开玩前结算写 `forecast` 块、观察到期日、建议最晚上线日。
- 改 `scripts/validate_ledger.py`：按模型类型重算、`forecast` 块校验。
- 改 `scripts/build_quick_doc.py`：开玩前预判的"立即建站"与第一部分（含"预判依据与风险"）。
- 改 `scripts/report_status.py`：可预判、复核到期、预判失准、开玩日推迟、补参照。
- 改 `数据结构/observation.schema.json`、`数据结构/direction.schema.json`。
- 改 `选站契约.md` §10.2、§10.6，新增 §10.9；`命令与观察.md` 新增 §7.7；`数据采集.md` 新增 §7.6；`xinci-bench-quick/SKILL.md`；本地说明页 `xinci-bench-workflow/工作流说明.html` 与发布页。
- 测试：新建 `scripts/tests/test_quick_reference.py`、`scripts/tests/test_quick_forecast.py`、`scripts/tests/test_quick_pregame.py`；改 `helpers.py`、`test_quick_model.py`、`test_quick_observation.py`、`test_trends_volume.py`、`test_report_status.py`、`test_build_quick_doc.py`、`test_documentation.py`。

下文路径省略前缀 `xinci-bench-workflow/xinci-bench-core/`。

---

## 任务

### Task 1: 假设表 q4 与预测模型

**Files:**
- Modify: `scripts/quick_model.py`
- Modify: `选站契约.md`（§10.6 假设表：版本号与新行）
- Test: `scripts/tests/test_quick_model.py`、`scripts/tests/test_documentation.py`

**Interfaces:**
- Produces:
  - `QUICK_ASSUMPTIONS["version"] == "2026-10-16.q4"`，新增键：`forecast_days: (3, 21)`、`forecast_per_run: 2`、`min_references: 3`、`forecast_launch_lead: 1`、`review_days: 7`、`review_stop_ratio: 0.25`、`us_only_cutoff: 0.5`、`reference_object_window: (9, 3)`（开玩日前第 9 到第 3 天）、`reference_task_days: 14`、`reference_task_span: 60`、`forecast_slip_days: 7`。
  - `GAME_CATEGORIES = ("open_world_survival", "mmo_gacha", "metroidvania_adventure", "sports_racing_party", "roblox")`
  - `TASK_TYPE_RE = re.compile(r"[a-z][a-z0-9_]*")`（任务类型如 `map`、`tier_list`）
  - `reference_object_window(playable_at: str, a=QUICK_ASSUMPTIONS) -> list[str]` → `[开玩日-9, 开玩日-3]`
  - `forecast_totals(by_geo: dict, tasks: list[dict]) -> tuple[int, int]` → `(round(Σ O×r_p25), round(Σ O×r_median))`，O = `sum(by_geo.values())`，按任务逐项乘再相加
  - `forecast_suggestion(forecast_p25: int, forecast_median: int, complete: bool, a=QUICK_ASSUMPTIONS) -> str` → `"go" | "watching" | "skip" | "measure_rest"`
  - `forecast(by_geo: dict, tasks: list[dict], a=QUICK_ASSUMPTIONS, complete=True) -> dict`，键：`basis`（恒为 `"forecast"`）、`assumptions_version`、`object_volume`、`us_share`、`aio_factor`、`forecast_p25`、`forecast_median`、`scenarios`（下四分位，结构同 `compute()`）、`median_scenarios`、`passes`、`passes_median`、`single_site_100`、`threshold_visits`、`searches_needed`、`complete`、`suggestion`
  - `forecast_dates(playable_at: str, a=QUICK_ASSUMPTIONS) -> dict` → `{"launch_by": 开玩日-1, "review_at": 开玩日+7}`
  - `recompute(rec: dict, a=QUICK_ASSUMPTIONS) -> dict`：`rec["model"]["basis"] == "forecast"` 时 `forecast(rec["forecast"]["object_volume_pre"], rec["forecast"]["tasks"], a, complete=True)`，否则 `compute(rec, a)`

- [ ] **Step 1: 写失败的测试**

`test_quick_model.py` 新增 `ForecastTest`：

```python
class ForecastTest(unittest.TestCase):
    def test_go_on_p25(self):
        m = QM.forecast({"US": 300000, "GB": 100000},
                        [{"task": "map", "r_p25": 0.15, "r_median": 0.25}, {"task": "build", "r_p25": 0.06, "r_median": 0.1}])
        self.assertEqual((m["forecast_p25"], m["forecast_median"]), (84000, 140000))
        base = m["scenarios"]["base"]
        self.assertEqual((base["visits"], base["us_visits"], base["revenue"]), (10080, 7560, 35.28))
        self.assertEqual((m["passes"], m["suggestion"], m["basis"], m["aio_factor"]), (True, "go", "forecast", 0.6))
        self.assertEqual(m["median_scenarios"]["base"]["visits"], 16800)

    def test_median_only_is_watching(self):
        m = QM.forecast({"US": 400000}, [{"task": "map", "r_p25": 0.1, "r_median": 0.25}])
        self.assertEqual((m["passes"], m["passes_median"], m["suggestion"]), (False, True, "watching"))

    def test_threshold_boundary(self):
        one = [{"task": "map", "r_p25": 1.0, "r_median": 1.0}]
        self.assertEqual(QM.forecast({"US": 83334}, one)["suggestion"], "go")     # floor(83334×0.12)=10000
        self.assertEqual(QM.forecast({"US": 83333}, one)["suggestion"], "skip")

    def test_us_only_cutoff_uses_median(self):
        t = lambda med: [{"task": "map", "r_p25": 0.01, "r_median": med}]
        # 美国单国中位数基准 floor(300000×0.15×0.12)=5400 ≥ 门槛 × 50% → 还要测其他 5 国
        self.assertEqual(QM.forecast({"US": 300000}, t(0.15), complete=False)["suggestion"], "measure_rest")
        self.assertEqual(QM.forecast({"US": 300000}, t(0.1), complete=False)["suggestion"], "skip")

    def test_dates_and_windows(self):
        self.assertEqual(QM.forecast_dates("2026-10-29"), {"launch_by": "2026-10-28", "review_at": "2026-11-05"})
        self.assertEqual(QM.reference_object_window("2026-08-22"), ["2026-08-13", "2026-08-19"])

    def test_recompute_dispatches_on_model_basis(self):
        f = {"object_volume_pre": {"US": 400000}, "tasks": [{"task": "map", "r_p25": 0.1, "r_median": 0.25}]}
        m = QM.forecast(f["object_volume_pre"], f["tasks"])
        self.assertEqual(QM.recompute({"model": m, "forecast": f}), m)

    def test_compute_unchanged(self):
        # 抽出 _scenarios 的守护:改动前就会通过,改完仍须通过(美国 50000 → 基准 10000)
        rec = {"volume": {"estimate_7d": 50000, "by_geo": {"US": 50000}, "trend": {"non_declining": True}},
               "serp": {"aio_present": False, "aio_completes": False}}
        self.assertEqual(QM.compute(rec)["scenarios"]["base"], {"share": 0.2, "visits": 10000, "us_visits": 10000, "revenue": 40.0})
```

`test_documentation.py` 新增：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q -k ForecastTest -k test_pregame_numbers_match_code`
Expected: FAIL，`AttributeError: module 'quick_model' has no attribute 'forecast'`，文档测试缺 `今天之后 3–21 天`；`test_compute_unchanged` 此时就通过（它守的是重构）

- [ ] **Step 3: 实现 `quick_model.py` 新函数，写契约假设表**

- `_scenarios(total, us, factor, a) -> tuple[dict, dict]`：把 `compute()` 里逐情景算访问、美国访问、收入的循环原样抽出，返回 `(scenarios, raw)`；`compute()` 改为调用它。
- `forecast_suggestion`：用 `math.floor(F × share.base × aio_factor)` 算基准访问；`complete=False` 时中位数基准 `< threshold × us_only_cutoff` 为 `skip`，否则 `measure_rest`；`complete=True` 时下四分位过线为 `go`、仅中位数过线为 `watching`、其余 `skip`。
- `forecast`：先用 `forecast_totals` 得到两个取整后的合计，访问、收入、过线都从取整后的合计算（和观察校验同一口径）；`tasks` 须 1–4 项、`r_p25 ≤ r_median` 且非负、`by_geo` 键属于英文区，不满足 `require` 拒收；系数恒用 `a["aio_factor"]`；收入按 `by_geo` 里美国的比例分。
- 契约 §10.6：版本号改为 **2026-10-16.q4**，表里加上面 11 个新键各一行，再加一行列出 5 个游戏类别；Step 1 的 needle 全部写在这几行里（§10.9 留到 Task 10，只讲口径与流程，数字引用 §10.6）。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`，221 个测试

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/quick_model.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_model.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py xinci-bench-workflow/xinci-bench-core/选站契约.md
git commit -m "xinci-bench 快道预判:假设表升 q4,加 forecast() 预测模型(下四分位判 go、中位数进观察、美国单国截断线)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: 参照观察与量级观察的说法字段

**Files:**
- Modify: `scripts/write_observation.py`、`scripts/trends_volume.py`、`数据结构/observation.schema.json`
- Modify: `scripts/tests/helpers.py`
- Test: `scripts/tests/test_quick_observation.py`、`scripts/tests/test_trends_volume.py`

**Interfaces:**
- Consumes: `QM.GAME_CATEGORIES`、`QM.TASK_TYPE_RE`、`QM.reference_object_window`、`QM.QUICK_ASSUMPTIONS`（Task 1）
- Produces:
  - `W.QUICK_KINDS` 末尾加 `"quick_reference"`（Task 4 再加 `"quick_forecast"`）；`W.REQUIRED["quick_reference"] = ("object", "category", "task", "task_term", "playable_at", "anchor_term", "anchor_volume", "anchor_source", "object_window", "object_ratio", "task_window", "task_ratio", "full_60_days", "object_volume_pre", "task_volume_post", "r")`
  - `quick_reference` 的 `slug` 为 null，写到 `证据/_quick/`
  - `quick_volume.readings.term`：可选，非空文字
  - `trends_volume.build_observation(payload, slug, semrush_calls=0, at=None, term=None)`；CLI 加 `--term`；`trends_volume.SKIPPED_PREFIX = "未查:"`（现有写法换成常量）
  - `helpers.reference_obs(object="Game A", task="map", category="mmo_gacha", playable_at="2026-07-01", task_ratio=0.1, object_ratio=1.0, anchor_volume=10000, task_window=("2026-07-05", "2026-07-18"), observed_at="2026-10-16T08:00:00+00:00") -> dict`：体积与 r 按下面的公式派生，`full_60_days = 观察日 ≥ 开玩日 + 60`
  - `helpers.quick_volume_obs(..., term=None, observed_at=None)`：两个新关键字参数，给了就写进观察

- [ ] **Step 1: 写失败的测试**

`test_quick_observation.py` 新增 `ReferenceObservationTest`：

```python
class ReferenceObservationTest(unittest.TestCase):
    def test_valid_reference(self):
        obs = H.reference_obs(task_ratio=0.2)
        W.validate(obs)
        r = obs["readings"]
        self.assertEqual((r["object_volume_pre"], r["task_volume_post"], r["r"], r["full_60_days"]), (10000, 2000, 0.2, True))
        self.assertEqual(r["object_window"], ["2026-06-22", "2026-06-28"])

    def test_wardogs_numbers(self):
        obs = H.reference_obs(object="Wardogs", category="open_world_survival", playable_at="2026-08-22",
                              object_ratio=1.0646, task_ratio=0.1447, anchor_volume=8100,
                              task_window=("2026-09-04", "2026-09-17"))
        W.validate(obs)
        r = obs["readings"]
        self.assertEqual((r["object_volume_pre"], r["task_volume_post"], r["r"], r["full_60_days"]), (8623, 1172, 0.1359, False))

    def test_refusals(self):
        bad = {
            "object_window": lambda r: r.update(object_window=["2026-06-21", "2026-06-27"]),   # 不是开玩日前第 9 到第 3 天
            "task_window_len": lambda r: r.update(task_window=["2026-07-05", "2026-07-20"]),  # 不是 14 天
            "task_window_early": lambda r: r.update(task_window=["2026-06-30", "2026-07-13"]),  # 早于开玩日
            "task_window_late": lambda r: r.update(task_window=["2026-08-20", "2026-09-02"]),   # 超出开玩后 60 天
            "r": lambda r: r.update(r=0.3),
            "volume": lambda r: r.update(object_volume_pre=12000),
            "category": lambda r: r.update(category="rpg"),
            "task": lambda r: r.update(task="Tier List"),
            "source": lambda r: r.update(anchor_source="guess"),
            "zero_object": lambda r: r.update(object_ratio=0, object_volume_pre=0),
            "full_early": lambda r: r.update(full_60_days=True, playable_at="2026-08-22",
                                             task_window=["2026-09-04", "2026-09-17"],
                                             object_window=["2026-08-13", "2026-08-19"]),  # 观察日不到开玩后 60 天
        }
        for name, mutate in bad.items():
            obs = H.reference_obs()
            mutate(obs["readings"])
            with self.subTest(name), self.assertRaises(BenchError):
                W.validate(obs)

    def test_reference_slug_null_and_folder(self):
        with H.TmpRoot() as root:
            ref = W.write(root, H.reference_obs())
            self.assertTrue(ref.startswith("证据/_quick/") and ref.endswith("-quick_reference.json"))
        obs = dict(H.reference_obs(), slug="x")
        with self.assertRaises(BenchError):
            W.validate(obs)

    def test_volume_term_optional(self):
        W.validate(H.quick_volume_obs("x", term="Wardogs"))
        with self.assertRaises(BenchError):
            W.validate(H.quick_volume_obs("x", term="  "))
```

`test_trends_volume.py` 新增 `test_term_written_to_readings`：用现有的完整 payload 调 `build_observation(payload, "x", term="Wardogs")`，断言 `obs["readings"]["term"] == "Wardogs"`，不传时 `"term" not in obs["readings"]`；再断言 skipped 国家的 `basis` 以 `trends_volume.SKIPPED_PREFIX` 开头。

- [ ] **Step 2: 跑测试确认失败**

Run: `<全部测试>`
Expected: FAIL，`kind 须为 (...)` 拒收 `quick_reference`；`build_observation() got an unexpected keyword argument 'term'`

- [ ] **Step 3: 实现**

- `write_observation.py`：`_check_quick_reference(r, observed_at)`；`validate()` 里 `quick_signal` 那条 slug-null 判断加上 `quick_reference`；分派时 `scan` 与 `quick_reference`（Task 4 再加 `quick_forecast`）都传 `observed_at`；`write()` 的目录映射加 `"quick_reference": "_quick"`；`_check_quick_volume` 末尾校验可选 `term`。
- `_check_quick_reference` 的规则：文字字段非空；`category ∈ QM.GAME_CATEGORIES`；`QM.TASK_TYPE_RE.fullmatch(task)`；`playable_at` 是日期；`anchor_volume > 0`；`anchor_source ∈ ("lexicon", "semrush")`；`object_window == QM.reference_object_window(playable_at)`；`task_window` 两个日期相差 `reference_task_days - 1` 天，起点 ≥ 开玩日，终点 ≤ 开玩日 + `reference_task_span - 1`，终点早于观察日；`object_ratio > 0`、`task_ratio ≥ 0`；`|object_volume_pre - anchor_volume × object_ratio| ≤ 1`，任务词同理；`r == round(task_volume_post / object_volume_pre, 4)`；`full_60_days` 为布尔，为真时观察日 ≥ 开玩日 + `reference_task_span`。
- `observation.schema.json`：`kind` 枚举与 `readings_required` 加上 `quick_reference`（`test_observation_schema_matches_validator` 锁着）；`quick_volume` 的说明里写可选 `term`。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/write_observation.py xinci-bench-workflow/xinci-bench-core/scripts/trends_volume.py xinci-bench-workflow/xinci-bench-core/数据结构/observation.schema.json xinci-bench-workflow/xinci-bench-core/scripts/tests/helpers.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_observation.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_trends_volume.py
git commit -m "xinci-bench 快道预判:加参照观察 quick_reference 的校验(窗口写死、体积与倍数可复算);量级观察可记测的是哪个词" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: 参照库脚本 quick_reference.py

**Files:**
- Create: `scripts/quick_reference.py`
- Test: `scripts/tests/test_quick_reference.py`

**Interfaces:**
- Consumes: `W.write`、`W.read`、`QM.reference_object_window`、`QM.QUICK_ASSUMPTIONS`、`quick_pool.normalize_term`
- Produces:
  - `time_range(playable_at: str, on: str, a=QM.QUICK_ASSUMPTIONS) -> str` → `"<开玩日-9> <min(开玩日+59, on-1)>"`，交给 `xinciTrends` 的 `time`
  - `window_ratio(dates: list[str], values: list[list], start: str, end: str) -> float`：窗口内第一列均值 ÷ 第二列均值，四位小数；窗口里缺日期或锚词均值为 0 拒收
  - `best_task_window(dates, values, playable_at, a=QM.QUICK_ASSUMPTIONS) -> dict` → `{"window": [start, end], "ratio": float, "full_60_days": bool}`
  - `build_observation(payload: dict, at: str | None = None) -> dict`：payload 键 `object, category, task, task_term, playable_at, anchor_term, anchor_volume, anchor_source, object_series, task_series`，可选 `semrush_calls`；两个 series 都是 `xinciTrends` 的原样输出（`geo, terms, time, url, dates, values`）
  - `load_library(root) -> list[dict]`：每项 `{"ref", "observed_at", **readings}`，同一 `(规范化对象名, task)` 只留观察时间最新的一条
  - `quantiles(rs: list[float]) -> tuple[float, float]` → `(p25, median)`，`statistics.quantiles(rs, n=4, method="inclusive")[0]` 与 `statistics.median`，四位小数
  - `rates(library: list[dict], task: str, category: str, a=QM.QUICK_ASSUMPTIONS) -> dict | None` → `{"r_p25", "r_median", "references", "reference_refs", "scope"}`，`scope` 为 `"category"`（同任务同类别 ≥ 3 条）或 `"task_type"`（退到同任务全部类别 ≥ 3 条），都不够返回 None
  - `check_refs(root, refs: list[str], task: str, category: str, scope: str, a=QM.QUICK_ASSUMPTIONS) -> dict`：用给定的参照路径重算，返回与 `rates()` 同结构；路径不是参照观察、任务不符、`scope=="category"` 时类别不符、同一对象重复、不到 3 条都拒收
  - CLI：`quick_reference.py time-range --playable-at D [--on D]`；`quick_reference.py build --input F [--dry-run]`（打印 `{"写入": ref, "r": ..., "任务词窗口": [...], "满 60 天": bool}`）；`quick_reference.py summary [--task T] [--category C]`（每个任务类型 × 类别一行：条数、下四分位、中位数）；拒收时退出码 1、stderr 以"拒收:"开头

- [ ] **Step 1: 写失败的测试**

`test_quick_reference.py`（夹具 `series(term, start, n, term_vals, anchor_vals)` 在文件内定义，返回 `xinciTrends` 形状的字典，日期逐日递增）：

```python
class WindowTest(unittest.TestCase):
    def test_time_range(self):
        self.assertEqual(QR.time_range("2026-07-01", "2026-10-16"), "2026-06-22 2026-08-29")
        self.assertEqual(QR.time_range("2026-10-01", "2026-10-16"), "2026-09-22 2026-10-15")

    def test_best_window_picks_highest_14_days(self):
        # 开玩日 07-01 起 60 天;任务词在 07-20..08-02 这 14 天是 10,其余 2;锚词恒 50
        s = series("game a map", "2026-06-22", 69, lambda d: 10 if "2026-07-20" <= d <= "2026-08-02" else 2, lambda d: 50)
        w = QR.best_task_window(s["dates"], s["values"], "2026-07-01")
        self.assertEqual((w["window"], w["ratio"], w["full_60_days"]), (["2026-07-20", "2026-08-02"], 0.2, True))

    def test_ties_take_earliest_and_short_series_not_full(self):
        s = series("x", "2026-09-22", 24, lambda d: 5, lambda d: 50)          # 开玩后只有 15 天
        w = QR.best_task_window(s["dates"], s["values"], "2026-10-01")
        self.assertEqual((w["window"][0], w["full_60_days"]), ("2026-10-01", False))

    def test_under_14_days_refused(self):
        s = series("x", "2026-09-22", 20, lambda d: 5, lambda d: 50)          # 开玩后 11 天
        with self.assertRaises(BenchError):
            QR.best_task_window(s["dates"], s["values"], "2026-10-01")

    def test_weekly_series_refused(self):
        s = series("x", "2026-06-22", 69, lambda d: 5, lambda d: 50)
        s["dates"], s["values"] = s["dates"][::7], s["values"][::7]
        with self.assertRaises(BenchError):
            QR.best_task_window(s["dates"], s["values"], "2026-07-01")


class BuildTest(unittest.TestCase):
    def payload(self, **over):
        obj = series("Game A", "2026-06-22", 69, lambda d: 50, lambda d: 50)          # 对象名窗口比值 1.0
        task = series("game a map", "2026-06-22", 69, lambda d: 5, lambda d: 50)      # 任务词比值 0.1
        return {"object": "Game A", "category": "mmo_gacha", "task": "map", "task_term": "game a map",
                "playable_at": "2026-07-01", "anchor_term": "map seed", "anchor_volume": 10000,
                "anchor_source": "lexicon", "object_series": obj, "task_series": task, **over}

    def test_build_valid_observation(self):
        obs = QR.build_observation(self.payload(), at="2026-10-16T08:00:00+00:00")
        W.validate(obs)
        self.assertEqual((obs["readings"]["r"], obs["readings"]["object_volume_pre"]), (0.1, 10000))
        self.assertEqual(len(obs["source_urls"]), 2)

    def test_object_unreadable_refused(self):
        p = self.payload(object_series=series("Game A", "2026-06-22", 69, lambda d: 0, lambda d: 50))
        with self.assertRaises(BenchError):
            QR.build_observation(p, at="2026-10-16T08:00:00+00:00")

    def test_series_terms_must_match(self):
        with self.assertRaises(BenchError):
            QR.build_observation(self.payload(anchor_term="other anchor"), at="2026-10-16T08:00:00+00:00")


class LibraryTest(unittest.TestCase):
    def test_quantiles(self):
        self.assertEqual(QR.quantiles([0.1, 0.2, 0.3]), (0.15, 0.2))
        self.assertEqual(QR.quantiles([0.1, 0.2, 0.3, 0.4]), (0.175, 0.25))

    def test_rates_scope_fallback_and_shortage(self):
        with H.TmpRoot() as root:
            for i, (cat, r) in enumerate([("mmo_gacha", 0.1), ("mmo_gacha", 0.2), ("roblox", 0.3)]):
                W.write(root, H.reference_obs(object=f"Game {i}", category=cat, task_ratio=r))
            lib = QR.load_library(root)
            got = QR.rates(lib, "map", "mmo_gacha")
            self.assertEqual((got["scope"], got["references"], got["r_p25"], got["r_median"]), ("task_type", 3, 0.15, 0.2))
            self.assertIsNone(QR.rates(lib, "build", "mmo_gacha"))
            W.write(root, H.reference_obs(object="Game 9", category="mmo_gacha", task_ratio=0.3))
            self.assertEqual(QR.rates(QR.load_library(root), "map", "mmo_gacha")["scope"], "category")

    def test_library_keeps_latest_per_object_task(self):
        with H.TmpRoot() as root:
            W.write(root, H.reference_obs(object="Game A", task_ratio=0.1, observed_at="2026-10-01T08:00:00+00:00"))
            W.write(root, H.reference_obs(object="game  a", task_ratio=0.3, observed_at="2026-10-16T08:00:00+00:00"))
            lib = QR.load_library(root)
            self.assertEqual([x["r"] for x in lib], [0.3])

    def test_check_refs_refuses_mismatch(self):
        with H.TmpRoot() as root:
            refs = [W.write(root, H.reference_obs(object=f"Game {i}", task_ratio=r)) for i, r in enumerate((0.1, 0.2, 0.3))]
            self.assertEqual(QR.check_refs(root, refs, "map", "mmo_gacha", "category")["r_p25"], 0.15)
            for bad in (refs[:2], refs + [refs[0]]):
                with self.subTest(len(bad)), self.assertRaises(BenchError):
                    QR.check_refs(root, bad, "map", "mmo_gacha", "category")
            with self.assertRaises(BenchError):
                QR.check_refs(root, refs, "build", "mmo_gacha", "category")

    def test_cli_build_and_summary(self):
        # build --dry-run 不写文件、打印 r;summary 在空库上打印空列表;拒收时退出码 1
        ...
```

最后一个 CLI 用例按注释写全：`main(["--data-root", root, "build", "--input", f, "--dry-run"])` 返回 0 且 `证据/_quick/` 下没有文件；`main([... "summary"])` 返回 0；`--input` 指向缺 `task` 的 payload 时返回 1。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_reference.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'quick_reference'`

- [ ] **Step 3: 实现 `scripts/quick_reference.py`**

- 文件头 docstring 写清"参照只测美国、两个词分别和同一个锚词比、窗口写死"；`build_observation` 核对两个 series 的 `geo == "US"`、`terms == [object 或 task_term, anchor_term]`；对象名比值 = `window_ratio(对象名窗口)`，为 0 时拒收"对象名开玩前读不出,不能做参照"；体积 `round(anchor_volume × 比值)`；`observed_at` 缺省取 `now()`；最后 `W.validate(obs)` 再返回。
- `best_task_window`：先核对日期逐日连续（相邻相差 1 天），不连续拒收"曲线不是逐日的(日期范围太长 Trends 会按周返回),缩短 time";只看开玩日到开玩日 + 59 天；滑动 14 天找第一列均值最大的窗口，并列取最早；`full_60_days` = 曲线最后一天 ≥ 开玩日 + 59。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/quick_reference.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_reference.py
git commit -m "xinci-bench 快道预判:加参照库脚本 quick_reference.py(取数日期范围、写死的窗口、分位倍数、同类别不足退到同任务)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: 预判观察与 quick_forecast.py

**Files:**
- Create: `scripts/quick_forecast.py`
- Modify: `scripts/write_observation.py`、`数据结构/observation.schema.json`、`scripts/tests/helpers.py`
- Test: `scripts/tests/test_quick_forecast.py`

**Interfaces:**
- Consumes: `QM.forecast`、`QM.forecast_totals`、`QM.forecast_suggestion`（Task 1）；`QR.load_library`、`QR.rates`（Task 3）；`trends_volume.SKIPPED_PREFIX`（Task 2）
- Produces:
  - `W.QUICK_KINDS` 末尾加 `"quick_forecast"`；`W.FORECAST_CHECKS = ("P1", "P2", "P3", "P4", "P5", "P6")`；`W.REQUIRED["quick_forecast"] = ("object", "category", "playable_at", "date_source", "object_volume_pre", "object_volume_ref", "skipped_geos", "tasks", "forecast_p25", "forecast_median", "suggestion", "checks", "serp")`
  - `tasks[]` 每项：`task, terms, r_p25, r_median, references, reference_refs, scope`
  - `quick_forecast.build_observation(root, payload: dict, at: str | None = None) -> dict`：payload 键 `slug, object, category, playable_at, date_source, object_volume_ref（可为 null）, tasks（[{task, terms}]）, checks（P1–P6，P3 可以不写）, serp, source_urls`，可选 `browser_preflight`、`semrush_calls`
  - CLI：`quick_forecast.py --input F [--dry-run]`，打印 `{"写入": ref, "suggestion": ..., "forecast_p25": ..., "forecast_median": ..., "下四分位基准访问": ...}`
  - `helpers.forecast_payload(slug="mho-map", object="Monster Hunter Outlanders", playable_at="2026-10-29", volume_ref=None, tasks=None) -> dict` 与 `helpers.write_references(root, rs=(0.1, 0.2, 0.3), category="mmo_gacha", task="map") -> list[str]`

- [ ] **Step 1: 写失败的测试**

`test_quick_forecast.py`（每个用例 `TmpRoot` 里先 `H.write_references(root)`，再写对象名量级观察 `H.quick_volume_obs(slug, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0, term="Monster Hunter Outlanders")`）：

```python
class BuildForecastTest(unittest.TestCase):
    def test_go_forecast(self):
        with H.TmpRoot() as root:
            vref = setup(root)                        # 文件内辅助:写参照与对象名量级,返回量级观察路径
            obs = QF.build_observation(root, H.forecast_payload(volume_ref=vref), at="2026-10-13T08:00:00+00:00")
            W.validate(obs)
            r = obs["readings"]
            self.assertEqual((r["forecast_p25"], r["forecast_median"], r["suggestion"]), (90000, 120000, "go"))
            t = r["tasks"][0]
            self.assertEqual((t["r_p25"], t["r_median"], t["references"], t["scope"]), (0.15, 0.2, 3, "category"))
            self.assertEqual((r["object_volume_pre"], r["skipped_geos"]), ({"US": 600000}, []))

    def test_references_short_fails_p3(self):
        with H.TmpRoot() as root:
            vref = setup(root)
            p = H.forecast_payload(volume_ref=vref, tasks=[{"task": "calculator", "terms": ["mho calculator"]}])
            r = QF.build_observation(root, p, at="2026-10-13T08:00:00+00:00")["readings"]
            self.assertEqual((r["checks"]["P3"]["pass"], r["suggestion"], r["forecast_p25"]), (False, "skip", None))
            self.assertIn("参照不足", r["checks"]["P3"]["basis"])

    def test_skipped_geos_need_measure_rest(self):
        # 其他 5 国用 trends_volume 的"未查:"行 → complete=False → measure_rest
        ...

    def test_object_volume_term_normalized(self):
        # 量级观察 term="monster  hunter OUTLANDERS" 也认
        ...

    def test_object_volume_other_object_refused(self):
        # 量级观察 term="Other Game" → BenchError;量级观察属于别的 slug → BenchError
        ...


class ForecastValidationTest(unittest.TestCase):
    def test_playable_window_boundaries(self):
        for day, ok in (("2026-10-15", False), ("2026-10-16", True), ("2026-11-03", True), ("2026-11-04", False)):
            obs = H.forecast_obs(playable_at=day)        # 观察日 2026-10-13,P1 判过
            with self.subTest(day):
                if ok:
                    W.validate(obs)
                else:
                    self.assertRaises(BenchError, W.validate, obs)

    def test_refusals(self):
        bad = {
            "few_refs": lambda r: r["tasks"][0].update(references=2, reference_refs=r["tasks"][0]["reference_refs"][:2]),
            "p25_gt_median": lambda r: r["tasks"][0].update(r_p25=0.3),
            "total": lambda r: r.update(forecast_p25=95000),
            "suggestion": lambda r: r.update(suggestion="watching"),
            "p2_us_zero": lambda r: r.update(object_volume_pre={"US": 0, "GB": 600000}, forecast_p25=90000),
            "five_tasks": lambda r: r.update(tasks=r["tasks"] * 5),
            "no_wiki_serp": lambda r: r.update(serp=[{"query": "mho map", "top10": []}, {"query": "mho tier list", "top10": []}]),
            "fail_not_skip": lambda r: r["checks"].update(P5={"pass": False, "basis": "占位"}),   # 有不过项时 suggestion 须为 skip
        }
        for name, mutate in bad.items():
            obs = H.forecast_obs()
            mutate(obs["readings"])
            with self.subTest(name), self.assertRaises(BenchError):
                W.validate(obs)

    def test_failed_check_allows_nulls(self):
        obs = H.forecast_obs()
        obs["readings"].update(checks={**obs["readings"]["checks"], "P5": {"pass": False, "basis": "已有 wiki"}},
                               object_volume_pre=None, object_volume_ref=None, forecast_p25=None,
                               forecast_median=None, suggestion="skip")
        W.validate(obs)

    def test_p5_needs_preflight(self):
        obs = H.forecast_obs()
        del obs["browser_preflight"]
        self.assertRaises(BenchError, W.validate, obs)
```

`helpers.forecast_obs(slug="mho-map", playable_at="2026-10-29")` 返回一份手写、六条全过、`go` 的合法预判观察（数和上面 `test_go_forecast` 一致：美国 600000、参照 0.1/0.2/0.3），`reference_refs` 填三个 `证据/_quick/...-quick_reference.json` 形式的路径。三个 `...` 用例按注释写全。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_forecast.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'quick_forecast'`

- [ ] **Step 3: 实现**

- `write_observation._check_quick_forecast(r, observed_at)`：`_check_null_rule(checks, FORECAST_CHECKS, object)`；`category`、`playable_at`、`date_source` 基本校验；P1 判过时开玩日 − 观察日在 `forecast_days` 之内；`tasks` 1–4 项、任务类型合规且不重复、`terms` 非空；`serp` 为列表，P5 有结论时至少两条、其中一条查询以 " wiki" 结尾（不分大小写）、每条有 `query` 与 `top10` 列表；没有不过项时：`object_volume_pre` 键属于英文区且 `US > 0`、`object_volume_ref` 以 `证据/` 开头、`skipped_geos` 属于英文区且不含 US、不与 `object_volume_pre` 重叠，每项任务 `references ≥ min_references`、`len(reference_refs) == references`、`0 ≤ r_p25 ≤ r_median`、`scope ∈ ("category", "task_type")`，`(forecast_p25, forecast_median) == QM.forecast_totals(...)`，`suggestion == QM.forecast_suggestion(..., complete=not skipped_geos)`；有不过项时 `suggestion == "skip"`。`validate()` 里 P5 有结论时要求 `browser_preflight`（同 quick_screen 的写法）。
- `quick_forecast.build_observation`：读 `object_volume_ref` 须为本 slug 的 `quick_volume`，`normalize_term(readings.term) == normalize_term(object)`；`object_volume_pre` 取读得出的国家的 `estimate_7d`；`basis` 以 `SKIPPED_PREFIX` 开头的国家进 `skipped_geos`；逐项 `QR.rates(QR.load_library(root), task, category)`，有一项为 None 就把 P3 记为不过、basis 写"参照不足:<任务> 同类型参照不到 3 条"，否则 P3 记过（basis 写条数与口径）；有不过项时数值字段置 null、`suggestion="skip"`；最后 `W.validate`。
- `observation.schema.json` 加 `quick_forecast`（枚举与 `readings_required`），说明里写 `tasks[]` 的字段。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/quick_forecast.py xinci-bench-workflow/xinci-bench-core/scripts/write_observation.py xinci-bench-workflow/xinci-bench-core/数据结构/observation.schema.json xinci-bench-workflow/xinci-bench-core/scripts/tests/helpers.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_forecast.py
git commit -m "xinci-bench 快道预判:加预判观察 quick_forecast(P1–P6、3–21 天窗口、合计可复算)与生成脚本 quick_forecast.py" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: 预判登记

**Files:**
- Modify: `scripts/ledger.py`、`scripts/tests/helpers.py`
- Test: `scripts/tests/test_quick_pregame.py`（新建）

**Interfaces:**
- Consumes: `quick_forecast.build_observation`（Task 4）
- Produces:
  - `register_quick(root, slug, title, site_type, obj, terms, screen_ref, reason, by="xinci-bench-quick", forecast_ref=None) -> dict`：`screen_ref` 与 `forecast_ref` 恰好给一个；给 `forecast_ref` 时记 `rec["basis"] = "forecast"`，`evidence_refs = [forecast_ref, object_volume_ref]`
  - CLI `register-quick --input` 的 JSON 可用 `"forecast"` 键代替 `"screen"`
  - `derive_quick` 改用 `_latest_term_volume(obs, terms)`：最新一份 `term` 不写、或规范化后属于本方向说法的 `quick_volume`
  - `helpers.setup_forecast(root, slug="mho-map", object_us=600000, playable_at="2026-10-29", brief=True) -> tuple[str, list[str]]`：写参照、对象名量级、预判观察，登记（说法 `[{"term": "mho map", "source": "autocomplete", "first_seen": "2026-10-12"}]`，对象 `{"name": "Monster Hunter Outlanders", "type": "game", "first_public": playable_at, "date_source": "https://example.org/mho"}`），再写简报素材并 `update` 引用

- [ ] **Step 1: 写失败的测试**

```python
class RegisterForecastTest(unittest.TestCase):
    def test_register_future_playable(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual((rec["basis"], rec["state"], rec["object"]["first_public"]), ("forecast", "found", "2026-10-29"))
            self.assertEqual(rec["evidence_refs"][:2], refs[:2])            # 预判观察、对象名量级

    def test_refusals(self):
        cases = {
            "not_game": dict(obj_type="other"),
            "date_mismatch": dict(first_public="2026-10-30"),
            "term_not_in_tasks": dict(terms=["mho tier list"]),
            "skip_suggestion": dict(object_us=100000),                     # 预判建议 skip 不登记
            "both_refs": dict(with_screen=True),
        }
        for name, kw in cases.items():
            with self.subTest(name), H.TmpRoot() as root, self.assertRaises(BenchError):
                register_variant(root, **kw)               # 文件内辅助:按 kw 改一处后调 register_quick

    def test_current_registration_unchanged(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_quick(root)
            self.assertNotIn("basis", load_ledger(root)["directions"][slug])

    def test_derive_ignores_object_name_volume(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            rec = load_ledger(root)["directions"][slug]
            self.assertIsNone(L.derive_quick(root, rec)["volume"])        # 只有对象名的量,任务词还没测
```

`register_variant` 按 `cases` 的键各改一处，其余同 `setup_forecast`。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pregame.py`
Expected: FAIL，`register_quick() got an unexpected keyword argument 'forecast_ref'`

- [ ] **Step 3: 实现**

预判登记的拒收条件：观察须为本 slug 的 `quick_forecast`、P1–P6 全过、`suggestion ∈ ("go", "watching")`；`obj.type == "game"`；`obj.first_public == readings.playable_at`；开玩日 − 观察日在 `forecast_days` 内；每个登记的说法（规范化后）都在某项任务的 `terms` 里（新增 `_check_forecast_terms(terms, forecast)`）；`object_volume_ref` 须是本 slug 的 `quick_volume`。其余（slug、标题、说法冲突、`consume` 原料池）沿用现有代码。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/ledger.py xinci-bench-workflow/xinci-bench-core/scripts/tests/helpers.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pregame.py
git commit -m "xinci-bench 快道预判:register-quick 支持按预判观察登记(未来开玩日 3–21 天、basis=forecast);测算只认本方向说法的量级观察" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: 预判结算与账本校验

**Files:**
- Modify: `scripts/ledger.py`、`scripts/settle.py`、`scripts/validate_ledger.py`、`数据结构/direction.schema.json`
- Test: `scripts/tests/test_quick_pregame.py`

**Interfaces:**
- Consumes: `QR.check_refs`（Task 3）、`QM.forecast`、`QM.forecast_dates`、`QM.recompute`（Task 1）、`H.setup_forecast`（Task 5）
- Produces:
  - `ledger.forecast_model(root, rec) -> dict`：从方向引用里最新的 `quick_forecast` 重算（对象名量级须在 `evidence_refs` 里；每项任务 `QR.check_refs` 的结果须与观察里的倍数、条数一致）
  - `ledger._precheck_forecast(root, rec, to, on)`：`rec.get("basis") == "forecast" and rec["state"] == "found"` 时由 `_precheck_quick` 调用
  - 开玩前结算后方向多 `forecast` 块：`{"ref", "playable_at", "object_volume_pre", "tasks": [{"task", "r_p25", "r_median"}], "forecast_p25", "forecast_median", "review_at", "review": None, "slipped_days": 0}`；`model = forecast_model(...)`；`volume`、`serp` 为 null
  - go：`follow_up.launch_by = 开玩日 - 1`；watching：`watch.expires_at = review_at`

- [ ] **Step 1: 写失败的测试**

```python
class PregameSettleTest(unittest.TestCase):
    def test_pregame_go(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            rec = settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="倍数只有 3 个参照", on="2026-10-14")
            self.assertEqual((rec["state"], rec["follow_up"]["launch_by"], rec["forecast"]["review_at"]), ("go", "2026-10-28", "2026-11-05"))
            self.assertEqual((rec["model"]["basis"], rec["forecast"]["forecast_p25"], rec["volume"]), ("forecast", 90000, None))
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-10-14"), [])

    def test_pregame_watching_expires_at_review(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000)        # 下四分位 8100 访问、中位数 10800
            rec = settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
            self.assertEqual(rec["watch"]["expires_at"], "2026-11-05")

    def test_wrong_verdict_refused(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000)
            self.assertRaises(BenchError, settle.settle, root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")
            self.assertRaises(BenchError, settle.settle, root, slug, "rejected", gate="volume", reason="x",
                              biggest_unknown="y", on="2026-10-14")          # 开玩前不能否决
            settle.settle(root, slug, "parked", reason="先放着", biggest_unknown="y", on="2026-10-14")

    def test_pregame_settle_outside_window_refused(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            self.assertRaises(BenchError, settle.settle, root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-27")

    def test_go_needs_brief(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, brief=False)
            self.assertRaises(BenchError, settle.settle, root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def test_tampered_reference_rate_refused(self):
        # 手写一份预判观察:reference_refs 仍是那三条参照,但 r_p25 写 0.12(合计按 0.12 重算,观察本身合法、能写入);
        # update 引用后结算 go → 拒收,信息含"参照倍数与参照库重算不一致"
        ...

    def test_validate_catches_model_drift(self):
        # 结算后手改账本 rec["forecast"]["tasks"][0]["r_p25"] = 0.2 → check_direction 报"快道模型重算与账本不一致"
        ...
```

两个 `...` 用例按注释写全。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pregame.py`
Expected: FAIL，`test_pregame_go` 在 `_precheck_quick` 报"缺速判观察 quick_screen"

- [ ] **Step 3: 实现**

- `_precheck_forecast`：parked 直接放行；rejected 拒收"预判方向开玩前只能结算 go、观察中或搁置;否决等开玩后复核按现行路径";go/watching 要求最新预判观察的 `playable_at == rec.object.first_public`、开玩日 − `on` 在 `forecast_days` 内、`forecast_model()` 的 `suggestion` 与结论一致（go 只认 `go`，watching 只认 `watching`）；go 另按现行规则要求 `quick_brief`（数据拿得到、3 天内做完）。
- `settle._fill_quick`：开头判断开玩前（`basis == "forecast"` 且 `state == "found"`），走新分支：go、watching 写 `model`、`forecast`、`watch`、`follow_up`；parked 只尝试写 `model`（`forecast_model` 拒收时记 None，同现行写法），不写 `forecast` 块；其余照旧。
- `validate_ledger._quick_errors`：`QM.compute(rec)` 换成 `QM.recompute(rec)`；`basis` 存在时只能是 `"forecast"`；模型是预判时 `forecast` 块键齐全、`forecast.playable_at == object.first_public`、`review_at == forecast_dates(playable_at)["review_at"]`。
- `direction.schema.json` 写 `basis` 与 `forecast` 两个可选字段的说明（`quick_required` 不变）。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/ledger.py xinci-bench-workflow/xinci-bench-core/scripts/settle.py xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py xinci-bench-workflow/xinci-bench-core/数据结构/direction.schema.json xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pregame.py
git commit -m "xinci-bench 快道预判:开玩前结算(重算参照倍数、建议最晚开玩前 1 天上线、观察到开玩后 7 天);账本校验按模型类型重算" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 7: 预判决策书

**Files:**
- Modify: `scripts/build_quick_doc.py`
- Test: `scripts/tests/test_build_quick_doc.py`

**Interfaces:**
- Consumes: 开玩前结算后的方向记录（Task 6）
- Produces: `render_md(root, rec)` 在 `rec["model"]["basis"] == "forecast"` 时改用 `_go_block_forecast(rec, by_kind)` 与 `_part_one_forecast(rec, by_kind)`；`_brief` 不变

- [ ] **Step 1: 写失败的测试**

```python
class PregameDocTest(unittest.TestCase):
    def test_go_doc_has_forecast_sections(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="倍数只有 3 个参照", on="2026-10-14")
            md = (Path(root) / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            for needle in ("## 立即建站", "建议最晚 2026-10-28（开玩日 2026-10-29 前 1 天）上线",
                           "### 1. 即将开玩的游戏", "### 3. 任务与参照倍数", "### 6. 预判依据与风险",
                           "下四分位", "中位数", "10,800", "3 条参照", "2026-11-05 复核",
                           "**最大的未知：倍数只有 3 个参照。**", "## 第二部分 最小版本建站简报"):
                self.assertIn(needle, md)
            self.assertNotIn("当前月搜索量", md)

    def test_watching_doc_has_no_go_block(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000)
            settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
            md = (Path(root) / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertNotIn("## 立即建站", md)
            self.assertIn("### 6. 预判依据与风险", md)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/test_build_quick_doc.py`
Expected: FAIL，`_go_block` 读 `vol['estimate_7d']` 时 `TypeError`（`volume` 为 None）

- [ ] **Step 3: 实现**

第一部分六节：1 即将开玩的游戏（P1：开玩日、日期来源、离今天几天）；2 有人在等（P2：对象名开玩前月量按国家列表）；3 任务与参照倍数（每项任务一行：说法、参照条数、下四分位、中位数、取自同类别还是全部类别）；4 首页现场（P5 两次查询的前 10 摘要、P6 记"开玩前未知，按 0.6"）；5 预测访问与收入（下四分位、中位数两张三档表）；6 预判依据与风险（加粗最大未知；参照条数与倍数、两档结果、窗口写死、复核日与止损线 `forecast_p25 × review_stop_ratio`、开玩日推迟超过 7 天要重新评估）。每节第一句加粗大白话，数字都从记录派生，沿用 `_fmt`、`_money`、`_table`。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/build_quick_doc.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_build_quick_doc.py
git commit -m "xinci-bench 快道预判:决策书加开玩前预判版本(立即建站写开玩前 1 天、第一部分含预判依据与风险)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: 复核、预判观察复查与开玩日变化

**Files:**
- Modify: `scripts/ledger.py`
- Test: `scripts/tests/test_quick_pregame.py`

**Interfaces:**
- Consumes: 开玩前结算后的 `forecast` 块（Task 6）、`H.quick_volume_obs(..., term=, observed_at=)`（Task 2）、`H.quick_screen_obs`
- Produces:
  - `review_forecast(root, slug, refs=(), on=None) -> dict`：只对 `basis == "forecast"`、`state == "go"`、`forecast.review` 为 null 的方向；写 `rec["forecast"]["review"] = {"at", "actual", "forecast_p25", "ratio", "stop", "by_task"}`；返回 `{"slug", **review, "message"}`，`stop` 时 `message == "预判失准,建议停止追加投入"`
  - CLI `ledger.py review-forecast --slug S --ref R [--ref R ...]`
  - `watch_check` 对预判观察：复核日前拒收；最新速判观察须在开玩日或之后；该方向第一次复查时先把 `watch.expires_at` 改为 `on + watch_days`
  - `update(root, slug, patch, refs=())`：预判方向（found / watching / go）可改 `object.first_public`（须同时给 `date_source`，新日期须在今天之后），并顺延 `forecast.playable_at`、`forecast.review_at`、`forecast.slipped_days`（累加新旧日期之差）、`follow_up.launch_by`（仍 pending 时）、`watch.expires_at`（观察中时）

- [ ] **Step 1: 写失败的测试**

```python
def task_volume(slug, estimate, day="2026-11-05", term="mho map"):
    return H.quick_volume_obs(slug, anchor_volume=estimate, new_mean=50.0, anchor_mean=50.0,
                              term=term, observed_at=f"{day}T08:00:00+00:00")


class ReviewTest(unittest.TestCase):
    def go(self, root):
        slug, _ = H.setup_forecast(root)
        settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="倍数", on="2026-10-14")
        return slug

    def test_stop_below_quarter(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            out = L.review_forecast(root, slug, [W.write(root, task_volume(slug, 22499))], on="2026-11-05")
            self.assertEqual((out["actual"], out["stop"], out["message"]), (22499, True, "预判失准,建议停止追加投入"))

    def test_quarter_boundary_not_stop(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            self.assertFalse(L.review_forecast(root, slug, [W.write(root, task_volume(slug, 22500))], on="2026-11-05")["stop"])

    def test_review_refusals(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            early = W.write(root, task_volume(slug, 30000))
            self.assertRaises(BenchError, L.review_forecast, root, slug, [early], on="2026-11-04")       # 复核日未到
            pre = W.write(root, task_volume(slug, 30000, day="2026-10-20"))
            self.assertRaises(BenchError, L.review_forecast, root, slug, [pre], on="2026-11-05")        # 开玩前测的量
            other = W.write(root, task_volume(slug, 30000, term="mho codes"))
            self.assertRaises(BenchError, L.review_forecast, root, slug, [other], on="2026-11-05")      # 不是本方向的说法
            L.review_forecast(root, slug, [early], on="2026-11-05")
            self.assertRaises(BenchError, L.review_forecast, root, slug, [early], on="2026-11-06")      # 已复核


class PregameWatchTest(unittest.TestCase):
    def watching(self, root):
        slug, _ = H.setup_forecast(root, object_us=450000)
        settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
        return slug

    def test_before_review_refused(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            self.assertRaises(BenchError, L.watch_check, root, slug, [], on="2026-11-04")

    def test_first_check_rebases_expiry(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            screen = dict(H.quick_screen_obs(slug, term="mho map"), observed_at="2026-11-05T08:00:00+00:00")
            refs = [W.write(root, screen), W.write(root, task_volume(slug, 30000))]
            out = L.watch_check(root, slug, refs, on="2026-11-05")
            self.assertEqual((out["suggestion"], out["expires_at"]), ("watching", "2026-12-05"))

    def test_pre_launch_screen_refused(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            refs = [W.write(root, H.quick_screen_obs(slug, term="mho map")), W.write(root, task_volume(slug, 30000))]
            self.assertRaises(BenchError, L.watch_check, root, slug, refs, on="2026-11-05")        # 速判是 10-13 开玩前看的


class SlipTest(unittest.TestCase):
    def test_slip_moves_dates(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="倍数", on="2026-10-14")
            rec = L.update(root, slug, {"object": {"first_public": "2026-11-12", "date_source": "https://example.org/delay"}},
                           on="2026-10-20")
            self.assertEqual((rec["follow_up"]["launch_by"], rec["forecast"]["review_at"], rec["forecast"]["slipped_days"]),
                             ("2026-11-11", "2026-11-19", 14))

    def test_slip_to_past_refused(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            for day in ("2026-10-20", "2026-10-19"):
                with self.subTest(day):
                    self.assertRaises(BenchError, L.update, root, slug,
                                      {"object": {"first_public": day, "date_source": "https://example.org/x"}}, on="2026-10-20")

    def test_current_direction_still_cannot_change_date(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_quick(root)
            self.assertRaises(BenchError, L.update, root, slug,
                              {"object": {"first_public": "2026-10-05", "date_source": "https://example.org/x"}})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pregame.py`
Expected: FAIL，`module 'ledger' has no attribute 'review_forecast'`；`update() got an unexpected keyword argument 'on'`

- [ ] **Step 3: 实现**

- `update` 加关键字参数 `on=None`（缺省 `today()`，现有调用不受影响）；预判方向在 go 状态也允许、且只允许 `object` 这一项补数；现行方向的 `object` 仍只许改 `date_source`。
- `review_forecast`：每项任务（取最新预判观察的 `tasks`）挑观察日 ≥ 开玩日、`term` 属于该任务说法的最新 `quick_volume`，缺哪项就拒收并列出；`actual = Σ estimate_7d`；`stop = actual < forecast_p25 × review_stop_ratio`；`ratio = round(actual / forecast_p25, 4)`。
- `watch_check`：现有代码 `screen` 为 None 时会直接抛 `TypeError`，加一句 `require(screen, "缺速判观察 quick_screen")`。
- found 状态改了开玩日后，旧预判观察的 `playable_at` 与方向不一致，`_precheck_forecast` 会拦住结算；须重新写预判观察、`update --ref` 引用后再结算（拒收信息里写明这一步）。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/ledger.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pregame.py
git commit -m "xinci-bench 快道预判:开玩后 7 天复核(实测低于预测 25% 提示止损)、预判观察复查改按开玩后速判、开玩日变化自动顺延" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 9: 看板提醒

**Files:**
- Modify: `scripts/report_status.py`
- Test: `scripts/tests/test_report_status.py`

**Interfaces:**
- Consumes: `QR.load_library`（Task 3）、`forecast` 块与 `review`（Task 6、8）、`quick_pool.upcoming(root, on, days)`
- Produces: `_quick_status(...)` 多五个键：
  - `forecast_window`：`[{"object", "stage", "playable_at", "days_ahead"}]`，开玩日在今天之后 3–21 天的待看原料
  - `forecast_reviews_due`：`[{"slug", "state", "review_at"}]`，预判 go 未复核、或预判观察还没复查过，且 `on ≥ review_at`
  - `forecast_warnings`：`[{"slug", "actual", "forecast_p25"}]`，复核 `stop` 为真且跟进没放弃
  - `forecast_slipped`：`[{"slug", "first_public", "slipped_days"}]`，go 或观察中、`slipped_days > forecast_slip_days`
  - `references_due`：`[{"object", "task", "action", "due"}]`，`action == "add"`：有 `forecast` 块的方向开玩满 14 天、参照库里还没有该对象该任务；`action == "update"`：参照 `full_60_days` 为假、开玩已满 60 天
  - `pending_go` 每行多 `"forecast": bool`；命令行输出对应五类提醒各一行，预判 go 的"【立即建站】"行写"(开玩前预判)"

- [ ] **Step 1: 写失败的测试**

```python
class PregameStatusTest(unittest.TestCase):
    def test_window_lists_3_to_21_days(self):
        # 原料池里开玩日 10-15(2 天)、10-16(3 天)、11-03(21 天)、11-04(22 天) 各一条,on=2026-10-13
        # → forecast_window 只有 10-16 与 11-03,days_ahead 3 与 21
        ...

    def test_review_due_and_warning(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")
            q = report_status.status(root, on="2026-11-05")["quick"]
            self.assertEqual(q["forecast_reviews_due"], [{"slug": slug, "state": "go", "review_at": "2026-11-05"}])
            self.assertTrue(q["pending_go"][0]["forecast"])
            ref = W.write(root, task_volume(slug, 10000))       # 与 Task 8 同一夹具
            L.review_forecast(root, slug, [ref], on="2026-11-05")
            q = report_status.status(root, on="2026-11-06")["quick"]
            self.assertEqual((q["forecast_reviews_due"], q["forecast_warnings"][0]["actual"]), ([], 10000))

    def test_slipped_over_7_days(self):
        # 顺延 8 天出现在 forecast_slipped,顺延 7 天不出现
        ...

    def test_references_due(self):
        # 预判 go 开玩日 10-29:on=11-11 没有 add,on=11-12(满 14 天)有 {"object": "Monster Hunter Outlanders", "task": "map", "action": "add"}
        # 写一条 full_60_days=false 的参照(开玩日 2026-08-22)后,on=2026-10-21 出现 action="update"
        ...

    def test_cli_prints_pregame_lines(self):
        # main(["--data-root", root]) 输出含"可预判""复核到期""(开玩前预判)"
        ...
```

`...` 用例按注释写全；`task_volume` 移到 `helpers.py` 供两处共用。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py`
Expected: FAIL，`KeyError: 'forecast_reviews_due'`

- [ ] **Step 3: 实现**

`forecast_window` 用 `quick_pool.upcoming(root, on=on, days=forecast_days[1])` 再筛 `days_ahead ≥ forecast_days[0]`；其余四类只读账本与参照库。命令行文案：`可预判 <对象>:<开玩日>,还有 N 天(每轮最多预判 2 个)`、`复核到期 <slug>:<review_at>,测任务词的量后跑 ledger.py review-forecast(观察中的跑 watch-check)`、`预判失准 <slug>:实测 X / 预测 Y,建议停止追加投入`、`开玩日推迟 <slug>:累计 N 天,现为 <日期>,请重新评估`、`补参照 <对象> <任务>`（`update` 写"更新参照"）。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/report_status.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py xinci-bench-workflow/xinci-bench-core/scripts/tests/helpers.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pregame.py
git commit -m "xinci-bench 快道预判:看板加可预判、复核到期、预判失准、开玩日推迟、补参照五类提醒" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 10: 契约、命令手册、采集规程、SKILL 与说明页

**Files:**
- Modify: `选站契约.md`（§10.2 七步里加预判一步；新增 §10.9 上线前预判，目录同步）
- Modify: `命令与观察.md`（新增 §7.7 上线前预判，目录同步）
- Modify: `数据采集.md`（新增 §7.6 参照与预判取数，目录同步）
- Modify: `xinci-bench-workflow/xinci-bench-quick/SKILL.md`（第 2、4–8 步）
- Modify: `docs/superpowers/specs/2026-10-16-xinci-bench-quick-pregame-go-design.md`（状态改为"已批准，已实施"；新增"13. 实施时补的口径"，内容即本计划开头 10 条；目录同步）
- Modify: `xinci-bench-workflow/工作流说明.html`（本地，未入库）与发布页 https://claude.ai/artifact/6FibYDXgPJoGp7Yz7VTn6Y
- Test: `scripts/tests/test_documentation.py`

**Interfaces:**
- Consumes: 前 9 个任务的命令与字段

- [ ] **Step 1: 写失败的测试**

```python
    def test_pregame_tools_documented(self):
        doc, coll, skill = text("命令与观察.md"), text("数据采集.md"), text("../xinci-bench-quick/SKILL.md")
        for needle in ("quick_reference.py time-range", "quick_reference.py build", "quick_reference.py summary",
                       "quick_forecast.py --input", "ledger.py review-forecast", "\"basis\": \"forecast\"",
                       "\"skipped_geos\"", "\"scope\""):
            self.assertIn(needle, doc)
        self.assertIn("xinciTrends(", coll)
        self.assertIn("quick_reference.py time-range", coll)
        for needle in ("quick_forecast.py", "review-forecast", "每轮最多预判 2 个"):
            self.assertIn(needle, skill)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py`
Expected: FAIL，`'quick_reference.py time-range' not found`

- [ ] **Step 3: 写文档**

- 契约 §10.9：适用范围 P1–P6、测算单位、公式、参照窗口、倍数取法、判定三档、复核与止损、开玩日变化、同一轮 Trends 不够时的优先级（飙升词 > 复核到期 > 预判 > 补参照）；数字引用 §10.6，不另写一份。§10.2 在"扫信号"与"零成本速判"之间加一步"上线前预判"。
- 命令与观察 §7.7：五个命令（`quick_reference.py time-range / build / summary`、`quick_forecast.py`、`ledger.py review-forecast`）的入参与出参，以及 `quick_reference`、`quick_forecast` 两类观察、方向的 `basis` 与 `forecast` 块，全部用带逐字段注释的 JSON（不用表格）。
- 数据采集 §7.6：参照怎么取（先 `time-range` 得日期范围，再在 Trends 页面跑两次 `xinciTrends({geo: "US", terms: [<对象名或任务词>, <锚词>], time: <日期范围>})`，两次间隔 ≥ 35 秒，交给 `quick_reference.py build`）；预判对象怎么测（先只测美国、`trends_volume.py --term <对象名>`，`quick_forecast.py` 给出 `measure_rest` 才测其他 5 国）；冷启动先补设计稿 5.3 列的游戏，每天 2–4 条。
- SKILL：第 2 步加看板五类预判提醒；第 4 步后加"预判"一步（取 `forecast_window`、最多 2 个、P5 首页计入当轮 10 个名额、写预判观察、过了就 `register-quick` 用 `forecast` 键）；第 3 步加复核（go 跑 `review-forecast`，观察中照常 `watch-check`）；第 7、8 步写预判 go 的建议最晚上线日是开玩前 1 天。
- 说明页：加"上线前预判"一节，按 `scratchpad/htmldoc/to_artifact.py` 生成发布版，`Artifact` 用同一路径重新发布到原网址（不传 `icon`）。

- [ ] **Step 4: 跑全部测试**

Run: `<全部测试>`
Expected: `OK`，约 278 个测试；再跑 `python3 xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py --data-root <TmpRoot 走一遍预判全流程后的目录>` 输出 0 个错误（Task 6–9 的测试里已覆盖，这一步只确认命令行可用）

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/选站契约.md xinci-bench-workflow/xinci-bench-core/命令与观察.md xinci-bench-workflow/xinci-bench-core/数据采集.md xinci-bench-workflow/xinci-bench-quick/SKILL.md xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py docs/superpowers/specs/2026-10-16-xinci-bench-quick-pregame-go-design.md
git commit -m "xinci-bench 快道预判:契约加 10.9 上线前预判、命令手册 7.7、采集规程 7.6、快道 SKILL 加预判与复核;设计稿补实施口径" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
