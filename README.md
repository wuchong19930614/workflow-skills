# workflow-skills

工作流 skill 正本仓库。当前包含 **xinci 新词工作流**:发现并验证新兴/全新的英文 Google 搜索词,产出"能否支撑一个独立 SEO 站"的建站决策书。默认是用户逐步确认的单步模式;用户显式启动 xinci-run 后,才在本次预算内连续编排。

## 单元清单

| 单元 | 职责 |
| --- | --- |
| [xinci-run](xinci-workflow/xinci-run/SKILL.md) | 连续运行驱动器,暗号 `xinci_run`。跑到任一 go 决策、Semrush 额度耗尽或预算用完(默认 6 轮) |
| [xinci-status](xinci-workflow/xinci-status/SKILL.md) | 状态看板,只读 |
| [xinci-scan](xinci-workflow/xinci-scan/SKILL.md) | 扫描发现 new 道候选,当场初筛 |
| [xinci-track](xinci-workflow/xinci-track/SKILL.md) | 复查 new 道 tracking 候选与到期 SERP 型拒绝 |
| [xinci-mature](xinci-workflow/xinci-mature/SKILL.md) | 成熟错价词道(mature)的发现、前半程与到期 SERP 型拒绝复核 |
| [xinci-qualify](xinci-workflow/xinci-qualify/SKILL.md) | 深度认定,100 分制 80 分线 |
| [xinci-decide](xinci-workflow/xinci-decide/SKILL.md) | 建站 go/no-go 决策书 |
| [xinci-core](xinci-workflow/xinci-core/) | 共享核心:通用约定、契约、schema、脚本 |

工作流怎么运转见 **[xinci-workflow/README.md](xinci-workflow/README.md)**。

## 仓库边界

**本仓库只放 skill 与契约,不放执行产出。** 账本、证据、决策书、运行清单、运行状态、淘汰方向索引、去重裁决一律住在用户配置的数据区。当前 checkout 可以配置到同级仓库 `keywords-macdownds` 的 `数据/新词工作流/`,但这只是一个实例,不是规范默认值。契约里的 `账本/`、`证据/`、`运行/`、`决策书/` 等相对路径都从实际配置的数据区起算。

### 第一次使用:先定数据区

脚本不猜数据区在哪,没配置过就退出码 2 并提示先问用户。

```bash
python3 xinci-workflow/xinci-core/scripts/init_workspace.py --data-root <数据区路径>
```

幂等:创建目录结构与空账本,并把路径记进 `.xinci-data-root`(不入库)。解析顺序:`--data-root` > 环境变量 `XINCI_DATA_ROOT` > `.xinci-data-root` > 拒绝执行。

## 双环境接入(symlink,不入库)

在仓库根执行,Codex CLI 与 Claude Code 读同一份正本:

```bash
for s in xinci-run xinci-status xinci-scan xinci-track xinci-mature xinci-qualify xinci-decide; do
  ln -sfn "$(pwd)/xinci-workflow/$s" ~/.codex/skills/$s
  ln -sfn "$(pwd)/xinci-workflow/$s" ~/.claude/skills/$s
done
```

xinci-core 不是 skill,无需 symlink。

## 测试

```bash
python3 -m unittest discover xinci-workflow/xinci-core/scripts/tests
python3 xinci-workflow/xinci-core/scripts/validate_ledger.py
```

`validate_ledger.py` 校验账本不变式与运行清单格式,有错非零退出。
