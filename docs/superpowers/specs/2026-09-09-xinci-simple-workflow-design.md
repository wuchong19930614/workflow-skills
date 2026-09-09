# xinci-simple-workflow 设计

- 状态：设计稿（已与用户逐节评审通过，未落地实现）
- 日期：2026-09-09
- 目标：从已有真实搜索量的英文词里，找出 SERP 守得弱、AI Overview 吃不掉、base case 月收入 ≥ $500 的主题簇，产出一份机会报告，尽快给出可建 Google SEO 站的词
- 前身与关系：xinci 新词工作流（`xinci-workflow/`）原样冻结，零运行时依赖；Codex 侧 `keyword-tool-mining` 的六道门只作逻辑参考

## 目录

- [1. 为什么要有这套工作流](#1-为什么要有这套工作流)
- [2. 定位与边界](#2-定位与边界)
  - [2.1 一句话定位](#21-一句话定位)
  - [2.2 候选单位是主题簇](#22-候选单位是主题簇)
  - [2.3 范围与四条零成本排除](#23-范围与四条零成本排除)
  - [2.4 与 xinci 的关系](#24-与-xinci-的关系)
  - [2.5 明确不做的事](#25-明确不做的事)
- [3. 漏斗与闸门](#3-漏斗与闸门)
  - [3.1 第一层：发现](#31-第一层发现)
  - [3.2 第二层：代理排序](#32-第二层代理排序)
  - [3.3 第三层：现场核验](#33-第三层现场核验)
  - [3.4 第四层：收入模型](#34-第四层收入模型)
- [4. 数据模型与状态机](#4-数据模型与状态机)
  - [4.1 状态机](#41-状态机)
  - [4.2 候选记录](#42-候选记录)
  - [4.3 观察文件](#43-观察文件)
  - [4.4 数据区](#44-数据区)
- [5. 数据源与两条浏览器通道](#5-数据源与两条浏览器通道)
  - [5.1 通道分工](#51-通道分工)
  - [5.2 Semrush 额度纪律](#52-semrush-额度纪律)
  - [5.3 首页 DR 的来源](#53-首页-dr-的来源)
  - [5.4 浏览器预检](#54-浏览器预检)
- [6. 收入模型](#6-收入模型)
  - [6.1 形态判定](#61-形态判定)
  - [6.2 假设表](#62-假设表)
  - [6.3 三条统一折减](#63-三条统一折减)
  - [6.4 输出与门槛](#64-输出与门槛)
  - [6.5 门槛隐含的量级](#65-门槛隐含的量级)
- [7. 机会报告](#7-机会报告)
- [8. 单元划分与脚本](#8-单元划分与脚本)
  - [8.1 目录结构](#81-目录结构)
  - [8.2 三个 skill 的职责](#82-三个-skill-的职责)
  - [8.3 脚本清单](#83-脚本清单)
  - [8.4 单步驱动](#84-单步驱动)
- [9. 错误处理](#9-错误处理)
- [10. 测试](#10-测试)
- [11. 验收标准](#11-验收标准)
- [12. 设计决策记录](#12-设计决策记录)

## 1. 为什么要有这套工作流

2026-09-09 对 xinci 新词工作流 20 天运行的结构诊断得出：它在优化的目标是"能在建站前完成商业尽调的 B2B 合规 SaaS 点子"，不是"能建 Google SEO 站的词"。44 次运行、204 轮、约 187 小时机器时间，产出 0 个 qualified；唯一一次快道 go 在 7 天窗口内无人建站而过期。它的 new 道刻意避开搜索量（数据采集指南 §「自动补全」原话），广告线固定 N/A，认定门要求证明"可触达付费子集 × 单价 − CAC > 0"。

用户拍板：切到流量型选词，新建独立精简工作流，xinci 冻结。

## 2. 定位与边界

### 2.1 一句话定位

`xinci-simple-workflow` 从已有真实搜索量的英文词里，找出 SERP 守得弱、AI Overview 吃不掉、base case 月收入 ≥ $500 的主题簇，产出一份机会报告。建站方式不预设，报告就是交付物。

### 2.2 候选单位是主题簇

候选是一个主关键词加一组支撑词，不是单词。一个站要靶一簇；量级、竞争、收入都按簇算。

### 2.3 范围与四条零成本排除

- 只看英文 + Google 美区（`gl=us&hl=en&pws=0`）。
- 零成本排除四类，scan 时判一次，verify 时复核一次：
  1. YMYL：题目影响健康、金融、法律、安全。按类别定义，不按例子清单。
  2. 需要亲身体验或一手数据才能写好：产品实测、旅行体验、个人测评。
  3. 纯品牌词与导航词：`X login`、`X customer service`、`X near me`。
  4. 新闻热点：几周内会消失的事件词。

### 2.4 与 xinci 的关系

- 零运行时依赖：不 import xinci 脚本，不引用 xinci 契约文件。
- 数据区独立在 `keywords-macdownds/数据/xinci-simple/`，与 `数据/新词工作流/` 零交集。
- 只复用两样东西的思路：数据区配置方式（`data_root.py` 模式）、G1 SERP 读取规程（复制精简版进 `数据采集.md`，不引用原文件）。
- xinci 保持现状，不改、不删。

### 2.5 明确不做的事

不注册域名、不建站、不写内容；不设形成期、不做 80 分评分、不做 B2B 付费者尽调；不算 CAC、不算内容成本、不预测排名时间。

## 3. 漏斗与闸门

四层，便宜的在前。

### 3.1 第一层：发现

由 `xinci-simple-scan` 执行，数据源为 Semrush 加免费源。三条来源轮换：

- **(a) Keyword Magic 词根轮换**：工具词根（`keyword-tool-mining` 的 51 个：Generator / Converter / Calculator / Checker / …）加查表类词根（specs / chart / size / dimensions / compatibility / requirements / schedule / code / list 等）。一次一个词根，不合并。
- **(b) 小站反推**：在 Semrush 找 Authority Score 低、自然流量高的小站，拉其 top keywords，找同类空位。
- **(c) 论坛反复问的问题**：Reddit / 专业论坛里反复被问且靠人肉回答的问题，回 Semrush 验量。

Keyword Magic 固定过滤：数据库 US、KD ≤ 49、Intent 排除 Navigational、排除成人词。预览优先（≤ 50 行），CSV 只在能改变决策时导出。

**准入（零成本）**：簇量（phrase-match 合计月量）≥ 50,000 或主词月量 ≥ 5,000；四条范围排除全部不命中。达标即 `ledger.py register` 为 `found`。阈值是可调默认值，写在 `选词契约.md`。

### 3.2 第二层：代理排序

`rank.py` 对全部 `found` 候选算排序分，决定谁先进现场核验。输入五项：KD、簇量、首页 DR < 30 的域名数、首页 UGC/论坛占位数、首页内容年龄中位数。每项在当前 `found` 池内归一化到 0–1（KD 反向，其余正向），等权平均得 `rank_score`；缺失项取 0.5。输出排序，不输出否决。**代理不能单独否决任何候选**。权重等权是初始口径，首批 verify 结果出来后可按"排序分与实际通过率的相关性"调整。

### 3.3 第三层：现场核验

由 `xinci-simple-verify` 执行，内置浏览器面板、美区、桌面、未登录。取排序前 N（默认 5）。

- **G1 Google 直答（硬否决）**：AI Overview、精选摘要、原生小组件（计算器、换算、天气、日期）把任务在首屏做完 → `rejected`。AI Overview 存在但任务未做完 → 通过，收入模型 CTR × 0.6。判"做完"看用户还要不要点任何结果。
- **G2 首页结构**：读满第一页，继续第二页到明显质量断层。维基级/大媒体霸榜、视频霸屏（非视频任务）、品牌首页而非内页霸榜 → `rejected`。相当比例是内页、小站、论坛、明显老化内容 → 通过。**不得只看前三条**。
- **G3 可打败性**：首页 10 条中，"完整完成任务 且 DR ≥ 50 且 内容新鲜格式对"三项同时满足的结果数：≥ 3 → `rejected`；1–2 → 通过，收入模型 CTR × 0.7，报告记风险；0 → 空位。按结果"做什么"分类，不按"是谁"。三项定义：**完整完成任务** = 用户看完这条不必再点别处；**新鲜** = 页面可见日期在 24 个月内，或无日期但内容与当前事实一致；**格式对** = 结果形态与查询要的形态一致（要表给表、要工具给工具、要步骤给步骤）。

本节的"首页"指 Google 第一页的前 10 条自然结果，不含广告、People also ask、视频轮播、购物模块；"DR" 指 Semrush Authority Score。
- **季节性**：Google Trends 12 个月、US。量集中在 ≤ 3 个月且无意做季节站 → `parked`。
- **范围排除复核**：四条再看一遍，命中 → `rejected`。

每个候选写一份 `证据/<slug>/<日期>-verify.json`，只记看到的。

### 3.4 第四层：收入模型

`revenue_model.py` 按第 6 节算三情景。`base ≥ $500` → `transition found→verified` 并 `build_report.py`；否则 `rejected`，reason 写实际 base 数与差值。

## 4. 数据模型与状态机

### 4.1 状态机

```
found ──现场核验 + 收入模型通过──→ verified
  ├──任一硬门否决 / 收入不足──→ rejected
  └──季节性 / 证据不足──→ parked ──→ verified | rejected
```

合法转移表（`ledger.py` 强制）：

```python
LEGAL = {
    ("found", "verified"), ("found", "rejected"), ("found", "parked"),
    ("parked", "verified"), ("parked", "rejected"),
}
TERMINAL = {"verified", "rejected"}
```

`verified` 是终点，报告是交付物。没有 tracking、形成期、qualified、decide。

### 4.2 候选记录

账本 `账本/候选账本.json` 结构 `{"schema_version": 1, "candidates": {slug: record}}`，脚本原子写。记录字段：

```json
{
  "slug": "heic-to-jpg-converter",            // 唯一标识，小写连字符
  "primary_keyword": "heic to jpg converter", // 主关键词，精确措辞
  "cluster": {
    "total_volume": 182000,                    // phrase-match 合计月量，来自 Semrush 预览
    "keywords": [                              // 支撑词 top 20，scan 时记
      {"term": "heic to jpg", "volume": 90500, "kd": 38}
    ]
  },
  "seed": {
    "type": "root",                            // root | small_site | forum
    "value": "Converter",                      // 词根名 / 小站域名 / 论坛帖 URL
    "queried_at": "2026-09-10T03:12:00+00:00"  // Semrush 查询时间
  },
  "state": "found",                            // found | parked | verified | rejected
  "proxy": {
    "kd": 38,                                  // 主词 KD
    "low_dr_count": 4,                         // 首页 DR<30 域名数，来自 Semrush SERP overview
    "ugc_count": 2,                            // 首页 reddit/quora/论坛条数
    "content_age_median_days": 540,            // 首页内容年龄中位数，缺则 null
    "rank_score": 0.71                         // rank.py 输出，0–1
  },
  "form": "tool",                              // verify 时定：info | lookup | tool | commercial | mixed；scan 时 null
  "revenue": {                                 // verify 时算；scan 时 null
    "downside": 210, "base": 640, "upside": 1300,
    "volume_needed_for_500": 142000,           // 反推簇量
    "assumptions_version": "2026-09-09"        // 假设表版本
  },
  "evidence_refs": ["证据/heic-to-jpg-converter/2026-09-10-scan.json"],
  "history": [                                 // 只追加
    {"at": "2026-09-10T03:15:00+00:00", "from": null, "to": "found", "by": "xinci-simple-scan", "reason": "..."}
  ]
}
```

每个字段都要回答得出"哪个决策用到它"。

### 4.3 观察文件

`证据/<slug>/<YYYY-MM-DD>-<scan|verify>.json`，只记看到了什么，不写裁决。

```json
{
  "slug": "heic-to-jpg-converter",
  "observed_at": "2026-09-10T05:40:00+00:00",
  "stage": "verify",                           // scan | verify
  "browser_preflight": {                       // verify 必填，scan 可省
    "controllable": true, "desktop": true, "region": "us", "logged_out": true,
    "evidence": "Sign in 可见；#gb 无账号元素；页脚 Unknown location"
  },
  "query_url": "https://www.google.com/search?q=heic+to+jpg+converter&gl=us&hl=en&pws=0",
  "ai_overview": {"present": true, "completes_task": false, "excerpt": "..."},
  "serp_top10": [                              // G2/G3 逐条
    {"pos": 1, "domain": "cloudconvert.com", "dr": 78, "type": "tool", "completes_task": true, "dated": "2026-06"}
  ],
  "page2_note": "第二页起为博客与问答，无完整工具",
  "trends_12m": "全年平稳，无月份超均值 2 倍",
  "scope_recheck": {"ymyl": false, "firsthand": false, "brand_nav": false, "news": false},
  "source_urls": ["..."],                      // 本次实际打开的 URL
  "points": ["..."]                            // 要点，不转录
}
```

### 4.4 数据区

```
keywords-macdownds/数据/xinci-simple/
├── 账本/候选账本.json
├── 证据/<slug>/<日期>-<scan|verify>.json
├── 报告/<slug>.md
└── 运行/<日期>-<skill>[-HHMM].json
```

运行清单字段：

```json
{
  "date": "2026-09-10",
  "skill": "xinci-simple-scan",             // xinci-simple-scan | xinci-simple-verify
  "sources_opened": ["https://..."],         // 本次实际打开的 URL，Semrush 与 Google 都记
  "candidates_touched": ["heic-to-jpg-converter"],
  "billable_calls": 3,                       // Semrush 计费查询数；DataForSEO 接入后另加 dataforseo_calls
  "notes": ["..."]                           // 事实备注，不写过程流水
}
```

同日同 skill 再次运行须传 `--suffix HHMM`，不覆盖。

用 `.xinci-simple-data-root` 配置（仓库根，不入库），解析顺序 `--data-root` > 环境变量 `XINCI_SIMPLE_DATA_ROOT` > 配置文件 > 拒绝执行并提示先问用户。

## 5. 数据源与两条浏览器通道

### 5.1 通道分工

| 用途 | 通道 | 原因 |
|---|---|---|
| Semrush Keyword Magic / Domain Overview / Keyword Overview（含 SERP overview） | Claude in Chrome（用户真实 Chrome，共享账号已登录） | 需要登录态 |
| Google SERP（G1/G2/G3）、`allintitle:`、Google Trends | 内置浏览器面板（美区、桌面、未登录） | 必须未登录，否则个性化污染 |
| DataForSEO | 可选，REST API 走 curl，凭据放环境变量 `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | MCP 未安装；首版不依赖，Semrush + 免费源起步；接上后用于批量拉 shortlist 的 SERP 域名 DR |

### 5.2 Semrush 额度纪律

- 每次计费查询必须能改变一个决策；为流程而跑的查询禁止。
- 预览优先，一次看 ≤ 50 行；CSV 导出只在预览已证明簇值得深看时。
- 每轮的 Semrush 调用数如实记入运行清单 `billable_calls`。

### 5.3 首页 DR 的来源

Semrush Keyword Overview 页底部的 SERP overview 面板给前 10 条的 Authority Score，一次查询拿全。这是 `proxy.low_dr_count` 与 G3 可打败性共用的数据，不逐域名查。

### 5.4 浏览器预检

verify 开始前在内置面板打开一次美区查询，现场核对四项：可控（能读页面文本）、桌面（`#rcnt`/`#center_col` 在场或桌面布局证据）、美区（URL 三参齐备）、未登录（Sign in 可见、无账号元素）。结果写进每份 verify 观察的 `browser_preflight`，不做 SHA 绑定与 15 分钟时效那套。任一不合规 → 不写 G1–G3 结论。

## 6. 收入模型

### 6.1 形态判定

verify 时按 SERP 结果类型与查询意图判一个 `form`：

- `info`：答案是解释、清单、步骤
- `lookup`：答案是一个数字或判断，需逐对象查表
- `tool`：任务要算、转、生成，首页有或应有工具
- `commercial`：带购买意图（best / review / vs / for sale）
- `mixed`：两种以上并存

### 6.2 假设表

版本化默认值，`assumptions_version` 写进候选记录与报告，实测后可改：

| 形态 | 收入路径 | base 公式 |
|---|---|---|
| `info` / `lookup` | 展示广告 | 会话 = 簇量 × CTR 7%；月收入 = 会话 ÷ 1000 × RPM；RPM 按垂类：科技/通用 $10、家居/DIY/汽车 $18、爱好/宠物 $12 |
| `tool` | 展示广告 | 同上，CTR 取 10% |
| `commercial` | 联盟佣金 | 点击 = 簇量 × CTR 7%；月收入 = 点击 × 外链点击率 15% × 转化 3% × 佣金 $30 |
| `mixed` | 两条各算 | base 取保守那条 |

downside = base 公式中 CTR × 0.5，其余不变；upside = CTR × 1.5，其余不变。只动 CTR 一个变量，三情景之间可直接比较。

### 6.3 三条统一折减

- AI Overview 存在但未做完 → CTR × 0.6
- 首页有 1–2 个"完整 + DR ≥ 50 + 新鲜"结果 → CTR × 0.7
- 季节性判 `parked` 的不算收入

### 6.4 输出与门槛

`revenue_model.py` 输出 `downside / base / upside` 与 `volume_needed_for_500`（在当前假设与折减下，base 到 $500 需要的簇量）。`base ≥ 500` → `verified`；否则 `rejected`，reason 写实际 base 与差值。

### 6.5 门槛隐含的量级

$500/月在展示广告 RPM $10、CTR 7% 下需要簇量约 714,000/月；RPM $18 约 397,000；`tool` 形态 RPM $10、CTR 10% 约 500,000；`commercial` 形态约 53,000。这个门会天然把候选推向大簇信息站或商业意图簇。首批报告出来后按实际调整门槛与假设表，不在设计阶段预调。

## 7. 机会报告

`报告/<slug>.md`，只出 md，`build_report.py` 从账本与观察文件生成，不手写。固定 9 节：

1. **主关键词与簇**：主词、簇量、支撑词 top 20（词 / 月量 / KD）、来源（词根 / 小站 / 论坛）
2. **形态与意图**：`form` 与判断依据
3. **量级证据**：Semrush 预览要点、查询日期、过滤条件
4. **竞争现场**：首页 10 条逐条——域名 / DR / 类型 / 是否完成任务 / 内容日期；第二页要点
5. **AI Overview 状态**：无 / 有但未完成（原文要点）
6. **季节性**：Trends 12 月一句话
7. **收入三情景**：假设逐项、三个数、反推簇量、`assumptions_version`
8. **范围排除复核**：四条逐条
9. **建议 play 与风险**：`single_domain`（簇量 < 150,000，一站一簇）或 `cluster_expansion`（大簇分阶段）；前三风险；下一步是人的动作

不含页面地图、内容大纲、域名建议。

## 8. 单元划分与脚本

### 8.1 目录结构

```
xinci-simple-workflow/
├── README.md
├── xinci-simple-core/
│   ├── 选词契约.md              闸门、季节性、排除、状态机、证据要求、假设表；唯一判据来源；目标 ≤ 300 行
│   ├── 数据采集.md              Semrush 纪律、SERP 读取规程（精简复制）、两条通道、预检四项
│   ├── 数据结构/
│   │   ├── candidate.schema.json
│   │   └── observation.schema.json
│   └── scripts/
│       ├── data_root.py
│       ├── init_workspace.py
│       ├── ledger.py
│       ├── rank.py
│       ├── revenue_model.py
│       ├── build_report.py
│       ├── report_status.py
│       ├── validate_ledger.py
│       └── tests/
├── xinci-simple-scan/SKILL.md
├── xinci-simple-verify/SKILL.md
└── xinci-simple-status/SKILL.md
```

symlink 接入：`~/.claude/skills/xinci-simple-<name>` 与 `~/.codex/skills/xinci-simple-<name>` → 仓库对应目录；core 不是 skill。

### 8.2 三个 skill 的职责

- **xinci-simple-scan**：按来源轮换取词 → 零成本排除 → 准入 → `ledger.py register`（`found`）→ `rank.py` → 写运行清单。一次调用目标 20–50 个 `found`。可指定来源类型与词根。
- **xinci-simple-verify**：取排序前 N（默认 5，可指定 slug）→ 预检 → G1/G2/G3/季节性/排除复核 → 写 verify 观察 → `revenue_model.py` → `ledger.py transition` → 通过的 `build_report.py` → 写运行清单。
- **xinci-simple-status**：只读看板：各状态计数、`found` 按排序分列表、`parked` 停留天数、`verified` 报告路径。

SKILL.md 结构沿 xinci：frontmatter（`name` + 中文 description 附英文触发词）→ 一句话定位 → 行动前必读（core 文件相对路径）→ 步骤 → 硬规则 → 命令模板。判据不写在 SKILL.md，只指向 `选词契约.md`。

### 8.3 脚本清单

Python 3 标准库，零第三方依赖。

| 脚本 | 职责 | 接口 |
|---|---|---|
| `data_root.py` | 数据区解析 | `resolve_or_exit(explicit)` |
| `init_workspace.py` | 建四目录与空账本，幂等 | `--data-root` |
| `ledger.py` | 账本读写 | `register --slug --primary-keyword --cluster-json --seed-json --proxy-json --evidence --by --reason`；`transition --slug --to --evidence --by --reason [--form --revenue-json]`；`list [--state]` |
| `rank.py` | 代理排序 | `rank(record) -> float`；CLI 读账本输出排序表并回写 `proxy.rank_score` |
| `revenue_model.py` | 三情景 | `model(form, cluster_volume, niche, aio_present, strong_complete_count) -> dict`；CLI |
| `build_report.py` | 生成报告 | `--slug`，读账本与最新 verify 观察，写 `报告/<slug>.md` |
| `report_status.py` | 看板 | `[--json]` |
| `validate_ledger.py` | 不变式校验 | 状态在词汇表、evidence 存在、history 末项 == state、verified 有报告文件、孤儿证据目录告警 |

### 8.4 单步驱动

用户说"scan"就扫一批，说"verify"就核前 N。不做 run 控制器、不做预算轮次、不做 SHA 绑定。以后需要连续跑再加薄驱动器。

## 9. 错误处理

- 浏览器预检四项任一不合规 → verify 不写 G1–G3 结论，只在观察 `points` 记原因，候选留 `found`。
- Semrush 登录失效、验证码、额度提示 → 停下如实报告，不绕、不猜数。
- `ledger.py`：非法转移、证据文件不存在、`reason` 为空、`verified` 缺 `form`/`revenue` → 拒收并返回非零。
- `revenue_model.py`：`form` 不在词汇表、簇量缺失 → 报错不出数。
- `build_report.py`：缺 verify 观察或账本字段缺 → 报错，不生成半份报告。
- `parked` 停留超 90 天 → `report_status.py` 提醒，不自动转移。

## 10. 测试

unittest，`python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests`。

- `test_ledger`：4 态合法表；非法转移拒收；证据缺失拒收；`reason` 空拒收；`verified` 缺 `form`/`revenue` 拒收；history 只追加；原子写（写入中断不留半文件）。
- `test_revenue_model`：四形态各一例；两条折减单独与叠加；$500 边界（499 拒 / 500 过）；`volume_needed_for_500` 反推与正算一致；非法 `form` 报错。
- `test_rank`：五项输入的单调性（KD 低分高、簇量高分高、低 DR 多分高、UGC 多分高、年龄大分高）；缺字段不崩、取中性值。
- `test_build_report`：9 节标题齐全；报告数值与输入一致；缺观察报错。
- `test_validate_ledger`：真实空数据区零错误；构造坏账本能捕获每类不变式。

## 11. 验收标准

1. 首批 scan 注册 ≥ 20 个 `found`，每个有 scan 观察与 Semrush 预览要点。
2. verify 前 5 个各有完整 verify 观察，且要么有报告、要么 `rejected` 的 reason 写明门与数字。
3. 两条浏览器通道各实际使用过一次，运行清单可查。
4. Semrush 计费调用数如实记入运行清单。
5. 全部单元测试通过；`validate_ledger.py` 对真实数据区零错误。
6. `~/.claude/skills/` 与 `~/.codex/skills/` 两处 symlink 解析到同一 SKILL.md。

## 12. 设计决策记录

- **新建而非改造 xinci**：xinci 的状态机（7 天形成期、80 分认定）对成熟词大半不适用，1,583 行的 registrar 已出过"同一规则两套实现"的 bug；改造成本不低于新建且更易前后矛盾。
- **不复活 Codex 侧 keyword-mature-strong-80**：它带 $1,000/月 + 80 分线 + 预算预留机制，与 xinci 一样重，且从未跑出过数据。只借 `keyword-tool-mining` 的六道门骨架与 51 个词根。
- **代理指标可排序不可否决**：用户定的口径。三组"KD 低但实测竞争高"的背离仍成立，所以最终以 SERP 现场阅读定；但让代理决定"看不看"能把浏览器时间花在最值得的候选上。
- **G3 从"exact-task 完成度"改为"可打败性"**：信息站竞争是常态，"≥ 2 个完整答案即否决"会杀掉几乎所有信息词。改问"完整 + DR ≥ 50 + 新鲜"三项同时满足的有几个。
- **$500/月 门槛由用户定**：设计只揭示它隐含的量级，不预调。
- **报告不含页面地图**：建站方式未定，先不做。
- **单步驱动**：xinci-run 的控制器复杂度是它自耗的一部分；先手动，够快再说。
