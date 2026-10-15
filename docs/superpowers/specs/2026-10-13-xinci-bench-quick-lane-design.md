# xinci-bench 新词快道设计

- 状态：设计稿（已与用户逐节评审通过，未落地实现）
- 日期：2026-10-13
- 目标：在 xinci-bench 里加一条"新词快道"，专抓最近 1 周到 3 个月才出现、首页还没有专门页面、而且会反复被搜的新词；判断我们第一个做，上线 90 天内能否有一个月达到 1 万美区访问，能就立刻强烈推荐用户建站
- 前身与关系：在 [xinci-bench-workflow 设计稿](2026-10-13-xinci-bench-workflow-design.md)（下称"标杆道设计稿"）基础上扩展；标杆道的判据、假设表、状态与流程不变

## 目录

- [1. 为什么要加快道](#1-为什么要加快道)
- [2. 定位与口径](#2-定位与口径)
  - [2.1 一句话定位](#21-一句话定位)
  - [2.2 用户定的口径](#22-用户定的口径)
  - [2.3 默认做法](#23-默认做法)
  - [2.4 与标杆道的关系](#24-与标杆道的关系)
  - [2.5 明确不做的事](#25-明确不做的事)
- [3. 流程与状态](#3-流程与状态)
  - [3.1 一次运行的七步](#31-一次运行的七步)
  - [3.2 状态机](#32-状态机)
  - [3.3 否决门](#33-否决门)
- [4. 数据来源与获取方式](#4-数据来源与获取方式)
  - [4.1 通道分工](#41-通道分工)
  - [4.2 搜索侧来源](#42-搜索侧来源)
  - [4.3 上游来源](#43-上游来源)
  - [4.4 现场来源](#44-现场来源)
  - [4.5 已确认不可用的来源](#45-已确认不可用的来源)
- [5. 速判六条](#5-速判六条)
- [6. 量级换算与测算](#6-量级换算与测算)
  - [6.1 锚词换算](#61-锚词换算)
  - [6.2 访问与收入](#62-访问与收入)
  - [6.3 判定](#63-判定)
  - [6.4 假设表](#64-假设表)
- [7. 强烈推荐与建站跟进](#7-强烈推荐与建站跟进)
  - [7.1 四处推荐](#71-四处推荐)
  - [7.2 建站跟进状态](#72-建站跟进状态)
  - [7.3 验收节点](#73-验收节点)
- [8. 产出物](#8-产出物)
  - [8.1 快道决策书](#81-快道决策书)
  - [8.2 最小版本建站简报](#82-最小版本建站简报)
- [9. 数据模型](#9-数据模型)
  - [9.1 快道方向记录](#91-快道方向记录)
  - [9.2 四类新观察](#92-四类新观察)
  - [9.3 原料池、淘汰记录与补全快照](#93-原料池淘汰记录与补全快照)
  - [9.4 数据区](#94-数据区)
- [10. 单元与脚本](#10-单元与脚本)
  - [10.1 新增](#101-新增)
  - [10.2 修改](#102-修改)
  - [10.3 运行清单](#103-运行清单)
- [11. 错误处理](#11-错误处理)
- [12. 测试](#12-测试)
- [13. 验收标准](#13-验收标准)
- [14. 设计决策记录](#14-设计决策记录)
- [15. 实现时的调整](#15-实现时的调整)
- [16. 实现后的口径调整](#16-实现后的口径调整)

## 1. 为什么要加快道

标杆道的入场条件是"标杆站美区自然流量 ≥ 5,000/月"，一个刚起量一周、还没人做站的词按定义没有标杆，标杆道结构上抓不到。用户认为这类词"有流量、没竞争、非常好上站"，不能错过。

旧的 xinci 新词工作流（20 天、437 个候选、0 个认定通过）曾专找新事物，校准结论是"面向普通用户与开发者的新事物，答案与事物几乎同时到"。但它的目标是 B2B 付费者，新词阶段刻意禁用搜索量，从未测过"普通用户新词 + 广告流量"能否成立，所以这条结论对快道**未验证**，不作否决依据。它留下的两条教训照用：来源标的"新"常常不准，要从对象自己的发布页核日期；它唯一的 go 因 7 天窗口内没人建站而过期，所以快道的 go 必须强推、必须跟进。

## 2. 定位与口径

### 2.1 一句话定位

快道从上游新对象（新游戏、新产品、新功能、新规则）出发，用自动补全和 Trends 抓刚冒头的任务说法，速判"真新、有人搜、不是一次性、范围内、没人做、没被答完"，用锚词把 Trends 换算成月搜索量，估上线 90 天内的月访问；过线就判 go 并四处强推，量不够但在涨的进"观察中"等它长。

### 2.2 用户定的口径

2026-10-13 逐条确认：

- **放在哪**：xinci-bench 里加一条独立的快道（方案 A），新增 skill `xinci-bench-quick`，底座共用。
- **触发**：暗号 `xinci_bench_quick_run`，手动运行，不做定时任务。
- **门槛**：预计上线后 90 天内有一个月 ≥ 10,000 美区访问，且需求不是一次性的；预计 ≥ 25,000 的另标"单站就能到 $100"。
- **首发份额**：保守 10% / 基准 20% / 乐观 30%；AI 概览在场但没答完时再 ×0.6。
- **建站**：用户自己建；工作流走到 go 时要强烈推荐。
- **Steam、Roblox**：不用 GitHub Actions 绕道，靠替代来源。
- **默认值**（第 3、5、6、7 节）全部接受：观察期 30 天、每次最多现场看 10 个词、"真新" 90 天、冲高回落 30%、原料保留 7 天、10 个任务词、四处强推、收入按 AdSense $4/千访问展示、最晚上线 7 天、验收节点 14/30/90 天、30 天低于预期 25% 止损。

### 2.3 默认做法

- 英文站、只算美区，范围排除沿用标杆道五条（YMYL、品牌导航、新闻热点、成人赌博、侵权）。新闻热点是快道最大的噪声，速判时专门核。
- 新站 90 天内大概率只能接 AdSense，收入按 $4/千访问展示；1 万访问约 $40/月。新站能否立即申请 Mediavine Journey 未确认。

### 2.4 与标杆道的关系

- 账本、种子池、观察只追加、结算与回滚、决策书 html 渲染、运行清单、看板共用。
- 每条方向记录新增 `lane`：`bench` 或 `quick`。标杆道记录的其他字段与规则不变。
- 快道判 go 的方向不再进标杆道。
- 速判发现首页已有小站在做（`occupied`）时，把那个站的域名登记成标杆道种子（来源 `serp`），等它攒够流量走标杆道评估。
- 两条道各自的运行互不阻塞：同一条道同时只能有一个未完成运行。

### 2.5 明确不做的事

- 不建站、不注册域名、不上线、不做定时任务。
- 不预测排名，不承诺收入；快道假设表只由用户改。
- 不外推增长：估算按当前量。

## 3. 流程与状态

### 3.1 一次运行的七步

1. **先提醒**：列出所有跟进状态为"待开建"的快道 go，放在汇报最前面再推荐一次；列出"已上线"且验收节点已到的方向。
2. **复查观察中**：对每个 watching 方向重新换算量级、重看首页，转 go、继续观察（记一次复查）或否决；登记满 30 天仍不够的否决（`volume`）。
3. **扫信号**：从第 4 节的来源抓新对象和新说法，写一份原料批次观察，原料进原料池；与已有方向、旧裁决、快道淘汰记录去重。
4. **零成本速判**：Q1–Q4（第 5 节），不花 Semrush、不看 Google。
5. **首屏速判**：内置浏览器读 Google 首页判 Q5、Q6；两次请求间隔 ≥ 60 秒，每次运行最多看 10 个词。
6. **登记、测算、结算**：过了速判的词登记为快道方向，锚词换算量级，按第 6 节判 go / 观察中 / 否决 / 搁置，经 `settle.py` 结算。
7. **推荐与汇报**：出 go 按第 7 节四处强推；汇报写各来源扫了多少、各步筛掉多少、观察中剩几个和各自剩余天数、Semrush 调用数。

### 3.2 状态机

快道在标杆道四态之外加 `watching`：

```
found    → go | rejected | parked | watching
watching → go | rejected
parked   → go | rejected
```

- `watching`：速判六条全过，基准预计 < 1 万，且趋势不降（§6.3）。登记日起 30 天到期；每次运行复查一次，复查记在记录里，不算状态转移。到期仍 < 1 万 → `rejected`（`volume`）；复查时首页出现完整做了任务的页面 → `rejected`（`occupied`）。
- 标杆道的合法转移不变；`watching` 只对 `lane=quick` 合法。

### 3.3 否决门

| 门 | 条件 | 最少证据 |
| --- | --- | --- |
| `scope` | 范围排除命中 | 速判观察里 Q4 不过及命中项 |
| `not_new` | 对象首次公开超过 90 天，或老东西换名 | 速判观察里 Q1 不过及日期来源 |
| `oneoff` | 新闻热点、一次性需求、冲高回落 | 速判观察里 Q3 不过及依据（冲高回落须有量级观察的曲线） |
| `occupied` | 首页已有页面完整做了这个任务 | 速判观察里 Q5 不过及该页面 |
| `answered` | AI 概览或原生组件已答完 | 速判观察里 Q6 不过 |
| `volume` | 观察到期，基准预计仍 < 1 万；或基准 < 1 万且趋势下降 | 最新一份量级观察，模型重算一致 |

`parked`：关键证据拿不到（Trends 读不出、首页预检失败重试仍失败、对象发布日期查不到）。

速判不过的词**不登记成方向**，只进快道淘汰记录（§9.3），记门代码与速判观察，同标杆道"初核不过只进淘汰索引"。上表的否决门用于已登记的方向：结算时、或 watching 复查时发现不过。

## 4. 数据来源与获取方式

2026-10-13 从本机逐个实测。未在本次运行实际取回的来源不得写"已检查"；每次运行实际打开的网址记进观察 `source_urls`。

### 4.1 通道分工

| 通道 | 用于 |
| --- | --- |
| curl / 脚本 | 自动补全、Trends 热搜 RSS、各公开接口与订阅源 |
| 内置浏览器 | Trends 曲线与飙升词（在 trends 页面内调用内部接口）、Google 首页现场、Reddit（经 Google 搜索）、Google Play |
| 用户的 Chrome | 只在旧词库没有合适锚词时，用 Semrush 查锚词月量 |

社区类内容（Product Hunt、Reddit）有潜力的条目要在真实浏览器读原页（沿用旧新词工作流原则）。

### 4.2 搜索侧来源

| 编号 | 来源 | 获取方式 | 取什么 | 限制 | 实测 |
| --- | --- | --- | --- | --- | --- |
| ① | Google 自动补全 | `GET https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=us&q=<查询>`；返回 `[原查询, [≤10 条建议]]`（`client=chrome` 另带相关度与类型） | 建议列表；每个对象查"对象名 + 空格"和"对象名 + 每个任务词"，存快照、与上次比出新建议 | 频率上限未确认，脚本间隔 ≥1 秒 | 可用；"grow a garden 2 " 返回含 "grow a garden 2 calculator" 的 10 条 |
| ② | Trends 曲线 | 内置浏览器打开 `trends.google.com/trends/explore?geo=US&q=<词>`，页内 `fetch('/trends/api/explore?hl=en-US&tz=0&req=<JSON>')`，切掉返回体前缀 `)]}'`，取 `TIMESERIES` 的 request 与 token，再请求 `/trends/api/widgetdata/multiline?req=…&token=…` | `timelineData[].formattedTime` 与 `value`；时间窗 `now 7-d`（逐小时）、`today 1-m`（逐日）、`today 3-m` | 两次请求间隔 ≥1.5 秒，否则 429；curl 直接请求返回 429；低量词是噪声大的小整数 | 可用；7 天 169 点、30 天 31 点 |
| ③ | Trends 飙升相关查询 | 同 ②，取 `RELATED_QUERIES` 的 request 与 token，请求 `/trends/api/widgetdata/relatedsearches` | `rankedList[0]` 热门（0–100）、`rankedList[1]` 飙升（百分比或 Breakout）；对新对象查，也对任务词以 `now 7-d` 查 | 同 ② | 可用；"grow a garden 2 weather tracker" +200% |
| ④ | 锚词换算 | 同 ②，一次请求放新词与锚词两个 `comparisonItem` | 两条曲线同窗均值 → 比值 → 月搜索量（§6.1） | 锚词与新词均值比须在 1/5 到 5 之间 | 可用；对 "what county am i in"（74,000）得 "grow a garden 2" 约 4,992（30 天）/ 5,579（7 天），这次比值约 1/15，只能当量级 |
| ⑤ | Trends 热搜 RSS | `GET https://trends.google.com/trending/rss?geo=US` | 每条 `title`、`ht:approx_traffic`、`ht:news_item_title`、`ht:news_item_url` | — | 可用；10 条，基本是新闻与人名 |
| ⑥ | Semrush | 用户 Chrome，Keyword Overview / Keyword Magic | 锚词月量（旧词库没有合适锚词时） | 每天约一百来次；新词自身量在 Semrush 里多久出现未确认 | 首次运行时测 |

### 4.3 上游来源

| 编号 | 来源 | 获取方式 | 取什么 | 实测 |
| --- | --- | --- | --- | --- |
| ⑦ | SteamCharts（替代 Steam） | curl `https://steamcharts.com/top`（HTML 表）；单款历史 `https://steamcharts.com/app/<id>` | app id、名称、当前在线人数；与上次快照比出新进榜；单款在线人数走势（Q3）。不含发布日期，Q1 改从 Wikipedia 或 Google 读 | 可用；前 25 名，第一名 Counter-Strike 2 在线 531,467 |
| ⑧ | Roblox（替代） | 不直接取；用 ①③ 盯"roblox"与任务词的飙升，加 ⑬ YouTube | 新体验名与任务说法 | 官方与第三方统计站都取不到（见 4.5） |
| ⑨ | Apple 免费榜 RSS | curl `https://rss.applemarketingtools.com/api/v2/us/apps/top-free/50/apps.json` | `name`、`releaseDate`、`url`；`genre=6014` 过滤无效，游戏无法单独筛 | 可用；如 Muse from Meta 发布于 2026-09-08 |
| ⑨ | iTunes 搜索接口 | curl `https://itunes.apple.com/search?term=<词>&country=us&entity=software` | `trackName`、`releaseDate`、`primaryGenreName`；核对象发布日期、看是否已有配套 App | 可用；搜到 "Grow A Garden : Codes & Stocks" |
| ⑨ | Google Play | 内置浏览器读 `https://play.google.com/store/games?hl=en&gl=US` | 新上榜游戏名 | 未实测（curl 只得脚本外壳） |
| ⑩ | Product Hunt | curl `https://www.producthunt.com/feed`（Atom） | 每条 `title`、`link`、`published`、`content`；有潜力的再用浏览器读原页 | 可用；50 条 |
| ⑪ | GitHub | curl `https://github.com/trending?since=daily`（或 `weekly`）HTML；`gh api "search/repositories?q=created:>YYYY-MM-DD&sort=stars&order=desc"` | 仓库名、`created_at`、`stargazers_count` | 可用；weekly 12 个仓库；搜索接口返回 9 月下旬新建、2–5.5 万 star 的仓库。未登录搜索接口每分钟 10 次，gh 已登录可提高 |
| ⑫ | Hacker News | curl `https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&numericFilters=points>50` | `title`、`url`、`points`、`created_at` | 可用 |
| ⑬ | YouTube 搜索 | curl `https://www.youtube.com/results?search_query=<词>` | 页面内 `videoRenderer` 条目数与 `publishedTimeText`（相对时间）；看创作者是否跟进 | 可用但易碎：出口不在美国，页面为繁体中文（香港），改版即失效 |
| ⑭ | Wikipedia 浏览量 | curl `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/<词条>/daily/<起>/<止>`（日期 YYYYMMDD） | 每日 `views`；对象热度的绝对参照与持续性（Q3） | 可用；Grow_a_Garden 9-01 为 152、10-12 为 216 |
| ⑮ | 平台规则与政策 | curl `https://www.federalregister.gov/api/v1/documents.json?order=newest`；其他辖区沿用旧新词工作流 `数据采集指南.md` 的已验证取法 | `title`、`publication_date`、`type`、`abstract` | 可用 |

### 4.4 现场来源

| 编号 | 来源 | 获取方式 | 用于 |
| --- | --- | --- | --- |
| ⑯ | Google 首页 | 内置浏览器，规程同标杆道（`gl=us&hl=en&pws=0`、预检四项、请求间隔 ≥60 秒） | Q5 没人做、Q6 没被答完 |
| ⑯ | Reddit | 接口返回 403；内置浏览器搜 Google `site:reddit.com "<对象>" (calculator OR tracker OR tool)`，加 `tbs=qdr:w` | 社区里"有没有工具能做 X"的提问 |

### 4.5 已确认不可用的来源

2026-10-13 实测：Steam 官方接口（curl 连接失败、内置浏览器被拒、Chrome 错误页）、SteamSpy（Cloudflare 挑战）、Roblox 官网与接口（三通道均失败）、RoMonitor 与 RoTrends（curl 得脚本外壳）、Reddit 接口（403）、Trends 接口直接 curl（429）、Google 搜索页直接 curl（脚本外壳）。Exploding Topics 等付费趋势工具无账号，不用。

## 5. 速判六条

前四条零成本，过了才看 Google 首页。每条在速判观察里写 `pass`（true/false/null）与 `basis`；前一条已不过时后面的可填 null。

| 编号 | 条件 | 判法 | 不过时 |
| --- | --- | --- | --- |
| Q1 真新 | 对象首次公开在 90 天内 | 从对象自己的发布页、商店页、仓库首个版本读日期（不信来源的"新"标签）；Trends 可读时 90 天前应接近 0 | `not_new` |
| Q2 有人在搜 | 至少一项证据 | 自动补全出现该说法，或 Trends 曲线可读（不全为 0） | 不否决；原料保留 7 天，下次再看，过期丢弃 |
| Q3 不是一次性 | 四项都满足 | 任务会反复发生；不是新闻事件驱动（对照 ⑤ 热搜 RSS）；底层对象在涨或持平（在线人数、榜单、star、Wikipedia 浏览量）；不冲高回落（§6.3） | `oneoff` |
| Q4 范围 | 五条排除都未命中 | 同标杆道 | `scope` |
| Q5 没人做 | 首页前 10 条无页面完整做了这个任务 | "完整做了"同标杆道：页面上直接、免费拿到用户要的结果；新闻、论坛、视频、官方公告不算 | `occupied`；该站若是小站，登记为标杆道种子 |
| Q6 没被答完 | AI 概览或原生组件没答完 | 同标杆道首屏规程 | `answered` |

**任务词**（`TASK_WORDS`）：calculator、codes、tracker、tier list、map、checker、generator、converter、build、value。

## 6. 量级换算与测算

### 6.1 锚词换算

下面是示例值：

```json
{
  "anchor_term": "<旧词库里量级接近的词>",  // 锚词:优先旧词库里 90 天内测过、无季节性的词;没有再用 Semrush
  "anchor_volume": 9900,                   // 锚词已知月搜索量
  "anchor_source": "lexicon",              // lexicon 旧词库 | semrush
  "anchor_measured_at": "2026-10-08",      // 锚词测量日,须在 90 天内
  "window_days": 7,                        // 用最近 7 天;同时报 30 天做对照
  "new_mean_7d": 54.0, "anchor_mean_7d": 96.0,
  "new_mean_30d": 44.0, "anchor_mean_30d": 90.0,
  "ratio_7d": 0.5625,                      // 新词均值 ÷ 锚词均值;须在 0.2–5 之间,否则换锚词
  "estimate_7d": 5569,                     // anchor_volume × ratio_7d,这是"当前月搜索量"
  "estimate_30d": 4840,                    // 对照
  "series_30d": [0, 0, 11, "…", 52]        // 30 天逐日新词值,用于趋势与冲高回落判断
}
```

比值不在 0.2–5 之间的量级观察，`write_observation.py` 拒收；Trends 全为 0 时不能换算，原料留到下次。2026-10-13 那次实测（锚词 "what county am i in" 74,000，比值约 1/15）按这条规则应换一个量级更接近的锚词。

### 6.2 访问与收入

```
预计月访问(情景) = floor(当前月搜索量 × 首发份额(情景) × AI 概览系数)
首发份额:保守 0.10、基准 0.20、乐观 0.30
AI 概览系数:AI 概览在场但没答完 0.6,否则 1.0
预计月收入 = 预计月访问 × $4 ÷ 1000
```

按当前量算，不外推增长。输出还包括：基准过线所需月搜索量（无 AI 概览 50,000，有 AI 概览约 83,334）、是否"单站就能到 $100"（基准 ≥ 25,000）。

### 6.3 判定

- **趋势不降**：最近 7 天均值 ≥ 前 7 天均值的 80%（取自 `series_30d` 后 14 天）。
- **冲高回落**：最近 7 天均值 < 近 30 天峰值的 30% → Q3 不过（`oneoff`）。

| 结论 | 条件 |
| --- | --- |
| go | Q1–Q6 全过（Q2 有证据）；基准预计 ≥ 10,000；简报素材写明最小版本 ≤ 3 天能做出、数据拿得到 |
| watching | Q1–Q6 全过；基准 < 10,000；趋势不降 |
| rejected | 任一门不过（§3.3）；或 watching 到期仍 < 10,000；或基准 < 10,000 且趋势下降（`volume`） |
| parked | 关键证据拿不到 |

例子：今天测的 "grow a garden 2" 约 5,000/月 → 基准约 1,000 访问，若首页确实没人做且趋势不降，进 watching。

### 6.4 假设表

版本 `2026-10-13.q1`，写在 `quick_model.QUICK_ASSUMPTIONS`，与契约由文档一致性测试锁定；只由用户改。

| 项目 | 值 |
| --- | --- |
| 首发份额 保守/基准/乐观 | 0.10 / 0.20 / 0.30 |
| AI 概览在场未答完系数 | 0.6 |
| go 门槛（基准，90 天内单月） | 10,000 访问 |
| "单站就能到 $100" | 25,000 访问 |
| 收入展示 | AdSense $4/千访问 |
| 真新 | 对象首次公开 ≤ 90 天 |
| 观察期 | 30 天 |
| 冲高回落 | 最近 7 天均值 < 近 30 天峰值 × 0.3 |
| 趋势不降 | 最近 7 天均值 ≥ 前 7 天 × 0.8 |
| 锚词比值区间 | 0.2–5 |
| 原料保留 | 7 天 |
| 每次运行首屏上限 | 10 个词 |
| 建议最晚上线 | 判 go 后 7 天 |
| 验收节点 | 上线后 14 / 30 / 90 天 |
| 止损 | 第 30 天月点击 < 基准预计 × 0.25 |

## 7. 强烈推荐与建站跟进

### 7.1 四处推荐

判 go 当次运行，以下四处同时出现，直到用户把跟进状态改为"已开建"或"放弃"：

1. **推送通知**：`xinci-bench-quick` 的 SKILL 要求调用推送通知工具，内容含方向、预计基准访问与收入、建议最晚上线日期。
2. **运行汇报第一行**：以"【立即建站】"开头，写方向、预计访问与收入、决策书路径。
3. **决策书开头**：`## 立即建站` 一节（html 加底色），写窗口理由（首页没人做、起量日期）、建议最晚上线日期、三档预计、最小版本页面清单。
4. **看板顶部常驻**：`report_status.py` 第一屏列出所有"待开建"的快道 go；任何 bench 命令的 SKILL 汇报都先读看板再汇报。

### 7.2 建站跟进状态

```json
"follow_up": {
  "status": "pending",            // pending 待开建 | started 已开建 | launched 已上线 | abandoned 放弃
  "go_at": "2026-10-20",          // 判 go 日期
  "launch_by": "2026-10-27",      // 建议最晚上线 = go_at + 7 天
  "domain": null,                 // 已开建时填
  "started_at": null,
  "launched_at": null,            // 已上线时填,验收节点由它起算
  "reason": null                  // 放弃时填
}
```

用户（或执行者按用户口述）用 `ledger.py follow-up --slug <方向> --status started|launched|abandoned [--domain] [--date] [--reason]` 改；只能按 pending → started → launched 前进，任何时候可改 abandoned；不改 `state`。

### 7.3 验收节点

| 上线后 | 看什么 | 结论 |
| --- | --- | --- |
| 第 14 天 | 主页面是否收录、有展现 | 没有就先查收录 |
| 第 30 天 | 月点击是否 < 基准预计 × 0.25 | 低于即止损：不再加工时，站留着 |
| 第 90 天 | 单月是否 ≥ 10,000 访问 | 达到算成功 |

看板按 `launched_at` 列出已到期的节点；用户记录的点击与收入写进 `反馈/`（标杆道设计稿 §4.6 的校准入口），以后用来校准首发份额。

## 8. 产出物

### 8.1 快道决策书

由 `build_quick_doc.py` 生成 `文档/<slug>.md`，再用现有 `build_doc_html.py` 生成 html；纪律同标杆道（md 唯一事实来源、每节第一句加粗结论、数字标"模型估算"或"Trends 换算"、结算时把 md 的 SHA 记进 `decision.doc_sha256`）。

1. `## 立即建站`（仅 go）
2. `## 结论`：一句话理由、基准访问与收入、最大的未知
3. 新对象与新说法：对象、首次公开日期与来源、冒出的任务说法与来源
4. 有人在搜：自动补全、Trends 曲线、锚词换算
5. 不是一次性：任务频率、对象走势、是否新闻、冲高回落判断
6. 首页现场与 GEO：前 10 条、AI 概览、谁在做
7. 预计访问与收入：三档、所需搜索量、未确认假设
8. 风险与最大未知
9. 附：证据清单

### 8.2 最小版本建站简报

仅 go 时生成，接在决策书后：

1. 做什么：1 个主页面完成核心任务，最多 2–3 个配套页覆盖同一对象的其他任务词
2. 页面清单：路径、目标查询（照抄自动补全原话）、交付
3. 数据：来源、授权、更新频率
4. 上线清单：免费托管、Search Console 与 sitemap；SEO 与 GEO 固定条目沿用标杆道
5. 预计访问与收入：三档，AdSense
6. 验收与止损：§7.3

## 9. 数据模型

### 9.1 快道方向记录

与标杆道共用 `slug`、`title`、`site_type`、`state`、`model`、`decision`、`evidence_refs`、`bindings`、`history`，新增 `lane`；快道专有字段如下（示例值）：

```json
{
  "lane": "quick",                                  // bench | quick;标杆道记录写 bench
  "object": {
    "name": "Grow a Garden 2",                       // 催生新词的对象
    "first_public": "2026-09-28",                    // 首次公开日期
    "date_source": "https://…"                       // 日期从哪读的
  },
  "terms": [
    {"term": "grow a garden 2 calculator", "source": "autocomplete", "first_seen": "2026-10-13"}  // 冒出的任务说法
  ],
  "volume": null,                                    // 结算时从最新量级观察写入:estimate_7d、estimate_30d、锚词信息、趋势
  "serp": null,                                      // 结算时从最新速判观察写入:aio_present、aio_completes、occupied_by
  "watch": null,                                     // watching 时:{"since": "2026-10-13", "expires_at": "2026-11-12", "checks": [{"at": "…", "estimate_7d": 5579, "base_visits": 1115}]}
  "follow_up": null                                  // go 时初始化,见 §7.2
}
```

### 9.2 四类新观察

公共字段同标杆道（`slug`、`observed_at` ISO、`stage`、`kind`、`source_urls`、`semrush_calls`、`points`、`readings`）；快道观察 `stage` 固定为 `quick`。`quick_signal` 的 `slug` 为 null；其余三类的 `slug` 是拟登记或已登记的方向名（速判在登记前写，同标杆道初核观察先于登记）。下面是示例值：

```json
// quick_signal:一次运行的原料批次,slug 为 null
{"items": [{"source": "autocomplete", "object": "Grow a Garden 2", "term": "grow a garden 2 calculator",
            "url": "https://suggestqueries.google.com/…", "seen_at": "2026-10-13"}]}

// quick_screen:一个方向的速判
{"term": "grow a garden 2 calculator",
 "checks": {"Q1": {"pass": true, "basis": "官方发布页 2026-09-28"},
            "Q2": {"pass": true, "basis": "自动补全出现"},
            "Q3": {"pass": true, "basis": "每局都要算,在线人数持平"},
            "Q4": {"pass": true, "basis": "不涉排除项"},
            "Q5": {"pass": true, "basis": "首页为 reddit、YouTube、官方 Discord"},
            "Q6": {"pass": true, "basis": "无 AI 概览"}},
 "ai_overview": {"present": false, "completes_task": false, "cited_domains": []},
 "top10": [{"pos": 1, "domain": "reddit.com", "type": "forum", "completes_task": false}],
 "occupied_by": null}                       // Q5 不过时填完整做了任务的页面域名
// Q5、Q6 有结论时须带通过的 browser_preflight

// quick_volume:锚词换算,字段见 §6.1

// quick_brief:最小版本简报素材,判 go 时必须有
{"positioning": "输入作物与天气,算出售价",
 "pages": [{"path": "/", "target_query": "grow a garden 2 calculator", "deliverable": "按作物与突变算价格"}],
 "data_sources": ["游戏内价格表,社区 wiki"], "license": "事实数据,自行整理",
 "update_frequency": "随游戏更新", "build_days": 2, "data_available": true,
 "hosting": "Cloudflare Pages 免费版", "risks": ["游戏热度可能三个月内回落"]}
```

### 9.3 原料池、淘汰记录与补全快照

- `快道/原料.jsonl`：每行 `{id, source, object, term, url, seen_at, status}`，`status` 为 pending / used / expired；Q2 无证据的 pending 原料 7 天后标 expired。
- `快道/淘汰.json`：`{"terms": {"<规范化词>": {"gate", "at", "observation"}}}`，同词不再看。
- `快道/补全快照/<规范化查询>.json`：`[{fetched_at, query, suggestions}]`，追加；比对结果给出 `new_suggestions` 与 `gap_days`。

### 9.4 数据区

在现有数据区新增 `快道/`、`快道/补全快照/`、`快道/原料.jsonl`、`快道/淘汰.json`，由 `init_workspace.py` 幂等创建。现有账本为空，无需迁移；`lane` 缺失的记录按校验错误处理。

## 10. 单元与脚本

### 10.1 新增

| 文件 | 职责 |
| --- | --- |
| `xinci-bench-quick/SKILL.md` | 快道流程（§3.1），暗号 `xinci_bench_quick_run`；go 时调用推送通知并按 §7.1 汇报 |
| `scripts/quick_model.py` | `QUICK_ASSUMPTIONS`、锚词换算、趋势与冲高回落判断、三档访问与收入、判定建议 |
| `scripts/suggest_snapshot.py` | 取自动补全（可注入取数函数，测试不联网）、存快照、比出新建议与间隔天数；`--object` 按任务词展开 |
| `scripts/quick_pool.py` | 原料池登记与去重（对已有方向、旧裁决、快道淘汰）、7 天过期、淘汰记录 |
| `scripts/build_quick_doc.py` | 快道决策书 md（§8），调用 `build_doc_html.py` |

### 10.2 修改

| 文件 | 修改 |
| --- | --- |
| `ledger.py` | `lane`；`register_quick`（须有 Q1–Q6 全过的速判观察）；快道合法转移与六个否决门的最小证据；`watching` 复查记录；`follow-up` 子命令；`rank` 只排标杆道 |
| `write_observation.py` | 四类新观察的校验；锚词比值区间；Q5/Q6 有结论须带预检 |
| `settle.py` | 按 lane 选复核与文档生成；快道 go 初始化 `follow_up` |
| `validate_ledger.py` | 按 lane 校验；快道模型重算一致；watching 过期报错；follow_up 状态合法 |
| `run_log.py` | 支持 `xinci-bench-quick` 单阶段运行；两条道的未完成运行分开判断 |
| `report_status.py` | 顶部"待开建"快道 go；watching 列表与剩余天数；到期验收节点 |
| `init_workspace.py` | 新增 `快道/` 目录与空文件 |
| `build_doc_html.py` | `## 立即建站` 一节加底色 |
| 文档 | `选站契约.md` 加快道一章；`数据采集.md` 加 §4 的来源与取法；`命令与观察.md` 加快道命令与观察；三份 schema；README；工作流说明 html 与发布页 |

### 10.3 运行清单

快道运行的清单 `skill` 为 `xinci-bench-quick`，`round` 与 `max_rounds` 固定为 1，`source_kind` 记本次主要来源（新增取值 `quick`），`outcome` 为 started / completed / blocked，completed 后 `next_step=done`，blocked 可用同一运行编号恢复。

## 11. 错误处理

| 情况 | 处理 |
| --- | --- |
| 自动补全请求失败或被限流 | 该对象本次不比对，快照不写，汇报写明；不当作"没有新建议" |
| Trends 429 | 间隔加大重试一次；仍失败记 blocked，保留恢复位置 |
| Trends 全为 0 | 不能换算，原料留到下次（Q2 无证据） |
| 锚词比值不在 0.2–5 | 换锚词；旧词库与 Semrush 都找不到合适锚词 → parked |
| 对象发布日期查不到 | Q1 填 null，parked |
| 首页预检失败 | 同标杆道，重试一次仍失败记 blocker |
| 上游来源取不到 | 汇报写明哪个来源本次未取回，不写"已检查" |
| watching 超过 30 天未处理 | `validate_ledger.py` 报错；下次运行第 2 步先处理 |
| 结算失败 | 沿用 settle 的先复核再写、失败回滚 |

## 12. 测试

- 现有 93 个测试保持通过；新增约 40 个，按 TDD 写。
- `suggest_snapshot.py` 用注入的假取数函数测试，不联网；另在验收时对真实接口跑一次。
- 重点用例：锚词换算与比值区间、趋势与冲高回落、三档访问与门槛边界（9,999 与 10,000）、AI 概览系数、watching 到期转否决、`occupied` 时小站登记为标杆种子、follow_up 只能前进、两条道运行互不阻塞、快道决策书含"立即建站"且 html 加底色、文档一致性测试覆盖 `QUICK_ASSUMPTIONS` 与 `TASK_WORDS`。

## 13. 验收标准

1. 全部测试通过；真实数据区 `validate_ledger.py` 0 错误；`init_workspace.py` 重跑后出现 `快道/` 目录。
2. `suggest_snapshot.py --object "grow a garden 2"` 对真实接口取回建议并写出快照。
3. 四个旧 skill 的说明与快道 skill 互不冲突；`xinci-bench-quick` 软链到两个环境。
4. 工作流说明 html 与发布页加入快道内容。
5. 首次真实运行（不在实现验收内）：跑一次 `xinci_bench_quick_run`，各来源取回情况如实记录。

## 14. 设计决策记录

- **独立快道 skill、共用底座**：用户选方案 A；旧新词工作流两道混在一份契约里导致膨胀，不重蹈。
- **加 watching 状态**：新词的量在长，"量不够就否决"会错过正在起量的词；30 天到期防止无限挂着。
- **按当前量、不外推**：新词增长不可预测，外推会系统性高估。
- **门槛 1 万而不是 2.5 万**：最小版本 1–3 天、投入小，预估误差大，门槛太高会重演"什么都过不了"（用户选）。
- **首发份额 10/20/30%**：基准对应"排第 1、无 AI 概览"的点击率（AWR 2026-07 约 20%，美国桌面）；新域名多久能排上去未确认（用户选）。
- **不用 GitHub Actions 取 Steam/Roblox**：用户选；游戏方向靠 SteamCharts、自动补全、Trends、YouTube、Wikipedia。
- **手动触发、不做定时任务**：用户选暗号 `xinci_bench_quick_run`；代价是自动补全按"上一次运行"比对，记录间隔天数。
- **强推四处 + 跟进状态**：旧新词工作流唯一的 go 因无人建站过期；go 必须持续提醒，直到用户明确处理。

## 15. 实现时的调整

实施计划 `docs/superpowers/plans/2026-10-14-xinci-bench-quick-lane.md` 相对本设计稿补的 12 处：

1. 自动补全的"新建议"指以前所有快照里都没出现过的建议：同一查询隔几秒请求，返回的建议也不一样（2026-10-13 实测），只和上一次比会把波动当成新词；第一次快照只作基线。快照文件名为 `<规范化查询>-<查询 SHA-1 前 8 位>.json`，防止不同查询规范化后重名。
2. 运行清单的 `source_kind` 固定为 `quick`，本次用了哪些来源写在 `seed_value`。
3. `settle.py` 在任何写入之前先核对否决门属于该方向所在的道（快道不能用 `revenue` 等标杆道的门），不符直接拒收。
4. 速判 Q5 不过、占位的是小站时，用 `quick_pool.py reject --seed-domain <域名>` 在记淘汰的同时登记为标杆道种子（来源 serp）；已登记方向结算为 `occupied` 时仍用 `seeds.py add`。
5. 登记时速判观察里的词须是登记的说法之一（大小写与空格不计）；同一说法不能属于两个方向。
6. 量级观察额外校验：`ratio_7d` 须等于两条曲线 7 天均值之比，`estimate_7d` 须等于锚词月量 × 比值（允许取整误差 1），曲线至少 14 个非负数（Trends 显示 "<1" 的点记 0）。
7. 快道方向用 `ledger.py update` 只能改 `title`、`site_type`、`terms` 和追加观察引用，标杆道字段一律拒收。
8. 建站跟进的日期须为 YYYY-MM-DD，开建不早于判 go，上线不早于开建。
9. 原料池每行多记 `observation`（来自哪份 `quick_signal` 观察）与 `updated_at`；淘汰记录在顺带登记种子时多记 `seed`、`seed_added`。
10. 决策书把 §8.1 的第 3–8 项归在"第一部分 决策"（### 1–6）下，简报为"第二部分 最小版本建站简报"（### 1–6）。
11. 测试新增 69 个（含整体审查后补的 11 个；本稿估约 40 个），合计 162 个。
12. 工作流说明 html 与发布页（§13 第 4 条）放到实施与整体审查完成之后单独更新，因为测试数、脚本数要以最终代码为准。

整体审查（2026-10-14，fable 模型新会话）后加严的 5 处：

13. 快道所有日期（原料 `seen_at`、锚词测量日、对象首次公开日、说法首次看到日、建站跟进日期）都须是日历上真实存在的 YYYY-MM-DD，`2026-11-31` 这类拒收；`validate_ledger.py` 对账本里已存的跟进日期兜底。
14. 补挂速判观察、观察中复查、结算复核时都核对速判的词属于本方向；改说法时也不能和别的方向重复。
15. 原料过期后再被来源取回会重新进池（保留原 id，记 `revived_at`）；速判否决与登记会把对应的待看原料自动标 used；淘汰过的词再被取回时报淘汰原因。
16. 观察中复查的建议按最新速判里第一条不过的项给否决门，AI 概览已答完给 `rejected:answered`，冲高回落给 `rejected:oneoff`，之后才看量。
17. 运行清单判断"标杆道已有 3 个待深核方向"时只数标杆道，快道的待处理方向不会让标杆道跳过发现阶段。

## 16. 实现后的口径调整

2026-10-14 用户追加："快道里面，不要只看美区的，要看英文区的。"随后逐条确认：

1. **英文区**：美国、英国、加拿大、澳大利亚、新西兰、爱尔兰 6 国（`QUICK_ASSUMPTIONS.countries`）；不含印度、菲律宾等英语使用大国。
2. **量级**：6 国各做一次 Trends 锚词换算（`geo` 设为该国），换算量相加；读不出的国家记 0。量级观察改为每国一行，合计与"换算量最大的国家"由脚本核对，趋势与冲高回落用该国的逐日曲线判断。
3. **锚词月量**：旧词库只有美国的量，美国以外的锚词月量一律用 Semrush 查；新鲜度按各国里最早的测量日算。快道因此每个方向通常要花几次 Semrush。
4. **门槛**：上线 90 天内英文区单月合计 ≥ 10,000 访问。
5. **收入**：美国按 AdSense $4/千访问，其他 5 国按 $2/千访问（未确认）；访问按各国搜索量的比例分。"单站就能到 $100"改为直接看基准月收入 ≥ $100，原来的"2.5 万访问"只在全是美国流量时成立。
6. **首页速判**：Q5、Q6 仍只看美国首页。
7. **发现**：热搜 RSS 与 Trends 飙升词看 6 国；自动补全默认美国，地区性对象用 `suggest_snapshot.py --gl gb|ca|au|nz|ie`，各国快照分开存，美国快照沿用原文件名。
8. 假设表由 `2026-10-13.q1` 升为 `2026-10-14.q2`。

2026-10-14 首次真实运行后用户拍板 Q1 口径：

9. **"首次公开"按第一次让大量普通用户用上的日期**：公开测试、抢先体验、正式发售、App 上架、开放注册中最早的一天；向所有购买或预购者开放的测试算，只限少数受邀者的内测不算；公布、预告、开放预约不算，公布日写进 `date_source` 备查。起因：WARDOGS 2026-02-05 公布、08-22 预购玩家封闭测试、09-10 抢先体验，Aniimo 2025 年 6 月公布、2026-09-16 上线，按公布日两款都超 90 天，按能用的日期都在 90 天内；而计算器、地图这类任务词要等大家玩上了才出现。第 5 节 Q1 判法里"Trends 可读时 90 天前应接近 0"随之不再适用：公布与预告期间的搜索量不作为"不新"的证据。代码只核天数（`ledger.register_quick`），不用改。

同日用户确认三项（依据：WARDOGS、Aniimo 首页上 7 个专做这款游戏的占位工具站，按域名注册或首张证书取最早的日期，都比开放游玩日早 6–230 天；可玩后第 28、34 天首页已被占满）：

10. **游戏类真新窗口改为开放游玩后 14 天**，其他对象仍 90 天：登记时 `object.type` 写 `game` 或 `other`，`register-quick` 按类型核天数；假设表升为 `2026-10-14.q3`（`new_days_game = 14`）。样本只有 2 款，14 天是推断，之后按实测校准。
11. **加"即将开玩"日历**：新脚本 `wiki_releases.py` 从 Wikipedia 发售表取未来 30 天上线的原创、抢先体验游戏（有独立词条、英文区能玩），按近 30 天浏览量取前 20；原料可带 `playable_at` 与 `stage`，开玩日在今天之后的不进待看、只进 `quick_pool.py upcoming`，看板列出建议在开玩当天到第 3 天跑快道；保留 7 天从开玩日起算。发售表不含公开测试，测试靠 Trends 飙升词补。实测不可用：SteamDB（403）、Steam 商店与 Gematsu（连不上）、SteamCharts 不收测试版、TwitchTracker 榜单禁止抓取。仍不做定时任务。
12. **Trends 飙升词每次运行都要取**：`trends_fetch.js` 加 `xinciTrendsRising`，最多 6 个种子词（`beta`、`playtest` 用游戏分类 `cat: 8`，再加 3–4 个任务词），两次执行间隔 ≥ 30 秒（实测间隔 6 秒连查第 3 次就 429），遇 429 停下并写"本次未取"。

2026-10-15 第二次运行后修了实测发现的问题：

13. **发售表与原料池的缺口**：`wiki_releases.py` 也收最近 14 天已上线的（`--recent-days`，默认等于 `new_days_game`），这正是游戏类 Q1 窗口；浏览量 429 后没查的候选仍以浏览量 null 输出，不丢；剥掉 `{{efn}}`、`<ref>` 脚注，平台格跨行时沿用上一行。`quick_pool.add` 同一批里同一词被第二个来源看到也记进 `also_seen`。`trends_volume.py` 接受空曲线（`values=[]`）按读不出记 0。`ledger.update` 允许快道只更正 `object.date_source`，名称、类型、首次公开日仍不可改。

2026-10-15 用户对三条裁定拍板：

14. **试玩版算"用上"**，哪怕只含开头部分（Order of the Sinking Star 6 月的新品节试玩版、FF Resonance 09-03 的试玩版都算），原来"只含开头的试玩版不算"的裁定作废。
15. **查不到开玩日期的对象也看首页**（如 Roblox 体验）：照原料池顺序占首页名额，日期尽量从首页结果读；读不到时 Q1 记 null。
16. **读得出的国家必须换算**：锚词在某国热度为 0 就换锚词，美国以外的锚词月量去 Semrush 查，不能放进 `skipped` 按 0 计；`skipped` 只用于没查成的国家。`trends_volume.py` 的提示不再建议"放进 skipped"。

未做、需另行拍板：上线前按预测判 go（现在 go 要求当前搜索量过线，最早只能在开放游玩后判，而占位站是提前建的）。
