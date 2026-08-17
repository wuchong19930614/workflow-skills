---
name: xinci-decide
description: 对已认定(qualified)的新词候选出建站 go/no-go 决策:页面地图、收入三情景、风险清单、红队复核,产出 md+html 双格式决策书;或对窗口以天计的 screened 候选走快道出速建决策。当用户说给 X 出建站决策、X 能不能建站、出决策书时使用。English triggers: build decision, site go no-go, decision document. 认定评分用 xinci-qualify。
---

# xinci-decide 建站决策

回答最后一个问题:该不该为这个词建一个站?两种模式:

- **完整模式**:输入 `qualified` 候选,产出 build_ready / pilot_ready / hold / no_site;
- **快道模式**:输入窗口评估为 days 的 `screened` 候选,产出 fast_grab_ready——减配但透明,跳过的闸门明码标价。

决策书交付即停:注册域名、建站、发布,全部是用户的人工动作。

## 行动前必读

- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/生命周期契约.md(决策转移的证据要求;双格式校验)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/闸门契约.md(G8 页面地图标准)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/数据结构/decision.schema.json(结构化摘要字段)

## 完整模式工作流

1. **核对输入**:状态 qualified;通读认定观察,不重做已做过的审计,只补缺口。
2. **页面地图**:≥12 个任务互异页面 × ≥3 个簇 + ≥1 个自助产品资产;合并表述性变体。不足 → pilot(5–8 页有界实验)或 no_site。
3. **收入三情景**:downside / base / upside;base ≥$1,000/月、无主动销售、保守假设逐条标注来源、所需流量不超 owned-intent 估计。
4. **风险清单**:技术可行性、合规、免费与付费替代、维护负担、数据/API 成本。
5. **红队复核**:换立场反驳整个决策一轮,成立的反驳如实写入。
6. **写决策书两份**(见下"双格式约定"),**提议决策**,用户确认后:

```bash
python3 /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/scripts/registrar.py transition \
  --slug <slug> --to build_ready --by xinci-decide \
  --decision-ref "决策书/<slug>.md" --play single_domain
```

no-go(hold / no_site)只带 reason,不出决策书、不带 decision-ref。

## 快道模式工作流

1. **核对输入**:状态 screened 且 window_estimate=days。
2. **轻量决策书**,必含:词与任务;G0–G5 证据;窗口估计与 expiry(附推理);**跳过的闸门清单及"为何此刻无法执行"**(G6–G8 所需证据对天级新词客观不存在);48 小时发布计划(最小页面集);投入上限声明(损失封顶:一个域名 + 若干页面工时);风险确认(这是窗口赌注,不是被验证的生意);失效信号;升级通路说明(词若耐久,built 后可转回 tracking 走完整认定)。
3. 用户确认风险后:`--to fast_grab_ready --play fast_grab --expiry <日期> --decision-ref "决策书/<slug>.md"`。

## 双格式约定(md 给 AI,html 给人)

- `决策书/<slug>.md` —— 给之后落地网站内容的 AI 读。结构化、无修辞:主关键词与精确措辞、意图簇及每页对应查询、页面地图(每页任务定义)、自助产品资产规格、竞争缺口、变现路径、失效条件、明确的"不要做什么"。**md 是唯一事实来源。**
- `决策书/<slug>.html` —— 给人读:结论先行、分节排版、关键数字醒目;单文件、内联样式、零外部依赖,双击即开。
- 两份同批产出、同批更新,禁止只改一份。registrar 在注册决策时强制校验双文件同时存在。
- 每份决策书必含**失效条件**(出现什么信号即放弃)与**下一步人工动作清单**。

## 硬规则

- 不注册域名、不花钱、不发布——决策书交付即停。
- pilot 与快道决策不得声称全站分数。
- no-go 不出决策书,只在账本记决定性理由(数据极简原则)。
- 快道只收 window_estimate=days 的 screened 候选;别的候选想快,答案是不行。
- 提议与执行分离:转移经用户确认后才调 registrar;快道额外要求用户对"跳过闸门清单"逐条确认。例外:xinci-run 连续运行模式下,启动命令即标准授权,转移无需逐条确认;快道决策即运行的终止点,用户通过阅读交付的决策书完成风险确认,建站与否仍是用户的决定。
- 写运行清单 `运行/<日期>-xinci-decide.json`。
