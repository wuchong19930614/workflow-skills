# xinci-bench 快道预判：2026-10-17 拍板三条的实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现用户 2026-10-17 拍板的三条：参照与预判观察按自己记下的口径校验、预判方向搁置后开玩后判 go 须用开玩后的数据、判过不预判的游戏按原因决定何时重做（每款最多 2 次）。

**Architecture:** 两类预判观察的读数多记 `params` 与 `assumptions_version`，写入时须等于当前假设表、读回时按自己的口径校验，参照库与结算只用口径相同的；`ledger._precheck_quick` 给"预判后搁置 → go"加开玩后数据的约束；重做规则是 `quick_forecast.reforecast_status()` 纯函数，看板按它标状态和排序。

**Tech Stack:** Python 3 标准库、unittest、Markdown。

**Spec:** [docs/superpowers/specs/2026-10-16-xinci-bench-quick-pregame-go-design.md](../specs/2026-10-16-xinci-bench-quick-pregame-go-design.md) 第 14 节（14.1–14.3 是本计划的需求）；其余章节是背景。

## 目录

- [Global Constraints](#global-constraints)
- [Review Focus](#review-focus)
- [文件结构](#文件结构)
- [任务](#任务)
  - [Task 1: 观察按自己记下的口径校验（14.3）](#task-1-观察按自己记下的口径校验143)
  - [Task 2: 预判后搁置的方向开玩后判 go（14.2）](#task-2-预判后搁置的方向开玩后判-go142)
  - [Task 3: 判过不预判的游戏何时重做（14.1）](#task-3-判过不预判的游戏何时重做141)
  - [Task 4: 契约、命令手册、SKILL 与说明页](#task-4-契约命令手册skill-与说明页)

## Global Constraints

- 只用 Python 3 标准库与 unittest；测试只写 `TmpRoot`，不联网，不碰真实数据区。
- 现行快道路径（非预判方向）行为不变；已有测试只允许改本计划点名的一处（Task 3 的 `test_window_lists_3_to_21_days` 期望值补字段，不删断言）。
- 数值只从 `quick_model.QUICK_ASSUMPTIONS` 读；契约里的数字由文档一致性测试锁住。
- 中文拒收信息、注释、文档、提交信息；提交末尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`；不 push。
- 不改、不提交 `xinci-simple-workflow/xinci-simple-core/选词契约.md`；`xinci-bench-workflow/工作流说明.html` 保持不入库。
- 文档里命令与字段的入参出参用逐字段带注释的 JSON，不用表格；改过的目录列全所有层级标题。
- 测试命令（仓库根目录）：`python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`，下文记作 `<全部测试>`。

## Review Focus

1. **JSON 里的列表和假设表里的元组**：`reference_object_window`、`forecast_days` 在假设表里是元组，写进观察再读回是列表；"口径相同"必须按列表比，写入再读回不能因为类型不同被判成口径已变（Task 1 `test_params_survive_json_roundtrip`）。
2. **同一款游戏挂在两个方向名下预判过**：重做次数按规范化后的游戏名跨方向文件夹数，不按方向名（Task 3 `test_history_counts_across_slugs`）。
3. **预判和结算之间改了假设表**：结算要拒收并说清"口径已变，重做预判"，不能按新口径悄悄重算（Task 1 `test_settle_refuses_after_params_change`）。
4. **开玩当天测的速判**：第 0 天算开玩后，必须接受；第 14 天接受、第 15 天拒收（Task 2 `test_screen_window_boundaries`）。
5. **先 measure_rest、当天补测再出 skip**：只算一次预判，之后还能在开玩前 9–3 天重做（Task 3 `test_measure_rest_not_counted`）。

---

## 文件结构

- 改 `xinci-bench-workflow/xinci-bench-core/scripts/quick_model.py`：`reference_params()`、`forecast_params()`、`assumptions_from_params()`；Task 3 加 `forecast_max_per_object` 并升版本。
- 改 `scripts/write_observation.py`：两类预判观察多两个必填读数；`validate(obs, current=True)`，`read()` 用 `current=False`。
- 改 `scripts/quick_reference.py`、`scripts/quick_forecast.py`：生成时写入口径；参照库与 `check_refs` 只认当前口径；`quick_forecast.reforecast_status()`。
- 改 `scripts/ledger.py`：`forecast_model` 核口径；`_precheck_quick` 加搁置方向开玩后的约束。
- 改 `scripts/report_status.py`：预判历史、重做状态与排序、命令行文案。
- 改 `数据结构/observation.schema.json`、`选站契约.md`、`命令与观察.md`、`xinci-bench-workflow/xinci-bench-quick/SKILL.md`、设计稿状态行；本地说明页（不入库）。
- 测试：改 `scripts/tests/helpers.py`；新增用例放进 `test_quick_reference.py`、`test_quick_forecast.py`、`test_quick_pregame.py`、`test_report_status.py`、`test_documentation.py`。

下文路径省略前缀 `xinci-bench-workflow/xinci-bench-core/`。

---

## 任务

### Task 1: 观察按自己记下的口径校验（14.3）

**Files:**
- Modify: `scripts/quick_model.py`、`scripts/write_observation.py`、`scripts/quick_reference.py`、`scripts/quick_forecast.py`、`scripts/ledger.py`、`数据结构/observation.schema.json`、`scripts/tests/helpers.py`
- Test: `scripts/tests/test_quick_reference.py`、`scripts/tests/test_quick_forecast.py`、`scripts/tests/test_quick_pregame.py`

**Interfaces:**
- Produces:
  - `QM.reference_params(a=QUICK_ASSUMPTIONS) -> dict` → `{"object_window": [9, 3], "task_days": 14, "task_span": 60}`（值取自 `reference_object_window`、`reference_task_days`、`reference_task_span`，窗口转成列表）
  - `QM.forecast_params(a=QUICK_ASSUMPTIONS) -> dict` → `{"forecast_days": [3, 21], "min_references": 3, "threshold_visits": 10000, "share_base": 0.2, "aio_factor": 0.6, "us_only_cutoff": 0.5}`
  - `QM.assumptions_from_params(params: dict, a=QUICK_ASSUMPTIONS) -> dict`：返回 `a` 的副本，把 `params` 里出现的键换回假设表的写法（`object_window`→`reference_object_window` 元组、`task_days`→`reference_task_days`、`task_span`→`reference_task_span`、`forecast_days`→元组、`share_base`→`share["base"]`，其余同名覆盖）
  - `W.REQUIRED["quick_reference"]`、`W.REQUIRED["quick_forecast"]` 末尾各加 `"assumptions_version", "params"`
  - `W.validate(obs: dict, current: bool = True) -> None`：两类预判观察按 `QM.assumptions_from_params(readings["params"])` 校验；`current=True` 时另要求 `params == QM.reference_params()`（或 `forecast_params()`）且 `assumptions_version == QM.QUICK_ASSUMPTIONS["version"]`；`W.read()` 调 `validate(obs, current=False)`，`W.write()` 调默认值
  - `QR.build_observation` 与 `QF.build_observation` 生成的读数带当前的 `assumptions_version` 与 `params`
  - `QR.load_library(root, skipped=None)`：`params != QM.reference_params()` 的参照一律不进库；给了 `skipped` 时记 `{"ref", "reason": "口径已变,需重测(写于 <assumptions_version>)"}`
  - `QR.check_refs(...)`：引用的参照口径不是当前的就拒收，信息含"口径已变"
  - `L.forecast_model(root, rec)`：最新预判观察的 `params != QM.forecast_params()` 时拒收，信息含"口径已变,重做预判"
  - `helpers.reference_obs(...)`、`helpers.forecast_obs(...)` 带当前口径

- [ ] **Step 1: 写失败的测试**

`test_quick_reference.py` 新增 `ParamsTest`：

```python
class ParamsTest(unittest.TestCase):
    def test_reference_written_with_current_params(self):
        r = H.reference_obs()["readings"]
        self.assertEqual(r["params"], {"object_window": [9, 3], "task_days": 14, "task_span": 60})
        self.assertEqual(r["assumptions_version"], QM.QUICK_ASSUMPTIONS["version"])
        r = QR.build_observation(payload(), at="2026-10-16T08:00:00+00:00")["readings"]
        self.assertEqual(r["params"], QM.reference_params())

    def test_write_refuses_made_up_params(self):
        obs = H.reference_obs()
        obs["readings"]["params"]["task_days"] = 10
        with self.assertRaisesRegex(BenchError, "口径"):
            W.validate(obs)

    def test_params_survive_json_roundtrip(self):
        with H.TmpRoot() as root:
            ref = W.write(root, H.reference_obs())
            self.assertEqual(W.read(root, ref)["readings"]["params"], QM.reference_params())
            self.assertEqual(len(QR.load_library(root)), 1)

    def test_read_uses_own_params_after_change(self):
        with H.TmpRoot() as root:
            ref = W.write(root, H.reference_obs())
            with mock.patch.dict(QM.QUICK_ASSUMPTIONS, {"reference_object_window": (10, 4), "reference_task_days": 7}):
                self.assertEqual(W.read(root, ref)["readings"]["params"]["task_days"], 14)   # 照样读得进来
                skipped = []
                self.assertEqual(QR.load_library(root, skipped), [])                          # 口径不同不进库
                self.assertIn("口径已变", skipped[0]["reason"])
                with self.assertRaisesRegex(BenchError, "口径已变"):
                    QR.check_refs(root, [ref], "map", "mmo_gacha", "task_type")
```

`test_quick_forecast.py` 新增 `ForecastParamsTest`：`test_forecast_written_with_current_params`（`QF.build_observation` 输出与 `H.forecast_obs()` 的 `params == QM.forecast_params()`）、`test_read_forecast_after_threshold_change`（写入 `H.forecast_obs()` 后在 `mock.patch.dict(QM.QUICK_ASSUMPTIONS, {"threshold_visits": 5000})` 下 `W.read` 照样通过，`suggestion` 仍是 `"go"`）。

`test_quick_pregame.py` 新增 `ParamsSettleTest`：

```python
class ParamsSettleTest(unittest.TestCase):
    def test_settle_refuses_after_params_change(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            with mock.patch.dict(QM.QUICK_ASSUMPTIONS, {"us_only_cutoff": 0.4}):
                with self.assertRaisesRegex(BenchError, "口径已变,重做预判"):
                    settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")
            self.assertEqual(load_ledger(root)["directions"][slug]["state"], "found")

    def test_review_reads_settled_forecast_after_change(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")
            ref = W.write(root, H.task_volume(slug, 30000))
            with mock.patch.dict(QM.QUICK_ASSUMPTIONS, {"min_references": 4}):
                self.assertFalse(L.review_forecast(root, slug, [ref], on="2026-11-05")["stop"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<全部测试>`
Expected: FAIL，`KeyError: 'params'`；schema 一致性测试此时仍通过（还没改 REQUIRED）

- [ ] **Step 3: 实现**

- `write_observation.py`：`_check_quick_reference(r, observed_at, current)`、`_check_quick_forecast(r, observed_at, current)` 先核 `assumptions_version` 是非空文字、`params` 恰好含该类的键且值合法（窗口为两个正整数的列表、天数为正整数、比例在 0–1），再用 `a = QM.assumptions_from_params(r["params"])` 做原有全部校验（`reference_object_window(playable_at, a)`、`forecast_suggestion(..., a=a)`、`_check_forecast_task(t, a)` 等都把 `a` 传下去）；`current=True` 时口径或版本不等于当前就拒收"口径与当前假设表不一致(写入时须用当前口径)"。`validate()` 把 `current` 传给这两类，其余类型不受影响。
- `observation.schema.json` 的 `readings_required` 同步（文档测试锁着），说明里写两个新字段。
- `quick_reference.py`、`quick_forecast.py` 生成观察时写入；`load_library` 与 `check_refs` 按 Interfaces 处理口径；`quick_forecast.py` 输出里的"参照不可用"自然带上口径已变的条目。
- `ledger.forecast_model` 在核六条之前核口径。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/quick_model.py xinci-bench-workflow/xinci-bench-core/scripts/write_observation.py xinci-bench-workflow/xinci-bench-core/scripts/quick_reference.py xinci-bench-workflow/xinci-bench-core/scripts/quick_forecast.py xinci-bench-workflow/xinci-bench-core/scripts/ledger.py xinci-bench-workflow/xinci-bench-core/数据结构/observation.schema.json xinci-bench-workflow/xinci-bench-core/scripts/tests/
git commit -m "xinci-bench 快道预判:参照与预判观察记下自己的口径(params、assumptions_version),读回按自己的口径校验,参照库与结算只用当前口径" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: 预判后搁置的方向开玩后判 go（14.2）

**Files:**
- Modify: `scripts/ledger.py`
- Test: `scripts/tests/test_quick_pregame.py`

**Interfaces:**
- Consumes: `H.setup_forecast`、`H.quick_screen_obs`、`H.task_volume(slug, estimate, day="2026-11-05", term="mho map")`、`settle.settle`、`L.update`
- Produces: `ledger._require_parked_after_launch(rec, screen, vol)`：开玩日取 `rec["object"]["first_public"]`；最新速判观察日须在开玩日当天到开玩日 + `QUICK_ASSUMPTIONS["new_days_game"]` 天内（含两端），量级观察日须在开玩日当天或之后。`_precheck_quick` 在 `basis == "forecast"`、state parked、`to == "go"` 时调用；否决不调用。

- [ ] **Step 1: 写失败的测试**

```python
class ParkedAfterLaunchTest(unittest.TestCase):
    def parked(self, root):
        slug, _ = H.setup_forecast(root)                       # 开玩日 2026-10-29
        settle.settle(root, slug, "parked", reason="开玩前搁置", biggest_unknown="开玩后量", on="2026-10-14")
        return slug

    def evidence(self, root, slug, day, q5=True):
        screen = H.quick_screen_obs(slug, term="mho map", fail=None if q5 else {"Q5": False},
                                    occupied_by=None if q5 else "mhofans.wiki")
        screen["observed_at"] = f"{day}T08:00:00+00:00"
        refs = [W.write(root, screen), W.write(root, H.task_volume(slug, 60000, day=day))]
        L.update(root, slug, {}, refs)

    def test_pre_launch_evidence_refused(self):
        with H.TmpRoot() as root:
            slug = self.parked(root)
            self.evidence(root, slug, "2026-10-20")
            with self.assertRaisesRegex(BenchError, "开玩"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-20")

    def test_screen_window_boundaries(self):
        for day, ok in (("2026-10-29", True), ("2026-11-12", True), ("2026-11-13", False)):
            with self.subTest(day), H.TmpRoot() as root:
                slug = self.parked(root)
                self.evidence(root, slug, day)
                if ok:
                    rec = settle.settle(root, slug, "go", reason="开玩后过线", biggest_unknown="y", on=day)
                    self.assertEqual((rec["state"], rec["model"].get("basis")), ("go", None))   # 现行路径的模型
                else:
                    self.assertRaises(BenchError, settle.settle, root, slug, "go", reason="x", biggest_unknown="y", on=day)

    def test_rejection_not_restricted(self):
        with H.TmpRoot() as root:
            slug = self.parked(root)
            self.evidence(root, slug, "2026-10-20", q5=False)
            rec = settle.settle(root, slug, "rejected", gate="occupied", reason="开玩前已有专做本作的站",
                                biggest_unknown="y", on="2026-10-20")
            self.assertEqual(rec["state"], "rejected")

    def test_current_parked_unchanged(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_quick(root)                       # 现行方向,无 basis;速判与量级都是 2026-10-13 看的
            settle.settle(root, slug, "parked", reason="先放着", biggest_unknown="y", on="2026-10-13")
            rec = settle.settle(root, slug, "go", reason="补数后过线", biggest_unknown="y", on="2026-10-13")
            self.assertEqual(rec["state"], "go")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pregame.py`
Expected: FAIL，`test_pre_launch_evidence_refused` 报 `BenchError not raised`，`2026-11-13` 那个子用例同样没拒收

- [ ] **Step 3: 实现 `_require_parked_after_launch` 并在 `_precheck_quick` 里接上**

拒收信息写明开玩日和观察日，例如"预判后搁置的方向开玩后判 go:最新速判是 2026-10-20 看的,须在开玩日 2026-10-29 当天到开玩后 14 天内"。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/ledger.py xinci-bench-workflow/xinci-bench-core/scripts/tests/test_quick_pregame.py
git commit -m "xinci-bench 快道预判:预判后搁置的方向开玩后判 go,速判须在开玩后 14 天内、量级须在开玩后测;否决不限制" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: 判过不预判的游戏何时重做（14.1）

**Files:**
- Modify: `scripts/quick_model.py`、`scripts/quick_forecast.py`、`scripts/report_status.py`、`选站契约.md`（§10.6 加一行、版本号）
- Test: `scripts/tests/test_quick_forecast.py`、`scripts/tests/test_report_status.py`、`scripts/tests/test_documentation.py`

**Interfaces:**
- Consumes: `QR.rates`、`QR.load_library`（Task 1 之后只含当前口径）、`QM.QUICK_ASSUMPTIONS["reference_object_window"]`
- Produces:
  - `QUICK_ASSUMPTIONS["forecast_max_per_object"] = 2`，`version = "2026-10-17.q5"`
  - 预判历史条目（看板从各方向文件夹的预判观察整理）：`{"observed_at": "YYYY-MM-DD", "playable_at", "suggestion", "failed": "P1".."P6" 或 None（第一个不过的检查）, "tasks": ["map", ...], "category"}`
  - `QF.reforecast_status(history: list, playable_at: str, on: str, library: list, a=QM.QUICK_ASSUMPTIONS) -> dict` → `{"reforecast": "new" | "due" | "wait" | "no", "reason": str}`；`history` 按观察时间升序，最后一条是"上次"
  - `report_status._forecast_window` 每行在 `last_forecast` 之外加 `reforecast`、`reason`；排序键 `(状态序, playable_at)`，状态序 `new`/`due` 为 0、`wait` 为 1、`no` 为 2；命令行行尾加"→ 可重做/还不到时候/不再预判:<reason>"（`new` 不加）

判法按设计稿 14.1；"次数"只数建议不是 `measure_rest` 的预判；"窗口"是开玩日前第 `reference_object_window[0]` 到第 `[1]` 天（9 到 3）。`reason` 须包含下列关键词（测试按包含断言）：`new` →"没预判过"；满 2 次 →"已预判 2 次"；go/watching →"已登记"；P4/P5/P6 →"上次 P5 不过"（按实际编号）；P1 →"开玩日"（改期了写"开玩日改了"）；P3 →"参照不足"；P2 与量不够这一类的 due、wait、no 三种都含"开玩前 9–3 天"；measure_rest →"补测其余 5 国"。

- [ ] **Step 1: 写失败的测试**

`test_quick_forecast.py`：

```python
def h(observed, suggestion="skip", failed=None, playable="2026-10-29", tasks=("map",)):
    return {"observed_at": observed, "playable_at": playable, "suggestion": suggestion, "failed": failed,
            "tasks": list(tasks), "category": "mmo_gacha"}


class ReforecastTest(unittest.TestCase):
    def st(self, history, on, playable="2026-10-29", library=()):
        return QF.reforecast_status(history, playable, on, list(library))["reforecast"]

    def test_new_and_volume_skip_timeline(self):
        self.assertEqual(self.st([], "2026-10-14"), "new")
        early = [h("2026-10-13")]                                   # 开玩前 16 天做的,量不够
        self.assertEqual(self.st(early, "2026-10-19"), "wait")      # 开玩前 10 天
        self.assertEqual(self.st(early, "2026-10-20"), "due")       # 开玩前 9 天
        self.assertEqual(self.st(early, "2026-10-26"), "due")       # 开玩前 3 天
        self.assertEqual(self.st([h("2026-10-21")], "2026-10-22"), "no")    # 上次已在 9–3 天里做过

    def test_max_two(self):
        # 两次都在 9–3 天窗口之外做的;没有上限的话这里会是 due
        self.assertEqual(self.st([h("2026-10-12"), h("2026-10-13")], "2026-10-20"), "no")

    def test_measure_rest_not_counted(self):
        self.assertEqual(self.st([h("2026-10-13", "measure_rest")], "2026-10-13"), "due")
        self.assertEqual(self.st([h("2026-10-13", "measure_rest"), h("2026-10-13")], "2026-10-20"), "due")

    def test_permanent_failures(self):
        for p in ("P4", "P5", "P6"):
            self.assertEqual(self.st([h("2026-10-13", failed=p)], "2026-10-20"), "no")
        self.assertEqual(self.st([h("2026-10-13", "go")], "2026-10-20"), "no")

    def test_p1_only_after_date_change(self):
        last = [h("2026-10-13", failed="P1")]
        self.assertEqual(self.st(last, "2026-10-20"), "no")
        self.assertEqual(self.st(last, "2026-10-20", playable="2026-11-05"), "due")

    def test_p3_waits_for_references(self):
        last = [h("2026-10-13", failed="P3")]
        self.assertEqual(self.st(last, "2026-10-14"), "wait")
        lib = [dict(H.reference_obs(object=f"G{i}", task_ratio=r)["readings"], ref=f"证据/_quick/{i}.json",
                    observed_at="2026-10-16T08:00:00+00:00") for i, r in enumerate((0.1, 0.2, 0.3))]
        self.assertEqual(self.st(last, "2026-10-14", library=lib), "due")

    def test_p2_like_volume(self):
        self.assertEqual(self.st([h("2026-10-13", failed="P2")], "2026-10-20"), "due")

    def test_reason_keywords(self):
        self.assertIn("没预判过", QF.reforecast_status([], "2026-10-29", "2026-10-14", [])["reason"])
        self.assertIn("开玩前 9–3 天", QF.reforecast_status([h("2026-10-13")], "2026-10-29", "2026-10-14", [])["reason"])
```

`test_report_status.py`：`test_history_counts_across_slugs`（同一款游戏在两个方向名下各写一份 skip 预判，看板该行 `reforecast == "no"`、`reason` 含"已预判 2 次"）、`test_window_sorts_by_reforecast`（三款游戏分别是 new、wait、no，排序为 new、wait、no）、`test_cli_shows_reforecast`（命令行含"→ 还不到时候"）。现有 `test_window_lists_3_to_21_days` 的期望行各补 `"reforecast": "new", "reason": "没预判过"`（若实现的 `new` 原因文字更长，期望值照实现写，断言不删）。

`test_documentation.py` 在 `test_pregame_numbers_match_code` 的 needle 里加 `f"每款游戏最多预判 {a['forecast_max_per_object']} 次"`。

- [ ] **Step 2: 跑测试确认失败**

Run: `<全部测试>`
Expected: FAIL，`AttributeError: module 'quick_forecast' has no attribute 'reforecast_status'`；文档测试缺"每款游戏最多预判 2 次"

- [ ] **Step 3: 实现**

- `quick_model.py`：加键、升版本。
- `quick_forecast.reforecast_status`：按设计稿 14.1 的判法顺序（满 2 次 / go·watching → P4·P5·P6 → P1 → P3 → P2 与量不够 → measure_rest）。
- `report_status.py`：把 `_last_forecasts` 扩成按规范化游戏名收集全部预判观察的历史（读不出的照旧跳过），`last_forecast` 保持原结构；`_forecast_window` 调 `QF.reforecast_status`（参照库只读一次，和"参照不可用"共用）。
- `选站契约.md` §10.6：版本号改为 **2026-10-17.q5**，加一行"每款游戏最多预判 2 次（建议为 measure_rest 的不算）"。

- [ ] **Step 4: 跑测试确认通过**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/scripts/quick_model.py xinci-bench-workflow/xinci-bench-core/scripts/quick_forecast.py xinci-bench-workflow/xinci-bench-core/scripts/report_status.py xinci-bench-workflow/xinci-bench-core/选站契约.md xinci-bench-workflow/xinci-bench-core/scripts/tests/
git commit -m "xinci-bench 快道预判:判过不预判的游戏按原因决定何时重做(量不够开玩前 9–3 天再做、占位与范围不再做、参照不足等参照),每款最多 2 次;假设表升 q5" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: 契约、命令手册、SKILL 与说明页

**Files:**
- Modify: `选站契约.md` §10.9、`命令与观察.md` §7.7、`xinci-bench-workflow/xinci-bench-quick/SKILL.md` 第 5 步、设计稿状态行（"已实施"）
- Modify（不入库）: `xinci-bench-workflow/工作流说明.html`
- Test: `scripts/tests/test_documentation.py`

**Interfaces:**
- Consumes: Task 1–3 的字段、函数与看板文案

- [ ] **Step 1: 写失败的测试**

```python
    def test_pregame_decisions_documented(self):
        doc, skill, c = text("命令与观察.md"), text(<SKILL 路径,沿用 test_pregame_tools_documented 的写法>), text("选站契约.md")
        for needle in ("\"params\"", "\"assumptions_version\"", "\"reforecast\"", "口径已变"):
            self.assertIn(needle, doc)
        for needle in ("new", "due", "开玩前 9–3 天"):
            self.assertIn(needle, skill)
        for needle in ("口径已变", "开玩后 14 天内"):
            self.assertIn(needle, c)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py`
Expected: FAIL，`'"params"' not found`

- [ ] **Step 3: 写文档**

- 契约 §10.9：三条各补一段（口径按观察自己的校验、参照库只用当前口径；预判后搁置的方向开玩后判 go 的约束、否决不限；重做规则与每款最多 2 次），数字引用 §10.6。
- 命令与观察 §7.7：两类观察的 `assumptions_version`、`params` 字段（逐字段注释的 JSON）；看板"可预判"每行的 `reforecast`、`reason`；"参照不可用"里口径已变的写法。
- SKILL 第 5 步：只取看板里 `reforecast` 为 `new` 或 `due` 的游戏，每轮最多 2 个；`wait`、`no` 不做。
- 设计稿状态行改为"已批准，已实施（含 2026-10-17 追加的三条）"。
- 本地说明页：11.9 假设表加一行、版本改 q5；11.15 补三条；第 13 节测试数改成实际数（现在页头 462、第 13 节还写 213），页头测试数同步。然后用 `python3 <scratchpad>/htmldoc/to_artifact.py xinci-bench-workflow/工作流说明.html <scratchpad>/xinci-bench-doc/xinci-bench-工作流说明.html` 生成发布版（scratchpad 路径由控制方给）。发布由控制方做。

- [ ] **Step 4: 跑全部测试**

Run: `<全部测试>`
Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-bench-workflow/xinci-bench-core/选站契约.md xinci-bench-workflow/xinci-bench-core/命令与观察.md xinci-bench-workflow/xinci-bench-quick/SKILL.md xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py docs/superpowers/specs/2026-10-16-xinci-bench-quick-pregame-go-design.md
git commit -m "xinci-bench 快道预判:契约 10.9、命令手册 7.7、快道 SKILL 写入 10-17 拍板的三条" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
