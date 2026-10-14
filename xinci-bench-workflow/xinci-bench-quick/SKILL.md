---
name: xinci-bench-quick
description: '新词快道：暗号 xinci_bench_quick_run 或 /xinci-bench-quick。抓最近 1 周到 3 个月才冒出来、首页还没人做、会反复被搜的新词（新游戏、新产品、新规则带出的 calculator/codes/tracker 等任务），锚词换算 Trends 量级，预计上线 90 天内单月 ≥1 万英文区访问就判 go 并强烈推荐建站。不是 xinci_bench_run（标杆道）。'
---

# 新词快道

行动前读 `xinci-bench-workflow/xinci-bench-core/选站契约.md` 第 10 节与第 1、7 节，`数据采集.md` 第 4、6、7 节；命令与观察字段见 `命令与观察.md` 第 7 节。脚本都在 `xinci-bench-workflow/xinci-bench-core/scripts/`。暗号即授权既定的观察、账本、原料池和清单写入，不重复确认。

1. `report_status.py` 确认数据区；未配置才问用户。`run_log.py --plan --lane quick`：有未完成的快道运行就恢复它；没有才写 started 清单（运行编号字母数字连字符）。
2. **先提醒**：看板里每个"【立即建站】"行原样放进汇报最前面；验收节点到了的一并提醒。
3. **复查观察中**：每个 watching 方向重测量级（必要时重看首页），写新观察，`ledger.py watch-check --slug <方向> --ref <新观察>`；建议是 go 或否决就用 `settle.py` 结算，建议是 watching 就继续观察。
4. **扫信号**：`quick_pool.py expire`；按 `数据采集.md` 第 7 节取上游新对象与 Trends 飙升词，对新对象跑 `suggest_snapshot.py --object`；把取回的对象与说法写成一份 `quick_signal` 观察，`quick_pool.py add`。没在本次实际取回的来源不写"已检查"。
5. **零成本速判** Q1–Q4（Q1 的日期按第一次让大量普通用户用上的那天，不按公布日，见契约 10.4），再对剩下的用内置浏览器看首页判 Q5、Q6（两次请求间隔 ≥ 60 秒，每次最多 10 个词，按 `quick_pool.py pending --top 10` 的顺序取）。每个词写一份 `quick_screen` 观察；不过的 `quick_pool.py reject`；Q5 不过且占位的是小站，加 `--seed-domain` 同时登记为标杆道种子。
6. **登记与测算**：六条全过的 `ledger.py register-quick`；英文区 6 国（US、GB、CA、AU、NZ、IE）各做一次锚词换算：美国的锚词先查 `lexicon.py`，没有再用 Semrush，美国以外的锚词月量一律用 Semrush 查；先用美国的锚词在 Trends 页面把 6 国曲线都取一遍（`scripts/trends_fetch.js`，不花 Semrush），交给 `trends_volume.py`：读不出的国家自动记 0，只为它列出的国家去 Semrush 查锚词月量，补齐后由它写入 `quick_volume`（命令与观察 §7.5），不手算；预计能过线的写 `quick_brief`；`ledger.py update --ref` 引用后 `ledger.py quick-preview` 看三档。
7. **结算**：按预览建议 `settle.py --verdict go|watching|rejected|parked`，`--reason` 一句理由，`--biggest-unknown` 写最可能让结论翻转的一项；全部结束后 `validate_ledger.py`，再 `run_log.py --finish`。
8. **出 go 时强烈推荐**（缺一不可）：
   - 调用推送通知工具，内容含方向、基准访问与收入、建议最晚上线日期；
   - 汇报第一行以"【立即建站】"开头，写方向、基准访问与收入、建议最晚上线日期、决策书路径；
   - 说明决策书开头的"立即建站"一节，以及之后每次运行都会再提醒，直到用户说已开建或放弃（用 `ledger.py follow-up` 记）。

汇报：各来源取回多少、原料去重后多少、各速判条不过多少、登记多少、go / 观察中 / 否决（按门）/ 搁置数、观察中剩余天数、Semrush 调用数。不建站、不改假设表；用户说已开建、已上线或放弃时，照用户说的用 `ledger.py follow-up` 记。

动 Semrush 之前先看 `run_log.py --plan` 的 `semrush_stop`：为 true（今天两条道合计已用到 90 次）就不再开始花 Semrush 的步骤，当前阶段按 blocked 收尾，改天接着跑。
