---
name: xinci-mature
description: '成熟错价词道(lane=mature)的发现与前半程推进:找量级真实存在、SERP 却守得很弱的成熟英文查询。从第一步就取并要求量级数据(与新词道的 Semrush 禁令相反),按先算钱再看防守的顺序跑量级前置过滤、G6 六线判定、G1/G2/G3 与弱守六信号,存活的注册为 lane=mature 并推进到 formation_confirmed。当用户说跑一轮成熟词、找错价词、走广告线、mature 道时使用。English triggers: mature lane, mispriced keywords, ad-line scan. 新词道的发现用 xinci-scan;确认期评分用 xinci-qualify,建站决策用 xinci-decide。'
---

# xinci-mature 成熟错价词道

找的不是新词,是**老词里被守得很弱的那一格**:量级真实存在,而占位者只有散文、老化内容或错配格式。量级证据使 advertising / affiliate 更容易审计，但本道仍须检查全部六条盈利线，不能预设只靠广告。

**这条线至今没有一个正例(种子口径 0/4;含探针的口径为 1/6 进入账本、那 1 个随后否决,见数据采集指南「本节的诚实状态」)。** 本 skill 的第一目标是让它可执行、可累积样本,不是假装它已经成立。每一轮都必须记命中率并据实修订判据——这是数据采集指南给本道立的规矩,不是客套。

> **路径约定**:相对路径以仓库根为基准(正本在 `xinci-workflow/xinci-mature/SKILL.md`,symlink 加载时 `readlink` 后上溯两级即仓库根);bash 在仓库根执行,或展开为绝对路径。
>
> **`--by` 约定**:本 skill 是**单步形态**,registrar 命令一律 `--by xinci-mature`。registrar 会硬校验 `lane=mature`——拿它写 new 道候选会被拒。`xinci-run` 连续运行**不驱动本道前半程**(它的标准授权不覆盖 mature 的 captured/screened/tracking),所以本 skill 的每一次转移都要用户逐条确认。

## 第 0 步:确认数据区(强制,先于一切写操作)

```bash
python3 xinci-workflow/xinci-core/scripts/report_status.py
```

正常返回看板 → 数据区已配置,直接往下走。退出码 2 并提示「数据区未配置」→ 停下来问用户数据区放哪,不要替他选(理由见生命周期契约「开工第一步」)。

## 行动前必读

- xinci-workflow/xinci-core/数据采集指南.md 的「广告线的选源方法:成熟错价词道」全节——**本 skill 是它的执行载体,判据以它为准**
- xinci-workflow/xinci-core/闸门契约.md 的 G6(尤其广告线算式与量级硬门)、G2、G3
- xinci-workflow/xinci-core/陷阱类别.md(类别六、类别七;本道另两条反向排除「成熟工具词」「YMYL 高竞争垂类」**不是**其正式类别,判据见数据采集指南「反向排除」)
- xinci-workflow/xinci-core/生命周期契约.md

## 与新词道的三处硬差别(先记住,否则会照抄错判据)

| | `lane=new`(xinci-scan) | `lane=mature`(本 skill) |
| --- | --- | --- |
| 量级数据 | 窗口期**禁用** Semrush/KD/CPC/Trends——查无是定义属性 | 从第一步就**允许且要求**取量级以证明 mature 需求；具体门槛只约束流量线 |
| 广告线 | 固定 `N/A`，其他五线仍逐项检查 | **必须判**,且有量级硬门 **$200/月**;算式不写即 veto |
| 执行顺序 | G0/G4/G5 → G6/G7 预筛 → G1 → G2 → G3 | G0/G4/G5 加两个前置反向排除 → **量级前置过滤 + G6 六线** → G1 → G2 检查成熟工具词并读取弱守六信号 → G3 |

**KD 在两条道上一律不作为鼓励。** 契约记录的三组背离全是同一个方向——KD 14 对实测竞争 89、KD 27 对 71、KD 44 对约 85,**指标看起来容易、实际都更难**。KD / Authority Score / 外链数**不得决定 G2/G3,也不得直接挣竞争分**。

