---
name: xinci-bench-run
description: '标杆倒推选站的连续运行：暗号 xinci_bench_run（可带 max_rounds=N，默认3）或 /xinci-bench-run。每轮先补足 3 个待深核方向，再深核排序前 2 个；出 go 不停、跑满预算。不是 xinci_run 或 xinci_simple_run。'
---

# 连续运行

串联 scan 与 assess，不复制判据。行动前读 `xinci-bench-workflow/xinci-bench-core/选站契约.md` §0、§2、§7、§9，阶段步骤读对应 Skill。启动暗号即授权既定的观察、账本、种子池和清单写入，不重复确认。

## 启动与恢复

1. `report_status.py` 确认数据区；未配置才问路径。
2. `run_log.py --plan`：一个未完运行就恢复同一 run_id、轮号和预算；多个则返回 conflict，必须显式选定 `--run-id`；有未完运行时不能新建。
3. 没有未完运行才建立新 run_id（字母数字连字符），预算用用户给的 N，否则 3。
4. Semrush 部分由主会话亲自执行。开跑前确认 Chrome 工具可用；被自动模式分类器拦时不要转达授权重试，停下请用户加放行规则或切"逐条询问"模式。

## 每轮

1. **scan**：按 `--plan` 的 action 与 next_source 执行 xinci-bench-scan；`scan_outcome=skipped` 时写 started 后 finish skipped。
2. **assess**：执行 xinci-bench-assess，深核 `rank` 前 2 个；没有 found 时也要写 assess 清单并如实记零。
3. 每阶段结束都用 `run_log.py --finish`，只填本阶段新增调用；核对清单、账本、决策书与 `validate_ledger.py` 一致后，才算一轮完成。

## 停机

- 跑满 N 轮停。出 go 不停（用户 2026-10-13 定）。
- Semrush 登录失效、额度用完、验证码，或浏览器预检重试仍失败：写 blocked 清单，保留恢复位置，报告现象；同一 run_id 之后可以接着跑。

收尾汇报：k/N 轮、初核域名数与通过数、登记方向数、go/rejected（按 gate）/parked 数、每个 go 的方向与基准收入与决策书路径、取到的未确认假设证据、Semrush 累计调用、种子池余量、下次来源。建不建站由用户决定。
