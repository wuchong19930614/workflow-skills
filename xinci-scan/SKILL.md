---
name: xinci-scan
description: 扫描发现新兴/全新的英文 Google 搜索词候选:真浏览器直读 Reddit/Product Hunt/Hacker News/X/应用商店等信号面,或从有日期的法规/平台/技术变化推导付费者任务,捕获即跑 G1–G5 初筛并注册进账本。当用户说扫一下今天有什么新词、发现新机会、跑一轮雷达时使用。English triggers: scan new keywords, keyword radar, discover emerging terms. 看状态用 xinci-status,复查已有候选用 xinci-track。
---

# xinci-scan 扫描发现

捕获太新以致没有数据的搜索词,当场初筛,注册进账本。速度是这条赛道的全部意义:晚三天发现的候选通常已经没价值。空扫描是合法产出——如实报告远好于凑数。

## 行动前必读

- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/闸门契约.md(G1–G5 定义;G5 先于 G2 执行)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/陷阱类别.md(已知陷阱,命中直接验 G3)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/数据采集指南.md(真浏览器原则与来源表)
- /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/生命周期契约.md(注册与转移的证据要求)

## 工作流

1. **选两三个来源,真浏览器打开阅读。** 来源表见数据采集指南;轮换选源,覆盖优先。也可走变化面:从有日期的法规/平台/技术/成本变化推导受影响付费者的被迫任务,译成自然搜索语言假设。记录打开的每个 URL 和时间戳。
2. **提取命名候选。** 抓人们实际使用的词,不做转述。社区昵称和官方名竞争时两个都记(aliases)。
3. **判断可搜索性。** 这个东西让人想完成什么任务?没有任务的发布没有词。优先找挂着重复需求的名字:guide、calculator、converter、checker、tier list、兼容性问题。
4. **先查陷阱类别(G5)。** 命中已知陷阱的候选直接跳 G3 验证,失败即弃,不读 SERP 结构。
5. **跑 G1(最先),再 G2、G3、G4。** G1 一票否决且永不为省时间跳过。竞争判断读完整首页,禁止 top-3 定论。
6. **窗口评估。** 估计窗口以天/周/月计(可发现性、多少人能做同样的页面、官方答案多久出现),写明推理。
7. **写观察文件并注册。** 每个候选一份 `证据/<slug>/<日期>-scan.json`(要点式,schema 见 数据结构/observation.schema.json),然后:

```bash
python3 /Users/vito.wu/IdeaProjects/workflow-skills/xinci-core/scripts/registrar.py register \
  --slug <slug> --term "<精确措辞>" --source-url <URL> --source-note "<现场摘要>" \
  --task "<搜索者要完成的任务>" --evidence "证据/<slug>/<日期>-scan.json"
```

8. **提议下一步,由用户确认后执行转移:**
   - G1–G5 全过、窗口以周/月计 → 提议 `screened → tracking`(带 expiry 与失效条件);
   - G1–G5 全过、窗口以天计 → 提议走快道(转给 xinci-decide 快速模式);
   - 任一闸门否决 → 提议 `rejected`(带失败闸门与现场证据要点)。
9. **写运行清单** `运行/<日期>-xinci-scan.json`:打开过的来源、触及的候选、计费调用数(本阶段应为 0)。

## 硬规则

- 真浏览器直读,不走 API/MCP 数据工具拉社区内容;未在本次会话打开的来源不得声称已检查。
- 精确措辞 + 来源 URL + 时间戳,缺一不注册;凭记忆重构的词不是证据。
- 窗口期禁用 KD、KGR、CPC、Google Trends;Semrush 查无是这条赛道的定义属性,不作为否决理由。
- 每个进入 tracking 的候选必须带 expiry(附推理)和至少一条失效条件。
- 区分"发布"与"一时热闹":只产生一周好奇、没有重复任务的东西,直说不值得,不进清单。
- 提议与执行分离:转移一律经用户确认后才调 registrar。
- 本 skill 不注册域名、不花钱、不发布任何内容。
- 扫描产出为零时如实说零;禁止凑数,禁止 maybe 清单。