## 工作流

### 第 0 层:开局去重

提取出方向之后、花任何筛选成本之前,批量查一次(一次覆盖淘汰索引与账本):

```bash
printf '%s\n' "方向1" "方向2" ... | python3 xinci-workflow/xinci-core/scripts/screen_index.py check
```

命中的方向**不计入 funnel 的 `extracted`**——它们上一次已经有归宿了。索引本身不进上下文。

### 第 1 层:按四类源头提取方向(便宜)

要找的是**需求已经存在、供给却没跟上**的地方。四类源头不同权(依据见指南「该盯的源头」的首轮修订):

**结构上可靠,优先用:**

1. 需要**逐对象查表**的成熟任务(型号、地区、版本兼容性)——**挑答案是一个数字或一个判断的**,避开答案是一件可购买商品(SKU)的。散文答不了这类问题,而占位者往往只有散文;答案不是 SKU 时,没有零售商有动机建那张表。
2. 论坛/社区里**被反复问、且每次都靠人肉回答**的问题。反复问=有量;每次靠人肉答=没人做成页面或工具。社区面按真浏览器原则读真实页面。

**次级,前提自带陷阱类别六——采用前先零成本问一句「这个对象全集有没有法定或事实上的维护者?」答有即弃,不必读 SERP:**

3. 官方/权威页面排在首位但**答不全**的查询。
4. 规则、价格、产品线**改过之后**的老查询。

### 第 2 层:零成本批筛(G0 / G4 / G5 + 两个前置反向排除)

先跑与新词道相同的三道零成本闸:**G0**(合法性)、**G4**(任务可完全在线完成)、**G5**(陷阱类别,按类别自带处置档执行)。

再跑本道可在 SERP 前判断的**两个反向排除**——它们来自实测,不是推理,命中即弃。第三个“成熟工具词”必须读取完整首页，移到第 6 层处理，不能伪装成零成本判断:

- **YMYL 高竞争垂类**:凡题目影响**健康、财务、安全或法律权利**的一律按 YMYL 处理。**按类别定义,不按例子清单**——原稿只列了健身/补剂/交易/健康,漏掉法律,首轮种子 A(`statute of limitations`)正栽在这里。
- **横向对比与迁移**(陷阱类别七):`alternatives to X` / `X vs Y` 这类量级也真,但该对象类有自己的全集维护者——替代品目录站、分析机构榜单、社区 awesome 清单、竞品自建对比页。

秒弃的每一条都要批量追加进淘汰索引,不逐条写。gate 栏的写法要分清:「横向对比与迁移」是陷阱类别七,记 `G5`;**「YMYL 高竞争垂类」不是陷阱类别.md 的正式类别**,它是本道的选源前置排除——死因是“这一格一定有人当生意经营、防守必强”,属 G3 占位判断的零成本预判,gate 记 `G3`,`pattern` 固定写 `YMYL 高竞争垂类`(累计样本够了再按陷阱类别.md 的追加规则决定是否建类,建类前不要写成 G5):

```bash
# 本道一律用 JSON 行,因为要带 lane=mature(竖线格式写不了 lane,见第 8 层「淘汰索引的 lane 字段」)
printf '%s\n' \
  '{"term":"<词>","gate":"G3","reason":"[YMYL] 题目影响法律权利,高竞争垂类","pattern":"YMYL 高竞争垂类","lane":"mature"}' \
  '{"term":"<词>","gate":"G5","reason":"[横向对比与迁移] 对象全集已有维护者","lane":"mature"}' ... \
  | python3 xinci-workflow/xinci-core/scripts/screen_index.py append --date <YYYY-MM-DD>
```

### 第 3 层:流量线量级前置过滤(计费,先算钱再看防守)

**这一层是本道与新词道分道扬镳的地方,也是"先算钱"那条顺序的落点。** 一次 Semrush 查询先读两个数:

