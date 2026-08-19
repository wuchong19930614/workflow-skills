---
name: xinci-scan
description: 扫描发现新兴/全新的英文 Google 搜索词候选:真浏览器直读 Reddit/Product Hunt/Hacker News/X/应用商店等信号面,或从有日期的法规/平台/技术变化推导付费者任务,捕获即跑 G0–G5 初筛并注册进账本。当用户说扫一下今天有什么新词、发现新机会、跑一轮雷达时使用。English triggers: scan new keywords, keyword radar, discover emerging terms. 看状态用 xinci-status,复查已有候选用 xinci-track。
---

# xinci-scan 扫描发现

捕获太新以致没有数据的搜索词,当场初筛,注册进账本。速度是这条赛道的全部意义:晚三天发现的候选通常已经没价值。空扫描是合法产出——如实报告远好于凑数。

> **路径约定**:相对路径以仓库根为基准(正本在 `xinci-workflow/xinci-scan/SKILL.md`,symlink 加载时 `readlink` 后上溯两级即仓库根);bash 在仓库根执行,或展开为绝对路径。
>
> **`--by` 约定**:下面所有 registrar 命令模板写的是**单步形态**(`--by xinci-scan`)。**在 xinci-run 连续运行下(含被它派出的子代理)一律改成 `--by xinci-run` 再执行,照抄模板是错的**;`register` 的 `--by` 有默认值 `xinci-scan`,连续运行下必须显式传。取值规则与它为什么要紧,见生命周期契约「registrar 用法」的 `--by` 取值节。

## 行动前必读

- xinci-workflow/xinci-core/闸门契约.md(G0–G5 定义;执行顺序 G0→G4→G5→G1→G2→G3,零成本批先行)
- xinci-workflow/xinci-core/陷阱类别.md(已知陷阱,命中直接验 G3)
- xinci-workflow/xinci-core/数据采集指南.md(真浏览器原则与来源表)
- xinci-workflow/xinci-core/生命周期契约.md(注册与转移的证据要求)

## 工作流

扫描是**漏斗**,不是逐个深挖:便宜的筛在前、贵的审在后,每层都有配额与留痕。
一轮的形状应当是"**广撒网 → 逐层收口**",而不是"取三个样本各挖到底"。

### 第 0 层:开局去重与接队

读陷阱类别(已归并的模式由 G5 按其处置档处理:「直接筛除型」零成本弃、「验证型」跑 G3 验证),然后**用脚本批量去重,不要把索引读进上下文**——它按每天两三百条增长:

```bash
printf '%s\n' "方向1" "方向2" ... | python3 xinci-workflow/xinci-core/scripts/screen_index.py check
```

一次同时查淘汰索引与账本,输出只保留命中结果与新方向。已弃方向、已注册候选一律不重复评估。

> **执行时点**:去重要有待查方向才能跑,而方向在第 1 层才产生——所以实际顺序是「第 1 层提取 → 回到这里 check → 第 2 层筛」。它编为第 0 层是因为它属于开局纪律(先看见过什么,再花任何成本),不是因为它排在提取之前。**命中的方向不计入 funnel 的 `extracted`**:它们上一次已有归宿,再要求一次归宿,加总等式必然算不平。

**接队:账本里的 `captured` 候选是上轮排队的,本轮优先消化它们**——读它们的 `gates`:**缺哪门补哪门**(缺 G1 的先回第 3 层补 G1,补过了才进第 4 层;gates 齐到 G1 的直接进第 4 层)。排队候选的 expiry 已过的,提议 `captured→expired`,不再花深审配额。

> **连续运行模式下,接队不在这里做**:xinci-run 的运行循环步骤 1 已经统一处理了存量 captured(它要跨阶段排序"离 go 决策最近的先做"),本 skill 被派来执行的是「扫描新候选」这一步,直接从第 1 层开始。两处都做会重复深审、双花配额。**跳过的只是接队,本层的去重 check 照做**——提取完本轮方向后仍要 `screen_index.py check`,否则 `extracted` 记的就不是去重后的数。单步调用 xinci-scan 时仍按上一段执行。

