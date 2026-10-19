---
name: xinci-bench-quick
description: '新词快道：暗号 xinci_bench_quick_run 或 /xinci-bench-quick。抓最近才冒出来、首页还没人做、会反复被搜的新词（游戏开放游玩后 2 周内，其他 3 个月内；新游戏、新产品、新规则带出的 calculator/codes/tracker 等任务），并列出即将开玩的游戏，锚词换算 Trends 量级，预计上线 90 天内单月 ≥1 万英文区访问就判 go 并强烈推荐建站。不是 xinci_bench_run（标杆道）。'
---

# 新词快道

行动前读 `xinci-bench-workflow/xinci-bench-core/选站契约.md` 第 10 节与第 1、7 节，`数据采集.md` 第 4、6、7 节；命令与观察字段见 `命令与观察.md` 第 7 节。脚本都在 `xinci-bench-workflow/xinci-bench-core/scripts/`。暗号即授权既定的观察、账本、原料池和清单写入，不重复确认。

1. `report_status.py` 确认数据区；未配置才问用户。`run_log.py --plan --lane quick`：有未完成的快道运行就恢复它；没有时，`quick_new_round_allowed` 为 false（今天已开过一轮）就不开新的一轮，告诉用户每天最多 1 轮、改天再触发（用户明确说今天再跑才破例）；暗号带数字 N 也只跑今天这 1 轮，汇报里说明其余轮次分天跑；可以开时才写 started 清单（运行编号字母数字连字符），`--seed-value` 列出本次要取的来源，必须含 Trends 飙升词、Wikipedia 发售表、补全字母展开与非游戏上游。
2. **先提醒**：看板里每个"【立即建站】"行原样放进汇报最前面；验收节点到了的、"即将开玩"里建议今天跑的一并提醒。再带上看板的六类上线前预判提醒，各按看板原文列出：可预判（开玩日在预判窗口内的游戏，带 `reforecast` 与 `reason`）、复核到期、预判失准（建议停止追加投入）、开玩日推迟（累计超过上限，请用户重新评估）、预判后搁置的方向已开玩（开玩后 14 天内可按现行路径重新判 go，做法见第 8 步）、补参照与更新参照；看板有"参照不可用"行的也原样列出（那条参照被跳过、不参与取倍数，要用就重新 `quick_reference.py build`；原因写"口径已变,需重测"的，是假设表改过、旧口径的参照，同样要重测）。
3. **复查观察中**：每个 watching 方向重测量级（必要时重看首页），写新观察，`ledger.py watch-check --slug <方向> --ref <新观察>`；建议是 go 或否决就用 `settle.py` 结算，建议是 watching 就继续观察。预判方向（记录里 `basis` 为 `forecast`）复核日（开玩日 + 7 天）前 `watch-check` 会拒收，到了才复查：速判要开玩后看的，量级用 `trends_volume.py --term` 测该方向登记的说法之一（对象名的量不算），第一次复查后到期日改为复查日 + 30 天；没复查过之前 `settle.py` 不收这类方向的 go 与 volume、oneoff 否决（看板"复核到期"里列出的、`validate_ledger.py` 报"到了复核日，先跑 watch-check"的，先复查再结算）。**预判 go 到了复核日**（看板"复核到期"）：对每项任务测任务词的量级（`trends_volume.py --term <任务词>`，词取该任务在预判观察里的说法之一，一项任务一份，复核日当天或之后测、6 国都测，只测美国的会被拒收），跑 `ledger.py review-forecast --slug <方向> --ref <各任务的量级观察>`；`stop` 为 true 就在汇报里写"预判失准，建议停止追加投入"，要不要放弃由用户定，不自己改状态。开玩前判观察中、开玩后才判 go 的方向不用复核。
4. **扫信号**：`quick_pool.py expire`；按 `数据采集.md` 第 7 节取上游新对象，其中四项每次都要取：
   - **Trends 飙升词**：Trends 页面里用 `scripts/trends_fetch.js` 的 `xinciTrendsRising`，种子照第 1 步 `run_log.py --plan --lane quick` 输出里的 `rising_seeds` 取，6 个，`cat` 照给的写，不自己换，两次执行间隔 ≥ 30 秒，遇 429 停下，没查的种子写"本次未取"；
   - **Wikipedia 发售表**：`wiki_releases.py --output <scratchpad>/wiki_releases.json`（最近 14 天已上线与未来 30 天要上线的），把输出的 items 并进本次信号观察，浏览量没取到的也一起并进；
   - **补全字母展开**：`suggest_discover.py --output <scratchpad>/discover.json`（4 个前缀接 a–z，不花 Trends），items 并进本次信号观察；第一次跑只建基线、没有新对象，汇报里写明；
   - **非游戏上游**：`upstream_fetch.py --output <scratchpad>/upstream.json`（Product Hunt、Show HN、GitHub、联邦公报近 7 天），逐条看 items 里命中的说法是不是在说这个新对象，挑出来的才并进；政策条目只列出，由你判断有没有带出新的计算、查询需求。
   对新对象跑 `suggest_snapshot.py --object`；处在测试、抢先体验或即将上线的对象，原料写 `playable_at`（第一次让大量普通用户用上的日期）与 `stage`，还没到这天的只进即将开玩（`quick_pool.py upcoming`），不看首页。把取回的对象与说法写成一份 `quick_signal` 观察，`quick_pool.py add`。没在本次实际取回的来源不写"已检查"。
