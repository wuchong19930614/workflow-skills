---
name: xinci-track
description: '复查 new 道中处于追踪状态的候选:重跑 G1、看 SERP 变化、命名定型与需求形成信号,向用户提议继续追踪/续期修订/形成确认/过期/否决。当用户说复查追踪清单、看看候选 X 现在什么情况、复查 watchlist 时使用。English triggers: recheck candidates, track watchlist, re-observe keyword. 何时查由用户决定;可指定候选,未指定时该次调用默认授权遍历全部 lane=new 的 tracking 候选。mature 在 formation_confirmed 前由 xinci-mature 单步承接,不由本 skill 处理。本 skill 不自我调度。'
---

# xinci-track 追踪复查

> **2026-09-02 覆盖说明**：新 track observation 写 `schema_version: 2` 并复核六条盈利线；下文历史性的订阅/广告示例只用于读取旧证据，不再定义“无适用盈利线”。

对本次调用覆盖的 `lane=new` tracking 候选逐个复查:用户可明确指定;未指定时按下段规则遍历全部 new 道候选。mature 在 `formation_confirmed` 前由 xinci-mature 单步承接,本 skill 发现 mature tracking 候选时只报告已跳过并指向 xinci-mature,不调用 registrar。新词的观察会腐烂:第 3 天判断"竞争空场"的候选,第 17 天可能已经死了——所以每次复查必须重跑 G1,并把结论落成带日期的新观察。

何时复查由用户决定;本 skill 被调用才动,不设节奏、不催促。用户可指定候选;若只调用本 skill 而未给候选,该次调用默认授权遍历全部 `lane=new` 且状态为 `tracking` 的候选。

> **路径约定**:相对路径以仓库根为基准(正本在 `xinci-workflow/xinci-track/SKILL.md`,symlink 加载时 `readlink` 后上溯两级即仓库根);bash 在仓库根执行,或展开为绝对路径。
>
> **`--by` 约定**:下面所有 registrar 命令模板写的是**单步形态**(`--by xinci-track`)。**在 xinci-run 连续运行下(含被它派出的子代理)一律改成 `--by xinci-run`，并同时追加 `--run-id <活动会话>`；只替换 `--by` 或照抄单步模板都是错的**。`checked` 的 `--by` 有默认值 `xinci-track`,连续运行下必须显式传。取值规则见生命周期契约「registrar 用法」的 `--by` 取值节。

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

- xinci-workflow/xinci-core/生命周期契约.md(转移证据要求;时间字段只记录不调度)
- xinci-workflow/xinci-core/闸门契约.md(G0–G5;形成期允许的 Semrush 探针边界)
- xinci-workflow/xinci-core/数据采集指南.md(真浏览器原则;探针纪律)

## 工作流

对用户指定的每个 `lane=new` 候选执行;本次调用未指定候选时,遍历全部 `lane=new` 且状态为 `tracking` 的候选。指定项若是 mature,只报告其仍属于手工前半程,不写入:

1. **重跑 G1,同批零成本重核 G0。** 真浏览器搜精确词(美区桌面未登录)。只有环境合规时才提交 G1 结论:首屏若完成精确原子任务,先重做完整 `cluster_counterfactual`;五种站点级扩展全部不成立、结论为 `atomic_only` 时 G1 才翻转并提议 `rejected`。任一扩展形成独立重复任务时记 `viable_cluster`,改写任务并重新核对受影响的前置门,不得直接判死。环境无法达到美区、桌面、未登录,或结果明显受个性化污染时,只记带环境说明的观察,不写 G1 gates、不据此转移,候选继续留在 `tracking` 等待合规复查。G0(合法性与安全)按闸门契约先于一切执行,复查时零成本再问一次:目标平台 ToS 改了吗?这个任务的市场是否已被欺诈供血?G0 翻转同样提议 `rejected`——出口清单里的"G0 或 G1 翻转"就是指这两道。
2. **看 SERP 变化(即 G2/G3 的变化复看)。** 对照上次观察:竞品到位了吗?官方文档/工具出现了吗?谁在占坑?读完整首页,按"做什么"分类。完整复核六条 `g6_tentative_lines`，然后分别判定两条独立的 rejected 出口：
   - **G3 占位否决**：只有当前暂定通过线全部依赖自然流量（affiliate / advertising）时，竞品占位到 G3 否决线才提议 `tracking→rejected`。此时 affiliate / advertising 可以仍是 `tentative_pass`，决定性失败是 G3，不是“六线全灭”。subscription / lead_generation / transaction / paid_report 任一暂定可行时，占位事实只更新竞争记录。
   - **G6 无适用盈利线**：只有全部适用线都是 `tentative_veto` 时，才可以“无适用盈利线”为理由提议 `tracking→rejected`；不得伪造正式 `gates.G6=veto`。
   **复查范围就是 G0/G1 + G2/G3,不复查 G4/G5**——那两道是方向的固有属性,扫描期定了就不随时间变化(理由见闸门契约时间光谱表下「形成期为什么不是 G1–G5 全复查」)。**唯一的例外不由本 skill 触发**:扫描侧新归并出一个陷阱类别、而某个在追踪的候选正好命中它时,那是重新认识,由做归并的一方当场提议 `tracking→rejected`(生命周期契约 rejected 边第⑥种情形);本 skill 不为此例行重跑 G5。
