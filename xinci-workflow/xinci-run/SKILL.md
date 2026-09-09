---
name: xinci-run
description: '新词工作流的一体入口与连续运行驱动器。当消息中出现启动暗号 xinci_run、通过 /xinci-run 或 Skill 工具调用、或用户说"启动新词工作流"、"一直跑到找到为止"时使用。'
---

# xinci-run 连续运行驱动器

先读 `xinci-workflow/xinci-core/通用约定.md`；新运行还须读[运行证据契约](../xinci-core/运行证据契约.md)。再按需读取生命周期契约的「连续运行模式」「窗口赌注的挂起与出闸」「会话与轮次收尾」「schema v3」。不要在开局加载全部闸门、陷阱、采集指南或历史校准；进入某个阶段时读对应 SKILL.md，由阶段 Skill 指向当下需要的契约章节。

## 启动与授权

- `xinci_run`、`/xinci-run` 或“启动新词工作流”等调用即开始，不重复确认。预算为 `max_rounds=N`、`max_hours=H`；未给 `max_rounds` 时默认 6，两项并存取先命中者。
- 完成实质工作的降级轮不消耗预算，但连续 3 轮即被控制器拒绝再开。仅预检重试用 abort-round 留痕，不计轮；禁止靠空轮凑受阻条件。
- 启动即授权既定路径上的 registrar 转移，统一使用 `--by xinci-run --run-id <run_id>`；闸门、证据和分数线不降低。唯一例外是 `G3=veto_window_bet` 的出闸，仍须候选级明确确认。
- 每一轮只派一个轮次子代理；它以稳定 `executor_id` 亲自预检浏览器并完成整轮。同一轮不得按阶段更换子代理，未 `record-round` 不得再次开轮。没有 Agent 机制时，主上下文就是唯一执行者。

## 开局

```bash
python3 xinci-workflow/xinci-core/scripts/run_controller.py list
python3 xinci-workflow/xinci-core/scripts/run_controller.py start [--max-rounds N] [--max-hours H]  # 仅无 active 时
python3 xinci-workflow/xinci-core/scripts/run_controller.py begin-round --run-id <run_id> --executor-id <executor_id> \
  --round-type <discovery|progression|tracking|calibration> \
  --browser-controllable yes|no --browser-desktop yes|no --browser-region us|other|unknown --browser-logged-out yes|no \
  --preflight-evidence <数据区相对预检JSON> --work-package '<targets与completion JSON>'
python3 xinci-workflow/xinci-core/scripts/run_policy.py --run-id <run_id>
python3 xinci-workflow/xinci-core/scripts/report_status.py
```

有 active 就恢复，不重启。浏览器四项必须由本轮执行者现场核对；不能借用父任务、上一轮或另一执行者的预检。

先读 run_policy 的 candidate_actions，按可执行动作确定本轮工作包；不要把没有复查提醒解释为没有形成复核动作。未处理的候选不得记为 not_due。

## 每轮路由

1. **先推进存量。** 按状态路由：`formation_confirmed → xinci-qualify`；`qualified/hold → xinci-decide`；`tracking → xinci-track`；`screened` 按 expiry 与窗口走到期处置、tracking 或快道；new `captured` 先补缺门；到期 SERP 型 new `rejected` 按 xinci-track 复核。mature 在 formation_confirmed 前只记录应交 xinci-mature，不由连续运行推进。
2. **再按策略扫描。** `full` 才调用 xinci-scan 注册 new；`trigger_only` 只维护触发池；`debt_only` 只还债；`paused` 只恢复、校验和收尾。以 `run_policy.py` 输出为准，不在 Skill 里重新推导策略。
3. **分流。** 所有存活候选先 `captured→screened`；days 走 xinci-decide 快道，weeks/months 走 tracking。`G3=veto_window_bet` 留在 captured 等确认，确认后只可走快道或 rejected。
4. **收尾。** 汇集来源、计费调用、候选变化和漏斗后执行 `record-round`。一轮没有扫描时五项写 0；0 表示已统计为零。

优先级、积压阈值、来源轮换、校准轮、天花板和终止状态的正式定义只看生命周期契约与 `run_policy.py`；阶段判断只看对应 Skill 和闸门契约，禁止在本文件复制第二套判据。

## 轮次收尾

```bash
python3 xinci-workflow/xinci-core/scripts/run_controller.py record-round --run-id <run_id> \
  [--source-opened <URL>] [--source-blocked '<URL>(拦截现象)'] [--billable-calls <N>] [--note '<事实>'] \
  [--candidate-reviewed '{"slug":"<slug>","outcome":"not_due","reason":"<事实>","evidence_refs":[]}'] \
  [--false-negative-audit '<校准轮 JSON>'] --work-results '<逐项结果 JSON 数组>' \
  --funnel '{"extracted":0,"rejected_zero_cost":0,"rejected_g1":0,"deep_audited":0,"queued":0,"carryover_audited":0}'
```

- 正式漏斗满足 `extracted = rejected_zero_cost + rejected_g1 + deep_audited + queued`；`carryover_audited` 不参与等式。raw trigger 使用控制器生成的独立 `trigger_funnel`。
- 只读既有证据且无 history 写入时用 `--candidate-reviewed`，不冒充 `candidates_touched`。
- 每 10 个 discovery 轮后的 calibration 要先跑 `false_negative_sample.py`；样本与 blocked 规则见生命周期契约「schema v3」。

## 终止与异常

命中生命周期契约的 A–E 或 blocker 后，先完成当前原子动作和 `record-round`，再执行：

```bash
python3 xinci-workflow/xinci-core/scripts/run_controller.py finish --run-id <run_id> --status <中文展示名> --reason <事实> [--evidence-ref <数据区相对路径>]
```

- go 必须由本 run_id 的当前 GO 状态支持；Semrush 额度耗尽必须有网页版现场证据。预算/资源用完不是任务完成。
- 空轮、候选池空、“看起来找不到”和运行时间长都不是终止理由；验证码、认证、支付或浏览器封锁使所有可行工作停摆时如实标记 blocker。
- 新增或改写陷阱类别属于契约变更，不在启动 xinci-run 的标准授权内；运行中只记录提案与证据，等待用户确认。
- 整个 run 只由控制器维护一份清单；不另写阶段清单，不手改 session、manifest、账本或索引。
