---
name: xinci-run
description: '新词工作流的一体入口与连续运行驱动器:恢复现有会话后循环推进 new 道存量、触发池、扫描、初筛与决策；浏览器不满足 G1 前置条件时自动降级为 trigger-only，captured 积压超过硬线时只还债。产出任一 go 决策或实际观察到 Semrush 网页版额度耗尽时正常终止；预算、真实决策迁移停滞、会话资源或 blocker 按契约收尾且不伪装成完成。启动暗号 xinci_run。'
---

# xinci-run 一体入口·连续运行驱动器

**调用即启动整个工作流。** 以下任一方式触发本 skill,一律等同显式启动命令,读完必读文件后立即开跑,**不向用户确认"是否开始"、不要求补充参数**:

- 消息中出现启动暗号 `xinci_run`;
- 环境的 skill 调用机制(如 `/xinci-run`、Skill 工具);
- "启动新词工作流"、"一直跑到找到为止"等自然语言。

启动即标准授权:本次运行内既定路径上的 registrar 转移无需逐条确认,循环推进,直至命中终止契约;唯一例外是 `G3=veto_window_bet` 的 `captured→screened`,它要求用户单步接受窗口赌注风险。本 skill 只做编排;判断标准全部来自各阶段流程文件与 xinci-core 契约,**不因连续模式降低任何闸门或分数线**。

**预算参数**:启动消息中可附 `max_rounds=N`(轮次上限)和/或 `max_hours=H`(时长上限)。控制器始终保留轮次上限:**没有显式给 `max_rounds` 时仍默认 6**,即使只给了 `max_hours`;两项同时存在时谁先命中就收尾。若用户希望主要按时长运行,必须同时给足够大的 `max_rounds`,本工作流没有“轮次无限”这一档。终止 B(额度耗尽)在单次运行内几乎不可达(扫描期禁用 Semrush、形成期只允许轻探针、7 天跨度闸使单次运行做不出**新的** formation_confirmed;账本已有 formation_confirmed/qualified 存量时 qualify/decide 确实会动用 Semrush,但那是每候选个位数的 decision-changing 查询,离烧穿额度仍差得远),没有默认轮次预算的“不限”等于跑到会话资源耗尽。命中任一预算即走"正常收尾——预算命中"(见终止契约);预算是用户主权,不属于禁止的停止理由。**不因参数缺失暂停或询问**,按默认值开跑。

> **路径约定**:相对路径以仓库根为基准(正本在 `xinci-workflow/xinci-run/SKILL.md`,symlink 加载时 `readlink` 后上溯两级即仓库根);bash 在仓库根执行,或展开为绝对路径。

## 第 0 步:确认数据区(强制,先于一切写操作)

**第一次执行本工作流、或换了机器/checkout 时,必须先确认执行产出存到哪里。** 零成本一条命令:

```bash
python3 xinci-workflow/xinci-core/scripts/report_status.py
```

- 正常返回看板 → 数据区已配置,直接往下走,**别再问**。
- **退出码 2、提示「数据区未配置」→ 停下来问用户数据区放哪,不要替他选。** 这不是故障,是脚本刻意不猜(理由见生命周期契约「开工第一步」)。

拿到路径后固定下来(幂等,已存在的文件不动):

```bash
python3 xinci-workflow/xinci-core/scripts/init_workspace.py --data-root <用户给的路径>
```

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

0. **创建或恢复运行会话**:先执行 `run_controller.py recover`,再用 `list` 查活动 run；有 active 就恢复,没有才 `start`。不得重启未结束的 run。随后记录浏览器预检并计算本轮策略；每轮 `begin-round` 前和浏览器状态改变后都重算一次：

   ```bash
   python3 xinci-workflow/xinci-core/scripts/browser_preflight.py record --run-id <run_id> \
     --channel chrome --controllable yes --desktop yes --region us --logged-out yes
   python3 xinci-workflow/xinci-core/scripts/run_policy.py --run-id <run_id>
   ```

   `run_policy.py` 同时返回 `reachable_ceiling`——**本次运行在当前账本下最远能推进到哪一步**,开局就要读它。它有三档:`go`(存量里有 qualified/hold/formation_confirmed,或窗口以天计的 screened,或最早 `-track` 观察已满 7 天的 tracking——本次复查即可凑齐形成跨度)、`tracking`(存量都不满足,存量侧最远只到 tracking)、`trigger_only`(浏览器不满足 G1 前置)。
   **它是预算提示,不是许可或禁止**:天花板为 `tracking` 不表示不该扫描——本轮新扫出的、窗口以天计的候选照样可以走快道直达 go。它只回答"存量能不能出结论",好让轮次一开始就花在对的地方(推存量还是补触发池),而不是跑几轮才发现存量根本走不动。

   `mode=full` 才准通过正式 CLI 注册 new 候选；`trigger_only` 只收集/整理触发池，不写 G1、不注册候选；`debt_only` 只推进存量与到期项，不新增正式候选；`paused` 只允许恢复/校验/收尾。registrar 的 CLI 会再次核对 `formal_admission`，因此这不是建议。然后 `begin-round`，结束只调用 `record-round`。所有 `--by xinci-run` 命令必须带真实 run_id。运行 report_status 读账本；去重疑似项必须 resolve，不留口头裁决。