### 第 1 层:广度提取(便宜,常态目标一轮 200–300 个方向)

选来源真浏览器打开(来源表见数据采集指南;轮换选源,覆盖优先)。也可走变化面:从有日期的法规/平台/技术/成本变化推导受影响付费者的被迫任务。

**200–300 是常态目标,不是固定值**:连续运行模式下按 `captured` 积压量下调(存量 11–20 → 100–150,>20 → 50–80),软闸表见 xinci-run 运行循环步骤 1;单步调用按常态目标。下调时本层之后的各层预期比例不变(第 2 层砍 85%、第 3 层再砍一半),只是绝对数同比缩小。

**把一个源里所有有任务嫌疑的方向都提出来,不要只挑最显眼的那个。** 一个 release notes 页面通常含多条独立变更,一份法规公告通常牵出多个任务——逐条列,不合并、不省略。每条此刻只需两样东西:

- 词/方向(抓人们实际使用的措辞,不做转述;社区昵称与官方名竞争时都记)
- 一句话任务假设(这让人想完成什么?)

记录打开的每个 URL。**素材不足时换源补足**,而不是拿现有的少数深挖。

**这个量级靠逐页人工读达不到**:变化面允许用源自带的列表页、RSS、导出接口批量采集(边界见数据采集指南"社区面必须浏览器,变化面可结构化采集");社区面仍须真浏览器直读。提取结果在上下文里以**紧凑清单**形式存在(一行一条,约 20–30 token),不逐条展开成散文。

### 第 2 层:零成本批筛 G0 → G4 → G5(便宜,不开浏览器)

对第 1 层的每一条逐个过:

- **G0**(合法性与安全):违法、违反 ToS、欺诈供血、规避工具方向直接弃;
- **G4**(任务可完全在线完成):需要实地、物理、持照到场的任务直接弃——放在开浏览器之前,一次 SERP 都不浪费;
- **G5**(陷阱类别):**按命中类别节自带的处置档执行**——标「直接筛除型」的零成本判定即弃,一次 SERP 都不跑(死因已结构性确定,第四次验证不会有不同结论);标「验证型」的跳 G3 验证:判 `veto` 即弃、不读 SERP 结构,判 `pass` 或 `veto_window_bet` 都算存活,G5 记 pass 并回正常序列补 G1、G2(闸门缺一不可);
- **G6/G7 零成本预筛**:没有被迫/重复任务(只值一周好奇)、或官方答案明显在途/任务本身一次性的,同批弃(判据见闸门契约「G6/G7 的扫描期用法」;这是预筛,不产生认定阶段的 G6/G7 结论);
- **无任务**:提不出任何页面能完成的任务的,同批弃。

**留痕(硬性)**:本层秒弃的每一条都要进淘汰索引,**批量追加,不逐条写**:

```bash
printf '%s\n' "词|G0|违反 ToS" "词|G4|需要到场" "词|G7|官方答案在途" ... \
  | python3 xinci-workflow/xinci-core/scripts/screen_index.py append --date <YYYY-MM-DD>
```

同型的结构性模式在第 4 个字段标 `pattern`,`screen_index.py stats` 会在累计 ≥3 次时提示归并进陷阱类别。不注册进账本。**预期本层砍掉 85%**,剩 30–50 条进 G1。

**本层唯一的浏览器动作是验证型类别的 G3 验证**(其余都是零成本推理)。它虽然动用了真实 SERP,判 `veto` 时留痕仍走索引一侧:该模式已是正式类别,单个方向没有独立留档价值;这一次数到的免费实现清单按陷阱类别.md 的追加规则写进该类别节里。funnel 上它计入 `rejected_zero_cost`(本层筛除),不计 `rejected_g1`。