- **簇内词总数 N** < 约 1,000 → advertising 暂定否决
- **前 15 行合计** < 约 50K/月 **且**无单词 > 10K → advertising 暂定否决；affiliate 也须另证购买意图与可归因流量

**阈值只来自 3 个样本,须按真实结果继续调**;每次用到都要在运行清单里记下本次的实测值,供后续校准。两条都只筛流量线,不得把 advertising 的量级门套给 subscription / lead_generation / transaction / paid_report。

量级不足后仍继续完成其余四条非流量线；只有所有适用线都暂定否决,才追加索引(gate 记 G6)并且**不开浏览器**。否则继续后续 G1/G2/G3——一次计费查询先决定流量线,但不越权决定整候选。

**Semrush 纪律**:每一次计费查询必须能改变一个决策。本层的两个数就是决策本身,属 decision-changing;但**不要为凑流程整页导出**——按数据采集指南的预览纪律,看前 50 行预览、只记要点进观察文件,不整页转录。

### 第 4 层:G6 六线判定

**广告线**必须把反推算式写出来,不许只写"可以放广告":

```
需求会话数      = 目标月收入 ÷ RPM × 1000
需求簇内月搜索量 = 需求会话数 ÷ 可达位次点击率
```

- RPM 按 niche 取值并**注明出处**(金融/法律/保险显著高于技术/开发)
- 点击率**必须用新站现实可达的位次**估,不许用位次 1 的 20–30%
- **$200/月是硬门槛;算式、实测量级或来源缺一,该线即 veto**

示意量级:目标 $200/月、RPM $8、点击率 5% → 需求簇内月搜索量约 50 万;RPM $30 时约 13 万。

其余五线也逐项判断：subscription、lead_generation、affiliate、transaction、paid_report。每条写付费者、付费事件/重复单位、交付物、保守单价与数量、收入算式、来源和最大反证；不适用才写 `N/A`。`repeat_paid_task` 答否只否决 subscription，不能连带杀死 lead generation / transaction / paid report。闸门契约 G6「深审入口预检」的另两项也在本层一并做,不因赛道省略:`official_count_class`(受约束主体是不是官方会计数、且计数公开的类别)答否只否决依赖该总数的算式;`self_serve_legal_effect`(自助结论要不要第三方签字才算数)只否决声称替代签字的交付线,全部声称交付均依法无效时才是整候选否决。

**任一适用线 pass 即 G6 pass。** 窗口期在 schema v2 observation 的 `g6_tentative_lines` 完整写六条 `tentative_pass|tentative_veto|N/A`；确认期才用正式 `g6_lines`。

**三项互相反相关,是一个乘性夹逼,不是三个可分别满足的条件**(实测 3 样本):

- **CPC 高不只是 RPM 代理,它本身就是"这一格里有钱"的直接证据** → 有人正在为每次点击付 12 美元,防守必然强(`statute of limitations florida` CPC $12.11,量级过关,死在防守)
- **防守弱的地方通常正因为商业价值低** → RPM 低 → 需求量级反而暴涨(`cost per square foot` CPC $1.15–2.68,RPM 约 6,需求量级被抬到 66.7 万/月)
- **窄 B2B 垂类兼具好单价与无总量**(`commercial rent per square foot` 簇仅 290 词,头部词 140/月)

所以判广告线时**不许把这三项当成可以分别满足的条件**。"高 RPM + 无人经营"在成熟词上接近自相矛盾——这正是本道 0/4 的结构性原因,每一轮都要正面对它。

### 第 5 层:G1 快筛(真浏览器,美区桌面未登录)

```
https://www.google.com/search?q=<精确词>&gl=us&hl=en&pws=0
```

只看首屏,先判 Google 是否完成精确原子任务(完整作答的 featured snippet、原生计算器/转换器组件、承载全部答案的 knowledge panel、把任务做完的 AI Overview)。若已完成,必须再写完整 `cluster_counterfactual`:批处理、监控、审计轨迹、导出集成、多辖区任一形成独立重复任务 family,就记 `viable_cluster`、改写任务并重新核对前置门；五项全否才记 `atomic_only` 并判 G1 veto。

