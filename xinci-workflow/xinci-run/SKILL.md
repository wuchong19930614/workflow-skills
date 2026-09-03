---
name: xinci-run
description: '新词工作流的一体入口与连续运行驱动器。当消息中出现启动暗号 xinci_run、通过 /xinci-run 或 Skill 工具调用、或用户说"启动新词工作流"、"一直跑到找到为止"时使用。'
---

# xinci-run 连续运行驱动器
先读 `xinci-workflow/xinci-core/通用约定.md`。开局另读一次:生命周期契约「连续运行模式(xinci-run)」「窗口赌注的挂起与出闸」「会话与轮次收尾」「schema v3」;闸门契约;陷阱类别;数据采集指南。
进入运行循环某步前先读该步的 SKILL.md(xinci-scan / xinci-track / xinci-qualify / xinci-decide),按其执行,其中的提议-确认由标准授权取代;状态汇报直接跑 report_status。

## 调用即启动
- 启动暗号 `xinci_run`、`/xinci-run` 或 Skill 工具、"启动新词工作流"等自然语言,任一触发即开跑:读开局必读、报一句"进入连续运行"进入循环;不问"是否开始"、不列计划等确认、不因参数缺失暂停。
- 预算参数:`max_rounds=N`、`max_hours=H`。`max_rounds` 未给时默认 6(只给 `max_hours` 也如此);两项并存谁先命中就走收尾 D。没有"轮次无限"档,主要按时长跑须同时给足够大的 `max_rounds`。
- 启动即标准授权(见通用约定「运行模式与 `--by`」)。判断标准全部来自阶段 SKILL.md 与 xinci-core 契约,不因连续模式降低任何闸门或分数线。

## 执行架构:一轮一个执行者(有 Agent 机制时用轮次子代理)
- 每一轮只派一个轮次子代理。它以稳定 `executor_id` 亲自执行 `begin-round`,并在该轮内完成与 `round_type` 相符的全部阶段动作:读所需阶段 SKILL.md 与契约、操作浏览器、写观察文件、以 `--by xinci-run --run-id <run_id>` 调 registrar、当场批量 `screen_index.py append`。
- 同一轮不得按阶段更换子代理,也不得在尚未 `record-round` 时再次执行 `begin-round`。确需换执行者时,先依据已经完成的事实收尾当前轮,再由新执行者开始下一轮;不得借用前一执行者的浏览器预检。
- 轮次子代理只回传结构化结论:触及候选、执行的转移、来源与计费调用数、漏斗五项、疑似归并的模式名;秒弃与 G1 否决不回传;去重疑似项当场 `screen_index.py resolve`,不留口头裁决。
- 主上下文只编排:选择轮型、汇集结论、`record-round`、判断终止。新陷阱类别属于契约变更,不在启动 xinci-run 的标准授权内;只把提案与本轮证据写入 notes,等待用户确认后再改契约。无子代理机制时主上下文作为该轮唯一执行者,其余规则不变。

## 运行循环
**0. 会话恢复与开轮**
```bash
python3 xinci-workflow/xinci-core/scripts/run_controller.py list        # 有 active 就恢复,没有才 start;不重启未结束的 run
python3 xinci-workflow/xinci-core/scripts/run_controller.py start [--max-rounds N] [--max-hours H]
python3 xinci-workflow/xinci-core/scripts/run_controller.py begin-round --run-id <run_id> --executor-id <executor_id> \
  --round-type <discovery|progression|tracking|calibration> \
  --browser-controllable yes|no --browser-desktop yes|no --browser-region us|other|unknown --browser-logged-out yes|no
python3 xinci-workflow/xinci-core/scripts/run_policy.py --run-id <run_id>
python3 xinci-workflow/xinci-core/scripts/report_status.py
```
- `executor_id` 是本轮唯一实际执行者的稳定 ID;四个 `--browser-*` 项由该执行者亲自核对本轮浏览器状态,不得借用父任务、上一轮或其他子代理的状态。执行者或浏览器状态改变时,收尾当前轮后由新执行者开下一轮;控制器不允许在未收尾的同一轮重跑 `begin-round`。
- `begin-round` 的回显直接给出本轮预检判定(满足 G1 前置 / 不满足并点名缺哪几项 / 本轮未提交),不必跑 `run_policy` 才知道。
- 轮型:发现新方向 discovery;清理/推进存量 progression;专门复查追踪池 tracking;误杀回测 calibration。只推进存量的轮不得写 discovery。
- 每累计 10 个 discovery 轮,控制器强制下一次发现前先完成 calibration 轮:先跑 `false_negative_sample.py`,按 G6=10、G7=10、G5=5、G1=5、G3=5 分层复核,结果经 `record-round --false-negative-audit` 提交。
  JSON 键为 `status`(completed|blocked)、`reason`、`samples`、`untested_gates`。`completed` 须 35 条样本每条有证据;库存不足或某层无法复核写 `blocked`,`untested_gates` 与样本零覆盖的门一致,`blocked` 不重置计数;暂定与不确定结果不得改写为正式闸门结论。
