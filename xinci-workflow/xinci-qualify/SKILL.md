---
name: xinci-qualify
description: '对已进入形成确认(formation_confirmed)的 new 或 mature 候选做深度认定,也受理决策阶段搁置(hold)候选的重审。当用户说认定候选 X、判断这个机会是否真实、给 X 打分时使用。English triggers: qualify candidate, keyword qualification, score keyword opportunity. mature 的发现与 formation_confirmed 前推进由 xinci-mature 承接,不由本 skill 处理。“值不值得建站”与建站 go/no-go 决策用 xinci-decide。'
---

# xinci-qualify 深度认定

先读 `xinci-workflow/xinci-core/通用约定.md`。再读闸门契约 G6/G7/G8、G3「前置」与「关于 KD / KGR / allintitle 的统一立场」，评分契约，数据采集指南「Semrush 探针纪律」，生命周期契约「每转移的证据要求」中认定相关行。不要加载与本候选无关的扫描来源、陷阱案例或历史校准。

只回答"这个机会是真的吗";"该不该建站"归 xinci-decide。两种输入:

- **首次认定**:`formation_confirmed` 候选(lane 为 `new` 或 `mature`),走完整工作流,出口 `qualified` / `disqualified`。
- **hold 重审**:决策阶段搁置的 `hold` 候选,只针对搁置理由指向的门补审,不重做整套;唯一出口 `hold → disqualified`,不回 formation_confirmed。重审结论"认定仍成立"时不转移,交回 xinci-decide 重出决策。

其他状态的候选不收;mature 未合法到达 formation_confirmed 的,不替它补前半程。

## 工作流

1. **核对输入。** 状态与 lane 合法;通读全部历史观察,先掌握已知。状态到了就是确认期:Semrush 与 footprint 实测解禁,不看候选年龄。
2. **G6 商业闭环。** 六条盈利线逐线判定,判据见闸门契约 G6「六线判定」;每条写付费者、付费事件/重复单位、可交付物、保守单价与数量、收入算式、来源、最大反证。`lane=new` 的 advertising 记 `N/A`。
3. **G7 耐久性。** 按闸门契约 G7 逐一排查,记录判断依据。
4. **G8 簇广度(硬门)。** 枚举意图簇:合计 ≥3 个任务型查询、分布在 ≥2 个独立 family(不是每族各 3 条),合并表述性变体,不许同义改写凑数。达不到即 disqualified;pilot 由决策阶段页面地图触发,不是 G8 的降级出口。
5. **完整竞争审计。** 真浏览器读核心任务查询的完整 top-10(到第二页或质量断层),按"做什么"分类。占位否决是否生效按闸门契约 G3「前置」,用本次第 2 步的正式 G6 结论,不继承扫描期暂定线;数工具用问句式 + 产品向两族措辞各检索一次。
   实测至少一个竞品 footprint(authority、流量、词量、增速),用途与边界按闸门契约「关于 KD / KGR / allintitle 的统一立场」。
6. **评分。** 按评分契约六维打分,红队反驳并扣分。硬否决后不产生分数;`income_score` 必须 1–20。
7. **写观察文件并提议。** `证据/<slug>/<日期>-qualify.json`,`schema_version: 2`:逐维得分、红队记录、竞争分类清单、footprint 实测;`gates` 写 G6/G7/G8 的 pass,`g6_lines` 完整写六条 `pass|veto|N/A`,`income_score` 写收入维度分,`source_urls` 非空。
   向用户提议 qualified(附总分、`income_score`、通过线)或 disqualified(附决定性缺口:哪一项、差多少;两种出口都必须随 transition 提交本次 observation,不能只写 reason)。
   **第三个出口:认定暂缓。** 缺的证据是环境性的(本次会话取不到,如 Semrush 未登录、官方站维护、小站无 footprint 数据)时不出分、不出结论,按评分契约「证据缺失分两种」走:

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py defer-qualify \
  --slug <slug> --by xinci-qualify --reason "<缺的是哪一类证据、为何是环境性的>" \
  --pending-evidence "<待补项1>" --pending-evidence "<待补项2>" \
  --pending-until <YYYY-MM-DD> --evidence "证据/<slug>/<日期>-qualify.json"
```

   暂缓期内该候选不进 `run_policy` 的 go 天花板(再跑一遍只会得到同一个"取不到");到期后必须按当时手上的证据出结论。
8. **用户确认后**执行,再按通用约定写运行清单(`--skill xinci-qualify --billable-calls <N>`):
```bash
# qualified:score ≥80 与 income-score 1–20 都必填
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to qualified --by xinci-qualify --score <N> \
  --income-score <1-20> --g6-passed-lines <六条盈利线中实际通过者,逗号分隔> \
  --gates G6=pass,G7=pass,G8=pass --evidence "证据/<slug>/<日期>-qualify.json"

# disqualified:reason 写决定性缺口(哪一项、差多少);income-score 与 g6-passed-lines
# 可选但建议照写,否则"为什么差"只留在证据文件里
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to disqualified --by xinci-qualify --score <N> \
  --income-score <1-20> --g6-passed-lines <实际通过者> \
  --gates G6=pass,G7=pass,G8=pass --evidence "证据/<slug>/<日期>-qualify.json" \
  --reason "<决定性缺口:哪一项、差多少>"
```

## 硬规则

- 79 分不算过;不为凑候选降门槛,分数差多少如实写进缺口。
- veto 被推翻的候选回到普通评分,不豁免任何数值闸门。
- 每一次计费查询必须能改变决策;为流程而查是禁止的。
