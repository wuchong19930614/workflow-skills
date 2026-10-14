---
name: xinci-bench-status
description: '标杆倒推选站工作流的只读看板：各状态方向数、待深核排序、搁置天数、go 的决策书路径、种子池余量、待复查淘汰数、累计 Semrush 调用。用于 bench status、看 bench 工作流状态；不是 xinci-status 或 xinci-simple-status。'
---

# 看板

只读，不写任何文件。

1. `python3 xinci-bench-workflow/xinci-bench-core/scripts/report_status.py`；需要结构化数据时加 `--json`。退出码 2 表示数据区未配置，告诉用户需要先指定数据区，不替用户选。
2. 需要时再跑 `run_log.py --plan` 看恢复位置、下次来源；跑 `validate_ledger.py` 看账本是否有错。
3. 汇报时先给结论（有没有 go、下一步该做什么），再列数字；搁置超过 90 天的单独提醒；validator 有错时如实列出，不当作正常状态。

汇报前先跑 `report_status.py`：看板第一屏有"【立即建站】"行时，原样放在汇报最前面（新词快道的 go 在用户标已开建或放弃之前，每次都要再推荐一次）。
