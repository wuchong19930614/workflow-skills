---
name: xinci-qualify
description: '对已进入形成确认(formation_confirmed)的 new 或 mature 候选做深度认定,也受理决策阶段搁置(hold)候选的重审:G6 商业闭环、G7 耐久性、G8 簇广度、完整竞争审计与 100 分制评分(80 分线)。当用户说认定候选 X、判断这个机会是否真实、给 X 打分时使用。English triggers: qualify candidate, keyword qualification, score keyword opportunity. mature 的发现与 formation_confirmed 前推进由 xinci-mature 承接,不由本 skill 处理。“值不值得建站”与建站 go/no-go 决策用 xinci-decide。'
---

# xinci-qualify 深度认定

新产生的 qualify observation 使用 `schema_version: 2`；registrar 会强制六条盈利线完整出现。历史缺省 v1 的两线观察只读兼容，不代表其他四线已审。

回答一个问题:这个机会是真的吗?认定说"机会为真",不说"该建站"——后者是 xinci-decide 的事。

**两种输入**:

- **首次认定**:`formation_confirmed` 候选,走下面完整工作流,出口是 `qualified` 或 `disqualified`(registrar 强制,`qualified` 只接受来自 formation_confirmed 的转移);
- **hold 重审**:决策阶段搁置的 `hold` 候选,由用户送回重新核对认定结论。它已经带着 G6–G8 全 pass 与分数,**不会也不能回到 formation_confirmed**(状态机没有这条边);本 skill 对它的唯一出口是 `hold → disqualified`——补审推翻了某道认定门。若重审结论是"认定仍然成立",不做转移,把候选交回 xinci-decide 重出决策。

> **路径约定**:相对路径以仓库根为基准(正本在 `xinci-workflow/xinci-qualify/SKILL.md`,symlink 加载时 `readlink` 后上溯两级即仓库根);bash 在仓库根执行,或展开为绝对路径。
>
> **`--by` 约定**:下面的 registrar 命令模板写的是**单步形态**(`--by xinci-qualify`)。**在 xinci-run 连续运行下(含被它派出的子代理)一律改成 `--by xinci-run`，并同时追加 `--run-id <活动会话>`；只替换 `--by` 或照抄单步模板都是错的**。取值规则见生命周期契约「registrar 用法」的 `--by` 取值节。

## 第 0 步:确认数据区(强制,先于一切写操作)

**第一次执行本工作流、或换了机器/checkout 时,必须先确认执行产出存到哪里。** 零成本一条命令:

```bash
python3 xinci-workflow/xinci-core/scripts/report_status.py
```

- 正常返回看板 → 数据区已配置,直接往下走,**别再问**。
- **退出码 2、提示「数据区未配置」→ 停下来问用户数据区放哪,不要替他选。** 这不是故障,是脚本刻意不猜(理由见生命周期契约「开工第一步」)。

拿到路径后固定下来(幂等,已存在的文件不动):

```bash
python3 xinci-workflow/xinci-core/scripts/init_workspace.py --data-root <用户给的路径>
```

## 行动前必读

- xinci-workflow/xinci-core/闸门契约.md(G6/G7/G8 定义;KD/KGR 统一立场)
- xinci-workflow/xinci-core/评分契约.md(六维权重、红队扣分、80 分线)
- xinci-workflow/xinci-core/数据采集指南.md(确认期审计的数据纪律)
- xinci-workflow/xinci-core/生命周期契约.md(转移证据要求)

## 工作流

