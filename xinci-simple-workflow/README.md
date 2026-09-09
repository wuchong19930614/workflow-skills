# xinci-simple-workflow（流量型选词）

从**已有真实搜索量**的英文词里，找出 SERP 守得弱、AI Overview 吃不掉、base case 月收入 ≥ $200 的主题簇（门槛 2026-09-09 由 $500 下调，依据见契约 §6.0），产出一份机会报告。建站方式不预设，报告就是交付物。

## 与 xinci 新词工作流的关系

- 零运行时依赖：不 import 它的脚本、不引用它的契约。
- 数据区独立：`<数据区>/xinci-simple/`，与 `新词工作流/` 零交集。
- xinci 原样冻结。这套工作流是 2026-09-09 结构诊断后的方向切换（见 [设计稿](../docs/superpowers/specs/2026-09-09-xinci-simple-workflow-design.md)）。

## 单元清单

| 单元 | 职责 |
| --- | --- |
| [xinci-simple-scan](xinci-simple-scan/SKILL.md) | 发现：Semrush 词根轮换 / 小站反推 / 论坛问题 → 零成本排除 → 注册 `found` → 代理排序 |
| [xinci-simple-verify](xinci-simple-verify/SKILL.md) | 现场核验：G1 直答 / G2 首页结构 / G3 可打败性 / 季节性 / 范围复核 → 收入模型 → 机会报告 |
| [xinci-simple-status](xinci-simple-status/SKILL.md) | 只读看板 |
| [xinci-simple-run](xinci-simple-run/SKILL.md) | 连续运行驱动器，暗号 `xinci_simple_run max_rounds=N`：一轮 = scan 一批 + verify 前 5，跑满才停 |
| [xinci-simple-core](xinci-simple-core/) | 契约（[选词契约](xinci-simple-core/选词契约.md)、[数据采集](xinci-simple-core/数据采集.md)）、schema、脚本、测试 |

## 四层漏斗

1. **发现**（Semrush，Chrome 通道）：簇量 ≥ 50,000 或主词 ≥ 5,000，过四条排除（YMYL / 需亲身体验 / 品牌导航 / 新闻热点）→ `found`
2. **代理排序**（脚本）：KD、簇量、低 DR 数、UGC 数、内容年龄 → `rank_score`，只排序不否决
3. **现场核验**（内置浏览器，美区未登录）：G1 Google 直答硬否决；G2 首页结构；G3"完整 + DR ≥ 50 + 新鲜"结果数 ≥ 3 否决；季节性 → `parked`
4. **收入模型**（脚本）：按形态套假设表，三情景；`base ≥ $200` → `verified` + 报告

## 状态机

```
found ──核验 + 收入通过──→ verified（报告已出）
  ├──硬门否决 / 收入不足──→ rejected
  └──季节性 / 证据不足──→ parked ──→ verified | rejected
```

账本只能由 `ledger.py` 写。

## 第一次使用：先定数据区

```bash
python3 xinci-simple-workflow/xinci-simple-core/scripts/init_workspace.py --data-root <数据区路径>
```

幂等；路径记进仓库根 `.xinci-simple-data-root`（不入库）。解析顺序：`--data-root` > 环境变量 `XINCI_SIMPLE_DATA_ROOT` > 配置文件 > 拒绝执行。

## 双环境接入（symlink，不入库）

```bash
for s in xinci-simple-scan xinci-simple-verify xinci-simple-status; do
  ln -sfn "$(pwd)/xinci-simple-workflow/$s" ~/.codex/skills/$s
  ln -sfn "$(pwd)/xinci-simple-workflow/$s" ~/.claude/skills/$s
done
```

## 测试

```bash
python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q
python3 xinci-simple-workflow/xinci-simple-core/scripts/validate_ledger.py
```

## 脚本

| 脚本 | 用途 |
| --- | --- |
| `data_root.py` / `init_workspace.py` | 数据区解析与初始化 |
| `ledger.py` | `register` / `transition` / `list` |
| `rank.py` | 代理排序，回写 `rank_score` |
| `revenue_model.py` | 三情景收入模型 + `volume_needed_for_500` |
| `run_log.py` | 运行清单 |
| `build_report.py` | 9 节机会报告 |
| `report_status.py` / `validate_ledger.py` | 看板 / 不变式校验 |
