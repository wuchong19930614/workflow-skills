# xinci 新词工作流

发现并验证英文 Google 搜索词,回答“这个词能不能撑起一个独立 SEO 站”:go 结论交付 md+html 建站决策书,no-go 不产出决策书、只在账本登记决定性理由；若本次补审产生了新的现场观察,证据文件仍照常留存。

默认单步模式由用户逐次驱动,skill 不按时间字段自我调度;用户显式启动 `xinci-run` 后,它才在本次预算内连续编排各阶段。仓库层面的事(数据区配置、symlink 接入、测试)见[仓库根 README](../README.md)。

## 它做什么

从有日期的变化与社区信号面提取搜索任务。官方变化先进入触发池，补齐搜索语言与商业预检后才进入候选漏斗；候选逐个过九道闸门，最后形成建站 go/no-go 结论。全流程留痕:触发池记原料、账本记状态、证据文件记现场观察、索引记淘汰方向。

## 两条赛道

| 赛道 | 定义 | 量级数据 | 可走的盈利线 |
| --- | --- | --- | --- |
| `new` 新词道 | 措辞太新以致 Semrush 查无 | 窗口期禁用 | 六线均审；广告固定 `N/A` |
| `mature` 成熟错价词道 | 有真实搜索量、SERP 被守得弱 | 从第一步就要求取 | 六线均审，广告可成立 |

两道共用一条限制:**KD、Authority Score、外链数等域名强度代理不得决定 G2/G3 的放行、否决或竞争强弱**;门结论只由 G2 完整结构阅读与 G3 条件化占位审计(经营信号、真工具、持续可见度,再按盈利线映射)判定。确认期可以实测竞品 footprint(流量、覆盖词量、增速)来回答“实际占了多少市场”,它只进入竞争评分与风险说明,不反向改写 G2/G3。

> `mature` 道的发现与前半程由 **[xinci-mature](xinci-mature/SKILL.md) 单步承接**(2026-08-29 新建):xinci-scan / xinci-track / xinci-run 在 `formation_confirmed` 之前仍只处理 `new` 道,mature 的选源、量级前筛、注册、窗口期复核与形成确认改由 xinci-mature 执行(`--lane mature`、`--by xinci-mature`),判据仍以[数据采集指南](xinci-core/数据采集指南.md)「广告线的选源方法」为准。**建这个 skill 是为了让方法能被验证,不是宣布方法已成立**——本道累计 0/4,此前两个月只跑出 4 个种子的直接原因就是没有执行载体,每次都要手工照着指南从头走。候选一旦合法进入 `formation_confirmed`,现有 xinci-qualify / xinci-decide 才开始承接 mature；xinci-run 也只从这个状态起自动推进 mature 存量。**唯一的前半程 skill 例外**:手工流程已把 mature 候选合法送到 `screened` 且窗口为 days 时,可显式调用 xinci-decide 做快道决策或到期处置；xinci-run 不会替用户自动接这条 mature 快道。**方法未经更多前瞻验证前,仍不把 mature 接入 xinci-run 的自动发现循环**:xinci-mature 是单步形态,每一次转移都要用户逐条确认,registrar 也硬校验它只碰 `lane=mature`。原来那条理由在这一点上不变——未验证的方法不该自动跑(出处见[闸门校准.md](xinci-core/闸门校准.md) 第 8.1 节;该节另记的「skill 全文未出现 lane」是当时状况,现各入口已显式写明 lane 边界,不再作为理由)。

## 六条盈利线(G6,任一条过即放行)

| 盈利线 | 收入依据 | 关键约束 |
| --- | --- | --- |
| subscription | 账户数 × 周期单价 − 获客/交付成本 | 要有持续重复任务 |
| lead_generation | 有效线索数 × 单线索价值/成交贡献 | 可由少量高价值需求成立 |
| affiliate | 可归因购买量 × 佣金 | 依赖有机流量与购买意图 |
| transaction | 办理/撮合次数 × 单次抽成 | 要有可重复交易事件 |
| paid_report | 报告/证明包份数 × 单价 | 一次性付费也可成立 |
| advertising | 簇内月量 × 可达 CTR ÷ 1000 × RPM | base case 至少 $200/月 |

六条都要给出判定结果；`new` 的广告线明确记 `N/A`,不伪造 0、也不强查不存在的量级。`repeat_paid_task` 只约束 subscription；`official_count_class` 只约束依赖该口径的算式；`self_serve_legal_effect` 才约束所有声称替代法律签字/认证的自助交付。只有所有适用线均否决，G6 才否决整候选。账本用 `g6_passed_lines` 记明实际通过线,并强制 `income_score ≥1`。G3 的占位否决只对依赖自然流量的 affiliate / advertising 生效；lead generation、transaction、paid report 不得套广告量级硬门。

## 候选生命周期

状态只存在于账本,**只能由 `registrar.py` 写入**。共 16 个状态,内部有 7 个归档/决策终局状态;终局不等于全部“再无出边”:`built` 保留一条人工发起的升级通路,`disqualified` / `no_site` 还可被更好措辞的候选取代(`→ superseded`)。

