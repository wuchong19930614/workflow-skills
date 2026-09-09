# xinci-simple-run 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 [设计稿](../specs/2026-09-09-xinci-simple-run-design.md) 新增薄驱动器 skill `xinci-simple-run`，暗号 `xinci_simple_run max_rounds=N`，连续跑 N 轮 scan + verify。

**Architecture:** 纯文档 skill，不新增脚本；每轮派一个子代理按既有 scan / verify SKILL 跑完整轮，运行清单复用 `run_log.py` 加 `--suffix r<k>`。

**Tech Stack:** Markdown、symlink。

---

### Task 1: xinci-simple-run/SKILL.md

**Files:**
- Create: `xinci-simple-workflow/xinci-simple-run/SKILL.md`

- [x] **Step 1: 写 SKILL.md**，内容源：设计稿 §1–§6 逐节展开。frontmatter：

```yaml
---
name: xinci-simple-run
description: '流量型选词的连续运行驱动器。当消息中出现启动暗号 xinci_simple_run（可带 max_rounds=N,默认 3）、通过 /xinci-simple-run 或 Skill 工具调用、或用户说"连续跑几轮 simple"时使用。一轮 = 一次 xinci-simple-scan + verify 排序前 5;跑满预算才停,中途出 verified 不停。English triggers: xinci_simple_run, run simple workflow N rounds. 这是 xinci-simple-workflow,不是 xinci 新词工作流的 xinci-run。'
---
```

- [x] **Step 2: 自查**

Run: `python3 -c "import re;t=open('xinci-simple-workflow/xinci-simple-run/SKILL.md',encoding='utf-8').read();m=re.match(r'^---\nname: (\S+)\ndescription: .+\n---\n',t,re.S);print('ok' if m and 'xinci_simple_run' in t and 'max_rounds' in t else 'BAD')"`
Expected: `ok`
Run: `grep -n "xinci-workflow/\|xinci-core/" xinci-simple-workflow/xinci-simple-run/SKILL.md` → 无输出

- [x] **Step 3: 提交**

```bash
git add xinci-simple-workflow/xinci-simple-run/SKILL.md docs/superpowers/specs/2026-09-09-xinci-simple-run-design.md docs/superpowers/plans/2026-09-09-xinci-simple-run.md
git commit -m "xinci-simple:run 连续运行驱动器(暗号 xinci_simple_run)"
```

### Task 2: README、symlink、验收

**Files:**
- Modify: `xinci-simple-workflow/README.md`（单元清单加一行）
- Modify: `README.md`（xinci-simple 单元清单加一行）

- [x] **Step 1: 两处 README 各加一行**

```markdown
| [xinci-simple-run](xinci-simple-run/SKILL.md) | 连续运行驱动器，暗号 `xinci_simple_run max_rounds=N`：一轮 = scan 一批 + verify 前 5，跑满才停 |
```

（仓库根 README 的链接路径前加 `xinci-simple-workflow/`。）

- [x] **Step 2: symlink**

```bash
ln -sfn "$(pwd)/xinci-simple-workflow/xinci-simple-run" ~/.claude/skills/xinci-simple-run
ln -sfn "$(pwd)/xinci-simple-workflow/xinci-simple-run" ~/.codex/skills/xinci-simple-run
readlink ~/.claude/skills/xinci-simple-run ~/.codex/skills/xinci-simple-run
```

- [x] **Step 3: 验收**

```bash
grep -c "xinci-simple-run" README.md xinci-simple-workflow/README.md
python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q
git diff --check
```

Expected：两处 README 各 ≥ 1；`Ran 46 tests ... OK`；无输出。

- [x] **Step 4: 提交**

```bash
git add README.md xinci-simple-workflow/README.md
git commit -m "xinci-simple:README 与 symlink 接入 run 驱动器"
```
