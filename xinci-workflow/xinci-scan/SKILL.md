---
name: xinci-scan
description: '扫描发现新兴/全新的英文 Google 搜索词候选(lane=new)。当用户说扫一下今天有什么新词、发现新机会、跑一轮雷达时用。English triggers: scan new keywords, keyword radar, discover emerging terms. 看状态用 xinci-status,复查用 xinci-track。'
---

# xinci-scan 扫描发现

先读 `xinci-workflow/xinci-core/通用约定.md`(第 0 步、`--by`、运行清单、lane 边界、共同硬规则)。本 skill 只发现 `lane=new`:捕获太新以致没有数据的词,当场初筛,注册进账本。空扫描是合法产出。

行动前按本轮动作读取：闸门契约「时间光谱与适用矩阵」「扫描期执行顺序」及实际会运行的 G0–G7 章节；`陷阱速查.md`；数据采集指南「真浏览器原则」「G1 SERP 读取规程」「扫描来源」「Semrush 探针纪律」；生命周期契约「每转移的证据要求」「证据与命名约定」「留痕分界」。疑似命中陷阱时才读取 `陷阱类别.md` 对应类别，不能只凭速查表下结论。

## 工作流

扫描是漏斗:便宜的筛在前、贵的审在后,每层有配额与留痕。一轮的形状是"广撒网 → 逐层收口",不是"取三个样本各挖到底"。

### 第 0 层:开局去重与接队

提取出方向之后、花任何筛选成本之前,批量查一次(一次覆盖淘汰索引与账本;索引不进上下文):
```bash
printf '%s\n' "方向1" "方向2" ... | python3 xinci-workflow/xinci-core/scripts/screen_index.py check
```
- `[见过]` 自动跳过,且不计入 funnel 的 `extracted`;`[疑似重复·须快审]` 必须比较两者具体任务后登记裁决,不能口头略过:
```bash
python3 xinci-workflow/xinci-core/scripts/screen_index.py resolve \
  --term "<待查方向>" --matched "<输出中的 matched>" --term-task "<待查方向的具体任务>" \
  --matched-task "<旧方向的具体任务>" --term-evidence-url <待查方向来源URL> [--matched-evidence-url <旧方向来源URL>] \
  --by xinci-scan --decision <same|distinct> --reason "<两个具体任务为何相同或不同>"
```
- 旧条目缺 task 时须重开来源重建旧任务并显式传 `--matched-task`;旧条目已有 `source_urls` 时 `--matched-evidence-url` 可省略。修正错误裁决用 `--supersedes <当前 decision_id>` 追加,不编辑旧行。
- 接队只收 `lane=new` 的 `captured`:读 `gates` 与已有 observation,缺哪门补哪门;observation 已支撑尚未提交的门结论时出闸复用,不重审。缺 G1 的先回第 3 层;已有 `G3=pass` 不重跑;不得假定排队位天然已有 G0/G4/G5。
- 排队候选 expiry 已过的提议 `captured→expired --expiry-trigger date`(含 `G3=veto_window_bet` 挂起候选),不再花深审配额。mature 候选只报告"应交 xinci-mature"。
- 连续运行下接队不在这里做(xinci-run 运行循环步骤 1 统一处理存量),本 skill 直接从第 1 层开始;去重 check 照做。

### 第 1 层:广度提取(便宜,常态目标一轮 200–300 个方向)