3. **看命名定型。** 回访来源社区:叫法统一了还是分裂了?aliases 有没有胜出者?
4. **看需求形成信号。** 自动补全出现?首批 Semrush 行出现?讨论持续增长?(形成期允许轻量 Semrush 探针,仅限能改变决策的查询。)
   - 本次观察必须结构化写 `naming_status=unstable|stabilized` 与 `formation_signals`。合法信号为 `autocomplete / semrush_rows / sustained_discussion / repeated_independent_queries`；没有信号时写空数组，不得用叙述性乐观判断替代。
   - 若本次来源新暴露 G6 结构事实，写 `g6_entry_veto`：不重复只约束 subscription，官方不计数只约束依赖该口径的算式，二者必须随完整六线暂定结论判断；只有自助结果依法对所有声称交付均无效时才可独立提议 rejected。
5. **对照 expiry 与失效条件。** 失效条件命中或 expiry 已过 → 如实报告。
6. **写观察文件并登记复查:** observation 的 `gates` 只列本次实际重跑且证据条件合规的门;合规重跑 G1 时必须写本次 G1 结论,G1=`veto` 时还必须写 `cluster_counterfactual=atomic_only`,环境污染时则不写 G1。`g6_tentative_lines` 写本次复核后的逐线暂定结论,`source_urls` 列实际打开的页面。仅登记复查而不转移时用 checked;随后若 transition 提交 gates,复用这份观察作为 `--evidence`,registrar 会逐门核对。

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py checked \
  --slug <slug> --evidence "证据/<slug>/<日期>-track.json" --by xinci-track
```

7. **向用户提交提议清单**,每候选一条,五种出口(继续追踪 / 续期修订 / formation_confirmed / expired / rejected):
   - 继续追踪(观察已更新,无需转移);
   - 提议续期或字段修订(expiry 延后、aliases/失效条件追加),用户确认后:

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py amend \
  --slug <slug> --by xinci-track --reason "<用户确认的续期/修订理由>" \
  [--expiry YYYY-MM-DD] [--add-alias <胜出的叫法>] [--add-invalidation "<新失效条件>"]
```

   - 提议 `formation_confirmed`(要求:累计 ≥2 次 -track 观察且最早与最新相隔 ≥7 天、命名定型、≥1 项形成信号、本次 G1=pass);
   - 提议 `expired`(expiry 已过时提交 `--expiry-trigger date`;失效条件命中时提交 `--expiry-trigger invalidation`)或 `rejected`(G0/G1 翻转;占位否决按盈利线生效时竞品到达 G3 否决线;第 2 步复核后六条适用线全部 `tentative_veto`;或第 4 步 `self_serve_legal_effect` 证明全部声称交付依法无效)。(「命中新归并的陷阱类别」那一条 rejected 由扫描侧提议,不在本清单里,见上第 2 步。)
8. **用户确认后**才执行对应 transition；用 `run_manifest.py record-single --date <YYYY-MM-DD> --skill xinci-track [--suffix <HHMM>] ...` 原子写运行清单，控制器拒绝覆盖，不得手写 JSON。例外:xinci-run 连续运行模式下不另写本阶段清单,内容并入 run 清单。

## 硬规则

- 每次复查必重跑 G1、并零成本重核 G0,不许沿用上次结论。
- 提议与执行分离:本 skill 永不直接改状态,一切转移经用户确认。例外:xinci-run 连续运行模式下,启动命令即标准授权,无需逐条确认。
- expiry 已过的候选必须给出明确提议(expired,或说明为何值得用户续期并给新 expiry),不许沉默跳过;续期必须由用户确认并附理由,经 registrar amend 执行——手工编辑账本是禁止的。
- 不自我调度:不设 next_check、不承诺"下次几天后查"、不催促用户。
- `tracking_schedule.py` 从候选**首次进入 tracking**的 history 时间派生第 3/7/14 天只读提示（旧记录无 history 才回退首见时间）；它不自动唤起、不自动复查、不自动转移。
- 复核 `g6_tentative_lines` 时看六条盈利线；只有所有适用线都为 `tentative_veto` 才能以“无适用盈利线”提议 rejected。历史两线观察只证明当时检查过的两线，不能冒充其余四线已否决。
- Semrush 探针仅限形成期(即 `tracking` 状态本身,按状态判不按年龄)、仅限能改变决策的查询;查了改变不了提议的,不查。
- 观察写要点不写转录;未打开的页面不得列入 source_urls。