**例外:验证判出 `pass` 或 `veto_window_bet` 的方向存活**,注册进账本、回正常序列补 G1/G2,funnel 上按它最终走到哪一层记(补完 G1 被否就记 `rejected_g1`,走完深审就记 `deep_audited`,没走完就记 `queued`)——留痕分界见生命周期契约:它还有下一步,第 1 条命中。

### 第 3 层:G1 快筛(中等,每条约十几秒)

对第 2 层存活的每一条,真浏览器搜精确词(美区桌面未登录):

```
https://www.google.com/search?q=<精确词>&gl=us&hl=en&pws=0
```

**只看首屏,只判一件事**:Google 自己把任务做完了吗(完整作答的 featured snippet、原生计算器/转换器组件、承载全部答案的 knowledge panel、把任务做完的 AI Overview)?

**不翻第二页、不读完整结构、不打开竞品**——那些是第 4 层的事。G1 是一票否决且永不跳过,但它本身应该很快。

被 G1 否决的:**批量追加一行进淘汰方向索引,不注册进账本**——`gate` 记 G1,`reason` 写清是什么把任务做完了(featured snippet / 原生组件 / knowledge panel / AI Overview):

```bash
printf '%s\n' "词|G1|原生单位转换器组件直接作答" "词|G1|AI Overview 把步骤全列了" ... \
  | python3 xinci-workflow/xinci-core/scripts/screen_index.py append --date <YYYY-MM-DD>
```

预期本层再砍掉一半,约 18 条。**为什么不注册**:G1 是硬否决且永不复活,要留下的只是"这个方向见过、死在 G1",索引一行完整承载;逐条写观察文件 + register + transition 是每轮 36 次脚本调用、每周 100+ 条 rejected 塞满账本,写入成本会压过本轮真正值钱的 5 次深审。账本收的是「现场证据值得单独留档」的候选——还有下一步的,以及走完 G2/G3 深审的(存活与否都算,见第 4 层);G1 否决两条都不沾。完整分界见生命周期契约。

**本层是整个漏斗的真实瓶颈**,两条纪律:

- **每轮 30–50 次为上限**:再多会挤爆上下文(每次首屏约 400–500 token),也会挤掉深审的空间。超出上限、本轮没搜的方向照样排队进 `captured`,但**注册时 gates 里不许写 G1**(没搜就是没搜)——下轮第 0 层看 gates 缺 G1,会先把 G1 补上。registrar 是最后一道防线:缺 G1=pass 的候选进不了 screened。**G1 永不跳过,排队也不例外。**
- **记录搜索健康度**:连续搜索可能触发 Google 反爬。如实记下本轮搜了多少次、第几次开始出现验证码/限流/结果异常,写进运行清单 notes。撞到验证码属 blocker,停止本层并如实报告,**不得绕过、不得用接口替代**。

### 第 4 层:G2/G3 深审(昂贵,**每轮配额 ≤5 个**)

对过了 G1 的候选,按"离建站决策最近"排序,取配额内的做完整审计:

- **G2 完整首页结构**:读完第一页,继续到第二页或明显质量断层为止,禁止 top-3 定论;
- **G3 exact-task completion**:每个结果按"做什么"分类,永不按"是谁";窗口期只用浏览器可得证据判否决线(footprint 实测属确认期,见闸门契约 G3 分层)。
  **判出 `veto_window_bet` 时**:单步模式按第 5 层提议带豁免走快道;**连续运行模式下 registrar 拒收这个出口**(`by=xinci-run`),此时把候选**留在 `captured`**——带上 gates(含 `G3=veto_window_bet`)与 expiry,观察文件记明豁免依据,运行清单 notes 记一句"待用户单步确认豁免",然后继续跑。不许转 `rejected`(它没有失败的闸门),也不许换个 `by` 硬推 `screened`。funnel 上它计 `deep_audited`(本轮确实深审完了)。
  **数完"几个免费实现做完了任务"之后必须再判一次可见度**:它们为何(不)在本查询首页上?在且稳定 → `veto`;排不上但只因对象太新还没被收录 → `veto_window_bet`(临时空位,只准走快道),**判这一档前必须实测一个通用实现对上一个同类对象的收录时差**(打开它的页面看日期),没做这个实测只准判 `veto`;结构上进不来 SERP(站内应用页、登录墙后、平台内嵌、只在 App)→ 不具备持续可见度,不计入否决,记 `pass`。三分判据与出口限制见闸门契约 G3。

