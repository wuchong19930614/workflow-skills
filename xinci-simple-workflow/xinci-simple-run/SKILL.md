---
name: xinci-simple-run
description: '流量型选词的连续运行驱动器。当消息中出现启动暗号 xinci_simple_run（可带 max_rounds=N,默认 3）、通过 /xinci-simple-run 或 Skill 工具调用、或用户说"连续跑几轮 simple"时使用。一轮 = 一次 xinci-simple-scan + verify 排序前 5;跑满预算才停,中途出 verified 不停。English triggers: xinci_simple_run, run simple workflow N rounds. 这是 xinci-simple-workflow,不是 xinci 新词工作流的 xinci-run。'
---

# xinci-simple-run 连续运行驱动器

把 `xinci-simple-scan` 与 `xinci-simple-verify` 串成 N 轮连跑。本 skill 不含任何判据、不新增脚本、不写 session 文件；判据看 `xinci-simple-workflow/xinci-simple-core/选词契约.md`，步骤看两个阶段 skill 的 SKILL.md。

## 启动

- `xinci_simple_run`、`/xinci-simple-run` 或"连续跑几轮 simple"即开始，不重复确认。
- 预算 `max_rounds=N`，未给默认 **3**。一轮约 1–2 小时、Semrush 约 3–5 次计费查询，按此估预算。
- 启动即授权既定路径上的全部 `ledger.py` 写入（register / transition）；闸门、准入阈值、收入门槛不因连续运行降低。

第 0 步数据区同两个阶段 skill：`report_status.py` 正常即已配置；退出码 2 则问用户后 `init_workspace.py --data-root <路径>`。

## 一轮

1. **scan**：按 `xinci-simple-workflow/xinci-simple-scan/SKILL.md` 完整跑一次。来源按轮换自动选（读上一轮清单 note 决定下一个来源）；用户在启动命令里指定了来源或词根就按指定的。
2. **verify**：按 `xinci-simple-workflow/xinci-simple-verify/SKILL.md` 核 `rank.py --no-write --top 5`。
3. **运行清单**：scan 与 verify 各一份，`run_log.py --suffix r<轮号>`，`--note` 首条写 `xinci_simple_run 第 k/N 轮`。同日多次启动轮号从 1 重数，suffix 冲突则改 `r<k>-HHMM`。

## 执行者

- 每轮派一个子代理，`executor_id` 形如 `run-<HHMM>-r<k>`，由它亲自做浏览器预检（`数据采集.md §4`）并跑完整轮；同一轮不按阶段换执行者。主上下文只编排、核对清单、汇总。
- 没有 Agent 机制时主上下文就是执行者。
- 子代理返回后主上下文核对：本轮两份运行清单存在、`ledger.py list` 状态变化与子代理汇报一致；不一致按清单为准。

## 停机

只有三种，先完成当前原子动作（写完观察、写完清单）再停：

| 条件 | 判法 | 收尾 |
| --- | --- | --- |
| 预算满 | 已完成 N 轮 | 正常汇总 |
| blocker | Semrush 登录失效 / 验证码 / 额度提示；浏览器四项预检不合规且重试一次仍不合规 | 报 blocker，写明现象与发生在第几轮 |
| 来源枯竭 | 连续两轮 scan 零注册 **且** `found` 池为空 | 报来源枯竭，列已跑过的来源 |

中途出 `verified` **不停**。空轮、"看起来找不到"、运行时间长都不是停机理由。

## 收尾汇总

一段中文，含：跑了 k/N 轮；共注册多少 `found`、核了多少；`verified` 列表（主词 / base / 报告路径）；`rejected` 按门分布（G1 / G2 / G3 / 排除 / 收入不足）与 `parked` 数；Semrush 总计费调用数（各轮清单 `billable_calls` 之和）；下轮该轮到的来源。零产出如实说零。

## 硬规则

- 不复制 scan / verify 的步骤到本文件；两个阶段 skill 改了，本 skill 自动跟着。
- 不为凑轮数放宽准入或收入门槛；不用空轮凑停机条件。
- 不用 Chrome 读 Google SERP，不登录内置面板——两条通道纪律见 `数据采集.md §1`。
- 汇总只陈述事实，建站与否是用户的决定。
