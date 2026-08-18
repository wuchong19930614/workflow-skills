# workflow-skills

工作流 skill 正本仓库。当前包含 **xinci 新词工作流**:发现并验证新兴/全新的英文 Google 搜索词,产出"能否支撑一个独立 SEO 站"的建站决策书。由用户人工驱动,skill 不自我调度。

## 单元清单

| 单元 | 职责 |
| --- | --- |
| [xinci-run](xinci-workflow/xinci-run/SKILL.md) | 连续运行驱动器:启动后循环推进,直到任一 go 决策或 Semrush 额度实际耗尽。启动暗号 `xinci_run`,消息中出现即一体启动整个工作流 |
| [xinci-status](xinci-workflow/xinci-status/SKILL.md) | 状态看板:只读汇报账本事实 |
| [xinci-scan](xinci-workflow/xinci-scan/SKILL.md) | 扫描发现:真浏览器捕获候选,当场 G1–G5 初筛 |
| [xinci-track](xinci-workflow/xinci-track/SKILL.md) | 追踪复查:用户指定候选,重跑 G1,提议转移 |
| [xinci-qualify](xinci-workflow/xinci-qualify/SKILL.md) | 深度认定:G6–G8 + 竞争审计 + 100 分制(80 分线) |
| [xinci-decide](xinci-workflow/xinci-decide/SKILL.md) | 建站决策:页面地图 + 收入模型 + md/html 双格式决策书 |
| [xinci-core](xinci-workflow/xinci-core/) | 共享核心:契约、闸门、schema、registrar 脚本(判断标准唯一来源) |

设计文档:[设计/新词工作流skill设计-2026-08-17.md](设计/新词工作流skill设计-2026-08-17.md)。数据区:`数据/新词工作流/`(账本 / 证据 / 决策书 / 运行 / 淘汰方向索引)。

## 双环境接入(symlink,不入库)

skill 通过 symlink 同时接入 Codex CLI 与 Claude Code,两环境读同一份正本。仓库可放在任意位置——**在仓库根执行**:

```bash
for s in xinci-run xinci-status xinci-scan xinci-track xinci-qualify xinci-decide; do
  ln -sfn "$(pwd)/xinci-workflow/$s" ~/.codex/skills/$s
  ln -sfn "$(pwd)/xinci-workflow/$s" ~/.claude/skills/$s
done
```

xinci-core 不是 skill,无需 symlink;各 SKILL.md 以仓库根相对路径引用它(路径约定见各 SKILL.md 开头)。

## 测试

```bash
python3 -m unittest discover xinci-workflow/xinci-core/scripts/tests
python3 xinci-workflow/xinci-core/scripts/validate_ledger.py
```

`validate_ledger.py` 同时校验账本不变式(捕获绕过 registrar 的手工编辑)与运行清单格式(清单全靠手写,字段漂移只能靠它发现);有错即非零退出。
