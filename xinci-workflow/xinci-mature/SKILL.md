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
| 广告线 | 固定 `N/A`,其余五线仍逐项检查 | 按 G6 收入模型判定；缺算式或量级证据记未知 |
| 执行顺序 | G0/G4/G5 → G6/G7 预筛 → G1 → G2 → G3 | 轻筛与赛道范围 → 量级取证 + G6 预筛 → G1 → G2 → G3 |

## 工作流
### 第 0 层:开局去重与接队
同 xinci-scan 第 0 层;接队改收 `lane=mature` 的 `captured`(xinci-scan 不接它),expiry 已过的提议 `captured→expired --expiry-trigger date`。

### 第 1 层:按四类源头提取方向
按数据采集指南「该盯的源头」四类提取，优先前两类。对象全集已有维护者时标记类别六，在现场审计核实覆盖；维护者身份不构成否决。

### 第 2 层:轻筛与验证路由
G0 / G4 / G5 同 xinci-scan 第 2 层。再按数据采集指南「反向排除」区分赛道范围与现场检查:
- YMYL 高竞争垂类:按类别定义(影响健康、财务、安全或法律权利),不按例子清单。它不是 G0–G8 闸门结论,不得伪装成 G3;索引写 `stage=prescreen`,`reason_code=ymyl_high_competition`,`pattern` 固定写 `YMYL 高竞争垂类`;
- 横向对比与迁移:标记验证型类别七，继续商业预筛与现场审计；命中措辞不淘汰，只有取得有效否决证据才按实际闸门留痕。
本道写索引一律用 JSON 行并带 `"lane":"mature"`(竖线格式写不了 lane,缺省视为 new;第 5、6 层的否决行同样带):
```bash
printf '%s\n' \
  '{"term":"<词>","stage":"prescreen","reason_code":"ymyl_high_competition","reason":"[YMYL] 题目影响法律权利,高竞争垂类","pattern":"YMYL 高竞争垂类","lane":"mature"}' \
  | python3 xinci-workflow/xinci-core/scripts/screen_index.py append --date <YYYY-MM-DD>
```

### 第 3 层:流量线量级取证
按数据采集指南「第一步,量级取证」记录实际覆盖范围、簇内词数与可见搜索量，只发起能改变决策的查询。部分预览与历史经验值用于排序，不产生广告线否决；通过、否决或未知统一在下一层按 G6 收入模型判定。

### 第 4 层:G6 六线判定
按闸门契约 G6「六线判定」与「深审入口预检」执行,六条线逐项写进 observation 的 `g6_tentative_lines`；任一适用线 tentative_pass 仅表示继续深审，不写 gates.G6。正式 G6 由确认期认定产生，未知处理与共享证据记录见证据判定契约。
广告线的反推算式与收入硬门只按闸门契约 G6 执行，不在本 Skill 维护第二份口径。

### 第 5 层:G1 快筛(同 xinci-scan 第 3 层)

### 第 6 层:G2 完整结构阅读与竞争观察
G2 按闸门契约 G2。先处理第三个反向排除——成熟工具词:完整首页出现专做该任务的站，按 G3 与公共供给覆盖检查验证，不因出现一个同类站就立即淘汰；有效占位否决成立才按实际阶段留痕。
随后按数据采集指南「第二步,竞争观察」记录任务缺口与占据事实；不数信号决定过门。判读时使用问句式与产品向两族措辞，与 G3 共用现场证据。

### 第 7 层:G3 占位审计(同 xinci-scan 第 4 层的 G3 部分,按闸门契约 G3 执行)

### 第 8 层:注册与分流
register / transition / amend 命令同 xinci-scan 第 4–5 层(含 `veto_window_bet` 处置),差别只有:`--by xinci-mature`、register 加 `--lane mature --origin signal`。
- 深审判否同样先 register 再 `captured→rejected`;超配额或缺门的按排队位注册(带 gates + expiry)，已完成全部初筛者按正常出闸注册。
- 出闸 `captured→screened` 的 `--window-estimate` 据实填:成熟词的窗口通常以月计,不照抄新词道的 days/weeks。
- `screened→tracking→formation_confirmed` 与 new 道同规则。mature 的追踪复查也由本 skill 单步执行:复用 xinci-track「追踪共用操作」（含出口提议）,`checked` 与 `amend` 显式传 `--by xinci-mature`。到 `formation_confirmed` 为止是本 skill 的边界。

### 第 9 层:写运行清单
命令同通用约定「运行清单」,`--skill xinci-mature`。`--note` 记录本轮独立任务数、各阶段出口与第 3 层数据的覆盖范围；累计统计按闸门版本分组，部分预览不得冒充完整簇量。

## 硬规则
- 闸门与分数线不因本道而降低;差别只在哪条盈利线可用、量级是否准入条件。
- 量级数据只用来证明 mature 需求存在并判流量线;广告量级门不得连带否决四条非流量线。KD / Authority Score / 外链数不得决定 G2/G3 或直接挣竞争分(见闸门契约「关于 KD / KGR / allintitle 的统一立场」)。
