---
name: xinci-bench-scan
description: '标杆倒推选站的发现阶段：从种子池或 sibling/serp/geo/community 来源取一批域名，初核"近 24 个月注册、AS≤30、英文区自然流量≥5,000"的低权重新站，合格的登记为方向。用于 bench scan、找标杆站、找新起量小站；深核用 xinci-bench-assess，不是 xinci 或 xinci-simple 工作流。'
---

# 找标杆

行动前读 `xinci-bench-workflow/xinci-bench-core/选站契约.md` §1–3、§7 与 `数据采集.md` §1–3、§6；写观察和清单的命令见 `命令与观察.md` §2–3。脚本都在 `xinci-bench-workflow/xinci-bench-core/scripts/`。

1. `report_status.py` 确认数据区；退出码 2 才问用户路径，再 `init_workspace.py --data-root <路径>`。种子池为空且从未导入时，先 `seed_import.py --legacy-root <xinci-simple 数据区>`。
2. `run_log.py --plan` 读恢复位置与 `next_source`；conflict=true 时显式确定 run_id。用户指定的来源优先；恢复 started/blocked 阶段沿用原来源与 seed_value。写 scan started 清单。
3. 取一批种子：`legacy` 用 `seeds.py take --source legacy --n 16`；其他来源先按 `选站契约.md` §3.1 的做法发现域名，`seeds.py add` 登记后再取。`seeds.py requeue` 把复查日已到的 B3 淘汰域名放回池。
4. 批量分析粗筛 AS 与流量（每批 ≤ 16 个）；过粗筛的逐个做 B1–B5：RDAP 注册日、Domain Overview 的域级 AS、美区自然流量与按国家分布（换算英文区 6 国合计）、Organic Research 去品牌词和定位词后的流量与词/页分布、范围排除。前项已不过的，后项填 null 省额度。
5. 整批写一份 scan 观察（`write_observation.py`）。全过的 `ledger.py register` 登记方向（同一标杆已用于别的方向须 `--confirm-distinct`）并 `seeds.py checked`；不过的 `seeds.py reject`。
6. `run_log.py --finish --run-id <ID> --outcome completed --semrush-calls <本阶段新增>`，`--direction-touched` 写本阶段登记的方向。汇报：初核数、登记数、淘汰按编号分布、Semrush 调用数、下次来源。

连续运行时 found 已有 ≥ 3 个：不查 Semrush，写 started 后 `--finish --outcome skipped`，交给 assess。

不做深核与 SERP 现场；不改门槛；登录失效、额度用完或验证码时 `--finish --outcome blocked` 并报告现象。

汇报前先跑 `report_status.py`：看板第一屏有"【立即建站】"行时，原样放在汇报最前面（新词快道的 go 在用户标已开建或放弃之前，每次都要再推荐一次）。

动 Semrush 之前先看 `run_log.py --plan` 的 `semrush_stop`：为 true（今天两条道合计已用到 90 次）就不再开始花 Semrush 的步骤，当前阶段按 blocked 收尾，改天接着跑。