- 200–300 是单步或 `run_policy.mode=full` 的目标;`debt_only` / `trigger_only` / `paused` 的正式候选提取目标为 0,不得缩小批次绕过。`trigger_only` 可继续收集原始变化,不得进候选漏斗。
- 真浏览器打开来源(来源表见数据采集指南;轮换选源,覆盖优先)。变化面从有日期的法规/平台/技术/成本变化推导付费者的被迫任务,按"七条正向选源信号"排序(只排序,不是硬门);变化面允许列表页/RSS/导出接口批量采集,社区面仍须真浏览器直读。
- 把一个源里所有有任务嫌疑的方向都提出来,逐条列,不合并不省略。每条只记两样:搜索措辞(不转述;官方标题只能进触发池)+ 一句话任务假设。记录打开的每个 URL;素材不足换源补足。提取结果以紧凑清单存在,一行一条。
- 变化面先 `trigger_pool.py add --date --title --source-url --source-family --task-hypothesis`(去重表:同一份公报不重复看)。派生的任务措辞可直接进零成本漏斗,不必先 approve;要给原料配上任务措辞与商业假设时才用 approve(`--search-evidence-url` 可选):
  `trigger_pool.py approve --trigger-id --query --payer --repeat-unit --self-serve-path --base-case-source --search-evidence-url --reason`。
- approve 不产生 G0–G8 结论;raw trigger 不计 `extracted`,其漏斗由 `record-round` 自动生成。注册时变化面候选带 `--origin trigger --trigger-id <id>`(pending 亦可,只要未废弃),信号面带 `--origin signal`(连续运行必填,见通用约定)。

### 第 2 层:零成本批筛 G0 → G4 → G5 → G6/G7 预筛(便宜)

对每条逐个过,判据按闸门契约 G0 / G4 / G5 / G6「深审入口预检」/ G7 与「G6/G7 的扫描期用法」执行;提不出任务的同批弃。G5 命中「直接筛除型」零成本弃;「验证型」先完成 G6/G7 预筛,再开浏览器跑 G3 验证(本层唯一的浏览器动作)。observation 完整写六条 `g6_tentative_lines`,new 道 advertising 固定 `N/A`。

秒弃的批量追加进淘汰索引,不注册:
```bash
printf '%s\n' "词|G0|违反 ToS" "词|G4|需要到场" "词|G6|六线全灭" "词|G7|官方答案在途|<pattern>" ... \
  | python3 xinci-workflow/xinci-core/scripts/screen_index.py append --date <YYYY-MM-DD>
```
- 第 4 个字段标 `pattern`;认出新模式时按生命周期契约「归并纪律」形成新增类别提案,附实际观察并等待用户确认,不得把一次观察静默升级成通用判据。确认后的归并记录写法见同节。`screen_index.py stats` 只统计索引一侧,账本一侧的模式名靠运行清单 notes 累计。
- 已在账本的排队候选补跑时才判出六线全灭,走 `captured→rejected`(生命周期契约 rejected 边第⑦种),不进索引。
- 预期本层砍掉 85%,剩 30–50 条进 G1。`rejected_zero_cost` 的语义是"第 2 层筛除",不等于"从未打开浏览器":验证型 G3 判 `veto` 的方向计入本格(类别级死因走索引,不注册)。
- 验证判 `pass` 的方向存活,按排队位注册(带 gates 含 G3 结论 + expiry,见第 4 层),本轮继续补 G1/G2。funnel 按本轮走到的层记:补 G1 被否 → `captured→rejected`,记 `deep_audited`;走完 G2 → `deep_audited`;没排上 → `queued`;下轮再审属存量 `carryover_audited`。

### 第 3 层:G1 快筛(中等,每轮 30–50 次上限)

