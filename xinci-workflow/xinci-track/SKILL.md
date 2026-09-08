---
name: xinci-track
description: '复查 new 道中处于追踪状态(tracking)的候选，或复核 recheck_after 已到的 new rejected 候选。当用户说复查追踪清单、看看候选 X 现在什么情况、复查 watchlist 时使用。English triggers: recheck candidates, track watchlist, re-observe keyword. 何时查由用户决定;可指定候选,未指定时该次调用默认授权遍历全部 lane=new 的 tracking 候选。mature 在 formation_confirmed 前由 xinci-mature 承接,不由本 skill 处理。本 skill 不自我调度。'
---

# xinci-track 追踪复查

先读 `xinci-workflow/xinci-core/通用约定.md`，再按需读取生命周期契约「受控重开」「每转移的证据要求」「时间字段」；闸门契约「时间光谱」及本次实际复核的 G0–G3；数据采集指南「G1 SERP 读取规程」「Semrush 探针纪律」。出现新结构性模式时先读 `陷阱速查.md`，疑似命中后再读完整类别。

输入:`lane=new` 且状态为 `tracking` 的候选,或用户从 xinci-status 到期复核清单中指定的 `state=rejected,recheck_after≤今天` 候选。用户指定则只查指定项;未指定则只遍历 tracking,不得自动重开 rejected。指定项若是 mature,只报告"应交 xinci-mature",不写入。

### rejected 的受控重开

只复核最近一次拒绝中的 G1/G2/G3 veto。取得晚于拒绝时间的新 `-track.json` 现场观察,并把当时每一道 veto 明确翻转为 `pass`;缺一项就保持 rejected。先向用户提议,确认后执行:

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py reopen \
  --slug <slug> --by xinci-track --reason "<哪些 SERP 事实发生了变化>" \
  --evidence "证据/<slug>/<日期>-track.json"
```

重开后状态回到 captured、旧窗口闸门清空,后续交 xinci-scan 重跑完整初筛。G0/G4/G5 结构性否决不可重开;本入口不接受 mature。

## 追踪共用操作

以下操作由 new 道的 xinci-track 与 mature 道的 xinci-mature 共用；输入与 `--by` 按通用约定的 lane 边界，复用操作不转移候选所有权。

1. **重跑 G1,同批零成本重核 G0。** 真浏览器搜精确词(美区桌面未登录)。判据与站点簇反事实见闸门契约 G1;环境不合规时只记带环境说明的观察,不写 G1 gates、不据此转移,候选留在 `tracking`。G0 或 G1 翻转 → 提议 `rejected`。
2. **看 SERP 变化(G2/G3 复看)。** 对照上次观察读完整首页,按"做什么"分类。完整复核六条 `g6_tentative_lines`,占位否决是否生效按闸门契约 G3「前置:G3 的否决只对"靠自然位吃流量"的模式生效」;六条适用线全部 `tentative_veto` 时按生命周期契约 rejected 边第⑦种提议 `rejected`。
   常规复查范围只有 G0/G1 + G2/G3,不重跑既有 G4/G5(见闸门契约「时间光谱与适用矩阵」)。若本次证据暴露尚未成册的新结构性陷阱,本 skill 只形成“新增类别 + 当前候选归并”的提案;新增通用判据属于契约变更,须用户确认。确认后由本 skill 补入陷阱类别与索引,并按 rejected 第⑥种提议当前候选转移;连续运行只记 notes 等待确认,不得静默改契约。
3. **看命名定型。** 回访来源社区:叫法统一了还是分裂了?aliases 有没有胜出者?
4. **看需求形成信号。** 自动补全、首批 Semrush 行、讨论增长。Semrush 探针仅限 `tracking` 状态(按状态判不按年龄)、仅限能改变决策的查询;查了改变不了提议的,不查。
   观察必写 `naming_status=unstable|stabilized` 与 `formation_signals`,合法取值 `autocomplete / semrush_rows / sustained_discussion / repeated_independent_queries`,无信号写空数组,不得用叙述性乐观判断替代。
   新 G6 事实按闸门契约逐线记录；计数缺口记 points 与未知，不写历史 official_count_class 入口否决。其他结构事实的出口见生命周期契约。
5. **对照 expiry 与失效条件。** 命中或已过 → 如实报告,不许沉默跳过。
6. **写观察文件并登记复查。** `证据/<slug>/<日期>-track.json`,`schema_version: 3`。`gates` 只列本次实际重跑且证据合规的门(G1=`veto` 时须带 `cluster_counterfactual=atomic_only`);`g6_tentative_lines` 写本次逐线暂定结论;`source_urls` 列实际打开的页面。
   历史只含两线的观察只证明当时那两线,不能冒充其余四线已否决。仅登记不转移用 checked;随后 transition 提交 gates 时复用这份观察作 `--evidence`,registrar 逐门核对。
```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py checked \
  --slug <slug> --evidence "证据/<slug>/<日期>-track.json" --by xinci-track
```

7. **向用户提交提议清单**,每候选一条,五种出口:
   - 继续追踪(观察已更新,无需转移);
   - 续期或字段修订(expiry 延后、aliases / 失效条件追加),须附理由,用户确认后:
```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py amend \
  --slug <slug> --by xinci-track --reason "<用户确认的续期/修订理由>" \
  [--expiry YYYY-MM-DD] [--add-alias <胜出的叫法>] [--add-invalidation "<新失效条件>"]
```

   - `formation_confirmed`:累计 ≥2 次 `-track` 观察且跨度达标(按自然日,口径与最早可推进日见生命周期契约「时间字段」;`report_status.py` 直接给出 `formation_eligible_date`)、`naming_status=stabilized`、`formation_signals` ≥1 项、本次 G1=pass;
   - `expired`:expiry 已过用 `--expiry-trigger date`,失效条件命中用 `--expiry-trigger invalidation`;
   - `rejected`:第 1 步 G0/G1 翻转;第 2 步占位否决生效或六条适用线全部 `tentative_veto`;第 4 步 `self_serve_legal_effect` 证明全部声称交付依法无效。
8. **用户确认后**执行对应 transition(字段见生命周期契约「每转移的证据要求」，参数见「CLI 入口」),再按通用约定写运行清单(`--skill xinci-track`)。

## 硬规则

- 不自我调度:不设 next_check、不承诺"下次几天后查"、不催促用户。`tracking_schedule.py` 只从首次进入 tracking 的 history 时间派生第 3/7/14 天只读提示,不唤起、不复查、不转移。
