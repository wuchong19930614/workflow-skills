---
name: xinci-mature
description: '成熟错价词道(lane=mature)的发现与前半程推进。当用户说跑一轮成熟词、找错价词、走广告线、mature 道，或复核到期的 mature rejected 候选时使用。English triggers: mature lane, mispriced keywords, ad-line scan. 新词道用 xinci-scan;确认期评分用 xinci-qualify,建站决策用 xinci-decide。'
---

# xinci-mature 成熟错价词道

先读 `xinci-workflow/xinci-core/通用约定.md` 与 `xinci-workflow/xinci-scan/SKILL.md` 的漏斗、配额、留痕和命令部分。再读数据采集指南「广告线的选源方法:成熟错价词道」、闸门契约 G6，以及 `陷阱速查.md`；只有方向疑似命中类别六或七时才读 `陷阱类别.md` 对应类别。

找的不是新词,是老词里被守得很弱的那一格:量级真实存在,而占位者只有散文、老化内容或错配格式。这条线至今 0 正例(口径见数据采集指南「本节的诚实状态」),第一目标是可执行、可累积样本;报告时不得把"跑通了流程"说成"这条线成立",也不得因想要正例放宽判据。
本 skill 是单步形态:registrar 命令一律 `--by xinci-mature`,每次转移都要用户确认;registrar 硬校验 `lane=mature`(归属见通用约定「lane 边界」)。

若输入是 `lane=mature,state=rejected` 且 `recheck_after` 已到,不进入下面的发现漏斗:按 xinci-track 的受控重开流程复查原 G1/G2/G3 veto,取得更晚的新现场观察并逐门翻转后先向用户提议;确认后执行 `registrar.py reopen --by xinci-mature`,回到 captured 再走完整初筛。结构性 G0/G4/G5 否决不可重开。

## 与新词道的三处硬差别
| | `lane=new`(xinci-scan) | `lane=mature`(本 skill) |
| --- | --- | --- |
| 量级数据 | 窗口期禁用 Semrush/KD/CPC/Trends | 从第一步就允许且要求取量级;门槛只约束流量线 |
| 广告线 | 固定 `N/A`,其余五线仍逐项检查 | 必须判,量级硬门 $200/月;算式不写即 veto |
| 执行顺序 | G0/G4/G5 → G6/G7 预筛 → G1 → G2 → G3 | G0/G4/G5 加两个前置反向排除 → 量级前置过滤 + G6 六线 → G1 → G2 加成熟工具词排除与弱守六信号 → G3 |

## 工作流
### 第 0 层:开局去重与接队
同 xinci-scan 第 0 层;接队改收 `lane=mature` 的 `captured`(xinci-scan 不接它),expiry 已过的提议 `captured→expired --expiry-trigger date`。

### 第 1 层:按四类源头提取方向
按数据采集指南「该盯的源头」四类提取，优先前两类。采用两类次级来源前，先判断对象全集是否已有法定或事实维护者；有则按类别六处置，不读 SERP。

### 第 2 层:零成本批筛 + 两个前置反向排除
G0 / G4 / G5 同 xinci-scan 第 2 层。再跑本道可在 SERP 前判断的两个反向排除(判据见数据采集指南「反向排除」),命中即弃:
- YMYL 高竞争垂类:按类别定义(影响健康、财务、安全或法律权利),不按例子清单。它不是 G0–G8 闸门结论,不得伪装成 G3;索引写 `stage=prescreen`,`reason_code=ymyl_high_competition`,`pattern` 固定写 `YMYL 高竞争垂类`;
- 横向对比与迁移:陷阱类别七,gate 记 `G5`。
本道写索引一律用 JSON 行并带 `"lane":"mature"`(竖线格式写不了 lane,缺省视为 new;第 5、6 层的否决行同样带):
```bash
printf '%s\n' \
  '{"term":"<词>","stage":"prescreen","reason_code":"ymyl_high_competition","reason":"[YMYL] 题目影响法律权利,高竞争垂类","pattern":"YMYL 高竞争垂类","lane":"mature"}' \
  '{"term":"<词>","gate":"G5","reason":"[横向对比与迁移] 对象全集已有维护者","lane":"mature"}' ... \
  | python3 xinci-workflow/xinci-core/scripts/screen_index.py append --date <YYYY-MM-DD>
```

### 第 3 层:流量线量级前置过滤(计费,先算钱再看防守)
一次 Semrush 查询读两个数,只筛流量线,不得把量级门套给 subscription / lead_generation / transaction / paid_report:
- 簇内词总数 N < 约 1,000,或前 15 行合计 < 约 50K/月且无单词 > 10K → advertising 暂定否决;affiliate 须另证购买意图与可归因流量。
- 阈值只来自 3 个样本,每次用到都把实测值记进运行清单(第 9 层)。看前 50 行预览、只记要点,不整页导出。
- 量级不足仍继续完成其余四条非流量线;只有所有适用线都暂定否决,才追加索引(gate 记 G6)且不开浏览器。

### 第 4 层:G6 六线判定
按闸门契约 G6「六线判定」与「深审入口预检」执行,六条线逐项写进 observation 的 `g6_tentative_lines`,任一适用线 pass 即 G6 pass。
广告线的反推算式、$200/月硬门和乘性夹逼只按闸门契约 G6 执行，不在本 Skill 维护第二份口径。

### 第 5 层:G1 快筛(同 xinci-scan 第 3 层)

### 第 6 层:G2 完整结构阅读 + 弱守六信号
G2 按闸门契约 G2。先处理第三个反向排除——成熟工具词:完整首页出现专做该任务的站，按 G3 与公共供给覆盖检查验证，不因出现一个同类站就立即淘汰；有效占位否决成立才按实际阶段留痕。
随后按数据采集指南「要找的是什么:反向错价」第二步的六条弱守信号逐项记录；至少命中三条才算弱守，并附现场证据。判读时必须同时使用问句式与产品向两族措辞。

### 第 7 层:G3 占位审计(同 xinci-scan 第 4 层的 G3 部分,按闸门契约 G3 执行)

### 第 8 层:注册与分流
register / transition / amend 命令同 xinci-scan 第 4–5 层(含 `veto_window_bet` 处置),差别只有:`--by xinci-mature`、register 加 `--lane mature --origin signal`。
- 深审判否同样先 register 再 `captured→rejected`;超配额与验证存活的按排队位注册(带 gates + expiry)。
- 出闸 `captured→screened` 的 `--window-estimate` 据实填:成熟词的窗口通常以月计,不照抄新词道的 days/weeks。
- `screened→tracking→formation_confirmed` 与 new 道同规则。mature 的追踪复查也由本 skill 单步执行:照抄 xinci-track 第 1–7 步(含第 7 步五种出口提议),`checked` 与 `amend` 显式传 `--by xinci-mature`。到 `formation_confirmed` 为止是本 skill 的边界。

### 第 9 层:写运行清单
命令同通用约定「运行清单」,`--skill xinci-mature`。`--note` 必记两项:①命中率(本轮提取 N 个方向、存活几个、累计 X/Y);②第 3 层实测的簇内词总数与前 15 行合计,及相对当前阈值(1,000 / 50K / 10K)的偏差。

## 硬规则
- 闸门与分数线不因本道而降低;差别只在哪条盈利线可用、量级是否准入条件。
- 量级数据只用来证明 mature 需求存在并判流量线;广告量级门不得连带否决四条非流量线。KD / Authority Score / 外链数不得决定 G2/G3 或直接挣竞争分(见闸门契约「关于 KD / KGR / allintitle 的统一立场」)。
