---
name: xinci-qualify
description: 对形成确认(formation_confirmed)的新词候选做深度认定:G6 商业闭环、G7 耐久性、G8 簇广度、完整竞争审计与 100 分制评分(80 分线)。当用户说认定候选 X、X 值不值得建站、给 X 打分时使用。English triggers: qualify candidate, keyword qualification, score keyword opportunity. 建站 go/no-go 决策用 xinci-decide。
---

# xinci-qualify 深度认定

回答一个问题:这个机会是真的吗?输入必须是 `formation_confirmed` 状态的候选(registrar 强制,其他状态拒收)。认定说"机会为真",不说"该建站"——后者是 xinci-decide 的事。

## 行动前必读

- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-workflow/xinci-core/闸门契约.md(G6/G7/G8 定义;KD/KGR 统一立场)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-workflow/xinci-core/评分契约.md(六维权重、红队扣分、80 分线)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-workflow/xinci-core/数据采集指南.md(确认期审计的数据纪律)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-workflow/xinci-core/生命周期契约.md(转移证据要求)

## 工作流

1. **核对输入。** 候选状态必须是 formation_confirmed;通读其全部历史观察,先掌握已知,再花新的注意力。
2. **G6 商业闭环。** 付费者是谁、任务是否被迫或重复、自助变现路径、$1,000/月上限的合理性——四件缺一即 veto。
3. **G7 耐久性。** 版本更替风险、官方答案风险、好奇 vs 重复任务,逐一排查并记录判断依据。
4. **G8 簇广度。** 枚举意图簇:≥3 个任务型查询 × ≥2 个独立 family 才够全站;合并表述性变体,不许同义改写凑数。
5. **完整竞争审计。** 真浏览器读核心任务查询的完整 top-10(到第二页或质量断层),每个结果按"做什么"分类;**实测至少一个竞品的 footprint**(authority、流量、词量、增速)——存在不等于占据。
6. **评分。** 按评分契约六维打分,做红队反驳并扣分。硬否决之后不产生最终分数。
7. **写观察文件**(`证据/<slug>/<日期>-qualify.json`:逐维得分、红队记录、竞争分类清单、footprint 实测),**向用户提议** qualified(附分数)或 disqualified(附决定性缺口:哪一项、差多少)。
8. **用户确认后**执行:

```bash
python3 /Users/vito.wu/IdeaProjects/workflow-skills/xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to qualified --by xinci-qualify --score <N> \
  --gates G6=pass,G7=pass,G8=pass --evidence "证据/<slug>/<日期>-qualify.json"
```

写运行清单 `运行/<日期>-xinci-qualify.json`(含计费调用数)。

## 硬规则

- 只收 formation_confirmed;想认定其他状态的候选,先按生命周期契约把它推进到位。
- 低 KD 只触发一次 exact-task 完成度检查,永不作为鼓励(KD 14 对实测竞争 89 的背离案例见闸门契约)。
- 竞争判断按"做什么"不按"是谁";两个以上免费结果做好任务且有持续可见度即 veto。
- veto 被推翻的候选回到普通评分,不豁免任何数值闸门。
- 79 分不算过;为凑候选降门槛是禁止的。分数差多少如实写进缺口。
- 每一次计费查询必须能改变决策;为流程而查是禁止的。
- 提议与执行分离:转移经用户确认后才调 registrar。例外:xinci-run 连续运行模式下,启动命令即标准授权,无需逐条确认。
