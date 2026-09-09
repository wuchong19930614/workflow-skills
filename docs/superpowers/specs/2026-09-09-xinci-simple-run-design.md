# xinci-simple-run 设计（xinci-simple-workflow 增补）

- 状态：设计稿（已与用户评审通过）
- 日期：2026-09-09
- 增补对象：[xinci-simple-workflow 设计](2026-09-09-xinci-simple-workflow-design.md) §8.4「单步驱动」预留的薄驱动器
- 目标：给用户一个与 `xinci_run max_rounds=10` 用法一致的启动暗号，连续跑多轮 scan + verify，不引入 xinci-run 那套控制器

## 目录

- [1. 触发](#1-触发)
- [2. 一轮的定义](#2-一轮的定义)
- [3. 执行者](#3-执行者)
- [4. 停机条件](#4-停机条件)
- [5. 收尾汇总](#5-收尾汇总)
- [6. 不做的事](#6-不做的事)
- [7. 单元与文件](#7-单元与文件)
- [8. 验收](#8-验收)

## 1. 触发

消息中出现 `xinci_simple_run`，或通过 `/xinci-simple-run` / Skill 工具调用，即开始，不重复确认。可带 `max_rounds=N`；未给时默认 **3**（一轮比 xinci 重，不取 6）。

## 2. 一轮的定义

一轮 = 按 `xinci-simple-scan/SKILL.md` 完整跑一次（来源按轮换自动选）+ 按 `xinci-simple-verify/SKILL.md` 核 `rank.py --top 5`。

每轮的 scan 与 verify 各写一份运行清单，`--suffix r<轮号>`，`--note` 首条写 `xinci_simple_run 第 k/N 轮`。同日多次启动 run 时轮号从 1 重数，suffix 冲突则追加 `-HHMM`。

## 3. 执行者

每轮派一个子代理，稳定 `executor_id`（形如 `run-<HHMM>-r<k>`），由它亲自做浏览器预检并跑完整轮，主上下文只编排与汇总。没有 Agent 机制时主上下文自己跑。同一轮不按阶段更换执行者。

## 4. 停机条件

只有三种，先完成当前原子动作再停：

| 条件 | 判法 | 收尾状态 |
| --- | --- | --- |
| 预算满 | 已完成 N 轮 | 正常收尾 |
| blocker | Semrush 登录失效 / 验证码 / 额度提示；浏览器四项预检不合规且重试一次仍不合规 | 报 blocker 停，写明现象 |
| 来源枯竭 | 连续两轮 scan 零注册 **且** `found` 池为空 | 报来源枯竭停 |

中途出 `verified` 不停。空轮、"看起来找不到"、运行时间长都不是停机理由。

## 5. 收尾汇总

一段中文：跑了 k/N 轮；共注册多少 `found`、核了多少；`verified` 列表（主词 / base / 报告路径）；`rejected` 按门分布（G1 / G2 / G3 / 季节性→parked / 排除 / 收入不足）；`parked` 数；Semrush 总计费调用数；下轮该轮到的来源。零产出如实说零。

## 6. 不做的事

- 不新增脚本、不改 `run_log.py`（每轮仍按 scan / verify 两个 skill 名写清单）、不改 `选词契约.md` 判据。
- 不写 session 文件、不做预检 SHA 绑定、不做降级轮计数、不做校准轮。
- 不做"出 verified 即停"的终止 A——用户要的是一次跑完尽量多出报告。

## 7. 单元与文件

- 新增 `xinci-simple-workflow/xinci-simple-run/SKILL.md`（唯一新文件）。
- `xinci-simple-workflow/README.md` 与仓库根 `README.md` 单元清单各加一行。
- symlink：`~/.claude/skills/xinci-simple-run`、`~/.codex/skills/xinci-simple-run`。

## 8. 验收

1. `xinci-simple-run/SKILL.md` frontmatter 合法，description 含 `xinci_simple_run` 与 `max_rounds`。
2. SKILL.md 不复制 scan / verify 的步骤，只引用它们的文件路径；不引用 xinci-workflow 任何文件。
3. 两处 README 单元清单含 `xinci-simple-run`。
4. 两处 symlink 解析到同一目录。
5. 既有 46 个测试仍全绿（本增补不动脚本）。
