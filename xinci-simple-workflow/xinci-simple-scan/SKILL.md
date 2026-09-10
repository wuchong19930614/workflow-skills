---
name: xinci-simple-scan
description: '发现已有搜索量、竞争可能较弱的英文主题簇：Semrush 词根、小站反推或论坛问题。用于 simple scan、扫老词、找流量簇；现场核验用 xinci-simple-verify，不是 xinci 新词工作流。'
---

# 发现

行动前读 `xinci-simple-workflow/xinci-simple-core/选词契约.md` §1–4、§7，以及 `数据采集.md` §1–2。首次写观察/清单时读 core 的 `命令与观察.md`。

1. `report_status.py` 确认数据区；退出码 2 才问用户路径，再 `init_workspace.py --data-root <路径>`。脚本均在 `xinci-simple-workflow/xinci-simple-core/scripts/`。
2. `run_log.py --plan` 读恢复位置、上次词根和来源；conflict=true 时显式确定 run_id，不能新开运行覆盖旧任务。用户指定优先；否则来源轮换，root 从词根表中上次完成词根的下一个继续，跨轮不重置。旧清单只有文本时先核对，不猜历史进度。
3. 开始阶段写 started 清单。通过当前环境 Chrome 工具操作用户已登录的 Semrush，遵守固定过滤与每次最多 50 行预览。
4. 先四项范围排除、再准入；不花 AS 查询在明显不合格项上。取主词、原始总量、top 20 逐词量及来源依据。准入后补 shortlist 的排序代理；无法取到的非 KD 字段记 null。
5. 查账本避免同簇重复。`write_observation.py` 追加 scan，`ledger.py register` 登记 found。达到待核验池 5 个即可结束本批；源内无合格项如实记零。
6. `rank.py` 排序；用 `run_log.py --finish --run-id <ID> --outcome completed` 结束阶段，自动推导 next_step=verify，只补实际结果和本条新增计费。报告注册/排除数、计费数及下一来源。

连续运行已有 ≥5 个 found 时，本阶段不查 Semrush，先登记 started，再 finish skipped 后交给 verify；用户明确指定新来源的单独 scan 可照指定执行。

逐词表不足以支撑候选收益、而上限表明补采有价值时，补预览/导出，再由 `ledger.py refresh-cluster` 更新非终态候选。原始总量与具体词表必须同数据库和过滤口径；不能按收入需要倒填词量。

不做 Google 现场核验；不把 Semrush 总量视为已核验量。中断写 blocked 清单，候选状态以账本为准。
