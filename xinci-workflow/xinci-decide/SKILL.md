---
name: xinci-decide
description: 对已认定(qualified)或搁置待议(hold)的新词候选出建站 go/no-go 决策:页面地图、收入三情景、风险清单、红队复核,产出 md+html 双格式决策书;或对窗口以天计的 screened 候选走快道出速建决策。当用户说给 X 出建站决策、X 能不能建站、出决策书时使用。English triggers: build decision, site go no-go, decision document. 认定评分用 xinci-qualify。
---

# xinci-decide 建站决策

回答最后一个问题:该不该为这个词建一个站?两种模式:

- **完整模式**:输入 `qualified` 候选(或用户送回重出决策的 `hold` 候选),产出 build_ready / pilot_ready / hold / no_site;
- **快道模式**:输入窗口评估为 days 的 `screened` 候选,产出 fast_grab_ready——减配但透明,跳过的闸门明码标价。

决策书交付即停:注册域名、建站、发布,全部是用户的人工动作。

> **路径约定**:相对路径以仓库根为基准(正本在 `xinci-workflow/xinci-decide/SKILL.md`,symlink 加载时 `readlink` 后上溯两级即仓库根);bash 在仓库根执行,或展开为绝对路径。
>
> **`--by` 约定**:下面的 registrar 命令模板写的是**单步形态**(`--by xinci-decide`)。**在 xinci-run 连续运行下(含被它派出的子代理)一律改成 `--by xinci-run` 再执行,照抄模板是错的**。取值规则见生命周期契约「registrar 用法」的 `--by` 取值节。

## 行动前必读

- xinci-workflow/xinci-core/生命周期契约.md(决策转移的证据要求;双格式校验)
- xinci-workflow/xinci-core/闸门契约.md(G8 页面地图标准;快道要引用的 G3 三分与 `veto_window_bet` 出口限制)
- xinci-workflow/xinci-core/评分契约.md(收入可行性的 $200/月 基准线;"pilot 与快道不得声称全站分数"的出处)
- xinci-workflow/xinci-core/数据采集指南.md(补缺口审计时的真浏览器原则与 Semrush decision-changing 纪律)

## 完整模式工作流

1. **核对输入**:状态 qualified,或 `hold`(用户送回重出决策——它已带 G6–G8 全 pass 与分数,出口是 build_ready / pilot_ready / no_site;`hold → hold` 不是合法转移,重审后仍无法决断就说明缺的是证据不是决策,如实说明并停);通读认定观察,不重做已做过的审计,只补缺口。若为补缺口做了新审计,把新观察落一份 `证据/<slug>/<日期>-decide.json` 并随转移提交;没有新观察就不写——决策阶段的产出是决策书,`-decide` 观察是可选的(数据极简)。
2. **页面地图**:≥12 个任务互异页面 × ≥3 个簇 + ≥1 个自助产品资产;合并表述性变体。不足 → pilot(5–8 页有界实验)或 no_site。
3. **收入三情景**:downside / base / upside;base ≥$200/月、无主动销售、保守假设逐条标注来源、所需流量不超**自有意图流量**的保守估计(owned-intent:只算页面地图里那些页面自己的目标查询能带来的流量,不把品牌词、外部推荐、社媒爆量算进来)。
4. **风险清单**:技术可行性、合规、免费与付费替代、维护负担、数据/API 成本。
5. **红队复核**:换立场反驳整个决策一轮,成立的反驳如实写入。
6. **写决策书两份**(见下"双格式约定"),**提议决策**,用户确认后:

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to build_ready --by xinci-decide \
  --decision-ref "决策书/<slug>.md" --play single_domain
```

`--play` 二选一,按页面地图的形状定,与 build_ready/pilot_ready 无关:`single_domain`(一个词簇撑一个站,pilot 默认走这个)、`cluster_expansion`(多簇分站或子目录扩张)。`--decision-ref` 是**相对数据区**的路径(`决策书/<slug>.md`),而下面生成 html 的脚本吃的是相对仓库根的路径(`数据/新词工作流/决策书/<slug>.md`)——两者基准不同,别互相套用。

no-go(hold / no_site)只带 reason,不出决策书、不带 decision-ref。

## 快道模式工作流

1. **核对输入**:状态 screened 且 window_estimate=days。
2. **轻量决策书**,必含:词与任务;G0–G5 证据;窗口估计与 expiry(附推理);**若 G3=`veto_window_bet`:G3 豁免声明**——数到的免费实现清单、为何判定它们只是还没被收录,以及明码标价一句"本次只赌收录时差,通用工具收录后位置即失";**跳过的闸门清单及"为何此刻无法执行"**(G6–G8 所需证据对天级新词客观不存在);48 小时发布计划(最小页面集);投入上限声明(损失封顶:一个域名 + 若干页面工时);风险确认(这是窗口赌注,不是被验证的生意);失效信号;升级通路说明(词若耐久,built 后可转回 tracking 走完整认定;**若本次 G3=`veto_window_bet`,升级时必须重跑 G3 并取得真 pass**,快道豁免不可继承)。
3. 用户确认风险后:`--to fast_grab_ready --play fast_grab --expiry <日期> --decision-ref "决策书/<slug>.md"`。
4. **快道的 no-go**:读完证据判定这个赌注不值(收录时差太短、任务其实一次性、投入上限也兜不住),提议 `rejected`(reason 写清不成立的那条判据)或由用户 `withdrawn`。**快道不产出 hold / no_site**——那两个是完整模式的结论,快道候选还没做过 G6–G8,没有资格被"搁置待议"。快道 no-go 同样不出决策书。

## 双格式约定(md 给 AI,html 给人)

- `决策书/<slug>.md` —— 给之后落地网站内容的 AI 读。结构化、无修辞:主关键词与精确措辞、意图簇及每页对应查询、页面地图(每页任务定义)、自助产品资产规格、竞争缺口、变现路径、失效条件、明确的"不要做什么"。**md 是唯一事实来源。**结论先行、关键数字用粗体——html 的排版直接来自 md 结构。
- `决策书/<slug>.html` —— 给人读;**不手写**,由脚本从 md 生成(单文件、内联样式、零外部依赖,双击即开):

```bash
python3 xinci-workflow/xinci-core/scripts/build_decision_html.py "数据/新词工作流/决策书/<slug>.md"
```

- md 每次修改后重跑脚本再生成 html,禁止手改 html。registrar 在注册决策时强制校验双文件同时存在。
- 每份决策书必含**失效条件**(出现什么信号即放弃)与**下一步人工动作清单**。

## 硬规则

- 不注册域名、不花钱、不发布——决策书交付即停。
- pilot 与快道决策不得声称全站分数。
- no-go 不出决策书,只在账本记决定性理由(数据极简原则)。
- 快道只收 window_estimate=days 的 screened 候选;别的候选想快,答案是不行。
- 快道只有两类出口:go 是 fast_grab_ready,no-go 是 rejected(判据不成立)或 withdrawn(用户撤回);hold 与 no_site 只属于完整模式。
- 提议与执行分离:转移经用户确认后才调 registrar;快道额外要求用户对"跳过闸门清单"逐条确认。例外:xinci-run 连续运行模式下,启动命令即标准授权,转移无需逐条确认;快道决策即运行的终止点,用户通过阅读交付的决策书完成风险确认,建站与否仍是用户的决定。
- 写运行清单 `运行/<日期>-xinci-decide.json`(同日再次运行加 HHMM 后缀,不覆盖已有清单)。例外:xinci-run 连续运行模式下不另写本阶段清单,内容并入 run 清单。