**深审判否的处置也在本层,不要拖到第 5 层**——第 5 层只处理深审存活的候选,一个 G2 判否或 G3 判 `veto` 的方向没有窗口可估、也不会出闸。它的留痕是**注册进账本再转 rejected**,不是一行索引:

```bash
# register 不带 --gates(带了就被 registrar 强制要 --expiry,而一个马上要 rejected
# 的方向没有排队期可言);闸门结论随下面这条 transition 一起提交
python3 xinci-workflow/xinci-core/scripts/registrar.py register \
  --slug <slug> --term "<精确措辞>" --source-url <URL> --source-note "<现场摘要>" \
  --task "<任务>" --evidence "证据/<slug>/<日期>-scan.json" --by xinci-scan
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to rejected --by xinci-scan \
  --gates G0=pass,G4=pass,G5=pass,G1=pass,G2=pass,G3=veto \
  --reason "G3 veto:数到 N 个免费实现做完任务且稳定可见(列出来);<结构阅读要点>"
```

(死在 G2 就把 `--gates` 写成 `...,G2=veto`,G3 那次没跑就不写——`gates` 只记真的跑过的门,与排队位同一条纪律。)

理由见生命周期契约「留痕分界」第 2 条:深审每轮只有 ≤5 次,它数到的免费实现清单与结构阅读要点是这个方向独有的证据,索引一行的 reason 装不下;而**没有**这条账本记录,下轮 `screen_index.py check` 就认不出它(check 同时查索引与账本,深审否决的候选只在账本一侧)。唯一的例外是命中已成册陷阱类别、当场跑 G3 验证判 `veto` 的方向——那是类别级死因的复核,按第 2 层走索引。

**超出配额的候选不许丢弃**:注册成 `captured`,带上已得的闸门结论**和一个 expiry**,下轮第 0 层优先消化。

expiry 是排队位的过期出口:排队每轮进多出少,没有 expiry 的方向会在队列里无声腐烂,而 report_status 只按 expiry 提示到期候选。给的是"这个方向大约还值得几天深审"的判断(附推理进观察文件),不是最终窗口评估——真正的 window_estimate 在第 5 层深审后才做。registrar 强制:带 `--gates` 就必须带 `--expiry`。

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py register \
  --slug <slug> --term "<精确措辞>" --source-url <URL> --source-note "<现场摘要>" \
  --task "<搜索者要完成的任务>" --gates G0=pass,G4=pass,G5=pass,G1=pass \
  --expiry <YYYY-MM-DD> --evidence "证据/<slug>/<日期>-scan.json" --by xinci-scan
```

### 第 5 层:窗口评估与注册(只对深审存活的候选)

估计窗口以天/周/月计(可发现性、多少人能做同样的页面、官方答案多久出现),写明推理。
每个候选一份观察文件 `证据/<slug>/<日期>-scan.json`(要点式,schema 见 数据结构/observation.schema.json),然后 register(命令格式同第 4 层的两个 register 块,深审已完成的把 `--gates` 一并带上 G2/G3 结论;上轮已排队注册过的候选跳过 register,直接出闸)。

**第一步一律是出闸 `captured → screened`,这一步不能跳。** register 出来的候选状态是 `captured`,而 `tracking` 与快道**都只从 `screened` 出发**(registrar 的合法边是 captured→screened→tracking / →fast_grab_ready,直接 `--to tracking` 会被判"非法转移")。窗口评估(`window_estimate`)与 G0–G5 全 pass 的校验也都落在这一步:

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to screened --by xinci-scan \
  --gates G2=pass,G3=pass --window-estimate <days|weeks|months> \
  --evidence "证据/<slug>/<日期>-scan.json"
```

