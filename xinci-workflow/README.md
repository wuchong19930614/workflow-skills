# xinci 新词工作流

发现并验证英文 Google 搜索词,产出"这个词能不能撑起一个独立 SEO 站"的建站决策书。

由用户人工驱动,skill 不自我调度。仓库层面的事(数据区配置、symlink 接入、测试)见[仓库根 README](../README.md)。

## 它做什么

从有日期的变化(法规、平台、厂商发布)与社区信号面提取搜索任务,逐个过九道闸门,给通过的候选做认定评分,最后出建站 go/no-go 决策书。全流程留痕:账本记状态、证据文件记现场观察、索引记淘汰方向。

## 两条赛道

| 赛道 | 定义 | 量级数据 | 可走的盈利线 |
| --- | --- | --- | --- |
| `new` 新词道 | 措辞太新以致 Semrush 查无 | 窗口期禁用 | 只能走订阅线 |
| `mature` 成熟错价词道 | 有真实搜索量、SERP 被守得弱 | 从第一步就要求取 | 两条都可能 |

两道共用一条限制:**KD 与域名指标不得用于判断竞争强弱**,竞争强弱只由 G2 完整结构阅读与 G3 三问判定。

> `mature` 道目前只有契约与 schema 支持,**尚无 skill 承接**:xinci-scan / xinci-run 只跑 `new` 道,mature 道按[数据采集指南](xinci-core/数据采集指南.md)「广告线的选源方法」手工单步执行(`--lane mature`、`--by user`)。方法未经前瞻验证前不改 skill,理由见[闸门校准.md](xinci-core/闸门校准.md) 第 8.1 节。

## 两条盈利线(G6,任一条过即放行)

| | 收入算式 | 卡在哪 |
| --- | --- | --- |
| 订阅线 | 受约束付费者数 × 可行单价 − 获客成本 | 付费者价值 |
| 广告线 | 簇内月量 × 可达位次 CTR ÷ 1000 × niche RPM | 量级 |

两条都要给出判定结果,但按赛道处理:`new` 的广告线明确记 `N/A`,不伪造 0、也不强查不存在的量级；`mature` 两条都判 pass/veto。订阅线以结构闭环为硬门、金额进入评分；广告线以 base case 达 $200/月为硬门。账本用 `g6_passed_lines` 记明靠哪条过,并强制 `income_score ≥1`——G3 的占位否决只对广告线单独成立的模式生效。窗口期尚未产生正式 G6 结论时,先形成**仅供本次 G3 使用的暂定盈利线**,不得把它写成 G6=pass；确认期再以正式 G6 结论重算。

## 候选生命周期

状态只存在于账本,**只能由 `registrar.py` 写入**。共 16 个状态,内部有 7 个归档/决策终局状态;其中 `built` 保留一条人工发起的升级通路,所以不是通常意义上的“再无出边”。

```
captured ──G0–G5 全过──→ screened ──登记 expiry──→ tracking ──形成达标──→ formation_confirmed
   │  也是扫描漏斗的排队位                              │                        │
   │                          │窗口以天计(快道)          │复查中闸门翻转           │ xinci-qualify
   ▼                          ▼                        ▼                        ▼
rejected              fast_grab_ready              rejected           qualified / disqualified
                              │                                              │ xinci-decide
                              ▼                                              ▼
                        built / expired              build_ready / pilot_ready / hold / no_site
```

归档/决策终局:`rejected` / `expired` / `superseded` / `withdrawn` / `built` / `disqualified` / `no_site`。`built` 的唯一例外出边是人工发起的 `built → tracking` 升级。

**留痕分界**:还有下一步的、以及走完 G2/G3 深审的候选进**账本**;零成本秒弃与 G1 否决只追加一行**淘汰方向索引**。

## 九道闸门

执行顺序 **G0 → G4 → G5 → G6/G7 零成本预筛(含 G6 深审入口预检) → G1 → G2 → G3**:零成本推理批先行,开浏览器的放后面。G6/G7 在扫描期不产生正式结论;G6 预检只额外形成供窗口期 G3 使用的暂定盈利线,正式结论仍在认定阶段。

