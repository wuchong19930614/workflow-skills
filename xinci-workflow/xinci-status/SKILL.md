---
name: xinci-status
description: '新词工作流状态看板,只读汇报候选账本的全局事实。当用户想看新词工作流状态、账本里有什么、各候选进展到哪、有哪些 expiry 快到期时使用。纯汇报不驱动。English triggers: xinci status, keyword workflow status, candidate ledger overview. 发现新词用 xinci-scan,复查用 xinci-track。'
---

# xinci-status 状态看板

先读 `xinci-workflow/xinci-core/通用约定.md`(第 0 步、面向用户只说中文、expired 边归属)。再读生命周期契约「时间字段:只记录,不调度」。

只读汇报,零判断,零写入:不调用 registrar,不改动账本与任何执行产出;唯一例外是第 0 步经用户给出路径后的 `init_workspace.py` 初始化。账本是唯一事实来源,不从证据文件反推状态,不脑补账本没有的信息。无论单步还是连续运行模式,本 skill 都只汇报。

## 工作流

1. 运行状态脚本:
```bash
python3 xinci-workflow/xinci-core/scripts/report_status.py
```
2. 如实转述输出:各状态候选数;每个候选的年龄、距上次复查天数、expiry 余量;"expiry 已过且非终态"清单;可逆 G1/G2/G3 否决已到 `recheck_after` 的清单。先总数,后明细,异常置底单列。
   - 只陈述事实("candidate-x 距上次复查 12 天,expiry 还剩 5 天"),不加"建议尽快复查"之类的驱动性措辞;复查与否、何时复查是用户的决定。
   - expiry 已过的候选照实列出,等用户处置,不代替用户提议 expired;到期不会自动重开。处置归属见通用约定「四条 expired 边的提议人」。
3. 用户要求或输出异常时,补账本与运行清单完整性检查:
```bash
python3 xinci-workflow/xinci-core/scripts/validate_ledger.py
```
