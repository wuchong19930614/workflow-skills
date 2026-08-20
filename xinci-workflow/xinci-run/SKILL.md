---
name: xinci-run
description: '新词工作流的一体入口与连续运行驱动器:调用本 skill 即启动整个工作流,不间断循环"推进存量候选→扫描新候选→初筛→决策",直到产出任一 go 决策(全站 go,或一份标好价的快道赌注)、Semrush 网页版额度实际耗尽,或预算用完(未指定时默认 max_rounds=6)才停;会话资源耗尽或撞上 blocker 时,如实报告后停,不伪装成完成。启动暗号 xinci_run:用户消息中出现该暗号即启动。也在用户说启动新词工作流、一直跑到找到为止、连续运行、run until found 时使用。单步操作用 xinci-scan/track/qualify/decide,看状态用 xinci-status。'
---

# xinci-run 一体入口·连续运行驱动器

**调用即启动整个工作流。** 以下任一方式触发本 skill,一律等同显式启动命令,读完必读文件后立即开跑,**不向用户确认"是否开始"、不要求补充参数**:

- 消息中出现启动暗号 `xinci_run`;
- 环境的 skill 调用机制(如 `/xinci-run`、Skill 工具);
- "启动新词工作流"、"一直跑到找到为止"等自然语言。

启动即标准授权:本次运行内既定路径上的 registrar 转移无需逐条确认,循环推进,直至命中终止契约;唯一例外是 `G3=veto_window_bet` 的 `captured→screened`,它要求用户单步接受窗口赌注风险。本 skill 只做编排;判断标准全部来自各阶段流程文件与 xinci-core 契约,**不因连续模式降低任何闸门或分数线**。

**预算参数**:启动消息中可附 `max_rounds=N`(最多跑 N 轮)或 `max_hours=H`(最长跑 H 小时)。**未指定时默认 `max_rounds=6`**——终止 B(额度耗尽)在单次运行内几乎不可达(扫描期禁用 Semrush、形成期只允许轻探针、7 天跨度闸使单次运行做不出**新的** formation_confirmed;账本已有 formation_confirmed/qualified 存量时 qualify/decide 确实会动用 Semrush,但那是每候选个位数的 decision-changing 查询,离烧穿额度仍差得远),没有默认预算的"不限"等于跑到会话资源耗尽。命中预算即走"正常收尾——预算命中"(见终止契约);预算是用户主权,不属于禁止的停止理由。**不因参数缺失暂停或询问**,按默认值开跑。

> **路径约定**:相对路径以仓库根为基准(正本在 `xinci-workflow/xinci-run/SKILL.md`,symlink 加载时 `readlink` 后上溯两级即仓库根);bash 在仓库根执行,或展开为绝对路径。

## 行动前必读(开局一次)

- xinci-workflow/xinci-core/生命周期契约.md(连续运行模式节:终止契约、标准授权、禁止的停止理由)
- xinci-workflow/xinci-core/闸门契约.md
- xinci-workflow/xinci-core/陷阱类别.md
- xinci-workflow/xinci-core/数据采集指南.md

## 阶段流程文件(首次进入对应步骤时读,执行以其为准)

本 skill 不复制各阶段的判断步骤;进入运行循环的某一步之前,先读该步的 SKILL.md,按它执行(其中既定路径的"提议-逐条确认"由本模式的标准授权取代;`G3=veto_window_bet` 出闸例外仍须单步确认,其余原样适用):

- 扫描:xinci-workflow/xinci-scan/SKILL.md
- 复查:xinci-workflow/xinci-track/SKILL.md
- 认定:xinci-workflow/xinci-qualify/SKILL.md
- 决策:xinci-workflow/xinci-decide/SKILL.md

(状态汇报不需要读 xinci-status/SKILL.md,开局直接跑 report_status 脚本即可。)

## 执行架构:子代理化(有 Agent 机制时必用)