- `run_policy.py` 返回的 `reachable_ceiling` 三档:`go`(存量有 qualified / hold / formation_confirmed、窗口以天计的 screened、或最早 `-track` 观察已满 7 天的 tracking)、`tracking`(存量最远只到 tracking)、`trigger_only`(浏览器不满足 G1 前置)。
  它是预算提示,不是许可或禁止:天花板为 `tracking` 时,新扫出的天级窗口候选仍可走快道到 go。
- 策略四档:`full` 才可注册 new 候选;`trigger_only` 只维护触发池,不写 G1、不注册;`debt_only` 只推进存量与到期项,不新增正式候选;`paused` 只允许恢复/校验/收尾。优先级见生命周期契约「连续运行模式(xinci-run)」。
- 还债配额 `carryover_quota`:正常至多 5,`debt_only` 至多 10。`blocked_source_families` 是本轮禁用来源,`trigger_pool.py add` 会拒收;`trigger_harvest=true` 时换其他 family 继续采集。

**1. 推进存量(优先;离 go 最近的先做)**
- `lane=mature` 在 formation_confirmed 前只在 notes 记"待用户单步调用 xinci-mature",不算 blocker、排队债或积压;之后进入下面的 qualify / decide 分支。
- qualified → xinci-decide 完整模式;formation_confirmed → xinci-qualify;hold → 读决定性理由:质疑 G6–G8 或认定的按 xinci-qualify 定向重审(推翻即 `hold→disqualified`),否则按 xinci-decide 重出决策,不得挡在循环外或转回 formation_confirmed。
- screened → expiry 已过以 `--expiry-trigger date` 转 expired;未过且 `window_estimate=days` 走 xinci-decide 快道;weeks/months 按 xinci-scan 分流要求转 tracking。带 `G3=veto_window_bet` 的只准快道,不得进 tracking。
- tracking → xinci-track 复查:达标转 formation_confirmed;expiry 过用 `date`、失效条件命中用 `invalidation` 转 expired;G0/G1 翻转转 rejected。单次运行内每个候选至多复查一次。`tracking_schedule.py` 的 3/7/14 天提示只读,不自动执行或转移。
- fast_grab_ready → expiry 过用 `date`、窗口已关闭用 `window_closed` 转 expired。
- new 道 rejected 且 `recheck_after` 已到:只复核最近拒绝中的 G1/G2/G3 veto;新现场观察逐门翻转后可由 xinci-run 执行 `reopen`,回到 captured 再走完整初筛。mature rejected 只在 notes 记“待用户单步调用 xinci-mature”,不得借 reopen 绕过 mature 前半程边界。
- new 道 captured(排队债;必须在任何新 admission 前还,次数记 `funnel.carryover_audited`,配额见步骤 0):先核对已有 observation,已支撑缺失门的直接在出闸时提交结论;
  否则按 `G0→G4→G5→G6/G7 预筛→G1→G2→G3` 只跑缺失的门,缺 G1 的先补 G1,环境不合规只记观察、不写 G1、不转移;出闸交齐 G0/G1/G2/G4/G5=pass 与有效 G3。
  排队 expiry 已过即以 `date` 转 expired,不占配额。带 `G3=veto_window_bet` 挂起的不再补门、不占配额,取得确认后由同一 run_id 出闸;其 expiry 过了照常转 expired。子代理执行步骤 2 时不重跑 xinci-scan 的开局接队。
- 积压硬闸:G1 合规且 `lane=new,state=captured` >20 → `debt_only`,本轮正式提取为 0;浏览器不满足 G1 → `trigger_only`(trigger pending 达 200 → `paused`),同时积压 >20 也不改成 `debt_only`。

**2. 扫描触发与新候选**(`full` 执行;`trigger_only` 只维护触发池;`debt_only` 跳过)
- 有日期的法规/平台/技术变化先 `trigger_pool.py add`(不得把官方标题当搜索词),逐条 `approve` / `discard`;`approve` 须补齐 `--query`、`--search-evidence-url`、`--payer --repeat-unit --self-serve-path --base-case-source`,批准只表示可进 G0。
- 注册:信号面 `--origin signal`;变化面 `--origin trigger --trigger-id <approved id>`,registrar 核对 term 与批准 query 一致;连续运行下 `register` 另须 `--site-thesis` 与至少两个 `--task-family`。
- G1 只显示原子任务已被完成时,observation 必须写 `cluster_counterfactual`(见闸门契约「G1 的站点簇反事实」);任一扩展成立就改写候选任务继续过门。
- 来源:单一 source_family 不得连续主导超过 2 轮;本 run 新增 trigger 达 5 条后任一 family 占比 >40% 就轮换。组合基线 50% 已验证高产家族、30% 相邻任务家族、20% 探索家族,按最近校准结果调整,变化写入 notes。