1. **推进存量(优先;离 go 决策最近的先做)**:
   - **先按 lane 划清边界**:`lane=new` 按下列全部状态推进；`lane=mature` 在 `formation_confirmed` 前(`captured` / `screened` / `tracking`)不由本循环操作,只在本轮 notes 记明“mature 前半程待用户单步调用 xinci-mature 推进”,不把它算 blocker、排队债或扫描积压。mature 到 `formation_confirmed` / `qualified` / `hold` 后才进入下面对应的 qualify / decide 分支；
   - hold 候选 → 先读 hold 的决定性理由:若理由质疑 G6–G8 或认定仍否成立,按 xinci-qualify 做定向重审(推翻即 `hold→disqualified`);否则按 xinci-decide 重出决策(`hold→build_ready / pilot_ready / no_site`)。不得把 hold 挡在循环外,也不得转回 formation_confirmed;
   - qualified 候选 → 按 xinci-decide 完整模式出决策(流程文件见上表;可能直接命中终止 A,且主要整理既有证据,成本最低);
   - screened 候选 → expiry 已过先以 `--expiry-trigger date` 按下面到期规则转 expired;未过期且 window_estimate=days 的立即按 xinci-decide 快道模式出决策;未过期且 window_estimate=weeks/months 的按 xinci-scan 分流要求转 tracking(带 expiry、失效条件与证据)。若它带 `G3=veto_window_bet`,说明此前已由用户单步确认完成出闸,只准走快道,不得进 tracking;
   - formation_confirmed 候选 → 按 xinci-qualify 流程认定(G6–G8 + 竞争审计 + 评分);
   - tracking 候选 → 按 xinci-track 流程复查(重跑 G1,看形成信号);达标即转 formation_confirmed,expiry 过时用 `--expiry-trigger date`、失效条件命中时用 `--expiry-trigger invalidation` 转 expired,G0/G1 翻转即转 rejected。**单次运行内每个 tracking 候选至多复查一次**——SERP 在几小时内不会变,重复复查是空烧;形成以真实天数计,registrar 的 7 天跨度闸也不接受当日凑数;
   - **new 道 captured 候选(上轮扫描排队的或 register→screened 之间中断留下的)→ 严格按 `gates` 与现有证据补齐缺口**:先核对已有 observation；若它已经直接支撑某道缺失门(典型是 register 成功、紧接的出闸 transition 尚未执行),可在本次出闸提交该观察中的结论,不重复浏览器审计；否则按扫描顺序 `G0→G4→G5→G6/G7 预筛→G1→G2→G3` 只跑真正缺失的门。缺 G1 的必须在 G2/G3 前补 G1；只有美区、桌面、未登录的合规环境才能写 G1,环境污染时只记观察、不写 G1、不转移。已有的门结论不重复验证,但不得把“通常排队位已有 G0/G4/G5”写成假设——出闸时按合并结果交齐 G0/G1/G2/G4/G5=`pass` 与有效 G3。排队 expiry 已过的,以 `--expiry-trigger date` **即转** `captured→expired`(标准授权覆盖它,不必回头问用户),不占深审配额。带 `G3=veto_window_bet` 挂起等确认的**不再补门**;没有一次性确认就不出闸,取得确认后由同一 run_id 出闸,不占深审配额;但**它的 expiry 过了照常以 date 触发转 `captured→expired`**——挂起不免疫过期,收它是契约内的既定路径、不降低任何闸门,在标准授权内。
     这是上轮欠的债,**必须在任何新候选 admission 前还**。还债配额由 `run_policy.py` 返回:正常至多 5，硬积压模式至多 10。次数记进 `funnel.carryover_audited`。
     **存量 captured 的消化归本步骤**:派子代理执行步骤 2 的扫描时,子代理从 xinci-scan 第 1 层开始,不再重跑它的第 0 层接队——两处都做会重复深审、双花配额。
   - **到期清理(`screened` / `fast_grab_ready`)**:`screened` 候选 expiry 已过(既没排上快道、也没转进追踪,窗口自己过了)→ 以 `--expiry-trigger date` **即转** `screened→expired`;`fast_grab_ready` 候选 expiry 已过时用 `date`、窗口已关闭(通用工具已收录该对象、赌注前提消失)时用 `window_closed` → **即转** `fast_grab_ready→expired`。两条都由标准授权直接转,不必回头问用户,也不占深审配额;它们没有失败的闸门,**不许塞进 `rejected`**。单步模式下这两条归 xinci-decide 提议(前者是它快道模式的输入、后者是它的产出),四条 expired 边的提议人见生命周期契约。
   - **积压硬闸**:`lane=new,state=captured` >20 时策略必须为 `debt_only`，本轮正式提取目标为 0；不再以“最低档”继续制造新债。浏览器不满足 G1 时为 `trigger_only`，同样不得把官方标题或缺 G1 项注册进账本。