5. **上线前预判**（契约 10.9，命令与字段见 `命令与观察.md` §7.7，取数规程见 `数据采集.md` §7.6）：
   - 取看板 `report_status.py --json` 里 `quick.forecast_window`（开玩日在预判窗口内的游戏），**只取 `reforecast` 为 `new`（没预判过）或 `due`（判过、现在可以重做）的行**，看板已把它们排在前面（再按开玩日），**每轮最多预判 2 个**；`wait`（还不到时候）、`no`（不再预判）的不做，行里的 `reason` 是大白话原因，汇报时原样列出；没有 `new`、`due` 就跳过本步。重做规则（契约 10.9）：每款游戏最多预判 2 次；上次量不够或美国读不出的，要等到开玩前 9–3 天才重做；参照不足的，补够参照才重做；P4、P5、P6 不过的，开玩后按现行路径看，不再预判；`measure_rest` 补测其余 5 国后重做。Trends 不够用时按优先级取：本轮飙升词 > 复核到期 > 预判 > 补参照，没做的写"本次未取"；
   - 每个对象：`suggest_snapshot.py --object` 找任务说法，定最小版本要做的 1–4 项任务；先判零成本的 P1、P3（`quick_reference.py summary` 看参照够不够）、P4，有不过的就不再花配额（后面写 `pass: null`）；再看美国首页判 P5、P6（"<游戏名> <任务词>"与"<游戏名> wiki"各一次，间隔 ≥ 60 秒，**这两次查询计入当轮 10 个首页名额**）；再**只测美国**的对象名量（`trends_volume.py --term <对象名>`，其余 5 国放 `skipped`）；用 `quick_forecast.py --input` 生成预判观察，不手算；
   - 看它给的 `suggestion`：`skip` 只记观察；`measure_rest` 补测其余 5 国后重跑；`go` 或 `watching` 才登记：写最小版本简报素材 `quick_brief`（go 必须），`ledger.py register-quick`，输入里用 `forecast` 键写预判观察路径（不写 `screen`；`object.type` 写 `game`，`first_public` 写开玩日），再 `ledger.py update --ref` 引用简报素材。预判方向不能用 `ledger.py quick-preview`（它读开玩后的当前量，会拒收），看 `quick_forecast.py` 的输出；
   - 有 Trends 余量时补参照：看板 `references_due` 每行一项，先 `quick_reference.py time-range` 得日期范围，再在 Trends 页面跑两次 `xinciTrends`（对象名 + 锚词、任务词 + 锚词，间隔 ≥ 35 秒），交给 `quick_reference.py build`；参照库不够时每轮补 2–4 条。