| 闸门 | 判什么 | 性质 |
| --- | --- | --- |
| **G0** | 合法性与安全 | 硬否决,先于一切 |
| **G1** | Google 首屏是否已把任务做完(featured snippet / 原生计算器 / knowledge panel / AI Overview) | 硬否决;未注册方向不复活,已注册候选可受控重开 |
| **G2** | 完整首页结构阅读 | 结构判断 |
| **G3** | exact-task completion:有没有人已经真把这件事做完了 | 三档:`pass` / `veto` / `veto_window_bet` |
| **G4** | 任务能否完全在线完成 | 零成本 |
| **G5** | 陷阱类别检查(9 类) | 按处置档执行:直接筛除型零成本,验证型当场跑 G3 验证 |
| **G6** | 商业闭环 + 两条盈利线算式 | 认定门,含强制的深审入口预检 |
| **G7** | 耐久性 | 认定门 |
| **G8** | 簇广度 | 认定门 |

G6 的**深审入口预检**是最省钱的一道:开审前先问"这个任务是否要求有预算的付费者逐个对象重复完成?"答否即弃,不读任何 SERP。

## 契约文件:判断标准的唯一来源

这些文件是规范性来源。代码与 skill 可以为执行方便摘述判据,但摘述不是第二份契约;一旦措辞冲突,以这里的契约为准并同步修正摘述。

| 文件 | 管什么 |
| --- | --- |
| [闸门契约.md](xinci-core/闸门契约.md) | G0–G8 的定义、执行顺序、两条盈利线算式、时间光谱 |
| [生命周期契约.md](xinci-core/生命周期契约.md) | 状态机、每条边的证据要求、留痕分界、连续运行模式、开工第一步 |
| [陷阱类别.md](xinci-core/陷阱类别.md) | 9 类已知陷阱与各自处置档(验证型 / 直接筛除型) |
| [数据采集指南.md](xinci-core/数据采集指南.md) | 真浏览器原则、来源表、Semrush 纪律(按赛道分)、正向选择器、广告线选源方法 |
| [评分契约.md](xinci-core/评分契约.md) | 认定阶段 100 分制六维权重与红队扣分(80 分线) |
| [闸门校准.md](xinci-core/闸门校准.md) | 闸门判据的实测记录与修订依据 |

[数据结构/](xinci-core/数据结构/) 下是 6 份 JSON Schema:候选、观察、去重裁决、运行清单、运行会话、事务。

## 脚本

| 脚本 | 作用 |
| --- | --- |
| `registrar.py` | 账本的**唯一**状态转移入口,逐项校验证据,原子替换 |
| `screen_index.py` | 淘汰方向索引:批量去重查询与追加。**勿手工编辑,勿整份读进上下文** |
| `dedup_decisions.py` | 疑似重复方向的 same/distinct 裁决登记 |
| `run_controller.py` | xinci-run 的可恢复运行会话控制器 |
| `run_state.py` / `run_manifest.py` | 运行会话与运行清单的共享契约与原子写入 |
| `transaction_journal.py` | 跨文件写入的前滚事务日志 |
| `validate_ledger.py` | 账本不变式 + 运行清单格式校验,有错非零退出 |
| `report_status.py` | 只读状态汇报,不推荐动作、不调度 |
| `data_root.py` | 数据区定位的唯一解析入口,未配置即拒绝执行 |
| `init_workspace.py` | 创建数据区结构与空账本(幂等),并落盘数据区选择 |
| `build_decision_html.py` | 决策书 md → html 单向生成 |
| `term_normalize.py` / `chinese_labels.py` | 措辞归一化规则 / 中文展示词汇 |

改完任何东西都跑一遍 `validate_ledger.py`:它同时捕获绕过 registrar 的手工编辑,以及全靠手写的运行清单的字段漂移。

## 怎么开始

数据区首次配置见[仓库根 README](../README.md#第一次使用先定数据区)。配好之后:

| 我想 | 用 |
| --- | --- |
| 一口气跑到出结果 | [xinci-run](xinci-run/SKILL.md)(暗号 `xinci_run`) |
| 看账本现在什么情况 | [xinci-status](xinci-status/SKILL.md) |
| 扫一轮新方向 | [xinci-scan](xinci-scan/SKILL.md) |
| 复查追踪清单 | [xinci-track](xinci-track/SKILL.md) |
| 给候选做认定评分 | [xinci-qualify](xinci-qualify/SKILL.md) |
| 出建站 go/no-go 决策 | [xinci-decide](xinci-decide/SKILL.md) |

每个 skill 的第 0 步都是确认数据区:脚本不猜数据区在哪,没配置过就退出码 2 并要求先问用户。