2. **扫描触发与新候选**:先把有日期的法规/平台/技术变化作为原始 trigger 写入 `trigger_pool.py add`，不得把官方公告标题直接当搜索词。只有补齐 task query、至少一个独立搜索语言证据 URL，以及 payer/repeat_unit/self_serve_path/base_case_source 后，才能 `approve`。批准只表示可进入 G0。正式注册时，信号面候选传 `--origin signal`；变化面候选传 `--origin trigger --trigger-id <approved id>`，registrar 会核对 term 与批准 query 一致。`mode=full` 才执行；`trigger_only` 只维护触发池；`debt_only` 跳过本步。单一 source_family 不得连续主导超过 2 轮或占本 run 新 trigger 的 40%，超过就轮换来源。
3. **分流**(步骤 1 还债深审出的候选与步骤 2 扫描出的候选**一并分流**,别只分流新扫的):**先出闸 `captured → screened`**(带 G2/G3 结论与 `--window-estimate`,这一步不能跳——tracking 与快道都只从 screened 出发,直接 `--to tracking` 会被 registrar 判非法转移;命令见 xinci-scan 第 5 层),再按窗口分流:窗口天级 → 立即走 xinci-decide 快道模式;窗口周/月级 → 转 tracking 入库。当前 new 扫描在订阅线暂定可行时不会新造 `G3=veto_window_bet`;账本中已合法存在的历史兼容候选仍按原出口留在 captured 挂起,用户确认后记录候选级一次性授权,再由同一 run_id 出闸(见硬规则)。然后继续循环。
4. **每轮收尾**:批量扫描开始时先把去重后的 term 写入 `stage_checkpoint.py start`；每条必须 `mark` 为 dedup/zero_cost/g1_rejected/deep_audited/queued/alias/pooled，全部有归宿后 `finish`。`pooled` 用于停在触发层的方向(已写进触发池、未注册为候选),它在 funnel 里同名成格并参与加总。`record-round` 会拒绝仍打开的阶段检查点。随后提交来源、计费调用、notes 与 funnel；不要手写 manifest。`queued` 只表示新债，**不算决策推进**；真实推进由账本 history 中 `from` 非空且 `to != from` 的迁移计数。

```bash
python3 xinci-workflow/xinci-core/scripts/run_controller.py record-round \
  --run-id <run_id> \
  [--source-opened <URL>] [--source-blocked '<URL>(拦截现象)'] \
  [--billable-calls <N>] [--note '<事实>'] \
  --funnel '{"extracted":0,"rejected_zero_cost":0,"rejected_g1":0,"deep_audited":0,"queued":0,"pooled":0,"carryover_audited":0}'
```

拒绝原因收敛时把 screen_unsatisfiable 假设放进 `--note`——**然后继续运行**。
5. 回到步骤 1。命中终止/收尾条件后,先写完且只保留一份本次 manifest,再执行 `run_controller.py finish --run-id <run_id> --status <状态> --reason <事实>` 关闭会话。`finish` 会先跑完整清单校验,拒绝字段漂移、清单缺失/重复、funnel 缺失、轮次不连续或漏记候选,失败时 session 保持 active;`--status go` 还要求账本中存在**当前仍处于 GO 状态、且由本次 run_id 转入**的候选,不能用文字理由冒充产出。活动会话存在时 registrar 拒绝所有单步写入。

## 终止契约(全文见生命周期契约,此处为执行摘要)