连续运行的天然瓶颈是主上下文:每轮的页面阅读若都留在主上下文,运行会在远未命中终止契约时撞上会话资源边界(收尾 C)。因此:

- **每个阶段动作(一次扫描轮、一个候选的复查/认定/决策)派一个子代理执行**:子代理读对应阶段 SKILL.md 与契约、操作浏览器、写观察文件、在标准授权下调用 registrar,**并在第 2/3 层当场批量 `screen_index.py append`**——本轮的秒弃与 G1 否决由它自己写进淘汰方向索引,一轮两三百条不许回传主上下文(那正是 screen_index 存在的理由:索引本身多大都不进上下文);最后只返回结构化结论(触及的候选、执行的转移、来源与计费调用数、漏斗五项、以及疑似该归并的模式名)。连续模式下(无论主上下文还是子代理执行)registrar 调用一律 `--by xinci-run`——history 里 by=xinci-run 就是"标准授权、未经逐条确认"的印记,区别于单步模式的 by=阶段名。
- **主上下文只做编排**:维护轮次、汇集子代理结论、通过 `record-round` 提交本轮事实、判断终止契约。**淘汰方向索引由执行者当场写,不经主上下文**;主上下文在这件事上只做一件——归并出新陷阱类别时补那一行归并记录(term 写模式名本身,见硬规则)。页面内容、SERP 细节留在子代理里,以观察文件为准。
- **子代理顺序执行,不并发**:真浏览器是共享资源,并发会互相踩踏。
- 环境无子代理机制时降级为主上下文直接执行各阶段,其余规则不变。

## 运行循环

