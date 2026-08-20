---
name: xinci-qualify
description: '对形成确认(formation_confirmed)的新词候选做深度认定,也受理决策阶段搁置(hold)候选的重审:G6 商业闭环、G7 耐久性、G8 簇广度、完整竞争审计与 100 分制评分(80 分线)。当用户说认定候选 X、判断这个机会是否真实、给 X 打分时使用。English triggers: qualify candidate, keyword qualification, score keyword opportunity. “值不值得建站”与建站 go/no-go 决策用 xinci-decide。'
---

# xinci-qualify 深度认定

回答一个问题:这个机会是真的吗?认定说"机会为真",不说"该建站"——后者是 xinci-decide 的事。

**两种输入**:

- **首次认定**:`formation_confirmed` 候选,走下面完整工作流,出口是 `qualified` 或 `disqualified`(registrar 强制,`qualified` 只接受来自 formation_confirmed 的转移);
- **hold 重审**:决策阶段搁置的 `hold` 候选,由用户送回重新核对认定结论。它已经带着 G6–G8 全 pass 与分数,**不会也不能回到 formation_confirmed**(状态机没有这条边);本 skill 对它的唯一出口是 `hold → disqualified`——补审推翻了某道认定门。若重审结论是"认定仍然成立",不做转移,把候选交回 xinci-decide 重出决策。

> **路径约定**:相对路径以仓库根为基准(正本在 `xinci-workflow/xinci-qualify/SKILL.md`,symlink 加载时 `readlink` 后上溯两级即仓库根);bash 在仓库根执行,或展开为绝对路径。
>
> **`--by` 约定**:下面的 registrar 命令模板写的是**单步形态**(`--by xinci-qualify`)。**在 xinci-run 连续运行下(含被它派出的子代理)一律改成 `--by xinci-run` 再执行,照抄模板是错的**。取值规则见生命周期契约「registrar 用法」的 `--by` 取值节。

## 行动前必读

- xinci-workflow/xinci-core/闸门契约.md(G6/G7/G8 定义;KD/KGR 统一立场)
- xinci-workflow/xinci-core/评分契约.md(六维权重、红队扣分、80 分线)
- xinci-workflow/xinci-core/数据采集指南.md(确认期审计的数据纪律)
- xinci-workflow/xinci-core/生命周期契约.md(转移证据要求)

## 工作流

1. **核对输入。** 候选状态是 formation_confirmed(首次认定)或 hold(重审);通读其全部历史观察,先掌握已知,再花新的注意力。hold 重审只需针对搁置理由指向的那几道门补审,不重做整套。**状态到了就是确认期**:Semrush 与 footprint 实测在此解禁,不看候选年龄(最快第 7 天到此,见闸门契约时间光谱)。
2. **G6 商业闭环。** 付费者是谁、任务是否被迫或重复、自助变现路径、保守假设下稳定收入 ≥$200/月 的可达性——四件缺一即 veto。
3. **G7 耐久性。** 版本更替风险、官方答案风险、好奇 vs 重复任务,逐一排查并记录判断依据。
4. **G8 簇广度(硬门)。** 枚举意图簇:≥3 个任务型查询 × ≥2 个独立 family;合并表述性变体,不许同义改写凑数。达不到即 disqualified——pilot 由决策阶段的页面地图线触发,不是 G8 的降级出口。
5. **完整竞争审计。** 真浏览器读核心任务查询的完整 top-10(到第二页或质量断层),每个结果按"做什么"分类;对判定"把任务做完了"的结果再判持续可见度(结构上进不来 SERP 的实现不计入否决,见闸门契约 G3 三分);**实测至少一个竞品的 footprint**(authority、流量、词量、增速)——存在不等于占据。
6. **评分。** 按评分契约六维打分,做红队反驳并扣分。硬否决之后不产生最终分数。
7. **写观察文件**(`证据/<slug>/<日期>-qualify.json`:逐维得分、红队记录、竞争分类清单、footprint 实测),qualified 观察必须在 `gates` 明确写 G6/G7/G8 的 pass,并把支撑来源列入非空 `source_urls`;registrar 会把 transition 的三门结论与这份观察逐门核对。然后**向用户提议** qualified(附分数)或 disqualified(附决定性缺口:哪一项、差多少)。
8. **用户确认后**执行:

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to qualified --by xinci-qualify --score <N> \
  --gates G6=pass,G7=pass,G8=pass --evidence "证据/<slug>/<日期>-qualify.json"
```

写运行清单 `运行/<日期>-xinci-qualify.json`(含计费调用数;同日再次运行加 HHMM 后缀,不覆盖已有清单)。例外:xinci-run 连续运行模式下不另写本阶段清单,内容并入 run 清单。

## 硬规则

- 只收 formation_confirmed(首次认定)与 hold(重审);其他状态的候选先按生命周期契约把它推进到位。hold 不必、也无法先转回 formation_confirmed。
- 低 KD 只触发一次 exact-task 完成度检查,永不作为鼓励(KD 14 对实测竞争 89 的背离案例见闸门契约)。
- 竞争判断按"做什么"不按"是谁";≥2 个免费结果做好任务且有持续可见度即 veto。
- veto 被推翻的候选回到普通评分,不豁免任何数值闸门。
- 79 分不算过;为凑候选降门槛是禁止的。分数差多少如实写进缺口。
- 每一次计费查询必须能改变决策;为流程而查是禁止的。
- 提议与执行分离:转移经用户确认后才调 registrar。例外:xinci-run 连续运行模式下,启动命令即标准授权,无需逐条确认。