对存活的每一条,真浏览器搜精确词,环境与读法按数据采集指南「G1 SERP 读取规程」:`https://www.google.com/search?q=<精确词>&gl=us&hl=en&pws=0`
- 只看首屏、只判 G1(按闸门契约 G1 含「站点簇反事实」执行);不翻第二页、不读结构、不开竞品。
- 环境不合规(非美区/桌面/未登录/不可控)时不写 G1 结论、不进索引。连续模式由 xinci-run 降为 `trigger_only`,不得为新方向留缺 G1 的排队位;单步模式可按排队位注册(gates 不写 G1、带 expiry),之后在合规环境补跑。
- 未注册方向的 G1 否决批量追加索引,JSON 行必须带 `atomic_only` 反事实(缺则拒收):
```bash
printf '%s\n' '{"term":"<词>","gate":"G1","reason":"<首屏是什么把任务做完了>","cluster_counterfactual":{"atomic_task_completed":true,"batch_processing":false,"monitoring":false,"audit_trail":false,"export_integration":false,"multi_jurisdiction":false,"decision":"atomic_only","reason":"<五种扩展为何都不成立>"}}' \
  | python3 xinci-workflow/xinci-core/scripts/screen_index.py append --date <YYYY-MM-DD>
```
- 已注册候选(排队的、验证存活的)补跑 G1 被否走 `captured→rejected`(rejected 边第⑤种),不进索引;分界见生命周期契约「留痕分界」。预期本层再砍一半。
- 两条纪律:①每轮 30–50 次上限,超出的方向照样排队注册为 `captured`,但 gates 不写 G1(没搜就是没搜),下轮第 0 层先补;②记录搜索健康度——本轮搜了多少次、第几次起出现验证码/限流/结果异常,写进运行清单 notes。撞到验证码属 blocker,停止本层如实报告,不得绕过、不得用接口替代。

### 第 4 层:G2/G3 深审(昂贵,每轮配额 ≤5 个)

过了 G1 的候选按"离建站决策最近"排序,配额内做完整审计:G2 按闸门契约 G2;G3 按闸门契约 G3(先按 `g6_tentative_lines` 判占位否决是否生效,再三问;窗口期只用浏览器可得证据)。漏做深审入口预检的此刻补齐;六线全灭按第 2 层秒弃留痕,不占配额。暂定线未建立时不作 G3 结论,留在 `captured` 补证据。

register 模板(单步形态;`--gates` 与 `--expiry` 成对出现,带 gates 就必带 expiry,observation.gates 须与之逐门一致、source_urls 非空):
```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py register \
  --slug <slug> --term "<精确措辞>" --source-url <URL> --source-note "<现场摘要>" \
  --task "<任务>" --site-thesis "<为何能形成独立站>" --task-family "<家族1>" --task-family "<家族2>" \
  [--gates G0=pass,G4=pass,G5=pass,G1=pass --expiry <YYYY-MM-DD>] --evidence "证据/<slug>/<日期>-scan.json" --by xinci-scan
```
- 深审判否(G2 veto,或占位否决生效前提下 G3 veto)的处置在本层完成:register 不带 `--gates`,闸门结论随 transition 提交;死在 G2 写 `...,G2=veto`,没跑的门不写。例外:命中已成册陷阱类别、当场验证判 `veto` 的方向按第 2 层走索引。死因像结构性模式时把模式名记进运行清单 notes。
```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to rejected --by xinci-scan --gates G0=pass,G4=pass,G5=pass,G1=pass,G2=pass,G3=veto \
  --evidence "证据/<slug>/<日期>-scan.json" --reason "G3 veto:<免费实现清单>;<结构阅读要点>"
```
- 超配额的候选不许丢弃:register 带已得 gates 和候选自身证据支撑的 `--expiry`,排队为 `captured`,下轮第 0 层优先消化。
- `G3=veto_window_bet`(判据与出口见闸门契约 G3「唯一的降级出口」;挂起与确认见通用约定「运行模式与 `--by`」)两种来路,后续相同:①本轮新扫方向判出——按排队位 register,gates 含 `G3=veto_window_bet`;②账本已有 `captured` 候选补审判出——用 amend 补记(`captured→captured` 不是转移):
```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py amend \
  --slug <slug> --by xinci-scan --gates G3=veto_window_bet --evidence "证据/<slug>/<日期>-scan.json" \
  --reason "降级依据:数到 N 个免费实现;实测某通用实现收录上一个同类对象用了 M 天"
```
- observation 的 `gates.G3` 写 `veto_window_bet` 并填结构化 `window_bet`。之后:单步模式按第 5 层提议出闸;连续模式留在 `captured`,notes 记"待用户单步确认窗口赌注",继续跑。funnel:来路①按本轮记 `deep_audited` / `queued`,来路②记 `carryover_audited`。

