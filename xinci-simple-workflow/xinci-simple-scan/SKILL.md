---
name: xinci-simple-scan
description: '流量型选词的发现层:从 Semrush 词根轮换、小站反推、论坛问题三条来源找已有真实搜索量且守得弱的主题簇,零成本排除后注册为 found 并算代理排序。当用户说 simple scan、扫一批老词、找有流量的簇、跑词根时使用。English triggers: simple scan, mature keyword sweep, traffic niche discovery. 这是 xinci-simple-workflow(流量型),不是 xinci 新词工作流;现场核验用 xinci-simple-verify,看板用 xinci-simple-status。'
---

# xinci-simple-scan 发现

从已有真实搜索量的英文词里找主题簇，零成本排除后注册为 `found`。本 skill 不开 Google SERP、不做现场核验——那是 xinci-simple-verify 的事。

行动前必读：`xinci-simple-workflow/xinci-simple-core/选词契约.md` §1、§3、§4、§7；`xinci-simple-workflow/xinci-simple-core/数据采集.md` §1、§2。判据全部以契约为准，本文件只串流程。

## 第 0 步：确认数据区

```bash
python3 xinci-simple-workflow/xinci-simple-core/scripts/report_status.py
```

正常返回看板 → 已配置，往下走。退出码 2 提示"数据区未配置" → 停下问用户数据区放哪，不替用户选；拿到路径后：

```bash
python3 xinci-simple-workflow/xinci-simple-core/scripts/init_workspace.py --data-root <用户给的路径>
```

## 工作流

1. **选来源。** 用户指定则用指定的（来源类型 / 词根 / 小站域名 / 论坛帖）。否则按运行清单里上次用的轮换：词根 → 小站 → 论坛 → 词根…；词根按 `数据采集.md §2.3` 词根表顺序，跳过本轮已跑的。
2. **Chrome 通道打开 Semrush**，按 `数据采集.md §2.2` 取预览。每条候选记：主词、簇量（total volume）、top 20 支撑词（词 / 月量 / KD）、主词 KD、Keyword Overview 底部 SERP overview 的前 10 条 Authority Score（数 AS < 30 的条数 → `low_dr_count`，并把 AS 列存进观察供 verify 用）、首页 reddit / quora / 论坛条数（`ugc_count`）、首页可见日期中位数（`content_age_median_days`，取不到记 null）。
3. **零成本排除四条**（契约 §1），命中即弃，弃的原因在最终报告里归类计数，不注册。
4. **准入**（契约 §3.3）：簇量 ≥ 50,000 或主词 ≥ 5,000。不达标不注册。
5. **写 scan 观察** `证据/<slug>/<日期>-scan.json`（字段见 `数据结构/observation.schema.json`；必含 `semrush_preview` 与 `source_urls`），然后 `ledger.py register`。
6. **排序**：`rank.py` 回写 `rank_score` 并打印 top 10。
7. **写运行清单**：`run_log.py`，`--billable-calls` 如实计 Semrush 查询数，`--source-opened` 记本次实际打开的每个 URL。
8. **向用户报告**：注册了几个、排序前 10、排除了几个及原因分布、Semrush 用了几次、下次轮到哪个来源。

一次调用目标 20–50 个 `found`。来源枯竭如实说，不凑数。

## 硬规则

- 不做现场核验；不用 Chrome 读 Google SERP；不登录内置面板。
- 每次 Semrush 查询能改变决策才跑；预览优先，CSV 只在能改变决策时导。
- 排除与准入只按契约 §1、§3.3，不临场加减条件。
- slug 小写连字符，与主词一一对应；同一簇不重复注册（`ledger.py list` 先查）。

## 命令模板

```bash
python3 xinci-simple-workflow/xinci-simple-core/scripts/ledger.py register \
  --slug heic-to-jpg-converter --primary-keyword "heic to jpg converter" \
  --cluster-json '{"total_volume":182000,"keywords":[{"term":"heic to jpg","volume":90500,"kd":38},{"term":"heic to jpg converter","volume":40500,"kd":41}]}' \
  --seed-json '{"type":"root","value":"Converter","queried_at":"2026-09-10T03:12:00+00:00"}' \
  --proxy-json '{"kd":38,"low_dr_count":4,"ugc_count":2,"content_age_median_days":540}' \
  --evidence "证据/heic-to-jpg-converter/2026-09-10-scan.json" \
  --by xinci-simple-scan --reason "准入:簇量 182K,四条排除未命中"

python3 xinci-simple-workflow/xinci-simple-core/scripts/rank.py --top 10

python3 xinci-simple-workflow/xinci-simple-core/scripts/run_log.py --date 2026-09-10 --skill xinci-simple-scan \
  --source-opened "https://www.semrush.com/analytics/keywordmagic/?q=converter&db=us" \
  --candidate-touched heic-to-jpg-converter \
  --billable-calls 3 --note "词根 Converter,预览 50 行,注册 7 个,排除 12 个(YMYL 3 / 品牌 5 / 平台原生 4)"
```

`seed.type` 取 `root` / `small_site` / `forum`；`value` 分别是词根名 / 小站域名 / 论坛帖 URL。同日再次运行 `run_log.py` 加 `--suffix HHMM`。
