---
name: xinci-simple-verify
description: '流量型选词的现场核验层:对 found 候选按排序取前 N,在美区未登录浏览器做 G1 Google 直答、G2 首页结构、G3 可打败性、季节性与范围复核,跑收入模型,通过的出机会报告。当用户说 simple verify、核验前几个、验一下 X、出报告时使用。English triggers: simple verify, verify traffic candidates, opportunity report. 这是 xinci-simple-workflow(流量型),不是 xinci 新词工作流;发现用 xinci-simple-scan。'
---

# xinci-simple-verify 现场核验

对 `found` 候选做 G1 / G2 / G3 / 季节性 / 范围复核，跑收入模型，通过的出机会报告。终点是 `verified` + `报告/<slug>.md`，或 `rejected` / `parked` 加写清楚的 reason。

行动前必读：`xinci-simple-workflow/xinci-simple-core/选词契约.md` §5、§6、§7、§8；`xinci-simple-workflow/xinci-simple-core/数据采集.md` §1、§3、§4、§5。判据全部以契约为准。

## 第 0 步：确认数据区

```bash
python3 xinci-simple-workflow/xinci-simple-core/scripts/report_status.py
```

退出码 2 → 问用户数据区放哪，`init_workspace.py --data-root <路径>`；正常则往下走。

## 工作流

1. **取目标。** 用户指定 slug 则用指定的；否则 `rank.py --no-write --top N`（默认 N=5）。
2. **预检。** 内置面板打开一次美区查询，按 `数据采集.md §4` 核四项，写进本轮每份 verify 观察的 `browser_preflight`。任一不合规 → 本轮不写 G1–G3 结论，只在 `points` 记原因，候选留 `found`，如实报告后停。
3. **逐候选现场核验**（按 `数据采集.md §3` 读整页）：
   - G1 直答（契约 §5.1）→ 做完了 → `rejected`
   - G2 首页结构（§5.2）→ 霸榜 → `rejected`；**不看前三条就下结论是违规**
   - G3 可打败性（§5.3）：数"完整完成 + DR ≥ 50 + 新鲜格式对"的 K；DR 取 scan 观察记的 SERP overview，缺则本次到 Semrush 补一次并计费 → K ≥ 3 → `rejected`
   - 季节性（§5.4）→ 集中 ≤ 3 个月 → `parked`
   - 范围排除复核（§5.5）→ 命中 → `rejected`
   - 写 verify 观察 `证据/<slug>/<日期>-verify.json`（字段见 `数据结构/observation.schema.json`：`browser_preflight` / `query_url` / `ai_overview` / `serp_top10` / `page2_note` / `trends_12m` / `scope_recheck` / `source_urls` / `points`）
4. **判形态** `form`（契约 §5.6），跑收入模型：
   ```bash
   python3 xinci-simple-workflow/xinci-simple-core/scripts/revenue_model.py \
     --form tool --cluster-volume 1600000 --niche tech --aio-present --strong-complete-count 1
   ```
   `--aio-present` 只在 AIO 存在且未做完时传；`--strong-complete-count` 传 G3 的 K（0/1/2）。
5. **出口**（契约 §6.4）：
   - 硬门否决 → `transition --to rejected`，reason 写"哪道门 + 现场看到什么"
   - 季节性 → `transition --to parked`，reason 写月份分布
   - `base ≥ 200`（当前门槛，见契约 §6.4）→ `transition --to verified --form <form> --revenue-json '<模型输出去掉 passes>'`，随后 `build_report.py --slug <slug>`
   - `base < 200` → `transition --to rejected`，reason 写"收入不足：base $X，差 $Y"
6. **写运行清单**：`run_log.py`，Google 与 Semrush 打开的 URL 都记进 `--source-opened`；`--billable-calls` 只计 Semrush。
7. **向用户报告**：每个候选一行——slug / 结论 / 决定性的门或 base / 报告路径。零通过如实说零。

## 硬规则

- 不得用 Chrome 读 Google SERP；`get_page_text` 不能用于判 G1（会跳过 AI Overview）。
- 不看满首页 + 第二页不下 G2 / G3 结论。
- 代理指标（KD / AS / KGR）不能单独否决；否决只出自 G1 / G2 / G3 / 季节性 / 排除 / 收入五处。
- 没通过就写 `rejected` 并给数字，不留 maybe、不留 `found` 等下次。
- 报告只由 `build_report.py` 生成，不手写、不手改。
- 门槛与假设表只能由用户变更。运行中发现门槛不合现实时，提交实测证据与提案，不自行改（判据变更后的翻案走 `ledger.py requalify`）。

## 命令模板

```bash
python3 xinci-simple-workflow/xinci-simple-core/scripts/rank.py --no-write --top 5

python3 xinci-simple-workflow/xinci-simple-core/scripts/revenue_model.py \
  --form tool --cluster-volume 1600000 --niche tech --aio-present --strong-complete-count 1
# → base $672(1.6M × CTR 0.10 × 0.6 × 0.7 ÷ 1000 × RPM $10)。当前门槛 $200:同样折减下 tool+tech 需簇量 476,190、tool+home 需 264,550

python3 xinci-simple-workflow/xinci-simple-core/scripts/ledger.py transition \
  --slug heic-to-jpg-converter --to verified \
  --evidence "证据/heic-to-jpg-converter/2026-09-11-verify.json" --by xinci-simple-verify \
  --reason "G1 pass(AIO 只罗列工具名未做转换),G2 pass(首页 6 条小站内页),G3 K=1(cloudconvert),base $672" \
  --form tool \
  --revenue-json '{"downside":336.0,"base":672.0,"upside":1008.0,"volume_needed_for_threshold":476190,"threshold":200,"assumptions_version":"2026-09-09.2","inputs":{"form":"tool","cluster_volume":1600000,"niche":"tech","aio_present":true,"strong_complete_count":1}}'

python3 xinci-simple-workflow/xinci-simple-core/scripts/build_report.py --slug heic-to-jpg-converter

python3 xinci-simple-workflow/xinci-simple-core/scripts/ledger.py transition \
  --slug some-term --to rejected \
  --evidence "证据/some-term/2026-09-11-verify.json" --by xinci-simple-verify \
  --reason "G1 直答:AIO 给出完整换算表并附示例,用户不必点任何结果"

python3 xinci-simple-workflow/xinci-simple-core/scripts/run_log.py --date 2026-09-11 --skill xinci-simple-verify \
  --source-opened "https://www.google.com/search?q=heic+to+jpg+converter&gl=us&hl=en&pws=0" \
  --source-opened "https://trends.google.com/trends/explore?geo=US&date=today%2012-m&q=heic%20to%20jpg" \
  --candidate-touched heic-to-jpg-converter --billable-calls 0 \
  --note "核验 5 个:1 verified / 3 rejected(G1×2,收入×1) / 1 parked"
```