### 第 5 层:窗口评估与注册(只对深审存活的候选)

- 每个候选一份观察文件 `证据/<slug>/<日期>-scan.json`(要点式,`schema_version: 2`,schema 见 数据结构/observation.schema.json),按闸门契约逐项写六条盈利线与 `cluster_counterfactual`;不得用"重复任务=否"一票否决所有盈利线。
- 估计窗口(days/weeks/months)并写明推理。本轮走完全程的候选 register 不带 `--gates`(模板见第 4 层);上轮已排队注册过的跳过 register,直接出闸。
- 第一步一律是出闸 `captured→screened`,不能跳(tracking 与快道都只从 `screened` 出发)。`--expiry` 写窗口失效日(覆盖排队位的旧 expiry);`--gates` 按缺口提交全部已验证结论(排队候选典型只补 `G2=pass,G3=pass`,gates 为空时交齐,不照抄),registrar 按账本已有 gates + 本次提交合并校验:
```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to screened --by xinci-scan --gates G0=pass,G4=pass,G5=pass,G1=pass,G2=pass,G3=pass \
  --window-estimate <days|weeks|months> --expiry <YYYY-MM-DD> --evidence "证据/<slug>/<日期>-scan.json"
```
- 出闸后提议下一步,用户确认后执行:G3=`pass` 且窗口以周/月计 → 提议 `screened→tracking`(带 expiry 与至少一条失效条件);窗口以天计 → 提议转 xinci-decide 快道。
- G3=`veto_window_bet` 且窗口以天计 → 出闸 `--reason` 写降级依据,只提议快道;不得进 tracking,合法出口见闸门契约 G3。

### 第 6 层:写运行清单(含漏斗数据)

```bash
python3 xinci-workflow/xinci-core/scripts/run_manifest.py record-single \
  --date <YYYY-MM-DD> --skill xinci-scan [--suffix <HHMM>] [--source-opened <URL>] [--source-blocked <URL>] \
  [--candidate-touched <slug>] [--billable-calls 0] [--note '<搜索健康度、深审否决的模式名>'] \
  --funnel '{"extracted":0,"rejected_zero_cost":0,"rejected_g1":0,"deep_audited":0,"queued":0,"carryover_audited":0}'
```
- `extracted`:去重后进入筛选的正式方向数(trigger 不计);`rejected_zero_cost`:第 2 层筛除;`rejected_g1`:第 3 层否决(索引一侧);`deep_audited`:第 4 层实际深审;`queued`:本轮没走完的存活方向(超深审配额 + 超 G1 上限未搜)。
- 四个去向加总必须等于 `extracted`(`validate_ledger.py` 强制,`funnel` 必须存在)。两项不参与等式:去重命中不计 `extracted`;消化存量 captured 的深审记 `carryover_audited`(与新扫描深审配额彼此独立,数值由 `run_policy.py` 返回)。只还债的轮次五项全 0,靠它留下成本。
- 连续运行不调本命令,由 `record-round` 写入。

## 硬规则

- 每个进入 tracking 的候选必须带 expiry(附推理)和至少一条失效条件。
- 区分"发布"与"一时热闹":只产生一周好奇、没有重复任务的东西,直说不值得,不进清单。
- 决策推进优先于广度:先还存量候选的证据债与状态债,仅 `mode=full` 做广度扫描。
- 排队位三条纪律:①`expiry` 由候选自身证据支撑,不得整批套同一天;②`gates` 只写真跑过的门;③new captured >20 时进入硬积压闸,连续运行禁止新增正式候选,只还债与清理到期项。
- 索引日期是硬字段:`append` 的每个新 term 必须有实际观察日;历史空日期只能用 `repair-date` 修订,不得手改 JSONL、不得用当前日期猜补。
- 每个被提取的方向必须有归宿(索引 / 注册 / 排队),不许无声丢弃。
