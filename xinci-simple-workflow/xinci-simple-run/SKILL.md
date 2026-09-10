---
name: xinci-simple-run
description: '流量型选词连续运行：xinci_simple_run（可带 max_rounds=N，默认3）、/xinci-simple-run 或连续跑几轮 simple。每轮补足待核验后 verify 前5，预算内出 verified 不停；不是 xinci 新词工作流。'
---

# 连续运行

串联 scan 与 verify，不复制判据。行动前读 core/选词契约.md §2、§7–9，阶段步骤读对应 Skill。启动暗号即授权既定观察、账本和清单写入，不重复确认。

## 启动与恢复

1. `report_status.py` 确认数据区；未配置才问路径。
2. `run_log.py --plan` 核对恢复位置。先汇总所有运行：一个未完则返回 resume；多个则返回 conflict 与 active_run_ids，必须显式选定 --run-id。存在 resume 时继续同一 ID、轮号和预算，不重启；新 ID 写入也会拒绝绕过未完运行。读取最新清单与账本核对已落盘动作；已完成转移不重复，缺报告先补。旧文本清单保留可读，不能猜作新格式进度。
3. 没有未完运行才建立唯一 run_id（字母数字连字符），预算用户指定，否则 3。每阶段 started 和结束都用结构化清单；命令见 core/命令与观察.md。

## 每轮

- 遵循 --plan 的 action；仅新 scan 阶段采用 next_source/source_reason，恢复阶段沿用原来源与种子。found ≥5 时仍为 scan，并返回 scan_outcome=skipped，先记 scan started 再 finish skipped，之后 verify；不足5：完整执行 scan 补一批。跳过不推进来源/词根游标。
- verify 重新排序前5；不足5核全部。零候选可结束 verify 阶段，但 scan 必须有实际搜索，不能空动作凑轮。
- 阶段结束默认使用 `run_log.py --finish --run-id <ID> --outcome completed|blocked|skipped`，只填实际结果和新增计费，脚本推导轮次与下一步；已完成阶段不能重复 finish。
- 计费数只记本条新增调用量；不在最终清单重复累计之前已登记的调用。复核账本与清单、报告完整性后才算一轮完成。

## 执行者

有 Agent 机制时每轮派一个子代理，亲自预检并完成整轮，不按阶段换人；主上下文编排与核对。没有则主上下文执行。每轮返回时核对清单、账本变化、双格式报告和 validator；不一致先修复，不凭口头汇报继续。

## 停机

- 完成 N 轮：汇总实际搜索范围与结果。
- Semrush 登录失效/验证码/额度提示，或浏览器预检重试仍失败：写 blocked 清单，保留恢复位置，报告现象。

零产出轮正常推进来源，在预算内继续；出 verified 也继续。计费和耗时按实测汇报。

收尾：k/N 轮、注册/核验数、收入预筛数、按门拒绝数、parked 数、verified 的主词/base/报告路径及独立投入建议、Semrush 累计调用数与下次来源。发现历史待复核项单独披露，不计入本次成功产出。建站与否由用户决定。