6. **零成本速判** Q1–Q4（Q1 的日期按第一次让大量普通用户用上的那天，试玩版也算，不按公布日；游戏须在那天之后 14 天内、其他 90 天内，见契约 10.4；查不到日期的如 Roblox 体验照常看首页，日期尽量从首页读，首页也读不到就用 `xinciTrendsFirstSeen` 查"<体验名> roblox"的 Trends 首次出现日），再对剩下的用内置浏览器看首页判 Q5、Q6（两次请求间隔 ≥ 60 秒，每次最多 10 个词，预判已用掉的名额要扣掉，按 `quick_pool.py pending --top 10` 的顺序取）。每个词写一份 `quick_screen` 观察；不过的 `quick_pool.py reject`；Q5 不过且占位的是小站，加 `--seed-domain` 同时登记为标杆道种子。Roblox 体验的原料写 `platform: "roblox"`（它的兑换码会自动排到其他说法后面）；DLC、资料片按新对象算；首页看过但对象还没上线、日期不明，既不登记也不淘汰的，不写速判观察，汇报里列出。
7. **登记与测算**（速判登记；预判登记在第 5 步）：六条全过的 `ledger.py register-quick`（`object.type` 写 `game` 或 `other`）；英文区 6 国（US、GB、CA、AU、NZ、IE）各做一次锚词换算：美国的锚词先查 `lexicon.py`，没有再用 Semrush，美国以外的锚词月量一律用 Semrush 查；先用美国的锚词在 Trends 页面把 6 国曲线都取一遍（`scripts/trends_fetch.js`，不花 Semrush），交给 `trends_volume.py`：读不出的国家自动记 0，只为它列出的国家去 Semrush 查锚词月量；锚词在某国热度为 0 就换锚词重查，读得出的国家不能放进 skipped 按 0 计；补齐后由它写入 `quick_volume`（命令与观察 §7.5），不手算；预计能过线的写 `quick_brief`；`ledger.py update --ref` 引用后 `ledger.py quick-preview` 看三档。
8. **结算**：按预览建议 `settle.py --verdict go|watching|rejected|parked`，`--reason` 一句理由，`--biggest-unknown` 写最可能让结论翻转的一项；全部结束后 `validate_ledger.py`，再 `run_log.py --finish`。预判方向开玩前只能结算 `go`、`watching` 或 `parked`，**不能 `rejected`**（要否决等复核日按现行路径），结论按 `quick_forecast.py` 的 `suggestion`（`go` 只认 `go`，`watching` 只认 `watching`）；结算被拒按原因处理：报"口径已变,重做预判"（预判观察自己的口径过时）的，对象名量级观察不是预判当天或之前 2 天内测的就先重测，再重新 `quick_forecast.py`，用 `ledger.py update --ref` 引用新的预判观察与对象名量级观察后再结算；报"参照 … 口径已变,需重测"（看板"参照不可用"也会列）的，先用 `quick_reference.py build` 重测这些参照，再照前一种重新预判。预判后搁置的方向开玩后要判 go：最新速判须在开玩日当天到开玩后 14 天内重做（量级观察在开玩日或之后），不满足 `settle.py` 拒收；游戏推迟了的，要在新开玩日到来前用下面的 `ledger.py update` 记下新开玩日，窗口跟着走，过了窗口又没推迟的只能否决或继续搁置；否决不受这条限制。开玩日变了（官方延期或提前）：`ledger.py update --slug <方向> --patch <含 {"object": {"first_public": "<新开玩日>", "date_source": "<出处>"}} 的文件>`，新日期须在今天之后，found、watching、go、parked 都能改；已结算的方向复核日与建议最晚上线日自动顺延，累计推迟超过上限看板会提醒；开玩前（还没结算）改了开玩日要重做预判、写新的 `quick_forecast` 并 `ledger.py update --ref` 引用后再结算。
9. **出 go 时强烈推荐**（缺一不可）：
   - 调用推送通知工具，内容含方向、基准访问与收入、建议最晚上线日期；
   - 汇报第一行以"【立即建站】"开头，写方向、基准访问与收入、建议最晚上线日期、决策书路径；预判 go 的建议最晚上线日是开玩日前 1 天（不是判 go 后 7 天），基准按参照库下四分位倍数预测，要标"开玩前预判"并写复核日（开玩日 + 7 天）；
   - 说明决策书开头的"立即建站"一节，以及之后每次运行都会再提醒，直到用户说已开建或放弃（用 `ledger.py follow-up` 记）。

汇报：各来源取回多少（Trends 飙升词按种子词列，没取到的写本次未取）、原料去重后多少、即将开玩几个及建议跑快道的日期、预判了几个与各自的建议（go / watching / skip / measure_rest）、补了几条参照、复核了几个预判（实测与预测下四分位的比）、各速判条不过多少、登记多少、go / 观察中 / 否决（按门）/ 搁置数、观察中剩余天数、Semrush 调用数。不建站、不改假设表；用户说已开建、已上线或放弃时，照用户说的用 `ledger.py follow-up` 记。

动 Semrush 之前先看 `run_log.py --plan` 的 `semrush_stop`：为 true（今天两条道合计已用到 90 次）就不再开始花 Semrush 的步骤，当前阶段按 blocked 收尾，改天接着跑。