排队候选注册时已带 G0/G4/G5/G1,本次只补 G2/G3——registrar 按**合并结果**校验 G0–G5 全 pass。`G3=veto_window_bet` 的候选出闸时额外要求 `--window-estimate days` + `--reason`(豁免依据),且 `--by` 不能是 xinci-run——**这不是"把 `--by` 换个值就能过"的意思,而是这条出口在连续运行下根本不可用**:连续运行时本该写的 `--by` 就是 `xinci-run`(见上「`--by` 约定」),写别的值是伪造授权印记。此时正确的处置是把候选留在 `captured` 挂起等用户单步确认(见下面的出口清单与 xinci-run 硬规则)。

**出闸后提议下一步,由用户确认后执行转移:**

- G0–G5 全过、窗口以周/月计 → 提议 `screened → tracking`(带 expiry 与失效条件);
- G0–G5 全过、窗口以天计 → 提议走快道(转给 xinci-decide 快速模式,它核对的输入正是 `screened` + `window_estimate=days`);
- G3 判定为**临时空位**(`veto_window_bet`)、窗口以天计 → 出闸时就带上豁免依据(`--reason`:数到的免费实现清单 + 为何判定它们只是还没被收录),观察文件记明该判断,然后提议走快道。该候选此后的合法出口共四个:`fast_grab_ready`(快道 go)、`rejected`(快道读完证据判定这个赌注不值)、`withdrawn`(用户撤回),以及它挂在 `captured` 时排队 expiry 过了的 `expired`;**唯独不得进 tracking**(理由见闸门契约 G3「唯一的降级出口」;`validate_ledger` 的 `WINDOW_BET_STATES` 同样只放行 `captured`/`screened`/`fast_grab_ready` 与终态,出现在 tracking 及其后继一律报错)。
  **此路径在连续运行模式下不可用**(registrar 拒收 `by=xinci-run`):此时候选**留在 `captured`**,带 gates 与 expiry 挂着等用户单步确认,清单 notes 记一句待确认——这是它的合法挂起位,不是失败,不许转 rejected。

(**深审被否决的候选不在本清单里**:它在第 4 层就走完了 register + `→rejected`,不进第 5 层——第 5 层只处理深审存活的候选,出闸的前提是 G0–G5 全 pass。)

### 第 6 层:写运行清单(含漏斗数据)

`运行/<日期>-xinci-scan.json`:打开过的来源、被拦的来源、触及的候选、计费调用数(本阶段应为 0),以及 **`funnel` 漏斗数据**:

```json
"funnel": {
  "extracted": 240,           // 第 1 层提取、经第 0 层去重后进入筛选的方向数(常态目标 200–300;连续模式积压时按软闸下调)
  "rejected_zero_cost": 204,  // 第 2 层筛除(含验证型类别 G3 判 veto;已进淘汰索引;预期约 85%)
  "rejected_g1": 18,          // 第 3 层 G1 否决(已进淘汰索引;预期约剩余的一半)
  "deep_audited": 5,          // 第 4 层实际深审(配额 ≤5)
  "queued": 13,               // 本轮没走完的存活方向(超深审配额 + 超 G1 上限未搜),注册为 captured 待下轮
  "carryover_audited": 0      // 可选,不参与加总:本轮消化存量 captured 所做的深审数(独立配额:默认 ≤5,captured 存量 >20 时 ≤10,表见 xinci-run 步骤 1)
}
```

**四个去向必须加总等于 extracted**——每个被提取的方向都要有归宿,不许无声丢弃。`validate_ledger.py` 强制此等式,并自 2026-08-19 起强制 `funnel` 本身必须存在(缺就报错)。

两条**不参与等式**的口径,写错了等式会算不平:

- 第 0 层**去重命中**的方向不计入 `extracted`(它们上一次已有归宿);
- 消化**存量 captured** 的深审记 `carryover_audited`,不记 `deep_audited`——它不属于本轮 `extracted`。只还债不扫新的轮次 `extracted` 与四个去向五项全 0,靠这个字段留下那一轮的真实成本。

