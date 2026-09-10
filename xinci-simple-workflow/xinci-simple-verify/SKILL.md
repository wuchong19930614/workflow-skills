---
name: xinci-simple-verify
description: '核验流量型主题簇：对排序前 N 或指定候选检查任务组 SERP、直答、竞争、季节性及收入，生成机会报告。用于 simple verify、核验前几个、验某词；不发现新词。'
---

# 现场核验

行动前读 `xinci-simple-workflow/xinci-simple-core/选词契约.md` §1–2、§5–10，`数据采集.md` §1、§3–6；写观察/清单与通过命令见 core 的 `命令与观察.md`。脚本均在 core/scripts。

1. `report_status.py` 确认数据区；缺配置才问路径。`run_log.py --plan` 核对恢复位置：多个未完运行会显式报 conflict，先确定 run_id；写 started 清单。指定 slug 则用指定的，否则 `rank.py --no-write --top N`，默认 5；parked 可由用户指定补核。
2. 对候选先复核范围。明确命中就追加 verify 观察并 `transition --to rejected --gate scope`，无需为被排除项查询。
3. 收入上限预筛：按原始总量运行 `revenue_model.py --upper-bound`。形态/垂类未知不限定选项；限定须有依据。上限不足门槛时保存完整输出到观察的 prescreen.result，写 basis，`--gate revenue_prescreen` 拒绝；不得记作已做现场核验。
4. 其余候选按任务分组，必要时补采逐词表（`refresh-cluster`），随后 `ledger.py set-task-plan` 预登记 core/support 角色、组词与核心任务依据。计划冻结，不能看过结果再删核心组或改角色。每组一个代表查询；不同意图、SERP 形态或直答风险须拆组。计入收入的词必须来自 cluster.keywords；不能计整批 phrase-match 总量。
5. 内置面板做四项预检。失败重试一次；仍不合规 → 不写 G1–G3、候选保留原状态，清单 blocked 后停。合规后逐组读满自然结果与第二页，核 G1/G2/G3、Trends 与范围复核。缺证据写 parked；不能把没看到数字判为全年平稳。
6. 每组用 `write_observation.py` 追加一份 schema_version=2 的 verify；字段包括 task_group、预检、AIO、摘要/组件、首页结构、逐结果 URL/AS/新鲜/格式、第二页、季节性与范围依据。观察不可覆盖，AS 不凭域名猜测。
7. 核心组硬门失败，使用结算命令加 --gate 提前拒绝；脚本核实对应最小证据，不要求后续无关门。支撑组需要剔除时在其观察 task_group.exclusion_reason 写明依据，保留该组观察；不能通过省略引用剔除组。核心组不能剔除。
8. 默认用 `settle_candidate.py --slug <slug> --evidence <组1观察> --evidence <组2观察> ... --by <执行者> --reason <依据>`，传入计划全部组。脚本重算后通过或按收入拒绝；缺证据会报错，补齐或明确传 --park。早期拒绝传 --gate；收入预筛仍保存 prescreen.result 与依据。
9. 结算自动生成并检查 md/html；报告失败后重复同一命令仅恢复报告，不重复历史。绑定错误如实报告，不能拿新观察覆写旧裁决。研究通过后按契约 §10 补最小产品、优势、投入/爬坡依据和有预算的最小验证计划，用 investment.py plan 冻结并重出报告；数值未知显式标 null + 原因，预算或关键条件不足时保留“投入未估算”并列缺口，不能为完成研究虚构参数。实际执行另依授权，不在 verify 中自动建站。收尾运行 validate_ledger.py 检查全账本。
10. `run_log.py --finish --run-id <ID> --outcome completed --billable-calls <本条新增调用数>` 结束阶段，轮次、预算和下一步由脚本推导；报告逐候选结果。重复完成会拒收，先读 --plan 再恢复，避免重复计费。

历史 verified 复核：不因旧状态直接重出报告。证据不足用 `invalidate --to parked --gate evidence`；范围命中用 `invalidate --to rejected --gate scope`，须追加说明旧材料来源的审计观察，明确未重新采集现场。原报告自动归档。判据变更翻案仅走 requalify，并提供用户批准的变更依据、完整新核验与收入。
