---
name: xinci-status
description: 新词工作流状态看板,只读汇报候选账本的全局事实。当用户想看新词工作流状态、账本里有什么、各候选进展到哪、有哪些 expiry 快到期时使用。纯汇报不驱动。English triggers: xinci status, keyword workflow status, candidate ledger overview. 发现新词用 xinci-scan,复查用 xinci-track。
---

# xinci-status 状态看板

只读汇报,零判断,零写入。这套工作流由用户人工驱动:本 skill 只陈述账本事实,不推荐动作、不安排日程、不执行任何状态转移。

> **路径约定**:相对路径以仓库根为基准(正本在 `xinci-workflow/xinci-status/SKILL.md`,symlink 加载时 `readlink` 后上溯两级即仓库根);bash 在仓库根执行,或展开为绝对路径。

## 行动前必读

- xinci-workflow/xinci-core/生命周期契约.md(状态词汇与时间字段约定)

## 工作流

1. 运行状态脚本:

```bash
python3 xinci-workflow/xinci-core/scripts/report_status.py
```

2. 如实转述输出:各状态候选数;每个候选的年龄、距上次复查天数、expiry 余量;"expiry 已过且非终态"清单。
3. 可补充运行账本完整性检查(用户要求或输出异常时):

```bash
python3 xinci-workflow/xinci-core/scripts/validate_ledger.py
```

## 硬规则

- 零写入。本 skill 不调用 registrar,不修改任何文件。
- 账本是唯一事实来源;不从证据文件反推状态,不脑补账本没有的信息。
- 只陈述事实("candidate-x 距上次复查 12 天,expiry 还剩 5 天"),不加"建议尽快复查"之类的驱动性措辞。复查与否、何时复查,是用户的决定。
- expiry 已过的候选照实列出,等用户处置;不代替用户提议 expired,那是 xinci-track 复查后的职责。
- 汇报以用户能一遍看懂为准:先总数,后明细,异常置底单列。