**读法必须能读到 AI Overview**:用 JS 读 `document.body.innerText` 再检索 `AI Overview`;读回的文本若从 `Web results` 起始而非整页开头,该次观察作废重读(出处见数据采集指南)。**只有美区、桌面、未登录且可控的环境才能下 G1 结论。**

否决的批量追加一行索引(gate 记 G1),不注册进账本；JSON 行必须携带 `cluster_counterfactual=atomic_only`(否则 `screen_index.py` 会拒收)与 `"lane":"mature"`,写法同 xinci-scan 第 3 层的 JSON 行示例再加 lane 字段。

### 第 6 层:G2 完整结构阅读 + 弱守六信号

读完第一页,继续到第二页或明显质量断层为止,**禁止用 top-3 判断竞争**。

先处理需要 G2 现场证据的第三个反向排除：**成熟工具词**的量级虽真，但赛道已经长期被争夺；完整首页若出现专做该任务的站，立即停止深审，追加一行索引留痕:与 YMYL 同理,它不是陷阱类别.md 的正式类别,死因是 G3 意义上的“这一格早有人当生意经营”,所以 gate 记 `G3`、`pattern` 固定写 `成熟工具词`,建类前不写 G5。它不属于第 2 层零成本秒弃，漏斗按本次实际 SERP/G2 审计归类。

"守得很弱"不是靠指标判的,是靠现场读出来的。六条信号(全部来自 G2 已有放行信号与 G3 第一问,不新增判据):

1. **占位者是内页、小站、论坛帖**,而非专做这件事的站
2. **内容明显老化**且该题目已经变了——首页结果日期集中在数年前,而规则/产品/价格已改过
3. **没有真工具**,任务要求算/查/比,而占位者只有散文
4. **格式错配**——查询要的是表格、清单、计算器,排上来的是长文
5. **意图错配**——排名页面答的不是这个问题
6. **没人把这一格当生意经营**——无付费产品、无按任务成簇、无维护痕迹

**六条里中三条以上才算弱守**,并且必须写明是哪几条、附现场证据。只中一两条的按正常竞争处理。

### 第 7 层:G3 占位审计(按盈利线映射)

按"**做什么**"给每个竞品分类,永不按"是谁"。先按本轮 G6 的逐线暂定结论判断占位否决是否生效,再执行三问:

- **只靠 affiliate / advertising 过** → 占位否决**生效**(两线依赖自然搜索流量)
- **subscription / lead_generation / transaction / paid_report 任一能过** → 占位事实转为竞争与获客成本输入，不自动否决整候选

**这条对本道尤其要紧**:mature 道若仅有流量型盈利线，G3 的 `veto` 会杀死候选；若高价值低量级盈利线成立，则占位事实不能套广告逻辑一票否决。三问全文与 `veto_window_bet` 的降级出口见闸门契约 G3。

### 第 8 层:注册与分流

存活的注册为 `lane=mature`:

```bash
python3 xinci-workflow/xinci-core/scripts/registrar.py register \
  --slug <slug> --term "<精确措辞>" --source-url <URL> --task "<任务>" \
  --site-thesis "<为何能形成独立站>" \
  --task-family "<任务家族1>" --task-family "<任务家族2>" \
  --lane mature --origin signal \
  --evidence "证据/<slug>/<日期>-scan.json" --by xinci-mature
  # 带 --gates 就必须同时带 --expiry(排队位规则与 new 道一致)
  # --site-thesis / --task-family:registrar 只对 --by xinci-run 强制,单步下推荐照写,与 new 道模板一致
```

