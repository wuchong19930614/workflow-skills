---
name: xinci-simple-verify
description: '核验流量型主题簇：对排序前 N 或指定候选检查任务组 SERP、直答、竞争、季节性及收入，生成机会报告。用于 simple verify、核验前几个、验某词；不发现新词。'
---

# 现场核验

行动前读 `xinci-simple-workflow/xinci-simple-core/选词契约.md` §1–2、§5–9，`数据采集.md` §1、§3–5、§7；写观察/清单与通过命令见 core 的 `命令与观察.md`。脚本均在 core/scripts。

1. `report_status.py` 确认数据区；缺配置才问路径。`run_log.py --plan` 核对恢复位置，写 started 清单。指定 slug 则用指定的，否则 `rank.py --no-write --top N`，默认 5；parked 可由用户指定补核。
2. 对候选先复核范围。明确命中就追加 verify 观察并 `transition --to rejected --gate scope`，无需为被排除项查询。
3. 收入上限预筛：按原始总量运行 `revenue_model.py --upper-bound`。形态/垂类未知不限定选项；限定须有依据。上限不足门槛时保存完整输出到观察的 prescreen.result，写 basis，`--gate revenue_prescreen` 拒绝；不得记作已做现场核验。
4. 其余候选按任务分组，必要时补采逐词表（`refresh-cluster`）。每组一个代表查询；不同意图、SERP 形态或直答风险须拆组。计入收入的词必须来自 cluster.keywords；不能计整批 phrase-match 总量。
5. 内置面板做四项预检。失败重试一次；仍不合规 → 不写 G1–G3、候选保留原状态，清单 blocked 后停。合规后逐组读满自然结果与第二页，核 G1/G2/G3、Trends 与范围复核。缺证据写 parked；不能把没看到数字判为全年平稳。
6. 每组用 `write_observation.py` 追加一份 schema_version=2 的 verify；字段包括 task_group、预检、AIO、摘要/组件、首页结构、逐结果 URL/AS/新鲜/格式、第二页、季节性与范围依据。观察不可覆盖，AS 不凭域名猜测。
7. 任一组被硬否决：若该组是候选核心任务，拒绝该候选并写 `--gate G1|G2|G3|scope`；若能独立剔除该任务组，说明缩小范围的依据，该组词不计收入，继续核剩余任务组。不能仍用原始总量算收益。
8. `qualification.py --slug <slug> --evidence <组1观察> --evidence <组2观察> ...` 重算已核验组的收入。证据不完整先补或 parked；完整但 base 不足则 `--gate revenue` 拒绝；通过则 `transition --to verified --form <输出form> --revenue-file <输出文件>`，传同一组观察引用。
9. `build_report.py --slug <slug>` 同批生成 md/html，再 `validate_ledger.py`。恢复时已通过但缺报告先补生成；证据绑定报错则如实报错，不能用新观察替换旧裁决。
10. 写 completed 清单；报告逐候选结论与决定性依据，分别计收入预筛、现场拒绝、parked 和 verified。运行清单只计本条新增的 Semrush 调用数。

历史 verified 复核：不因旧状态直接重出报告。证据不足用 `invalidate --to parked --gate evidence`；范围命中用 `invalidate --to rejected --gate scope`，须追加说明旧材料来源的审计观察，明确未重新采集现场。原报告自动归档。判据变更翻案仅走 requalify，并提供用户批准的变更依据、完整新核验与收入。
