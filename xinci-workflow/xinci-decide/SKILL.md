---
name: xinci-decide
description: '对已认定(qualified)或搁置待议(hold)的 new 或 mature 候选出建站 go/no-go 决策;也可对窗口以天计的 screened 候选走快道出速建决策,并受理 screened / fast_grab_ready 到期候选的 expired 提议。当用户说给 X 出建站决策、X 能不能建站、出决策书时使用。English triggers: build decision, site go no-go, decision document. mature 的发现、追踪与形成确认前推进由 xinci-mature 承接,不由本 skill 处理;已被合法送到 screened 的 mature 候选可显式调用本 skill 做快道决策。认定评分用 xinci-qualify。'
---

# xinci-decide 建站决策

先读 `xinci-workflow/xinci-core/通用约定.md`。完整模式读取生命周期契约的决策转移行、闸门契约 G8 决策门和评分契约；快道读取生命周期契约「窗口赌注的挂起与出闸」及闸门契约 G3 的 `veto_window_bet` 出口。只有补做现场审计时才读取数据采集指南对应章节，不默认加载全文。

- **完整模式**:输入 `qualified`,或用户送回重出决策的 `hold`(lane 为 new 或 mature);出口 build_ready / pilot_ready / hold / no_site(hold 送回时出口不含 hold)。
- **快道模式**:只收 window_estimate=days 的 `screened`;出口 fast_grab_ready。new 由常规扫描送入;mature 须已由 xinci-mature 合法送到 screened 并显式调用本 skill。

## 完整模式工作流

1. **核对输入。** 通读认定观察,不重做已做过的审计,只补缺口。为补缺口做了新审计才落 `证据/<slug>/<日期>-decide.json` 并随转移提交;没有新观察不写。`hold → hold` 不是合法转移:重审后仍无法决断,如实说明缺的是证据并停。
2. **页面地图。** ≥12 个任务互异页面 × ≥3 个簇 + ≥1 个自助产品资产,合并表述性变体。不足 → pilot 或 no_site;pilot 首发从地图中选 5–8 个最高价值页面,其余列入扩展 backlog(见闸门契约 G8 决策门)。
3. **收入三情景。** downside / base / upside,沿用认定时实际通过的盈利线与证据,不得换线绕门;逐条复核流量假设或账户/线索/交易/报告数量、单价、CAC 与交付成本,保守假设逐条标注来源。
4. **风险清单。** 技术可行性、合规、免费与付费替代、维护负担、数据/API 成本。
5. **红队复核。** 换立场反驳整个决策一轮,成立的反驳如实写入。
6. **先提议决策。** go(`build_ready` / `pilot_ready`)才按「双格式约定」写 md+html 决策书,用户确认后执行;no-go(`hold` / `no_site`)不写决策书、不带 decision-ref,只提交 `--reason`。随后按通用约定写运行清单(`--skill xinci-decide`)。
```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to build_ready --by xinci-decide --decision-ref "决策书/<slug>.md" --play single_domain
```
`--play` 二选一,按页面地图形状定,与 build_ready/pilot_ready 无关:`single_domain`(一个词簇撑一个站,pilot 默认)、`cluster_expansion`(多簇分站或子目录扩张)。`--decision-ref` 是相对数据区的路径;生成 html 的脚本吃的是文件系统路径,两者基准不同。

## 快道模式工作流

1. **核对输入。** 状态 screened 且 window_estimate=days。
2. **轻量决策书**,必含:
   - 词与任务;
   - G0/G1/G2/G4/G5=`pass` 的证据与 G3 实际结论证据(G3 为 `pass` 或 `veto_window_bet`,后者不叫"全过");
   - 窗口期 `g6_tentative_lines` 逐线结论、依据与"不等于正式 G6"的明示;
   - 窗口估计与 expiry(附推理);
   - G3=`veto_window_bet` 时的 G3 降级声明:数到的免费实现清单、为何判定它们只是未收录、"本次只赌收录时差,通用工具收录后位置即失"一句;
   - 未完成的正式闸门清单(G6–G8)及为何此刻无法执行;已有的暂定 G6 不得冒充正式结论;
   - 48 小时发布计划(最小页面集);
   - 投入上限声明(损失封顶:一个域名 + 若干页面工时);
   - 风险披露与授权状态(这是窗口赌注,不是被验证的生意);授权状态章节按模式写法见通用约定「运行模式与 `--by`」与生命周期契约「窗口赌注的挂起与出闸」;
   - 失效条件与下一步人工动作清单;
   - 升级通路:词若耐久,built 后可转回 tracking 走完整认定;G3=`veto_window_bet` 的升级须重跑 G3 取得真 pass,降级结论不可继承。
3. **执行。** 单步由用户读完披露并确认后执行;`G3=veto_window_bet` 无论哪种模式都须该候选的一次性明确确认。
```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to fast_grab_ready --by xinci-decide --play fast_grab --expiry <日期> --decision-ref "决策书/<slug>.md"
```
4. **快道 no-go。** 读完证据判定赌注不值(收录时差太短、任务其实一次性、投入上限兜不住)→ 提议 `rejected`(reason 写清不成立的判据)或由用户 `withdrawn`。不出决策书。
5. **到期处置。** 归属见通用约定「四条 expired 边的提议人」;用户按 xinci-status 到期清单送来,本 skill 提议、用户确认,不出决策书。`screened`:expiry 已过(`date`);`fast_grab_ready`:expiry 已过(`date`)或窗口关闭(`window_closed`,通用工具已收录该对象)。
```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to expired --by xinci-decide --expiry-trigger <date|window_closed> --reason "<expiry 已过经用户确认 / 窗口关闭:通用工具已收录该对象>"
```

## 双格式约定(md 给 AI,html 给人)

- `决策书/<slug>.md` 是唯一事实来源,给之后落地网站内容的 AI 读。结构化、无修辞、结论先行、关键数字粗体;含主关键词与精确措辞、意图簇及每页对应查询、页面地图(每页任务定义)、自助产品资产规格、竞争缺口、变现路径、失效条件(出现什么信号即放弃)、下一步人工动作清单、"不要做什么"。快道决策书同样必含失效条件与下一步人工动作清单。
- `决策书/<slug>.html` 给人读,不手写,由脚本从 md 生成(单文件、内联样式、零外部依赖);md 每次修改后重跑脚本,禁止手改 html。生成器把 md 的 SHA-256 写入 html meta,registrar 校验源哈希与完整确定性渲染结果,旧 html、伪造 meta、手改 html 一律拒收。
```bash
python3 xinci-workflow/xinci-core/scripts/build_decision_html.py "$(python3 xinci-workflow/xinci-core/scripts/data_root.py)/决策书/<slug>.md"
```

## 硬规则
- 快道不评分:账本 `score` 保持 null(`validate_ledger` 强制),决策书不出现任何分数。
- pilot 从 qualified 转来,账本照常带 ≥80 的认定分;决策书写清该分数说的是"机会为真",降为 pilot 是因为页面地图不满全站线,不得当"全站已验证"的依据。
- 快道决策出口只有 fast_grab_ready / rejected / withdrawn;hold 与 no_site 只属完整模式;到期出的是 expired,不是 rejected。