**排队位的接队与过期也归本 skill**:xinci-scan 不接 `lane=mature` 的 `captured`(它只报告应交本 skill),所以下一轮开局先读账本里 `lane=mature,state=captured` 的候选,按 gates 补缺的门;expiry 已过的提议 `captured→expired --expiry-trigger date`(与 new 道同一条边,由用户确认)。这与 xinci-track 不收 mature 追踪一样,是生命周期契约「四条 expired 边各自的提议人」在本道的落点。

**淘汰索引的 `lane` 字段**:本道写进索引的每一行都要带 `lane=mature`(闸门校准第 8.5 节给索引加了这个字段,缺省视为 new,两道死因不同不能混)。竖线格式写不了它,本道的 append 一律用 JSON 行,例如 `{"term":"<词>","gate":"G6","reason":"<量级与六线结论>","lane":"mature"}`;第 2 层与第 5 层的示例已按此写法给出。

随后按缺口出闸:`captured→screened` 要 G0/G1/G2/G4/G5=`pass` 与有效 G3,并带 `--window-estimate` 与 `--expiry`。成熟词的窗口通常以**月**计(需求是历史积累的,不会几天蒸发),据实填,不要照抄新词道的 days/weeks。

之后 `screened→tracking→formation_confirmed` 与 new 道同规则：累计 ≥2 个 `-track` 观察、跨度 ≥7 天，本次 G1=pass，并在本次 track 观察明确 `naming_status=stabilized` 与至少一项 `formation_signals`。**mature 的追踪复查也由本 skill 单步执行**(xinci-track 只收 `lane=new`,遇到 mature 只报告跳过):复查动作照抄 xinci-track 工作流第 1–7 步(第 7 步的提议清单也照抄:继续追踪 / 续期修订 / formation_confirmed / expired / rejected,用户逐条确认后才执行 transition),但 `registrar.py checked` 与 `amend` 都要显式传 `--by xinci-mature`(`checked` 的默认值是 `xinci-track`,照抄默认会被 lane 校验拒收)。**到 `formation_confirmed` 为止是本 skill 的边界**:确认期评分交 xinci-qualify,建站决策交 xinci-decide。

深审判否的候选同样先 register 再走 `captured→rejected`,reason 写清失败闸门与现场证据要点。

### 第 9 层:写运行清单(含命中率)

```bash
python3 xinci-workflow/xinci-core/scripts/run_manifest.py record-single \
  --date <YYYY-MM-DD> --skill xinci-mature \
  [--suffix <HHMM>] [--source-opened <URL>] [--candidate-touched <slug>] \
  [--billable-calls <N>] --note '<命中率与实测阈值事实>'
```

控制器原子创建清单并拒绝覆盖；同日重跑显式传 `--suffix`。不得手写 JSON。

**本道额外要求两项,不可省:**

1. **命中率**:本轮提取 N 个方向、存活几个、累计 X/Y。这是指南给本道立的规矩——0/4 证否不了什么,但每一轮都要记,否则永远不知道判据该往哪调。
2. **实测阈值**:第 3 层用到的簇内词总数与前 15 行合计,以及它们相对当前阈值(1,000 / 50K / 10K)偏了多少。阈值只有 3 个样本,靠这些记录慢慢调准。

## 硬规则

- **只碰 `lane=mature`**。registrar 会硬校验;new 道的发现与前半程用 xinci-scan。
- **不注册域名、不花钱建站、不发布**——找到词就停。
- **量级数据用来证明 mature 需求存在并判断 advertising / affiliate 等流量线**;广告量级门不得连带否决四条非流量线,KD / Authority Score / 外链数不得决定 G2/G3 或直接挣竞争分。
- **闸门与分数线不因本道而降低**。本道的差别在于哪条盈利线可用、以及量级是不是准入条件,不在于判得松一点。
- **单步形态,逐条确认**。本 skill 不在 xinci-run 的标准授权范围内;每一次 registrar 转移都要用户确认后执行。
- **0 正例要如实说**(种子口径 0/4,含探针口径 1/6 进账本、随后否决)。本道至今没有正例。报告时不得把"跑通了流程"说成"这条线成立",也不得因为想要正例而放宽任何一道判据。
