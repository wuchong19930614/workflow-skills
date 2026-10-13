# xinci-bench-workflow（标杆倒推选站）

从近 24 个月起量的低权重小站倒推建站方向，判断"上线后 12 个月内单站做到 $100/月"的把握，产出决策书；判 go 时附建站简报。站型不限（工具、内容、游戏），变现只算展示广告与付费功能，主做 Google SEO，GEO 用作筛选信号与建站规范。与 xinci、xinci-simple 两套工作流零运行时依赖。

| 单元 | 职责 |
| --- | --- |
| [scan](xinci-bench-scan/SKILL.md) | 取一批种子域名，初核 B1–B5，合格的登记为方向 |
| [assess](xinci-bench-assess/SKILL.md) | 六步深核、标杆份额法测算、结算并生成决策书与建站简报 |
| [run](xinci-bench-run/SKILL.md) | `xinci_bench_run max_rounds=N`，默认 3 轮；出 go 不停，跑满预算 |
| [status](xinci-bench-status/SKILL.md) | 只读看板 |
| [选站契约](xinci-bench-core/选站契约.md) | 唯一判据；[数据采集](xinci-bench-core/数据采集.md)管通道与坑；[命令与观察](xinci-bench-core/命令与观察.md)管调用 |

设计稿：[docs/superpowers/specs/2026-10-13-xinci-bench-workflow-design.md](../docs/superpowers/specs/2026-10-13-xinci-bench-workflow-design.md)。

## 首次使用

```bash
python3 xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py --data-root <用户指定数据区>
python3 xinci-bench-workflow/xinci-bench-core/scripts/seed_import.py --legacy-root <xinci-simple 数据区>
```

数据区解析：`--data-root` > `XINCI_BENCH_DATA_ROOT` > 仓库根 `.xinci-bench-data-root` > 退出码 2（先问用户，不猜位置）。旧数据区只读，导入前后核对 SHA-256。

## 检查

```bash
python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q
python3 xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py
python3 xinci-bench-workflow/xinci-bench-core/scripts/run_log.py --plan
```

`validate_ledger.py` 非零意味着真实数据需要处理，不能拿单元测试通过代替。

## 本地接入

```bash
for s in xinci-bench-scan xinci-bench-assess xinci-bench-status xinci-bench-run; do
  ln -sfn "$(pwd)/xinci-bench-workflow/$s" ~/.claude/skills/$s
  ln -sfn "$(pwd)/xinci-bench-workflow/$s" ~/.codex/skills/$s
done
```

xinci-bench-core 不是 skill，无需软链。
