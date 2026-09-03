---
name: xinci-mature
description: '成熟错价词道(lane=mature)的发现与前半程推进。当用户说跑一轮成熟词、找错价词、走广告线、mature 道时使用。English triggers: mature lane, mispriced keywords, ad-line scan. 新词道用 xinci-scan;确认期评分用 xinci-qualify,建站决策用 xinci-decide。'
---

# xinci-mature 成熟错价词道

先读 `xinci-workflow/xinci-core/通用约定.md`,再读 `xinci-workflow/xinci-scan/SKILL.md`——本文只写与 xinci-scan 的差异,漏斗结构、配额、留痕分界、命令模板都以它为准。判据以数据采集指南「广告线的选源方法:成熟错价词道」全节为准,另读闸门契约 G6 与陷阱类别六、七。

找的不是新词,是老词里被守得很弱的那一格:量级真实存在,而占位者只有散文、老化内容或错配格式。这条线至今 0 正例(口径见数据采集指南「本节的诚实状态」),第一目标是可执行、可累积样本;报告时不得把"跑通了流程"说成"这条线成立",也不得因想要正例放宽判据。
本 skill 是单步形态:registrar 命令一律 `--by xinci-mature`,每次转移都要用户确认;registrar 硬校验 `lane=mature`(归属见通用约定「lane 边界」)。

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
要找的是需求已存在、供给没跟上的地方(依据见数据采集指南「广告线的选源方法」下的「该盯的源头」)。四类不同权,前两类结构上可靠、优先用:
1. 需要逐对象查表的成熟任务(型号、地区、版本兼容性)——挑答案是一个数字或一个判断的,避开答案是可购买商品(SKU)的;
2. 论坛/社区里被反复问、每次都靠人肉回答的问题(社区面真浏览器读);
3. (次级)官方/权威页面排首位但答不全的查询;
4. (次级)规则、价格、产品线改过之后的老查询。
次级两类采用前先零成本问一句"这个对象全集有没有法定或事实上的维护者?",答有即弃,不读 SERP(陷阱类别六)。

### 第 2 层:零成本批筛 + 两个前置反向排除
G0 / G4 / G5 同 xinci-scan 第 2 层。再跑本道可在 SERP 前判断的两个反向排除(判据见数据采集指南「反向排除」),命中即弃:
- YMYL 高竞争垂类:按类别定义(影响健康、财务、安全或法律权利),不按例子清单。它不是陷阱类别.md 的正式类别,gate 记 `G3`,`pattern` 固定写 `YMYL 高竞争垂类`;
- 横向对比与迁移:陷阱类别七,gate 记 `G5`。
本道写索引一律用 JSON 行并带 `"lane":"mature"`(竖线格式写不了 lane,缺省视为 new;第 5、6 层的否决行同样带):
```bash
printf '%s\n' \
  '{"term":"<词>","gate":"G3","reason":"[YMYL] 题目影响法律权利,高竞争垂类","pattern":"YMYL 高竞争垂类","lane":"mature"}' \
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
广告线必须写出反推算式(需求会话数 = 目标月收入 ÷ RPM × 1000;需求簇内月搜索量 = 需求会话数 ÷ 可达位次点击率),RPM 注明出处,点击率用新站现实可达位次;$200/月是硬门,算式、实测量级或来源缺一即 veto。量级、RPM、弱守三项是一个乘性夹逼,不许当成可分别满足的条件(见闸门契约 G6)。

### 第 5 层:G1 快筛(同 xinci-scan 第 3 层)

### 第 6 层:G2 完整结构阅读 + 弱守六信号
G2 按闸门契约 G2。先处理第三个反向排除——成熟工具词:完整首页出现专做该任务的站,立即停止深审,追加索引(gate 记 `G3`,`pattern` 固定写 `成熟工具词`);它需要 G2 现场证据,不属于第 2 层零成本秒弃,漏斗按实际 G2 审计归类。
随后读弱守六信号(全部来自 G2 放行信号与 G3 第一问,不新增判据):
1. 占位者是内页、小站、论坛帖,而非专做这件事的站;
2. 内容明显老化且该题目已经变了;
3. 没有真工具,任务要求算/查/比而占位者只有散文;
4. 格式错配——查询要表格/清单/计算器,排上来的是长文;
5. 意图错配——排名页面答的不是这个问题;
6. 没人把这一格当生意经营——无付费产品、无按任务成簇、无维护痕迹。
六条里中三条以上才算弱守,写明是哪几条并附现场证据;只中一两条按正常竞争处理。判读时用问句式与产品向两族措辞各检索一次。

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