0. **创建或恢复运行会话**:先执行一次 `run_controller.py recover`(只恢复 `运行状态/事务` 的 pending journal,无 pending 时返回空数组),再执行 `list` 读取 `active` run_id；有 active 就 `show --run-id ...` 恢复,没有才 `start`(带用户预算;未指定时 `--max-rounds 6`)。每轮开始先 `begin-round`,结束只调用 `record-round`——它原子追加 manifest 后才结束轮次,旧 `end-round` 已停用。所有带 `--by xinci-run` 的 registrar 命令必须同时带 `--run-id <run_id>`。然后运行 report_status 读账本、读陷阱类别。去重用 `screen_index.py check`:只有 `[见过]` 自动跳过;`[疑似重复·须快审]` 比较具体任务后用 `screen_index.py resolve` 登记 same/distinct,不留口头裁决。
1. **推进存量(优先;离 go 决策最近的先做)**:
   - hold 候选 → 先读 hold 的决定性理由:若理由质疑 G6–G8 或认定仍否成立,按 xinci-qualify 做定向重审(推翻即 `hold→disqualified`);否则按 xinci-decide 重出决策(`hold→build_ready / pilot_ready / no_site`)。不得把 hold 挡在循环外,也不得转回 formation_confirmed;
   - qualified 候选 → 按 xinci-decide 完整模式出决策(流程文件见上表;可能直接命中终止 A,且主要整理既有证据,成本最低);
   - screened 候选 → expiry 已过先按下面到期规则转 expired;未过期且 window_estimate=days 的立即按 xinci-decide 快道模式出决策;未过期且 window_estimate=weeks/months 的按 xinci-scan 分流要求转 tracking(带 expiry、失效条件与证据)。若它带 `G3=veto_window_bet`,说明此前已由用户单步确认完成出闸,只准走快道,不得进 tracking;
   - formation_confirmed 候选 → 按 xinci-qualify 流程认定(G6–G8 + 竞争审计 + 评分);
   - tracking 候选 → 按 xinci-track 流程复查(重跑 G1,看形成信号);达标即转 formation_confirmed,expiry 过/失效条件命中即转 expired,G0/G1 翻转即转 rejected。**单次运行内每个 tracking 候选至多复查一次**——SERP 在几小时内不会变,重复复查是空烧;形成以真实天数计,registrar 的 7 天跨度闸也不接受当日凑数;
   - **captured 候选(上轮扫描排队的)→ 严格按 `gates` 只补缺失的门**:缺 G1 的(上轮超 G1 上限没搜)**先补 G1**;G1 已过后只补尚缺的 G2/G3,已有的 `G3=pass` 不重复验证——排队身份不豁免任何闸门,G1 永不跳过。排队 expiry 已过的,**即转** `captured→expired`(标准授权覆盖它,不必回头问用户),不占深审配额。带 `G3=veto_window_bet` 挂起等确认的**不再补门**;没有一次性确认就不出闸,取得确认后由同一 run_id 出闸,不占深审配额;但**它的 expiry 过了照常即转 `captured→expired`**——挂起不免疫过期,收它是契约内的既定路径、不降低任何闸门,在标准授权内。
     这是上轮欠的债,**必须在本轮扫描产生新债之前还**。**还债深审有自己的配额(默认 ≤5;`captured` 存量 >20 时按下面软闸表提到 ≤10),与步骤 2 扫描的 ≤5 深审配额彼此独立**——还债不吃掉本轮新扫描的深审名额,否则扫出来的存活方向只能全部排队,积压反而更快。还债深审的次数记进本轮 `funnel.carryover_audited`(不参与加总等式,它不属于本轮 `extracted`)。
     **存量 captured 的消化归本步骤**:派子代理执行步骤 2 的扫描时,子代理从 xinci-scan 第 1 层开始,不再重跑它的第 0 层接队——两处都做会重复深审、双花配额。
   - **到期清理(`screened` / `fast_grab_ready`)**:`screened` 候选 expiry 已过(既没排上快道、也没转进追踪,窗口自己过了)→ **即转** `screened→expired`;`fast_grab_ready` 候选 expiry 已过、或窗口已关闭(通用工具已收录该对象、赌注前提消失)→ **即转** `fast_grab_ready→expired`。两条都由标准授权直接转,不必回头问用户,也不占深审配额;它们没有失败的闸门,**不许塞进 `rejected`**。单步模式下这两条归 xinci-decide 提议(前者是它快道模式的输入、后者是它的产出),四条 expired 边的提议人见生命周期契约。
   - **积压软闸(按存量压低扫描量,不停扫)**:**在步骤 1 开始前**量一次 `captured` 存量(不含挂起等确认的)——本轮的还债深审配额与步骤 2 的提取目标都据这一个读数定(还债配额是步骤 1 内部的参数,量在步骤 1 之后就取不到了):

     | captured 存量 | 本轮提取目标 | 还债深审配额 |
     | --- | --- | --- |
     | ≤10 | 200–300(正常) | ≤5 |
     | 11–20 | 100–150(减半) | ≤5 |
     | >20 | 50–80(最低档) | ≤10(临时提到两轮的量) |

     理由:漏斗每轮放行 10–20 个候选、深审只吃 5 个,不设闸的话队列单调增长,越积压越违背这条赛道的前提——晚三天发现的候选通常已经没价值。但**整轮停扫是过头的**:每轮进 10–20、出 ≤5,一旦积压就会连着好几轮不扫新,而默认预算只有 6 轮,很可能整次运行一个新方向都没扫到。压低提取量同样能让队列收敛(进得少、出得稳),又保证每轮都有新输入。只有当**本轮确实一条都没扫**(例如所有来源被拦)时,该轮 `funnel` 才把 `extracted` 与四个去向五项全写 0——那是"本轮只推进存量"的记录,此时 `carryover_audited` 更要写实。
