---
name: xinci-bench-assess
description: '标杆倒推选站的深核与决策：对已登记的方向核起量手段、测方向需求、读 Google 首屏与 AI 概览、写差异点与交付依据，用标杆份额法算上线第 12 个月访问与收入，出 go/否决/搁置决策书，go 时附建站简报。用于 bench assess、深核方向、出建站简报；发现标杆用 xinci-bench-scan。'
---

# 深核与决策

行动前读 `xinci-bench-workflow/xinci-bench-core/选站契约.md` §1、§4–8 与 `数据采集.md` 全文；观察字段与命令见 `命令与观察.md` §4–5。脚本都在 `xinci-bench-workflow/xinci-bench-core/scripts/`。

1. `run_log.py --plan` 核对恢复位置，写 assess started 清单。`ledger.py rank` 取前 2 个 found（用户指定优先；不足 2 个核全部）。
2. 每个方向按契约 §4 六步走，每步先 `date -u` 取时间、写观察、记本观察的 Semrush 调用数：
   1. 每个标杆一份 benchmark：曲线、引荐域名与锚文本、三次垃圾更新前后、ads.txt、定价页；
   2. 一份 demand：先 `lexicon.py --match <主题词>` 查旧词库与旧裁决，再按需用 Keyword Magic 补测，每簇种子词用 Keyword Overview 取 6 国月量换算英文区簇量，对手流量按网址筛；
   3. 3–5 份 serp：内置面板预检通过后读首屏，两次请求间隔 ≥ 60 秒；
   4. 一份 differentiation、一份 delivery；准备判 go 时再写一份 brief。
3. 每步之后用 `ledger.py update --patch <补数> --ref <观察>` 把结构化结果补进方向记录；clean 只能给初核全过且非外链驱动的标杆。
4. `bench_model.py --direction <slug>` 看三档。可以提前否决：范围命中、标杆不成立、所有簇被答完，或基准明显 < $100，都不必走完六步。
5. `settle.py` 结算（go / rejected+gate / parked），`--reason` 写一句结论理由，`--biggest-unknown` 写最可能让结论翻转的一项。它会生成决策书 md/html 并校验；失败按报错补证据后用同一命令重跑。
6. 全部方向结束后 `validate_ledger.py`，再 `run_log.py --finish`。汇报每个方向的结论、基准第 12 个月访问与收入、决策书路径、用到的未确认假设和 Semrush 调用数。

不改门槛和假设表；取到"内容类/游戏类 RPM""Journey RPM""付费转化率"的证据时，写进观察 points 并在汇报里单独列出，由用户决定是否升版。建不建站由用户决定。

汇报前先跑 `report_status.py`：看板第一屏有"【立即建站】"行时，原样放在汇报最前面（新词快道的 go 在用户标已开建或放弃之前，每次都要再推荐一次）。

动 Semrush 之前先看 `run_log.py --plan` 的 `semrush_stop`：为 true（今天两条道合计已用到 90 次）就不再开始花 Semrush 的步骤，当前阶段按 blocked 收尾，改天接着跑。