**3. 分流**(步骤 1 还债与步骤 2 新扫一并分流)
- 先出闸 `captured→screened`(带 G2/G3 与 `--window-estimate`,命令见 xinci-scan);天级 → xinci-decide 快道;周/月级 → 转 tracking。直接 `--to tracking` 会被 registrar 拒。
- `G3=veto_window_bet` 的判出口径见闸门契约「`veto_window_bet`:唯一的降级出口」;判出的留在 captured 挂起,处理见硬规则。

**4. 收尾本轮**
```bash
python3 xinci-workflow/xinci-core/scripts/run_controller.py record-round --run-id <run_id> \
  [--source-opened <URL>] [--source-blocked '<URL>(拦截现象)'] [--billable-calls <N>] [--note '<事实>'] \
  [--candidate-reviewed '{"slug":"<slug>","outcome":"not_due","reason":"<事实>","evidence_refs":[]}'] \
  [--false-negative-audit '<校准轮 JSON>'] \
  --funnel '{"extracted":0,"rejected_zero_cost":0,"rejected_g1":0,"deep_audited":0,"queued":0,"carryover_audited":0}'
```
- `funnel.extracted` 只算进入候选筛选的 query;未扫描时五项全 0,0 不是"未统计";`trigger_funnel` 由控制器从触发池事件自动生成;只读既有证据、无 history 写入的存量用 `--candidate-reviewed`,不冒充 `candidates_touched`。
- `queued` 只是新债,不算决策推进。screen_unsatisfiable 假设放 `--note`,然后继续运行。

**5. 回到步骤 1;命中终止条件后收尾**(校验失败时 session 保持 active)
```bash
python3 xinci-workflow/xinci-core/scripts/run_controller.py finish --run-id <run_id> --status <中文展示名> --reason <事实> [--evidence-ref <数据区相对路径>]
```

## 终止契约(正本见生命周期契约「连续运行模式(xinci-run)」)
- A 拿到可交付结论:任一 go 决策落账即停,交付决策书;build_ready / pilot_ready 与 fast_grab_ready 分量不同,报告不混说。`--status go` 要求账本存在当前仍处 GO 状态且由本 run_id 转入的候选。
- B 额度耗尽:Semrush 网页版实际出现额度耗尽提示,保存截图并 `finish --evidence-ref`;提示要点、假设、报错猜测都不算。为触发 B 而空烧额度是禁止的。
- C 会话资源耗尽 / D 预算命中:完成当前动作、record-round、如实报告后停(C 报"任务未完成、额度未耗尽",D 报推进到哪与哪项预算命中)。
- E 连续三轮无真实决策迁移且队列增长:`consecutive_decision_stall_rounds >= 3` 时本轮 `debt_only`,record-round 后 `finish --status 已触发闸门校准`,不开下一轮。与 calibration 轮型是两套机制。
- 异常中止:blocker(认证/CAPTCHA/支付/浏览器封锁)使所有可行工作停摆时如实报告,不伪装成完成。扫描空轮、候选池空、"看起来找不到"、时间长、轮次多都不是停止理由。

## 硬规则
- 标准授权只覆盖 registrar 转移与既定流程内的浏览/记录,不覆盖契约外新动作。普通 `G3=pass` 快道在授权内;决策书必含"跳过的闸门清单 + 风险披露与授权状态",不得把事后阅读倒写成事前逐条确认。
- `G3=veto_window_bet` 候选(新判出与历史兼容的同样)出闸不在标准授权内:留在 captured 挂起,不转 rejected、不伪造单步 `--by`;用户读完证据明确接受后执行
  `run_controller.py confirm-window-bet --run-id <run_id> --slug <slug>`,确认一次性消费。新扫的按 xinci-scan 排队位写法在 `register` 时带 gates+expiry;已在账本的补审时用
  `registrar.py amend --slug <slug> --by xinci-run --run-id <run_id> --gates G3=veto_window_bet --evidence <本次观察> --reason "<降级依据>"`,observation 须有相同 gates、非空 source_urls 与结构化 window_bet。
- 整个运行只由控制器维护一份清单 `运行/<日期>-<HHMMSS>-<run-token>-xinci-run.json`,不另写阶段清单。被打断时已完成转移与清单有效,下次从 session 与账本现状继续。
- 控制器默认中文摘要;只在需解析字段时用 `--json`,不把机器输出原样转述给用户。`finish --status` 传中文展示名。