2. **扫描新候选**(提取目标按步骤 1 软闸表定,子代理从 xinci-scan 第 1 层开始):按 xinci-scan 流程(零成本批 G0→G4→G5 最先,G1 永不跳过;秒弃与 G1 否决都批量留痕进淘汰方向索引,账本只收还有下一步的候选)。**子代理跳过的只是第 0 层的「接队」(存量 captured 归步骤 1),第 0 层的去重 check 照做**:提取完本轮方向后立刻 `screen_index.py check`,命中的不再评估、也不计入 `extracted`。每轮轮换来源与角度:信号面(HN、Product Hunt、即刻、应用商店、厂商博客……)与变化面(有日期的法规/平台/技术/成本变化)交替;被拦截的来源如实记录并换源。
3. **分流**(步骤 1 还债深审出的候选与步骤 2 扫描出的候选**一并分流**,别只分流新扫的):**先出闸 `captured → screened`**(带 G2/G3 结论与 `--window-estimate`,这一步不能跳——tracking 与快道都只从 screened 出发,直接 `--to tracking` 会被 registrar 判非法转移;命令见 xinci-scan 第 5 层),再按窗口分流:窗口天级 → 立即走 xinci-decide 快道模式;窗口周/月级 → 转 tracking 入库;`G3=veto_window_bet` 的 → 留在 captured 挂起,用户确认后记录候选级一次性授权,再由同一 run_id 出闸(见硬规则)。然后继续循环。
4. **每轮收尾**:调用下面的受控入口提交来源、计费调用数、notes 与漏斗。不要手写 manifest,也不要调用 `end-round`;registrar 会把活动轮号写进 history,控制器据此自动归集本轮候选并反查 `funnel.queued` 是否真的对应带 gates+expiry 的排队候选。**还债深审的次数写进 `carryover_audited`**——它不参与加总等式;去重命中的方向同理不计入 `extracted`。本轮没扫描时五项全写 0。若 manifest 已写而 session 写入中断,`recover` 不处理这个写入点;用完全相同的 `record-round` 参数重试,脚本会幂等完成而不重复追加。

```bash
python3 xinci-workflow/xinci-core/scripts/run_controller.py record-round \
  --run-id <run_id> \
  [--source-opened <URL>] [--source-blocked '<URL>(拦截现象)'] \
  [--billable-calls <N>] [--note '<事实>'] \
  --funnel '{"extracted":0,"rejected_zero_cost":0,"rejected_g1":0,"deep_audited":0,"queued":0}'
```

拒绝原因收敛时把 screen_unsatisfiable 假设放进 `--note`——**然后继续运行**。
5. 回到步骤 1。命中终止/收尾条件后,先写完且只保留一份本次 manifest,再执行 `run_controller.py finish --run-id <run_id> --status <状态> --reason <事实>` 关闭会话。`finish` 会先跑完整清单校验,拒绝字段漂移、清单缺失/重复、funnel 缺失、轮次不连续或漏记候选,失败时 session 保持 active;`--status go` 还要求账本中存在**当前仍处于 GO 状态、且由本次 run_id 转入**的候选,不能用文字理由冒充产出。活动会话存在时 registrar 拒绝所有单步写入。

## 终止契约(全文见生命周期契约,此处为执行摘要)

- **正常终止 A——拿到可交付结论**:registrar 记录任一 go 决策(fast_grab_ready / pilot_ready / build_ready)。停,交付决策书(md+html)与账本状态。**两类 go 分量不同,报告时不许混说**:build_ready / pilot_ready 过了 G6–G8 与 80 分线,是"值得建站";fast_grab_ready 是"一份标好价的窗口赌注",不等于被验证的生意。
- **正常终止 B——额度耗尽**:Semrush 网页版界面**实际出现**额度耗尽提示;把提示要点记入运行清单后停,报告推进到了哪。假设或报错猜测不算。
- **正常收尾 C——会话资源耗尽**:上下文/会话资源接近极限时,完成当前动作、写运行清单、如实报告"会话资源耗尽,任务未完成、额度未耗尽"后停。这是操作边界不是任务终点,不得伪装成 A 或 B;已完成的转移保持有效,下次启动从账本现状继续。
- **正常收尾 D——预算命中**:预算用完——用户启动时给的 `max_rounds`/`max_hours`,或未指定时的默认 `max_rounds=6`。处理同 C:完成当前动作、写运行清单、如实报告推进到哪与预算命中,下次启动从账本现状继续。
- **异常中止**:blocker(认证/CAPTCHA/支付/浏览器封锁)使所有可行工作停摆。如实报告 blocker,不伪装成完成。
- **禁止停止**:扫描空轮、候选池空、"看起来找不到"、时间长、轮次多。空轮换来源换角度继续。(收尾 C/D 属操作边界与用户主权,不在此列。)

