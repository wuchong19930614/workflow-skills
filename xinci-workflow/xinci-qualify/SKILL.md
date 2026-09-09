---
name: xinci-qualify
description: '对已进入形成确认(formation_confirmed)的 new 或 mature 候选做深度认定,也受理决策阶段搁置(hold)候选的重审。当用户说认定候选 X、判断这个机会是否真实、给 X 打分时使用。English triggers: qualify candidate, keyword qualification, score keyword opportunity. mature 的发现与 formation_confirmed 前推进由 xinci-mature 承接,不由本 skill 处理。“值不值得建站”与建站 go/no-go 决策用 xinci-decide。'
---

# xinci-qualify 深度认定

先读 `xinci-workflow/xinci-core/通用约定.md`。再读闸门契约 G6/G7/G8、G3「前置」与「关于 KD / KGR / allintitle 的统一立场」，评分契约及证据判定契约，数据采集指南「Semrush 探针纪律」，生命周期契约「每转移的证据要求」中认定相关行。不要加载与本候选无关的扫描来源、陷阱案例或历史校准。

只回答"这个机会是真的吗";"该不该建站"归 xinci-decide。两种输入:

- **首次认定**:`formation_confirmed` 候选(lane 为 `new` 或 `mature`),走完整工作流,出口 `qualified` / `disqualified`；决定性证据不足则认定暂缓，状态不变。
- **hold 重审**:决策阶段搁置的 `hold` 候选,只针对搁置理由指向的门补审,不重做整套;唯一出口 `hold → disqualified`,不回 formation_confirmed。重审结论"认定仍成立"时不转移,交回 xinci-decide 重出决策；仍缺证据时保持 hold，记录缺口，不调用仅对 formation_confirmed 开放的 defer-qualify。

其他状态的候选不收;mature 未合法到达 formation_confirmed 的,不替它补前半程。

## 工作流

1. **核对输入。** 状态与 lane 合法；按证据判定契约「既有证据的阅读入口」读取索引、起点观察及相关引用，不默认展开全部历史。状态到了就是确认期:Semrush 与 footprint 实测解禁,不看候选年龄。
   索引的 review_required_gates 与 unknown_income_lines 必须进入本次补证据计划；账本历史 pass 不能覆盖新观察中的未知。需要解除的 G3 提醒须由更晚的本次 qualify 实测结论支持。
2. **G6 商业闭环。** 六条盈利线逐线判定,判据见闸门契约 G6「六线判定」;适用性轻筛后优先补强最有希望的路径；通过线写付费者、付费事件/重复单位、可交付物、保守单价与数量、收入算式、来源、最大反证；其他线允许明确记未知。`lane=new` 的 advertising 记 `N/A`。
3. **G7 耐久性。** 按闸门契约 G7 逐一排查,记录判断依据。
4. **G8 簇广度(硬门)。** 枚举意图簇:合计 ≥3 个任务型查询、分布在 ≥2 个独立 family(不是每族各 3 条),合并表述性变体,不许同义改写凑数。达不到即 disqualified;pilot 由决策阶段页面地图触发,不是 G8 的降级出口。
5. **完整竞争审计。** 真浏览器读核心任务查询的完整 top-10(到第二页或质量断层),按"做什么"分类。占位否决是否生效按闸门契约 G3「前置」,用本次第 2 步的正式 G6 结论,不继承扫描期暂定线;数工具用问句式 + 产品向两族措辞各检索一次。
   调查至少一个竞品 footprint；覆盖不足时按证据判定契约取替代证据。补齐 SEO 查询与任务缺口，不以买量或直销代替自然搜索入口。
6. **复核后评分。** 先按证据判定契约「评分前的证据复核」核对既有商业假设和扣分归属，再按评分契约六维打分、红队扣分；疑似一次性任务误罚、代理报价或覆盖缺口时参考「样本纠偏示例」。硬否决后不产生分数;`income_score` 必须 1–20。
7. **写观察文件并提议。** `证据/<slug>/<日期>-qualify.json`,`schema_version: 3`:assessment（字段见证据判定契约）、竞争分类清单、footprint 或替代证据;`gates` 只写实测结论，硬否决写对应 veto，不照抄 pass,`g6_lines` 完整写六条 `pass|veto|N/A|inconclusive`,可评分时 `income_score` 写收入维度分，暂缓或硬否决时省略,`source_urls` 非空。
   向用户提议 qualified(附总分、`income_score`、通过线)或 disqualified(附决定性缺口:哪一项、差多少;两种出口都必须随 transition 提交本次 observation,不能只写 reason)。
   **第三个出口:认定暂缓。** 存在未解决的决定性证据缺口（访问失败、数据不覆盖或未核实假设，且没有足够替代证据）时不出分、不出结论,按证据判定契约走:

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py defer-qualify \
  --slug <slug> --by xinci-qualify --reason "<缺的是哪一类证据、为什么会改变结论且尚未解决>" \
  --pending-evidence "<待补项1>" --pending-evidence "<待补项2>" \
  --pending-until <YYYY-MM-DD> --evidence "证据/<slug>/<日期>-qualify.json"
```

   暂缓期内该候选不进 `run_policy` 的 go 天花板(再跑一遍只会得到同一个"取不到");到期只复核证据是否变化；仍有决定性缺口则更新暂缓，不强制商业否决。
8. **生成提交提案。** 用公共脚本校验观察并生成参数，避免重填 gates、分数与通过线：
```bash
python3 xinci-workflow/xinci-core/scripts/qualification.py <观察文件路径> \
  --evidence-ref "证据/<slug>/<日期>-qualify.json"
```
连续运行加 `--by xinci-run --run-id <活动会话>`。脚本从当前数据区账本读取状态（可用 `--data-root` 指定）；输出 `registrar_argv` 是参数数组，不是已执行命令。数组为空时按 `next_action` 保持 hold 并交回决策或记录缺口，不提交转移。非空时补齐 `missing_arguments`（业务理由、暂缓复核日期），核对输入状态与授权后交 registrar。提案不替代提交时 registrar 对当前状态与授权的再次校验。
9. **执行并收尾。** 单步用户确认后提交；连续模式按既有启动授权提交，再按通用约定写清单。脚本只生成提案，registrar 仍执行全部证据、状态与权限校验。

## 硬规则

- 79 分不算过;不为凑候选降门槛,分数差多少如实写进缺口。
- veto 被推翻的候选回到普通评分,不豁免任何数值闸门。
- 每一次计费查询必须能改变决策;为流程而查是禁止的。
