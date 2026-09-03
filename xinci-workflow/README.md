# xinci 新词工作流

发现并验证英文 Google 搜索词,回答"这个词能不能撑起一个独立 SEO 站"。go 结论交付 md+html 建站决策书;no-go 不产出决策书,只在账本登记决定性理由。

默认单步模式由用户逐次驱动,skill 不自我调度;用户显式启动 xinci-run 后,它才在本次预算内连续编排各阶段。数据区配置、symlink 接入、测试见[仓库根 README](../README.md)。

## 它做什么

从有日期的变化与社区信号面提取搜索任务。官方变化先进入触发池,补齐搜索语言与商业预检后才进入候选漏斗;候选逐个过九道闸门,最后形成建站 go/no-go 结论。全流程留痕:触发池记原料、账本记状态、证据文件记现场观察、索引记淘汰方向。

## 两条赛道

| 赛道 | 定义 | 量级数据 | 广告线 |
| --- | --- | --- | --- |
| `new` 新词道 | 措辞太新以致 Semrush 查无 | 窗口期禁用 | 固定 `N/A` |
| `mature` 成熟错价词道 | 有真实搜索量、SERP 被守得弱 | 从第一步就要求取 | 可成立,$200/月硬门 |

两道共用一条限制:KD、Authority Score、外链数等域名强度代理不得决定 G2/G3(见闸门契约「关于 KD / KGR / allintitle 的统一立场」)。

`mature` 道的发现与 `formation_confirmed` 之前的推进由 xinci-mature 单步承接,每次转移用户逐条确认;xinci-run 只从 `formation_confirmed` 起自动推进 mature。本道至今 0 正例,skill 的目标是让方法可执行、可累积样本。各 skill 对两条赛道的分工见[通用约定「lane 边界」](xinci-core/通用约定.md)。

## 六条盈利线(G6,任一条过即放行)

subscription / lead_generation / affiliate / transaction / paid_report / advertising。六条都要给出判定;只有所有适用线均否决,G6 才否决整候选。算式与逐线约束见闸门契约 G6「六线判定」。

## 候选生命周期

状态只存在于账本,只能由 `registrar.py` 写入。

```
captured ──初筛出闸──→ screened ──登记 expiry──→ tracking ──形成达标──→ formation_confirmed
   │                        │                        │                        │ xinci-qualify
   ▼                        ▼ 窗口以天计(快道)        ▼ 闸门翻转               ▼
rejected            fast_grab_ready              rejected           qualified / disqualified
                            │                                              │ xinci-decide
                            ▼                                              ▼
                      built / expired              build_ready / pilot_ready / hold / no_site
```

上图只画主干。省略的边(快道 no-go → rejected、各态 expiry 过期 → expired、非终态 → withdrawn / superseded)与每条边的证据要求、提议人见[生命周期契约](xinci-core/生命周期契约.md)。

## 九道闸门

执行顺序 G0 → G4 → G5 → G6/G7 零成本预筛 → G1 → G2 → G3:零成本批先行,开浏览器的放后面。G6/G7/G8 是认定门,扫描期只做预筛。定义、判据与出口见[闸门契约](xinci-core/闸门契约.md)。

| 闸门 | 判什么 |
| --- | --- |
| G0 | 合法性与安全 |
| G1 | Google 首屏是否完成原子任务;若完成,站点簇反事实是否仍成立 |
| G2 | 完整首页结构阅读 |
| G3 | exact-task completion:有没有人已经把这件事做完了 |
| G4 | 任务能否完全在线完成 |
| G5 | 陷阱类别(当前 14 类) |
| G6 | 商业闭环 + 六条盈利线 |
| G7 | 耐久性 |
| G8 | 簇广度 |

## 文档:判断标准的唯一来源

| 文件 | 管什么 |
| --- | --- |
| [通用约定.md](xinci-core/通用约定.md) | 七个 skill 共用的开局步骤、运行模式与 `--by`、lane 边界、expired 边归属、共同硬规则 |
| [闸门契约.md](xinci-core/闸门契约.md) | G0–G8 定义、执行顺序、六线算式、时间光谱 |
| [生命周期契约.md](xinci-core/生命周期契约.md) | 状态机、每条边的证据要求、留痕分界、连续运行模式、registrar 用法 |
| [陷阱类别.md](xinci-core/陷阱类别.md) | 14 类陷阱与处置档 |
| [数据采集指南.md](xinci-core/数据采集指南.md) | 真浏览器原则、G1 SERP 读取规程、来源表、Semrush 纪律、选源信号、mature 道选源 |
| [评分契约.md](xinci-core/评分契约.md) | 六维权重、红队扣分、80 分线 |
| [闸门校准.md](xinci-core/闸门校准.md) | 实测记录、修订依据、事故复盘、待验证清单。**不是现行口径**,顶部索引表标明每节是否仍现行 |

契约是规范性来源;SKILL.md 与脚本可以摘述,但措辞冲突时以契约为准。[数据结构/](xinci-core/数据结构/) 下保留候选与观察两份 JSON Schema 作为字段文档,以及 `pattern-aliases.json`。

## 脚本

| 脚本 | 作用 |
| --- | --- |
| `registrar.py` | 账本唯一状态转移入口,逐项校验证据,原子替换 |
| `screen_index.py` | 淘汰方向索引:批量去重、带日期追加、去重裁决 |
| `trigger_pool.py` | 官方变化原料的 add/approve/discard 事件日志 |
| `run_controller.py` | xinci-run 的可恢复运行会话控制器(开轮时提交浏览器预检) |
| `run_policy.py` | 由预检、积压、停滞、来源轮换计算 full / trigger_only / debt_only / paused |
| `run_state.py` / `run_manifest.py` | 运行会话与运行清单的契约与原子写入;`correct-note` 给已写清单追加更正,不改原文 |
| `validate_ledger.py` | 账本不变式 + 运行清单格式校验,有错非零退出 |
| `report_status.py` | 只读状态汇报 |
| `data_root.py` / `init_workspace.py` | 数据区定位与初始化 |
| `build_decision_html.py` | 决策书 md → html |
| `tracking_schedule.py` / `false_negative_sample.py` | 追踪提示 / 校准轮抽样 |
| `term_normalize.py` / `chinese_labels.py` / `_common.py` / `_constants.py` | 归一化、中文展示、公共基础设施与常量 |

## 怎么开始

| 我想 | 用 |
| --- | --- |
| 一口气跑到出结果 | xinci-run(暗号 `xinci_run`) |
| 看账本现在什么情况 | xinci-status |
| 扫一轮新方向 | xinci-scan |
| 复查 new 追踪清单或到期 SERP 型拒绝 | xinci-track |
| 扫成熟错价词、复查 mature 前半程或到期 SERP 型拒绝 | xinci-mature |
| 给候选做认定评分 | xinci-qualify |
| 出建站 go/no-go 决策 | xinci-decide |

每个 skill 的第 0 步都是确认数据区,见通用约定。
