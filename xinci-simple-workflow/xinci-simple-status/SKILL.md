---
name: xinci-simple-status
description: '流量型选词工作流的只读看板:各状态计数、待核验候选按排序分、已搁置停留天数、已验证的报告路径。当用户想看 simple 工作流状态、老词账本里有什么时使用。English triggers: simple status, traffic keyword ledger overview. 这是 xinci-simple-workflow,不是 xinci 新词工作流的 xinci-status。'
---

# xinci-simple-status 看板

只读汇报：不调用 `ledger.py`，不改账本与任何产出；数据区未配置时按第 1 步处理。账本是唯一事实来源，不从证据文件反推状态。

## 工作流

1. 确认数据区并出看板：
   ```bash
   python3 xinci-simple-workflow/xinci-simple-core/scripts/report_status.py
   ```
   退出码 2 提示"数据区未配置" → 停下问用户数据区放哪，不替用户选；拿到路径后 `init_workspace.py --data-root <路径>`。
2. 如实转述：先各状态计数，再三段明细——待核验（按排序分）、已搁置（停留天数，超 90 天的行有提醒）、已验证（form / base / 报告路径、投入基线是否登记、是否有实际反馈；报告缺失会标出）。既有 verified 有 integrity_error 时明确标“待复核”，不能当作当前有效机会；只陈述事实，不加"建议尽快核验"之类的驱动性措辞；下一步做什么是用户的决定。
3. 用户要求或输出异常时补完整性检查：
   ```bash
   python3 xinci-simple-workflow/xinci-simple-core/scripts/validate_ledger.py
   ```
   错误逐条转述；缺报告、旧 verified 未满足 v2、绑定证据变动是错误；孤儿证据目录是警告，均照实列。

`--json` 出机器格式。发现新簇用 xinci-simple-scan，核验用 xinci-simple-verify。
