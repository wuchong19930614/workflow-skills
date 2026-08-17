---
name: xinci-track
description: 复查新词工作流中处于追踪状态的候选:重跑 G1、看 SERP 变化、命名定型与需求形成信号,向用户提议继续追踪/形成确认/过期。当用户说复查追踪清单、看看候选 X 现在什么情况、复查 watchlist 时使用。English triggers: recheck candidates, track watchlist, re-observe keyword. 由用户指定查什么、何时查;本 skill 不自我调度。
---

# xinci-track 追踪复查

对用户指定的 tracking 候选逐个复查。新词的观察会腐烂:第 3 天判断"竞争空场"的候选,第 17 天可能已经死了——所以每次复查必须重跑 G1,并把结论落成带日期的新观察。

复查哪些候选、何时复查,由用户决定;本 skill 被调用才动,不设节奏、不催促。

## 行动前必读

- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-workflow/xinci-core/生命周期契约.md(转移证据要求;时间字段只记录不调度)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-workflow/xinci-core/闸门契约.md(G0–G5;形成期允许的 Semrush 探针边界)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-workflow/xinci-core/数据采集指南.md(真浏览器原则;探针纪律)

## 工作流

对用户指定的每个候选(未指定则遍历全部 tracking 状态):

1. **重跑 G1。** 真浏览器搜精确词(美区桌面未登录)。首屏若已完成任务,G1 翻转,提议 `rejected`。
2. **看 SERP 变化。** 对照上次观察:竞品到位了吗?官方文档/工具出现了吗?谁在占坑?读完整首页。
3. **看命名定型。** 回访来源社区:叫法统一了还是分裂了?aliases 有没有胜出者?
4. **看需求形成信号。** 自动补全出现?首批 Semrush 行出现?讨论持续增长?(形成期允许轻量 Semrush 探针,仅限能改变决策的查询。)
5. **对照 expiry 与失效条件。** 失效条件命中或 expiry 已过 → 如实报告。
6. **写观察文件并登记复查:**

```bash
python3 /Users/vito.wu/IdeaProjects/workflow-skills/xinci-workflow/xinci-core/scripts/registrar.py checked \
  --slug <slug> --evidence "证据/<slug>/<日期>-track.json"
```

7. **向用户提交提议清单**,每候选一条,四种出口:
   - 继续追踪(观察已更新,无需转移);
   - 提议续期或字段修订(expiry 延后、aliases/失效条件追加),用户确认后:

```bash
python3 /Users/vito.wu/IdeaProjects/workflow-skills/xinci-workflow/xinci-core/scripts/registrar.py amend \
  --slug <slug> --by xinci-track --reason "<用户确认的续期/修订理由>" \
  [--expiry YYYY-MM-DD] [--add-alias <胜出的叫法>] [--add-invalidation "<新失效条件>"]
```

   - 提议 `formation_confirmed`(要求:累计 ≥2 次 -track 观察、命名定型、≥1 项形成信号、本次 G1=pass);
   - 提议 `expired`(expiry 已过/失效条件命中)或 `rejected`(G0 或 G1 翻转、竞品占位)。
8. **用户确认后**才执行对应 transition;写运行清单 `运行/<日期>-xinci-track.json`(同日再次运行加 HHMM 后缀)。

## 硬规则

- 每次复查必重跑 G1,不许沿用上次结论。
- 提议与执行分离:本 skill 永不直接改状态,一切转移经用户确认。例外:xinci-run 连续运行模式下,启动命令即标准授权,无需逐条确认。
- expiry 已过的候选必须给出明确提议(expired,或说明为何值得用户续期并给新 expiry),不许沉默跳过;续期必须由用户确认并附理由,经 registrar amend 执行——手工编辑账本是禁止的。
- 不自我调度:不设 next_check、不承诺"下次几天后查"、不催促用户。
- Semrush 探针仅限形成期、仅限能改变决策的查询;查了改变不了提议的,不查。
- 观察写要点不写转录;未打开的页面不得列入 source_urls。
