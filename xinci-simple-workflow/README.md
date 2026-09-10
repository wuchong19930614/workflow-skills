# xinci-simple-workflow（流量型选词）

从已有搜索量的 US 英文主题簇中，找首屏未完成任务、竞争可争取、base 月收入 ≥ $200 的机会，输出 md/html 报告。与 xinci 新词工作流零运行时依赖。

| 单元 | 职责 |
| --- | --- |
| [scan](xinci-simple-scan/SKILL.md) | 词根/小站/论坛发现，补足下一批待核验候选 |
| [verify](xinci-simple-verify/SKILL.md) | 收入上限预筛、任务组现场核验、逐组收入与报告 |
| [run](xinci-simple-run/SKILL.md) | `xinci_simple_run max_rounds=N`，默认3轮，可恢复，发现与核验按池量配合 |
| [status](xinci-simple-status/SKILL.md) | 只读看板，披露历史 verified 的完整性缺口 |
| [选词契约](xinci-simple-core/选词契约.md) | 唯一判据；[数据采集](xinci-simple-core/数据采集.md)管通道；[命令与观察](xinci-simple-core/命令与观察.md)管调用 |

## 投入与反馈

报告披露最小产品、进入优势、成本与工时、收入爬坡、回本期和最小验证计划。缺失投入明确为未知，研究通过不等于商业验证。

具体口径见[契约 §10](xinci-simple-core/选词契约.md#10-投入判断与现实反馈)，可复制输入与命令见[命令与观察](xinci-simple-core/命令与观察.md#投入计划与实际反馈)。当前每候选追踪一个原始试验；开发、上线、投放和招募仍需相应的明确授权。

## 首次使用

```bash
python3 xinci-simple-workflow/xinci-simple-core/scripts/init_workspace.py --data-root <用户指定数据区>
```

解析：命令参数 > XINCI_SIMPLE_DATA_ROOT > 仓库 `.xinci-simple-data-root` > 拒绝猜测。

本地接入可将四个 Skill 目录链接到所用环境的 skills 目录；不重复安装 core，也不修改其他工作流。

## 检查

```bash
python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -q
python3 xinci-simple-workflow/xinci-simple-core/scripts/validate_ledger.py
python3 xinci-simple-workflow/xinci-simple-core/scripts/run_log.py --plan
```

`validate_ledger.py` 非零意味着实际账本需要处理，不能以单元测试通过代替业务完整性。历史纠错与重新核验的入口见命令文档。
