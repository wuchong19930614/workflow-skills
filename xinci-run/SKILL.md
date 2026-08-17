---
name: xinci-run
description: 新词工作流连续运行驱动器:启动后不间断循环"推进存量候选→扫描新候选→初筛→决策",直到找到合适建站的关键词(任一 go 决策)或 Semrush 网页版额度实际耗尽才停。启动暗号 xinci_run:用户消息中出现该暗号即启动本工作流。也在用户说启动新词工作流、一直跑到找到为止、连续运行、run until found 时使用。单步操作用 xinci-scan/track/qualify/decide,看状态用 xinci-status。
---

# xinci-run 连续运行驱动器

**启动暗号:`xinci_run`。** 用户消息中出现该暗号,即等同显式启动命令——无需其他措辞,立即进入连续运行。

用户的启动命令(含暗号)即标准授权:本次运行内所有 registrar 转移无需逐条确认,循环推进,直至命中终止契约。本 skill 只做编排;判断标准全部来自各阶段流程与 xinci-core 契约,**不因连续模式软化任何闸门或分数线**。

## 行动前必读

- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/生命周期契约.md(连续运行模式节:终止契约、标准授权、禁止的停止理由)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/闸门契约.md
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/陷阱类别.md
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/数据采集指南.md

## 运行循环

0. **开局**:运行 report_status 读账本;读淘汰方向索引(`数据/新词工作流/淘汰方向.md`),载入已淘汰方向(去重,不重复评估)。
1. **推进存量(优先;离 go 决策最近的先做)**:
   - qualified 候选 → 按 xinci-decide 完整模式出决策(可能直接命中终止 A,且主要整理既有证据,成本最低);
   - formation_confirmed 候选 → 按 xinci-qualify 流程认定(G6–G8 + 竞争审计 + 评分);
   - tracking 候选 → 按 xinci-track 流程复查(重跑 G1,看形成信号);达标即转 formation_confirmed,expiry 过/失效条件命中即转 expired,G0/G1 翻转即转 rejected。
2. **扫描新候选**:按 xinci-scan 流程(G0 最先,G5 先于 G2,G1 永不跳过;秒弃留痕进淘汰方向索引)。每轮轮换来源与角度:信号面(HN、Product Hunt、即刻、应用商店、厂商博客……)与变化面(有日期的法规/平台/技术/成本变化)交替;被拦截的来源如实记录并换源。
3. **分流**:screened 且窗口天级 → 立即走 xinci-decide 快道;窗口周/月级 → 转 tracking 入库,继续循环。
4. **每轮收尾**:把本轮内容追加进本次运行的清单(来源、候选、计费调用数);拒绝原因收敛时写 screen_unsatisfiable 假设报告——**然后继续运行**。
5. 回到步骤 1。

## 终止契约(全文见生命周期契约,此处为执行摘要)

- **正常终止 A——找到了**:registrar 记录任一 go 决策(fast_grab_ready / pilot_ready / build_ready)。停,交付决策书(md+html)与账本状态。
- **正常终止 B——额度耗尽**:Semrush 网页版界面**实际出现**额度耗尽提示;把提示要点记入运行清单后停,报告推进到了哪。假设或报错猜测不算。
- **正常收尾 C——会话资源耗尽**:上下文/会话资源接近极限时,完成当前动作、写运行清单、如实报告"会话资源耗尽,任务未完成、额度未耗尽"后停。这是操作边界不是任务终点,不得伪装成 A 或 B;已完成的转移保持有效,下次启动从账本现状继续。
- **异常中止**:blocker(认证/CAPTCHA/支付/浏览器封锁)使所有可行工作停摆。如实报告 blocker,不伪装成完成。
- **禁止停止**:扫描空轮、候选池空、"看起来找不到"、时间长、轮次多。空轮换来源换角度继续。(收尾 C 属操作边界,不在此列。)

## 硬规则

- 不注册域名、不花钱、不发布——找到词就停,建站是用户的动作。
- 标准授权只覆盖 registrar 转移与既定流程内的浏览/记录;不覆盖任何契约外的新动作。
- Semrush 纪律仍为 decision-changing only;为触发终止条件而空烧额度是禁止的。
- 快道决策书照常必含"跳过的闸门清单 + 风险确认"章节——运行停止后由用户阅读决策书完成风险确认,建站与否是用户的决定。连续模式下登记的 fast_grab_ready 未经用户事前逐条确认,history 的 by=xinci-run 即此含义的记录。
- 整个连续运行只写一份清单 `运行/<日期>-xinci-run.json`(每轮追加;同日再次启动加 HHMM 后缀),期间执行的各阶段流程不另写各阶段清单;中途被用户打断时,已完成的转移与清单保持有效,下次启动从账本现状继续。