同日再次运行时文件名追加启动时刻(`<日期>-<HHMM>-xinci-scan.json`),不覆盖已有清单。例外:xinci-run 连续运行模式下不另写本阶段清单,内容并入 run 清单。

## 硬规则

- 真浏览器直读,不走 API/MCP 数据工具拉社区内容;未在本次会话打开的来源不得声称已检查。
- 精确措辞 + 来源 URL + 时间戳,缺一不注册;凭记忆重构的词不是证据。
- 窗口期(captured / screened 状态,不看年龄)禁用 Semrush、KD、KGR、CPC、Google Trends;Semrush 查无是这条赛道的定义属性,不作为否决理由。
- 每个进入 tracking 的候选必须带 expiry(附推理)和至少一条失效条件。
- 区分"发布"与"一时热闹":只产生一周好奇、没有重复任务的东西,直说不值得,不进清单。
- 提议与执行分离:转移一律经用户确认后才调 registrar。例外:xinci-run 连续运行模式下,启动命令即标准授权,无需逐条确认。
- 本 skill 不注册域名、不花钱、不发布任何内容。
- 扫描产出为零时如实说零;禁止凑数,禁止 maybe 清单。
- **广度优先于深度**:一轮的价值先由"提取了多少方向"决定,再由"审得多深"决定。一个源里的多条独立变更要逐条提,不合并、不只挑最显眼的那条;提取不足目标量时**换源补足**,而不是拿现有的少数一路深挖到底。
- **每个被提取的方向必须有归宿**:秒弃(进淘汰索引)、G1 否决(进淘汰索引)、深审(注册)、或排队(注册为 captured——含超深审配额的和超 G1 上限没搜的)——四选一,**不许无声丢弃**。运行清单的 `funnel` 四项去向加总须等于 `extracted`,由 `validate_ledger.py` 强制;去重命中的方向不计入 `extracted`,消化存量的深审记 `carryover_audited`,两者都不参与等式。
- **深审配额每轮 ≤5 个**:G2/G3 是全流程最贵的动作,超配额的候选注册成 `captured` 排队,下轮开局优先消化,不得因为"这轮做不完"而丢掉。连续运行模式下**新扫描深审与还债深审配额彼此独立**——本层的 ≤5 只管新扫描的,还债另有自己的配额(积压严重时会临时提高,表见 xinci-run 运行循环步骤 1),还债不吃掉本轮扫描的深审名额。
- **排队位的两条纪律**:①注册排队候选必须带 `expiry`(registrar 强制),否则窗口过了没有出口、方向无声腐烂;②`gates` 只写真的跑过的门——没搜 G1 就不许写 G1=pass,下轮补上再进深审。**排队会积压**(每轮进 10–20、出 ≤5),所以连续运行模式对积压设了软闸——不是停扫,而是按积压量压低本轮提取目标,见 xinci-run 运行循环步骤 1。
- 秒弃的方向与 **G1 否决**都必须留痕进淘汰方向索引(批量追加,不逐条写),防止后续扫描重复评估;账本收的是「现场证据值得单独留档」的候选:深审存活的、排队的,以及**深审判否的**(第 4 层 register + `→rejected`,别漏这一类)。同一结构性模式在索引中第三次出现时,按陷阱类别.md 的追加规则归并成正式类别(索引补一行归并记录:**term 写模式名本身**、gate 记 G5、reason 以 `[已归并]` 开头指向类别号——term 写成某个具体方向会被 append 的去重静默跳过;写法见生命周期契约「归并纪律」),此后同模式由 G5 **按该类别的处置档**处理——「直接筛除型」零成本弃、「验证型」仍跑 G3 验证;**留痕不变**,秒弃照常追加一行索引(gate 记 G5),否则下轮 check 认不出它。索引不会因此膨胀:`append` 按归一化 term 跳重复,每行始终是一个独立方向。