```
captured ──有效初筛结论满足出闸要求──→ screened ──登记 expiry──→ tracking ──形成达标──→ formation_confirmed
   │  也是扫描漏斗的排队位                              │                        │
   │                          │窗口以天计(快道)          │复查中闸门翻转           │ xinci-qualify
   ▼                          ▼                        ▼                        ▼
rejected              fast_grab_ready              rejected           qualified / disqualified
                              │                                              │ xinci-decide
                              ▼                                              ▼
                        built / expired              build_ready / pilot_ready / hold / no_site
```

“有效初筛结论满足出闸要求”指 G0/G1/G2/G4/G5=`pass`,G3=`pass` 或状态机兼容的 `veto_window_bet`;后者不是“全过”,只可按其专用快道出口推进。

归档/决策终局:`rejected` / `expired` / `superseded` / `withdrawn` / `built` / `disqualified` / `no_site`。终局的例外出边共两种:人工发起的 `built → tracking` 升级,以及 `disqualified` / `no_site` → `superseded`(被更好措辞的候选取代)。

**留痕分界**:还有下一步的、以及走完 G2/G3 深审的候选进**账本**;零成本秒弃与 G1 否决只追加一行**淘汰方向索引**。

## 九道闸门

执行顺序 **G0 → G4 → G5 → G6/G7 零成本预筛(含 G6 深审入口预检) → G1 → G2 → G3**:零成本推理批先行,开浏览器的放后面。G6/G7 在扫描期不产生正式结论;G6 入口第一问只判是否值得继续建立盈利线证据,答是后还要按四项结构硬门形成供窗口期 G3 使用的逐线暂定结论,正式结论仍在认定阶段。

| 闸门 | 判什么 | 性质 |
| --- | --- | --- |
| **G0** | 合法性与安全 | 硬否决,先于一切 |
| **G1** | Google 首屏是否已把任务做完(featured snippet / 原生计算器 / knowledge panel / AI Overview) | 硬否决;未注册方向不复活,已注册候选可受控重开 |
| **G2** | 完整首页结构阅读 | 结构判断 |
| **G3** | exact-task completion:有没有人已经真把这件事做完了 | 三档:`pass` / `veto` / `veto_window_bet` |
| **G4** | 任务能否完全在线完成 | 零成本 |
| **G5** | 陷阱类别检查(当前 14 类) | 按处置档执行:直接筛除型零成本,验证型当场跑 G3 验证 |
| **G6** | 商业闭环 + 六条盈利线算式 | 认定门,含逐线深审入口预检 |
| **G7** | 耐久性 | 认定门 |
| **G8** | 簇广度 | 认定门 |

G6 的**深审入口预检**是最省钱的一道，但必须逐线解释：不具备逐对象重复只否决 subscription；缺官方主体计数只否决依赖该口径的算式；自助结果依法必须由第三方签字才有效，才可能构成全局交付否决。任何其他盈利线仍可建立时都继续，不得把单项入口条件升级为整候选否决。

## 契约文件:判断标准的唯一来源

这些文件是规范性来源。代码与 skill 可以为执行方便摘述判据,但摘述不是第二份契约;一旦措辞冲突,以这里的契约为准并同步修正摘述。

| 文件 | 管什么 |
| --- | --- |
| [闸门契约.md](xinci-core/闸门契约.md) | G0–G8 的定义、执行顺序、六条盈利线算式、时间光谱 |
| [生命周期契约.md](xinci-core/生命周期契约.md) | 状态机、每条边的证据要求、留痕分界、连续运行模式、开工第一步 |
| [陷阱类别.md](xinci-core/陷阱类别.md) | 14 类已知陷阱与各自处置档(验证型 / 直接筛除型) |
| [数据采集指南.md](xinci-core/数据采集指南.md) | 真浏览器原则、来源表、Semrush 纪律(按赛道分)、正向选择器、广告线选源方法 |
| [评分契约.md](xinci-core/评分契约.md) | 认定阶段 100 分制六维权重与红队扣分(80 分线) |
| [闸门校准.md](xinci-core/闸门校准.md) | 闸门判据的实测记录与修订依据 |

[数据结构/](xinci-core/数据结构/) 下是 9 份 JSON Schema:候选、观察、去重裁决、运行清单、运行会话、事务、触发事件、浏览器预检、阶段检查点。

## 脚本

| 脚本 | 作用 |
| --- | --- |
| `registrar.py` | 账本的**唯一**状态转移入口,逐项校验证据,原子替换 |
| `screen_index.py` | 淘汰方向索引:批量去重、带日期追加、追加式历史日期修订 |
| `trigger_pool.py` | 官方变化原料的 add/approve/discard 事件日志 |
| `browser_preflight.py` / `run_policy.py` | 记录浏览器事实并计算 full/trigger-only/debt-only/paused 策略 |
| `stage_checkpoint.py` | 轮内批处理检查点；阻止 pending 项被 record-round 掩盖 |
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