- **正常终止 A——拿到可交付结论**:registrar 记录任一 go 决策(fast_grab_ready / pilot_ready / build_ready)。停,交付决策书(md+html)与账本状态。**两类 go 分量不同,报告时不许混说**:build_ready / pilot_ready 过了 G6–G8 与 80 分线,是"值得建站";fast_grab_ready 是"一份标好价的窗口赌注",不等于被验证的生意。
- **正常终止 B——额度耗尽**:Semrush 网页版界面**实际出现**额度耗尽提示;把提示要点记入运行清单后停,报告推进到了哪。假设或报错猜测不算。
- **正常收尾 C——会话资源耗尽**:上下文/会话资源接近极限时,完成当前动作、写运行清单、如实报告"会话资源耗尽,任务未完成、额度未耗尽"后停。这是操作边界不是任务终点,不得伪装成 A 或 B;已完成的转移保持有效,下次启动从账本现状继续。
- **正常收尾 D——预算命中**:任一预算先用完——始终存在的 `max_rounds`(未显式指定时为 6),或可选的 `max_hours`。两项同时存在时不是二选一,谁先命中就收尾。处理同 C:完成当前动作、写运行清单、如实报告推进到哪与预算命中,下次启动从账本现状继续。
- **正常收尾 E——连续三轮无真实决策迁移且队列增长**:`run_policy.py` 返回 `consecutive_decision_stall_rounds >= 3` 时停止新增候选并转入闸门/来源/容量校准。初次 register 的 `from=null→captured` 与 `funnel.queued` 都不算决策推进；只有既有候选发生真实状态迁移才算。完成本轮 record-round 后以“已触发闸门校准”收尾，如实报告。
- **异常中止**:blocker(认证/CAPTCHA/支付/浏览器封锁)使所有可行工作停摆。如实报告 blocker,不伪装成完成。
- **禁止停止**:扫描空轮、候选池空、"看起来找不到"、时间长、轮次多。按运行策略继续；只有命中契约化预算、校准、资源或 blocker 才收尾。

## 硬规则

- **面向用户只说中文**：机器内部为兼容账本而保留英文状态码，但 commentary、最终报告、状态解释和错误转述必须使用中文展示名，不得把 `budget_reached`、`active`、`captured` 等机器码直接交给用户。必要时表述为“运行预算已用完（内部状态码已留在会话文件）”。候选英文搜索词、网址、文件名和命令参数不属于界面文案，可原样保留。
- **结束状态中文对照**：`go`＝已产出可交付结论；`quota_exhausted`＝查询额度已用完；`budget_reached`＝运行预算已用完；`resource_exhausted`＝会话资源已用完；`calibration_triggered`＝已触发闸门校准；`blocked`＝执行受阻；`cancelled`＝已取消。调用控制器结束会话时优先给 `--status` 传中文展示名；控制器会在内部规范化为稳定机器码。
- 控制器默认输出中文摘要。只有脚本确实需要解析字段时才使用全局 `--json`，并且不得把该机器输出原样转述给用户。

- **调用即开跑**:被触发后读必读文件、报一句"进入连续运行"即进入循环;不询问"是否开始"、不列计划等确认、不因参数缺失暂停(本 skill 无必填参数,一切以账本现状为输入)。
- 不注册域名、不花钱、不发布——找到词就停,建站是用户的动作。
- 标准授权只覆盖 registrar 转移与既定流程内的浏览/记录;不覆盖任何契约外的新动作。
- **账本中历史兼容的 `G3=veto_window_bet` 候选,其出闸不在默认标准授权内**。候选留在 `captured` 挂起。用户读完证据并明确接受风险时,才执行 `run_controller.py confirm-window-bet --run-id <run_id> --slug <slug>`;确认记录一次性消费,未取得时 registrar 拒收出闸。不得转 `rejected` 或伪造单步 `--by`。
  - **历史兼容候选的 gates 写法**:连续模式不从本轮 new 扫描新造这一档。账本中已合法存在的历史兼容排队候选,若补审时才形成该结论,用 `registrar.py amend --slug <slug> --by xinci-run --gates G3=veto_window_bet --evidence <本次观察> --reason "<降级依据>"` 补记。observation 必须有相同 gates、非空 source_urls 和结构化 window_bet。
  - **唯一的例外动作是过期**:挂着期间 expiry 过了,照常按标准授权以 `--expiry-trigger date` 转 `captured→expired`(见步骤 1 的到期清理)。它没有失败的闸门,过期不是 rejected;不收的话,闸门契约 G3 给它列的第四个出口在连续运行下就没有提议人。
- Semrush 纪律仍为 decision-changing only;为触发终止条件而空烧额度是禁止的。
- 快道决策书照常必含"跳过的闸门清单 + 风险披露与授权状态"章节。连续模式下普通 `G3=pass` 快道由启动命令的标准授权执行；运行停止后用户阅读决策书是在决定是否建站,**不得倒写成转移前已经逐条确认风险**。history 的 `by=xinci-run` 只表示该转移处于本次标准授权内。`G3=veto_window_bet` 不在标准授权内,仍须候选级一次性明确确认。
- 整个连续运行只由控制器维护一份清单 `运行/<日期>-<HHMMSS>-<run-token>-xinci-run.json`;run token 消除同秒启动的文件名冲突。期间执行的各阶段流程不另写各阶段清单。中途被用户打断时,已完成的转移与清单保持有效,下次启动从 session 与账本现状继续。