## 硬规则

- **面向用户只说中文**：机器内部为兼容账本而保留英文状态码，但 commentary、最终报告、状态解释和错误转述必须使用中文展示名，不得把 `budget_reached`、`active`、`captured` 等机器码直接交给用户。必要时表述为“运行预算已用完（内部状态码已留在会话文件）”。候选英文搜索词、网址、文件名和命令参数不属于界面文案，可原样保留。
- **结束状态中文对照**：`go`＝已产出可交付结论；`quota_exhausted`＝查询额度已用完；`budget_reached`＝运行预算已用完；`resource_exhausted`＝会话资源已用完；`blocked`＝执行受阻；`cancelled`＝已取消。调用控制器结束会话时优先给 `--status` 传中文展示名；控制器会在内部规范化为稳定机器码。
- 控制器默认输出中文摘要。只有脚本确实需要解析字段时才使用全局 `--json`，并且不得把该机器输出原样转述给用户。

- **调用即开跑**:被触发后读必读文件、报一句"进入连续运行"即进入循环;不询问"是否开始"、不列计划等确认、不因参数缺失暂停(本 skill 无必填参数,一切以账本现状为输入)。
- 不注册域名、不花钱、不发布——找到词就停,建站是用户的动作。
- 标准授权只覆盖 registrar 转移与既定流程内的浏览/记录;不覆盖任何契约外的新动作。
- **`G3=veto_window_bet` 的出闸不在默认标准授权内**。判出后候选留在 `captured` 挂起。用户读完证据并明确接受风险时,才执行 `run_controller.py confirm-window-bet --run-id <run_id> --slug <slug>`;确认记录一次性消费,未取得时 registrar 拒收出闸。不得转 `rejected` 或伪造单步 `--by`。
  - **gates 写进账本的两种写法**:本轮新扫的候选在 `register` 时把 gates、expiry 与支撑同一结论的 `--evidence` 一次带齐;**上轮已注册的排队候选**用 `registrar.py amend --slug <slug> --by xinci-run --gates G3=veto_window_bet --evidence <本次观察> --reason "<降级依据>"` 补记。observation 必须有相同 gates、非空 source_urls 和结构化 window_bet。
  - **唯一的例外动作是过期**:挂着期间 expiry 过了,照常按标准授权转 `captured→expired`(见步骤 1 的到期清理)。它没有失败的闸门,过期不是 rejected;不收的话,闸门契约 G3 给它列的第四个出口在连续运行下就没有提议人。
- Semrush 纪律仍为 decision-changing only;为触发终止条件而空烧额度是禁止的。
- 快道决策书照常必含"跳过的闸门清单 + 风险确认"章节——运行停止后由用户阅读决策书完成风险确认,建站与否是用户的决定。连续模式下登记的 fast_grab_ready 未经用户事前逐条确认,history 的 by=xinci-run 即此含义的记录。
- 整个连续运行只由控制器维护一份清单 `运行/<日期>-<HHMMSS>-<run-token>-xinci-run.json`;run token 消除同秒启动的文件名冲突。期间执行的各阶段流程不另写各阶段清单。中途被用户打断时,已完成的转移与清单保持有效,下次启动从 session 与账本现状继续。