1. **核对输入。** 候选状态是 formation_confirmed(首次认定)或 hold(重审),lane 可为 `new` 或 `mature`;mature 只有已经合法到达 formation_confirmed 才由本 skill 接手,不替它补做前半程。通读其全部历史观察,先掌握已知,再花新的注意力。hold 重审只需针对搁置理由指向的那几道门补审,不重做整套。**状态到了就是确认期**:Semrush 与 footprint 实测在此解禁,不看候选年龄(最快第 7 天到此,见闸门契约时间光谱)。
2. **G6 商业闭环(六线 OR 门)。** 对六条盈利线逐线判定,任一条 pass 即放行：subscription、lead_generation、affiliate、transaction、paid_report、advertising。每条都要写付费者、付费事件/重复单位、可交付物、保守单价与数量、收入算式、来源和最大反证。订阅线要求重复任务；广告线必须用实测簇量 × 现实可达 CTR ÷ 1000 × 有出处的 RPM 算出 base case,**达到 $200/月才 pass**；lead generation / transaction / paid report 可用少量高价值需求成立,不得套广告量级硬门。`lane=new` 把广告线明确记 `N/A`。观察逐线写结论；账本用 `g6_passed_lines` 记实际通过线。
3. **G7 耐久性。** 版本更替风险、官方答案风险、好奇 vs 重复任务,逐一排查并记录判断依据。
4. **G8 簇广度(硬门)。** 枚举意图簇:≥3 个任务型查询 × ≥2 个独立 family;合并表述性变体,不许同义改写凑数。达不到即 disqualified——pilot 由决策阶段的页面地图线触发,不是 G8 的降级出口。
5. **完整竞争审计。** 真浏览器读核心任务查询的完整 top-10(到第二页或质量断层),每个结果按"做什么"分类,并按闸门契约 G3 的现行判定执行:这里必须使用本阶段第 2 步刚形成的**正式 G6 结论**,不得继承扫描期的暂定盈利线;只有实际通过线全部依赖 affiliate / advertising 时占位否决才生效,subscription / lead_generation / transaction / paid_report 任一通过时,占位降为决策阶段的竞争强度输入。数工具之前先判经营信号(内容后面有没有付费产品、有没有按国/按任务的簇、有没有维护痕迹);数工具用两族措辞各检索一次(问句式 + 产品向,缺一不可);对判定"把任务做完了"的结果再判持续可见度(结构上进不来 SERP 的实现不计入否决,见闸门契约 G3 三分)。**实测至少一个竞品的 footprint**(authority、流量、词量、增速):authority 只作背景记录,流量/覆盖词量/增速衡量实际占据并只进入评分与风险说明;这些指标都不得反向改写 G2/G3——存在不等于占据。
6. **评分。** 按评分契约六维打分,做红队反驳并扣分。硬否决之后不产生最终分数；收入可行性维度必须是 1–20,不得用其他五维把 0 收入补到 80。
7. **写观察文件**(`证据/<slug>/<日期>-qualify.json`:逐维得分、六条 G6 判定、红队记录、竞争分类清单、footprint 实测),qualified 观察必须在 `gates` 明确写 G6/G7/G8 的 pass,用 `g6_lines` 完整写六条线的 `pass|veto|N/A`,用 `income_score` 写收入维度分,并把支撑来源列入非空 `source_urls`;registrar 会核对三门、逐线结论、收入分与 transition 参数。然后**向用户提议** qualified(附总分、`income_score`、通过线)或 disqualified(附决定性缺口:哪一项、差多少)。两种 disqualified 来源态都必须把本次 `-qualify` observation 随 transition 提交，不能只写 reason。
8. **用户确认后**执行:

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to qualified --by xinci-qualify --score <N> \
  --income-score <1-20> --g6-passed-lines <六条盈利线中实际通过者,逗号分隔> \
  --gates G6=pass,G7=pass,G8=pass --evidence "证据/<slug>/<日期>-qualify.json"
```

用 `run_manifest.py record-single --date <YYYY-MM-DD> --skill xinci-qualify [--suffix <HHMM>] --billable-calls <N> ...` 原子写运行清单；控制器拒绝覆盖，不得手写 JSON。例外:xinci-run 连续运行模式下不另写本阶段清单,内容并入 run 清单。

## 硬规则

- 只收 formation_confirmed(首次认定)与 hold(重审);其他状态的候选先按生命周期契约把它推进到位。hold 不必、也无法先转回 formation_confirmed。
- 低 KD 只触发一次 exact-task 完成度检查,永不作为鼓励;KD、Authority Score、外链数不进入竞争分,也不得改写 G2/G3(KD 14 对实测竞争 89 的背离案例见闸门契约)。
- 竞争判断按"做什么"不按"是谁";否决线按闸门契约 G3 的现行判定执行(先按盈利线定否决是否生效、经营信号优先、只数真工具)。旧的"≥2 个免费结果即 veto"数量线已于 2026-08-23 废除,不得沿用——它在账本里唯一被证明对应真实生意的方向上判错过。
- veto 被推翻的候选回到普通评分,不豁免任何数值闸门。
- 79 分不算过;为凑候选降门槛是禁止的。分数差多少如实写进缺口。
- 每一次计费查询必须能改变决策;为流程而查是禁止的。
- 提议与执行分离:转移经用户确认后才调 registrar。例外:xinci-run 连续运行模式下,启动命令即标准授权,无需逐条确认。
