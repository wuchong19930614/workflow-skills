# xinci-simple-workflow 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 [设计稿](../specs/2026-09-09-xinci-simple-workflow-design.md) 落地 `xinci-simple-workflow/`：3 个 skill + 1 个 core（2 份契约、2 份 schema、9 个脚本、测试），接入双环境，初始化独立数据区。

**Architecture:** 判据只写在 `xinci-simple-core/选词契约.md`；4 态账本由 `ledger.py` 用合法转移表强制；`rank.py` / `revenue_model.py` 是纯函数 + CLI；`build_report.py` 从账本与观察生成报告；SKILL.md 只串流程、指向契约。与 xinci 零运行时依赖。

**Tech Stack:** Python 3 标准库（零第三方依赖）、unittest、Markdown、symlink。

**与设计稿的差异（本计划补的）：** 设计稿 §8.3 脚本清单漏了运行清单的写入脚本，本计划加 `run_log.py`（Task 5）。

---

## 文件结构

```
xinci-simple-workflow/
├── README.md                                    单元清单、数据区、symlink、测试命令
├── xinci-simple-core/
│   ├── 选词契约.md                               唯一判据来源
│   ├── 数据采集.md                               Semrush 纪律、SERP 读取规程、两条通道、预检
│   ├── 数据结构/
│   │   ├── candidate.schema.json
│   │   └── observation.schema.json
│   └── scripts/
│       ├── _common.py            now() / atomic_save() / ledger_path() / load_ledger()
│       ├── data_root.py          解析顺序 --data-root > XINCI_SIMPLE_DATA_ROOT > .xinci-simple-data-root > 退出码 2
│       ├── init_workspace.py     建 账本/证据/报告/运行 + 空账本，幂等
│       ├── ledger.py             register / transition / list；LEGAL / TERMINAL；证据存在；原子写
│       ├── rank.py               五项归一化等权 → rank_score，回写账本
│       ├── revenue_model.py      form + 簇量 + 折减 → 三情景 + volume_needed_for_500
│       ├── run_log.py            写 运行/<日期>-<skill>[-HHMM].json
│       ├── build_report.py       账本 + 最新 verify 观察 → 报告/<slug>.md（9 节）
│       ├── report_status.py      只读看板
│       ├── validate_ledger.py    不变式校验
│       └── tests/
│           ├── __init__.py
│           ├── helpers.py        临时数据区 + 造候选 + 造观察
│           ├── test_data_root.py
│           ├── test_ledger.py
│           ├── test_rank.py
│           ├── test_revenue_model.py
│           ├── test_run_log.py
│           ├── test_build_report.py
│           ├── test_report_status.py
│           └── test_validate_ledger.py
├── xinci-simple-scan/SKILL.md
├── xinci-simple-verify/SKILL.md
└── xinci-simple-status/SKILL.md
```

所有 bash 在仓库根 `/Users/vito.wu/IdeaProjects/workflow-skills` 执行。测试命令固定为：

```bash
python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q
```

分支：`xinci-simple-workflow`（已存在，设计稿在上面）。每个 Task 结束提交一次，提交信息中文。

---

### Task 1: 基建 —— 目录、gitignore、_common、data_root、init_workspace

**Files:**
- Modify: `.gitignore`
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/_common.py`
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/data_root.py`
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/init_workspace.py`
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/tests/__init__.py`（空文件）
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/tests/helpers.py`
- Test: `xinci-simple-workflow/xinci-simple-core/scripts/tests/test_data_root.py`

- [ ] **Step 1: 建目录并加 gitignore**

```bash
mkdir -p xinci-simple-workflow/xinci-simple-core/scripts/tests xinci-simple-workflow/xinci-simple-core/数据结构 xinci-simple-workflow/xinci-simple-scan xinci-simple-workflow/xinci-simple-verify xinci-simple-workflow/xinci-simple-status
touch xinci-simple-workflow/xinci-simple-core/scripts/tests/__init__.py
printf '\n# xinci-simple 的数据区配置同样是本地选择,不入库\n.xinci-simple-data-root\n' >> .gitignore
```

- [ ] **Step 2: 写失败测试 test_data_root.py**

```python
# 数据区解析:显式 > 环境变量 > 仓库配置 > 拒绝。不猜位置。
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import data_root as D


class DataRootTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._cfg_patch = mock.patch.object(D, "REPO_ROOT", self.tmp)
        self._cfg_patch.start()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(D.ENV_VAR, None)

    def tearDown(self):
        self._env.stop()
        self._cfg_patch.stop()
        self._tmp.cleanup()

    def test_explicit_wins(self):
        os.environ[D.ENV_VAR] = "/env/root"
        D.save("/cfg/root")
        self.assertEqual(D.resolve("/explicit"), Path("/explicit"))

    def test_env_over_config(self):
        os.environ[D.ENV_VAR] = "/env/root"
        D.save("/cfg/root")
        self.assertEqual(D.resolve(), Path("/env/root"))

    def test_config_when_nothing_else(self):
        D.save(self.tmp / "data")
        self.assertEqual(D.resolve(), (self.tmp / "data").resolve())

    def test_refuses_to_guess(self):
        with self.assertRaises(D.DataRootNotConfigured):
            D.resolve()

    def test_cli_exit_code_2_when_unconfigured(self):
        with self.assertRaises(SystemExit) as cm:
            D.resolve_or_exit(None)
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `ImportError: No module named 'data_root'` 或 ModuleNotFoundError

- [ ] **Step 4: 写 _common.py**

```python
#!/usr/bin/env python3
"""共用原语:时间戳、原子写、账本路径与读取。顶层不依赖任何其他工作流模块。"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    """UTC 秒级 ISO 时间戳,所有落盘时间字段统一用它。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_save(path, obj) -> None:
    """先写同目录临时文件再 os.replace,读者永远看不到半截 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def ledger_path(data_root) -> Path:
    return Path(data_root) / "账本" / "候选账本.json"


def load_ledger(data_root) -> dict:
    p = ledger_path(data_root)
    if not p.is_file():
        raise FileNotFoundError(f"账本不存在: {p}(先运行 init_workspace.py)")
    return json.loads(p.read_text(encoding="utf-8"))


def load_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
```

- [ ] **Step 5: 写 data_root.py**

```python
#!/usr/bin/env python3
"""数据区定位:唯一解析入口。不猜位置。

解析顺序:1. 显式 --data-root  2. 环境变量 XINCI_SIMPLE_DATA_ROOT
3. 仓库根配置 .xinci-simple-data-root  4. 抛 DataRootNotConfigured。
理由同 xinci:数据区放哪是用户的决定,脚本宁可拒绝执行也不猜。
"""
import os
from pathlib import Path

ENV_VAR = "XINCI_SIMPLE_DATA_ROOT"
CONFIG_NAME = ".xinci-simple-data-root"
# scripts/ → xinci-simple-core/ → xinci-simple-workflow/ → 仓库根
REPO_ROOT = Path(__file__).resolve().parents[3]


class DataRootNotConfigured(Exception):
    """数据区未配置。文案面向执行者,含可照做的下一步。"""


_MESSAGE = f"""数据区未配置,拒绝执行(不猜位置)。

xinci-simple 的执行产出(账本、证据、报告、运行清单)存在哪里,必须由用户指定。
**先问用户,不要替他选。**问清之后任选其一:

  1) 落盘到仓库配置(推荐):
       python3 xinci-simple-workflow/xinci-simple-core/scripts/init_workspace.py --data-root <路径>
     它会创建目录结构与空账本,并把路径写进 {REPO_ROOT / CONFIG_NAME}
  2) 只在当前 shell 生效:export {ENV_VAR}=<路径>
  3) 单次调用:给脚本加 --data-root <路径>"""


def config_path() -> Path:
    return REPO_ROOT / CONFIG_NAME


def read_config():
    p = config_path()
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8").strip()
    return Path(text) if text else None


def save(path) -> Path:
    p = config_path()
    p.write_text(str(Path(path).expanduser().resolve()) + "\n", encoding="utf-8")
    return p


def resolve(explicit=None) -> Path:
    for cand in (explicit, os.environ.get(ENV_VAR) or None, read_config()):
        if cand:
            return Path(cand).expanduser()
    raise DataRootNotConfigured(_MESSAGE)


def resolve_or_exit(explicit=None) -> Path:
    import sys
    try:
        return resolve(explicit)
    except DataRootNotConfigured as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(2)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="打印数据区路径;未配置时退出码 2")
    ap.add_argument("--data-root", default=None)
    a = ap.parse_args(argv)
    print(resolve_or_exit(a.data_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 写 init_workspace.py**

```python
#!/usr/bin/env python3
"""初始化数据区目录结构与空账本。幂等:已存在的不动。"""
import argparse
import json
import sys
from pathlib import Path

import data_root

SUBDIRS = ("账本", "证据", "报告", "运行")


def init_workspace(root) -> list:
    root = Path(root)
    created = []
    for name in SUBDIRS:
        d = root / name
        if not d.is_dir():
            d.mkdir(parents=True)
            created.append(str(d))
    ledger = root / "账本" / "候选账本.json"
    if not ledger.is_file():
        ledger.write_text(json.dumps({"schema_version": 1, "candidates": {}},
                                     ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        created.append(str(ledger))
    return created


def main(argv=None):
    ap = argparse.ArgumentParser(description="初始化 xinci-simple 数据区;显式 --data-root 会落盘到仓库配置")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--no-save", action="store_true", help="只建目录,不写仓库配置")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    created = init_workspace(root)
    print("数据区:" + str(root))
    print("已创建:" + (", ".join(created) if created else "无(全部已存在)"))
    if a.data_root and not a.no_save:
        print("已记入仓库配置:" + str(data_root.save(root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: 写 tests/helpers.py（后续所有测试共用）**

```python
"""测试共用:临时数据区、造候选、造观察文件。"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import init_workspace  # noqa: E402


class TmpRoot:
    """with TmpRoot() as root: ... 自动 init_workspace 并清理。"""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        init_workspace.init_workspace(self.root)
        return self.root

    def __exit__(self, *exc):
        self._tmp.cleanup()


def write_obs(root, slug, name, **fields) -> str:
    """写一份观察文件,返回数据区相对路径。"""
    obs = {"slug": slug, "observed_at": "2026-09-10T05:40:00+00:00", "stage": "scan",
           "source_urls": ["https://www.semrush.com/analytics/keywordmagic/"], "points": ["x"]}
    obs.update(fields)
    p = root / "证据" / slug / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obs, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"证据/{slug}/{name}"


CLUSTER = {"total_volume": 182000,
           "keywords": [{"term": "heic to jpg", "volume": 90500, "kd": 38},
                        {"term": "heic to jpg converter", "volume": 40500, "kd": 41}]}
SEED = {"type": "root", "value": "Converter", "queried_at": "2026-09-10T03:12:00+00:00"}
PROXY = {"kd": 38, "low_dr_count": 4, "ugc_count": 2, "content_age_median_days": 540}
VERIFY_OBS = {
    "stage": "verify",
    "browser_preflight": {"controllable": True, "desktop": True, "region": "us", "logged_out": True,
                          "evidence": "Sign in 可见;#gb 无账号元素"},
    "query_url": "https://www.google.com/search?q=heic+to+jpg+converter&gl=us&hl=en&pws=0",
    "ai_overview": {"present": True, "completes_task": False, "excerpt": "lists converters"},
    "serp_top10": [
        {"pos": 1, "domain": "cloudconvert.com", "dr": 78, "type": "tool", "completes_task": True, "dated": "2026-06"},
        {"pos": 2, "domain": "reddit.com", "dr": 92, "type": "forum", "completes_task": False, "dated": "2024-01"},
    ],
    "page2_note": "第二页起为博客与问答",
    "trends_12m": "全年平稳",
    "scope_recheck": {"ymyl": False, "firsthand": False, "brand_nav": False, "news": False},
    "source_urls": ["https://www.google.com/search?q=heic+to+jpg+converter&gl=us&hl=en&pws=0"],
    "points": ["首屏 AIO 只罗列工具名"],
}
REVENUE = {"downside": 320, "base": 640, "upside": 960, "volume_needed_for_500": 142000,
           "assumptions_version": "2026-09-09"}
```

- [ ] **Step 8: 跑测试确认通过**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `Ran 5 tests ... OK`

- [ ] **Step 9: 提交**

```bash
git add .gitignore xinci-simple-workflow/
git commit -m "xinci-simple:基建——数据区解析、初始化、共用原语与测试 helper"
```

---

### Task 2: ledger.py —— 4 态账本

**Files:**
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/ledger.py`
- Test: `xinci-simple-workflow/xinci-simple-core/scripts/tests/test_ledger.py`

- [ ] **Step 1: 写失败测试**

```python
# ledger:4 态合法表、证据存在、reason 非空、verified 需 form+revenue、history 只追加、原子写。
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
from helpers import TmpRoot, write_obs, CLUSTER, SEED, PROXY, REVENUE


def reg(root, slug="heic-to-jpg-converter"):
    ev = write_obs(root, slug, "2026-09-10-scan.json")
    L.register(root, slug=slug, primary_keyword=slug.replace("-", " "), cluster=CLUSTER,
               seed=SEED, proxy=PROXY, evidence=[ev], by="xinci-simple-scan", reason="准入:簇量 182K")
    return slug


class LedgerTest(unittest.TestCase):
    def test_register_creates_found(self):
        with TmpRoot() as root:
            slug = reg(root)
            rec = L.load(root)["candidates"][slug]
            self.assertEqual(rec["state"], "found")
            self.assertIsNone(rec["form"])
            self.assertIsNone(rec["revenue"])
            self.assertEqual(len(rec["history"]), 1)
            self.assertEqual(rec["history"][0]["to"], "found")
            self.assertIsNone(rec["history"][0]["from"])

    def test_register_requires_existing_evidence(self):
        with TmpRoot() as root:
            with self.assertRaises(L.LedgerError):
                L.register(root, slug="x", primary_keyword="x", cluster=CLUSTER, seed=SEED,
                           proxy=PROXY, evidence=["证据/x/none.json"], by="xinci-simple-scan", reason="r")

    def test_register_duplicate_rejected(self):
        with TmpRoot() as root:
            reg(root)
            with self.assertRaises(L.LedgerError):
                reg(root)

    def test_illegal_transition_rejected(self):
        with TmpRoot() as root:
            slug = reg(root)
            ev = write_obs(root, slug, "2026-09-10-verify.json", stage="verify")
            L.transition(root, slug, to="rejected", evidence=[ev], by="xinci-simple-verify", reason="G1 直答")
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="r",
                             form="tool", revenue=REVENUE)

    def test_reason_required(self):
        with TmpRoot() as root:
            slug = reg(root)
            ev = write_obs(root, slug, "2026-09-10-verify.json", stage="verify")
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to="rejected", evidence=[ev], by="x", reason="")

    def test_verified_requires_form_and_revenue(self):
        with TmpRoot() as root:
            slug = reg(root)
            ev = write_obs(root, slug, "2026-09-10-verify.json", stage="verify")
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="r")
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="r", form="tool")
            L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="base 640",
                         form="tool", revenue=REVENUE)
            rec = L.load(root)["candidates"][slug]
            self.assertEqual(rec["state"], "verified")
            self.assertEqual(rec["form"], "tool")
            self.assertEqual(rec["revenue"]["base"], 640)

    def test_parked_then_verified(self):
        with TmpRoot() as root:
            slug = reg(root)
            ev = write_obs(root, slug, "2026-09-10-verify.json", stage="verify")
            L.transition(root, slug, to="parked", evidence=[ev], by="x", reason="季节性")
            L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="r",
                         form="info", revenue=REVENUE)
            rec = L.load(root)["candidates"][slug]
            self.assertEqual([h["to"] for h in rec["history"]], ["found", "parked", "verified"])

    def test_invalid_form_rejected(self):
        with TmpRoot() as root:
            slug = reg(root)
            ev = write_obs(root, slug, "2026-09-10-verify.json", stage="verify")
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="r",
                             form="saas", revenue=REVENUE)

    def test_no_tmp_left_behind(self):
        with TmpRoot() as root:
            reg(root)
            self.assertEqual([p.name for p in (root / "账本").iterdir()], ["候选账本.json"])

    def test_list_by_state(self):
        with TmpRoot() as root:
            a = reg(root, "a-term")
            b = reg(root, "b-term")
            ev = write_obs(root, b, "2026-09-10-verify.json", stage="verify")
            L.transition(root, b, to="rejected", evidence=[ev], by="x", reason="G2")
            self.assertEqual([r["slug"] for r in L.list_candidates(root, state="found")], [a])
            self.assertEqual(len(L.list_candidates(root)), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `ModuleNotFoundError: No module named 'ledger'`

- [ ] **Step 3: 写 ledger.py**

```python
#!/usr/bin/env python3
"""候选账本:唯一写入口。4 态、合法转移表、证据必须存在、history 只追加、原子写。

判据不在这里:这里只保证"状态机不被违反、证据可追溯"。判据看 选词契约.md。
"""
import argparse
import json
import sys
from pathlib import Path

from _common import atomic_save, ledger_path, load_ledger, now

STATES = ("found", "parked", "verified", "rejected")
TERMINAL = {"verified", "rejected"}
LEGAL = {
    ("found", "verified"), ("found", "rejected"), ("found", "parked"),
    ("parked", "verified"), ("parked", "rejected"),
}
FORMS = ("info", "lookup", "tool", "commercial", "mixed")
REVENUE_KEYS = ("downside", "base", "upside", "volume_needed_for_500", "assumptions_version")


class LedgerError(Exception):
    pass


def _require(cond, msg):
    if not cond:
        raise LedgerError(msg)


def _check_evidence(root, refs):
    _require(isinstance(refs, list) and refs, "至少 1 个证据文件")
    for ref in refs:
        _require((Path(root) / ref).is_file(), f"证据文件不存在: {ref}")


def load(root) -> dict:
    return load_ledger(root)


def save(root, ledger) -> None:
    atomic_save(ledger_path(root), ledger)


def register(root, *, slug, primary_keyword, cluster, seed, proxy, evidence, by, reason) -> dict:
    _require(slug and slug == slug.lower() and " " not in slug, "slug 须小写且无空格")
    _require(primary_keyword and primary_keyword.strip(), "primary_keyword 必填")
    _require(isinstance(cluster, dict) and isinstance(cluster.get("total_volume"), int), "cluster.total_volume 须为整数")
    _require(isinstance(cluster.get("keywords"), list), "cluster.keywords 须为数组")
    _require(isinstance(seed, dict) and seed.get("type") in ("root", "small_site", "forum"), "seed.type 须为 root|small_site|forum")
    _require(isinstance(proxy, dict) and isinstance(proxy.get("kd"), (int, float)), "proxy.kd 必填")
    _require(by and reason and reason.strip(), "by 与 reason 必填")
    _check_evidence(root, evidence)
    ledger = load(root)
    _require(slug not in ledger["candidates"], f"slug 已存在: {slug}")
    rec = {
        "slug": slug, "primary_keyword": primary_keyword, "cluster": cluster, "seed": seed,
        "state": "found", "proxy": dict(proxy), "form": None, "revenue": None,
        "evidence_refs": list(evidence),
        "history": [{"at": now(), "from": None, "to": "found", "by": by, "reason": reason}],
    }
    ledger["candidates"][slug] = rec
    save(root, ledger)
    return rec


def transition(root, slug, *, to, evidence, by, reason, form=None, revenue=None) -> dict:
    ledger = load(root)
    _require(slug in ledger["candidates"], f"候选不存在: {slug}")
    rec = ledger["candidates"][slug]
    frm = rec["state"]
    _require(to in STATES, f"未知状态: {to}")
    _require((frm, to) in LEGAL, f"非法转移: {frm}→{to}")
    _require(by and reason and reason.strip(), "by 与 reason 必填")
    _check_evidence(root, evidence)
    if to == "verified":
        _require(form in FORMS, f"verified 要求 form ∈ {FORMS}")
        _require(isinstance(revenue, dict) and all(k in revenue for k in REVENUE_KEYS),
                 f"verified 要求 revenue 含 {REVENUE_KEYS}")
        _require(isinstance(revenue["base"], (int, float)) and revenue["base"] >= 500,
                 "verified 要求 revenue.base ≥ 500;不达标应转 rejected")
    if form is not None:
        _require(form in FORMS, f"form ∈ {FORMS}")
        rec["form"] = form
    if revenue is not None:
        rec["revenue"] = revenue
    rec["state"] = to
    for ref in evidence:
        if ref not in rec["evidence_refs"]:
            rec["evidence_refs"].append(ref)
    rec["history"].append({"at": now(), "from": frm, "to": to, "by": by, "reason": reason})
    save(root, ledger)
    return rec


def list_candidates(root, state=None) -> list:
    recs = list(load(root)["candidates"].values())
    if state:
        recs = [r for r in recs if r["state"] == state]
    return sorted(recs, key=lambda r: r["slug"])


def _json_arg(text, name):
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LedgerError(f"{name} 不是合法 JSON: {e}")


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="xinci-simple 账本写入口")
    ap.add_argument("--data-root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    r.add_argument("--slug", required=True)
    r.add_argument("--primary-keyword", required=True)
    r.add_argument("--cluster-json", required=True)
    r.add_argument("--seed-json", required=True)
    r.add_argument("--proxy-json", required=True)
    r.add_argument("--evidence", action="append", required=True)
    r.add_argument("--by", required=True)
    r.add_argument("--reason", required=True)
    t = sub.add_parser("transition")
    t.add_argument("--slug", required=True)
    t.add_argument("--to", required=True, choices=STATES)
    t.add_argument("--evidence", action="append", required=True)
    t.add_argument("--by", required=True)
    t.add_argument("--reason", required=True)
    t.add_argument("--form", default=None, choices=FORMS)
    t.add_argument("--revenue-json", default=None)
    ls = sub.add_parser("list")
    ls.add_argument("--state", default=None, choices=STATES)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "register":
            rec = register(root, slug=a.slug, primary_keyword=a.primary_keyword,
                           cluster=_json_arg(a.cluster_json, "--cluster-json"),
                           seed=_json_arg(a.seed_json, "--seed-json"),
                           proxy=_json_arg(a.proxy_json, "--proxy-json"),
                           evidence=a.evidence, by=a.by, reason=a.reason)
            print(f"已登记 {rec['slug']} → found")
        elif a.cmd == "transition":
            rec = transition(root, a.slug, to=a.to, evidence=a.evidence, by=a.by, reason=a.reason,
                             form=a.form,
                             revenue=_json_arg(a.revenue_json, "--revenue-json") if a.revenue_json else None)
            print(f"{rec['slug']}:{rec['history'][-2]['to']} → {rec['state']}")
        else:
            for rec in list_candidates(root, a.state):
                score = (rec.get("proxy") or {}).get("rank_score")
                print(f"{rec['state']:9} {rec['slug']:40} 簇量 {rec['cluster']['total_volume']:>8} "
                      f"rank {score if score is not None else '-'}")
    except LedgerError as e:
        print(f"拒收: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `Ran 15 tests ... OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-simple-workflow/
git commit -m "xinci-simple:ledger 4 态账本与合法转移表"
```

---

### Task 3: rank.py —— 代理排序

**Files:**
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/rank.py`
- Test: `xinci-simple-workflow/xinci-simple-core/scripts/tests/test_rank.py`

- [ ] **Step 1: 写失败测试**

```python
# rank:五项在 found 池内归一化(KD 反向),等权平均;缺失取 0.5;不否决。
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import rank as K
from helpers import TmpRoot, write_obs, CLUSTER, SEED


def mk(root, slug, kd, vol, low_dr, ugc, age):
    ev = write_obs(root, slug, "2026-09-10-scan.json")
    cluster = dict(CLUSTER, total_volume=vol)
    proxy = {"kd": kd, "low_dr_count": low_dr, "ugc_count": ugc, "content_age_median_days": age}
    L.register(root, slug=slug, primary_keyword=slug, cluster=cluster, seed=SEED, proxy=proxy,
               evidence=[ev], by="t", reason="r")


class RankTest(unittest.TestCase):
    def test_monotonic_each_dimension(self):
        with TmpRoot() as root:
            mk(root, "base", kd=30, vol=100000, low_dr=3, ugc=2, age=400)
            mk(root, "lower-kd", kd=10, vol=100000, low_dr=3, ugc=2, age=400)
            mk(root, "more-vol", kd=30, vol=300000, low_dr=3, ugc=2, age=400)
            mk(root, "more-lowdr", kd=30, vol=100000, low_dr=6, ugc=2, age=400)
            mk(root, "more-ugc", kd=30, vol=100000, low_dr=3, ugc=5, age=400)
            mk(root, "older", kd=30, vol=100000, low_dr=3, ugc=2, age=900)
            scores = K.rank_all(root)
            for better in ("lower-kd", "more-vol", "more-lowdr", "more-ugc", "older"):
                self.assertGreater(scores[better], scores["base"], better)

    def test_missing_field_neutral(self):
        with TmpRoot() as root:
            mk(root, "a", kd=30, vol=100000, low_dr=3, ugc=2, age=400)
            mk(root, "b", kd=10, vol=300000, low_dr=6, ugc=5, age=900)
            ev = write_obs(root, "c", "2026-09-10-scan.json")
            L.register(root, slug="c", primary_keyword="c", cluster=dict(CLUSTER, total_volume=200000),
                       seed=SEED, proxy={"kd": 20}, evidence=[ev], by="t", reason="r")
            scores = K.rank_all(root)
            self.assertTrue(0 <= scores["c"] <= 1)

    def test_writes_back_and_only_found(self):
        with TmpRoot() as root:
            mk(root, "a", kd=30, vol=100000, low_dr=3, ugc=2, age=400)
            mk(root, "b", kd=10, vol=300000, low_dr=6, ugc=5, age=900)
            ev = write_obs(root, "b", "2026-09-10-verify.json", stage="verify")
            L.transition(root, "b", to="rejected", evidence=[ev], by="t", reason="G1")
            scores = K.rank_all(root, write=True)
            self.assertIn("a", scores)
            self.assertNotIn("b", scores)
            self.assertEqual(L.load(root)["candidates"]["a"]["proxy"]["rank_score"], scores["a"])

    def test_single_candidate_gets_half(self):
        with TmpRoot() as root:
            mk(root, "a", kd=30, vol=100000, low_dr=3, ugc=2, age=400)
            self.assertEqual(K.rank_all(root)["a"], 0.5)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `ModuleNotFoundError: No module named 'rank'`

- [ ] **Step 3: 写 rank.py**

```python
#!/usr/bin/env python3
"""代理排序:决定谁先进现场核验。只排序,不否决。

五项:kd(反向)、cluster.total_volume、low_dr_count、ugc_count、content_age_median_days。
每项在当前 found 池内 min-max 归一化到 0–1,缺失取 0.5,等权平均。
池内只有一个候选或某项全相等时该项取 0.5。权重等权是初始口径,首批 verify 后可调。
"""
import argparse
import sys

import ledger as L

DIMS = (  # (取值函数, 是否反向)
    (lambda r: r["proxy"].get("kd"), True),
    (lambda r: r["cluster"].get("total_volume"), False),
    (lambda r: r["proxy"].get("low_dr_count"), False),
    (lambda r: r["proxy"].get("ugc_count"), False),
    (lambda r: r["proxy"].get("content_age_median_days"), False),
)


def _normalize(values):
    present = [v for v in values if isinstance(v, (int, float))]
    if len(present) < 2 or max(present) == min(present):
        return [0.5 for _ in values]
    lo, hi = min(present), max(present)
    return [((v - lo) / (hi - lo)) if isinstance(v, (int, float)) else 0.5 for v in values]


def rank_all(root, write=False) -> dict:
    recs = L.list_candidates(root, state="found")
    if not recs:
        return {}
    cols = []
    for getter, reverse in DIMS:
        norm = _normalize([getter(r) for r in recs])
        cols.append([1 - x if reverse else x for x in norm])
    scores = {r["slug"]: round(sum(col[i] for col in cols) / len(DIMS), 4) for i, r in enumerate(recs)}
    if write:
        ledger = L.load(root)
        for slug, s in scores.items():
            ledger["candidates"][slug]["proxy"]["rank_score"] = s
        L.save(root, ledger)
    return scores


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="对 found 候选算代理排序分并回写账本")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--top", type=int, default=0, help="只打印前 N")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    scores = rank_all(root, write=not a.no_write)
    rows = sorted(scores.items(), key=lambda kv: -kv[1])
    if a.top:
        rows = rows[:a.top]
    for slug, s in rows:
        print(f"{s:.4f}  {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `Ran 19 tests ... OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-simple-workflow/
git commit -m "xinci-simple:rank 代理排序(归一化等权,只排序不否决)"
```

---

### Task 4: revenue_model.py —— 三情景收入模型

**Files:**
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/revenue_model.py`
- Test: `xinci-simple-workflow/xinci-simple-core/scripts/tests/test_revenue_model.py`

假设表（设计稿 §6.2、§6.3，版本 `2026-09-09`）：
- `info`/`lookup`：会话 = 簇量 × 0.07；收入 = 会话 / 1000 × RPM；RPM：`tech` 10、`home` 18、`hobby` 12（默认 `tech`）
- `tool`：同上，CTR 0.10
- `commercial`：点击 = 簇量 × 0.07；收入 = 点击 × 0.15 × 0.03 × 30
- `mixed`：算 info 与 commercial，base 取小者
- 折减：AIO 存在未完成 → CTR × 0.6；强完整结果 1–2 个 → CTR × 0.7（≥3 由 G3 否决，不进模型）
- downside：CTR × 0.5；upside：CTR × 1.5
- `volume_needed_for_500`：base 公式反推

- [ ] **Step 1: 写失败测试**

```python
# revenue_model:四形态、两条折减、$500 边界、反推与正算一致、非法输入报错。
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import revenue_model as M


class RevenueModelTest(unittest.TestCase):
    def test_info_tech(self):
        r = M.model("info", 714286, niche="tech")
        self.assertAlmostEqual(r["base"], 500, delta=1)
        self.assertAlmostEqual(r["downside"], 250, delta=1)
        self.assertAlmostEqual(r["upside"], 750, delta=1)
        self.assertEqual(r["assumptions_version"], M.VERSION)

    def test_lookup_home_rpm(self):
        r = M.model("lookup", 100000, niche="home")
        self.assertAlmostEqual(r["base"], 100000 * 0.07 / 1000 * 18, places=2)

    def test_tool_ctr_10(self):
        r = M.model("tool", 100000)
        self.assertAlmostEqual(r["base"], 100000 * 0.10 / 1000 * 10, places=2)

    def test_commercial(self):
        r = M.model("commercial", 100000)
        self.assertAlmostEqual(r["base"], 100000 * 0.07 * 0.15 * 0.03 * 30, places=2)

    def test_mixed_takes_conservative(self):
        info = M.model("info", 100000)["base"]
        com = M.model("commercial", 100000)["base"]
        self.assertAlmostEqual(M.model("mixed", 100000)["base"], min(info, com), places=2)

    def test_aio_haircut(self):
        plain = M.model("info", 100000)["base"]
        self.assertAlmostEqual(M.model("info", 100000, aio_present=True)["base"], plain * 0.6, places=2)

    def test_strong_complete_haircut_and_stack(self):
        plain = M.model("info", 100000)["base"]
        self.assertAlmostEqual(M.model("info", 100000, strong_complete_count=1)["base"], plain * 0.7, places=2)
        self.assertAlmostEqual(M.model("info", 100000, strong_complete_count=2)["base"], plain * 0.7, places=2)
        self.assertAlmostEqual(M.model("info", 100000, aio_present=True, strong_complete_count=2)["base"],
                               plain * 0.6 * 0.7, places=2)

    def test_threshold_boundary(self):
        self.assertFalse(M.passes({"base": 499.99}))
        self.assertTrue(M.passes({"base": 500}))

    def test_volume_needed_roundtrip(self):
        r = M.model("info", 100000, aio_present=True, strong_complete_count=1)
        again = M.model("info", r["volume_needed_for_500"], aio_present=True, strong_complete_count=1)
        self.assertAlmostEqual(again["base"], 500, delta=1)

    def test_invalid_form_and_volume(self):
        with self.assertRaises(ValueError):
            M.model("saas", 100000)
        with self.assertRaises(ValueError):
            M.model("info", 0)
        with self.assertRaises(ValueError):
            M.model("info", 100000, niche="finance")
        with self.assertRaises(ValueError):
            M.model("info", 100000, strong_complete_count=3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `ModuleNotFoundError: No module named 'revenue_model'`

- [ ] **Step 3: 写 revenue_model.py**

```python
#!/usr/bin/env python3
"""三情景收入模型。纯函数 + CLI。假设表版本化,改假设先改 VERSION。

base 公式(选词契约 §收入模型):
  info/lookup: 簇量 × CTR 0.07 / 1000 × RPM[niche]
  tool:        簇量 × CTR 0.10 / 1000 × RPM[niche]
  commercial:  簇量 × CTR 0.07 × 0.15 × 0.03 × 30
  mixed:       min(info, commercial)
折减(乘在 CTR 上):AIO 存在未完成 ×0.6;强完整结果 1–2 个 ×0.7。
downside = CTR ×0.5;upside = CTR ×1.5。threshold = 500。
"""
import argparse
import json
import sys

VERSION = "2026-09-09"
THRESHOLD = 500
FORMS = ("info", "lookup", "tool", "commercial", "mixed")
RPM = {"tech": 10, "home": 18, "hobby": 12}
CTR = {"info": 0.07, "lookup": 0.07, "tool": 0.10, "commercial": 0.07}
AFFILIATE = {"outbound_ctr": 0.15, "conversion": 0.03, "commission": 30}
HAIRCUT_AIO = 0.6
HAIRCUT_STRONG = 0.7


def _ctr_multiplier(aio_present, strong_complete_count):
    m = 1.0
    if aio_present:
        m *= HAIRCUT_AIO
    if strong_complete_count in (1, 2):
        m *= HAIRCUT_STRONG
    return m


def _monthly(form, volume, niche, ctr_scale):
    """单一形态在给定 CTR 缩放下的月收入。"""
    if form == "commercial":
        clicks = volume * CTR["commercial"] * ctr_scale
        return clicks * AFFILIATE["outbound_ctr"] * AFFILIATE["conversion"] * AFFILIATE["commission"]
    sessions = volume * CTR[form] * ctr_scale
    return sessions / 1000 * RPM[niche]


def _base_fn(form, niche, mult):
    def f(volume, scale=1.0):
        s = mult * scale
        if form == "mixed":
            return min(_monthly("info", volume, niche, s), _monthly("commercial", volume, niche, s))
        return _monthly(form, volume, niche, s)
    return f


def model(form, cluster_volume, niche="tech", aio_present=False, strong_complete_count=0) -> dict:
    if form not in FORMS:
        raise ValueError(f"form 须为 {FORMS}")
    if not isinstance(cluster_volume, (int, float)) or cluster_volume <= 0:
        raise ValueError("cluster_volume 须为正数")
    if niche not in RPM:
        raise ValueError(f"niche 须为 {tuple(RPM)}")
    if strong_complete_count not in (0, 1, 2):
        raise ValueError("strong_complete_count 只能是 0/1/2;≥3 由 G3 否决,不进收入模型")
    f = _base_fn(form, niche, _ctr_multiplier(aio_present, strong_complete_count))
    base = f(cluster_volume)
    per_unit = base / cluster_volume  # 所有公式对簇量线性
    return {
        "downside": round(f(cluster_volume, 0.5), 2),
        "base": round(base, 2),
        "upside": round(f(cluster_volume, 1.5), 2),
        "volume_needed_for_500": int(round(THRESHOLD / per_unit)),
        "assumptions_version": VERSION,
        "inputs": {"form": form, "cluster_volume": cluster_volume, "niche": niche,
                   "aio_present": bool(aio_present), "strong_complete_count": strong_complete_count},
    }


def passes(revenue) -> bool:
    return isinstance(revenue.get("base"), (int, float)) and revenue["base"] >= THRESHOLD


def main(argv=None):
    ap = argparse.ArgumentParser(description="三情景收入模型;输出 JSON")
    ap.add_argument("--form", required=True, choices=FORMS)
    ap.add_argument("--cluster-volume", type=int, required=True)
    ap.add_argument("--niche", default="tech", choices=tuple(RPM))
    ap.add_argument("--aio-present", action="store_true")
    ap.add_argument("--strong-complete-count", type=int, default=0)
    a = ap.parse_args(argv)
    try:
        r = model(a.form, a.cluster_volume, a.niche, a.aio_present, a.strong_complete_count)
    except ValueError as e:
        print(f"拒收: {e}", file=sys.stderr)
        return 1
    r["passes"] = passes(r)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `Ran 29 tests ... OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-simple-workflow/
git commit -m "xinci-simple:revenue_model 三情景收入模型与 500 门"
```

---

### Task 5: run_log.py —— 运行清单

**Files:**
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/run_log.py`
- Test: `xinci-simple-workflow/xinci-simple-core/scripts/tests/test_run_log.py`

- [ ] **Step 1: 写失败测试**

```python
# run_log:写 运行/<日期>-<skill>[-HHMM].json;同名拒绝覆盖;字段齐全。
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_log as R
from helpers import TmpRoot


class RunLogTest(unittest.TestCase):
    def test_writes_manifest(self):
        with TmpRoot() as root:
            p = R.record(root, date="2026-09-10", skill="xinci-simple-scan",
                         sources_opened=["https://a", "https://a", "https://b"],
                         candidates_touched=["x"], billable_calls=3, notes=["词根 Converter"])
            self.assertEqual(p.name, "2026-09-10-xinci-simple-scan.json")
            d = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(d["sources_opened"], ["https://a", "https://b"])
            self.assertEqual(d["billable_calls"], 3)
            self.assertEqual(d["skill"], "xinci-simple-scan")

    def test_refuses_overwrite_without_suffix(self):
        with TmpRoot() as root:
            R.record(root, date="2026-09-10", skill="xinci-simple-scan", sources_opened=[],
                     candidates_touched=[], billable_calls=0, notes=[])
            with self.assertRaises(R.RunLogError):
                R.record(root, date="2026-09-10", skill="xinci-simple-scan", sources_opened=[],
                         candidates_touched=[], billable_calls=0, notes=[])
            p = R.record(root, date="2026-09-10", skill="xinci-simple-scan", sources_opened=[],
                         candidates_touched=[], billable_calls=0, notes=[], suffix="1530")
            self.assertEqual(p.name, "2026-09-10-xinci-simple-scan-1530.json")

    def test_rejects_unknown_skill_and_bad_calls(self):
        with TmpRoot() as root:
            with self.assertRaises(R.RunLogError):
                R.record(root, date="2026-09-10", skill="xinci-scan", sources_opened=[],
                         candidates_touched=[], billable_calls=0, notes=[])
            with self.assertRaises(R.RunLogError):
                R.record(root, date="2026-09-10", skill="xinci-simple-verify", sources_opened=[],
                         candidates_touched=[], billable_calls=-1, notes=[])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `ModuleNotFoundError: No module named 'run_log'`

- [ ] **Step 3: 写 run_log.py**

```python
#!/usr/bin/env python3
"""运行清单:每次 scan / verify 结束写一份小 JSON。审计轨迹,不可覆盖。"""
import argparse
import re
import sys
from pathlib import Path

from _common import atomic_save, now

SKILLS = ("xinci-simple-scan", "xinci-simple-verify")


class RunLogError(Exception):
    pass


def record(root, *, date, skill, sources_opened, candidates_touched, billable_calls, notes,
           suffix=None) -> Path:
    if skill not in SKILLS:
        raise RunLogError(f"skill 须为 {SKILLS}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
        raise RunLogError("date 须为 YYYY-MM-DD")
    if not isinstance(billable_calls, int) or billable_calls < 0:
        raise RunLogError("billable_calls 须为非负整数")
    name = f"{date}-{skill}" + (f"-{suffix}" if suffix else "") + ".json"
    path = Path(root) / "运行" / name
    if path.exists():
        raise RunLogError(f"运行清单已存在,同日再次运行请传 --suffix HHMM: {path.name}")
    seen, urls = set(), []
    for u in sources_opened or []:
        if u not in seen:
            seen.add(u)
            urls.append(u)
    atomic_save(path, {
        "date": date, "skill": skill, "recorded_at": now(),
        "sources_opened": urls,
        "candidates_touched": sorted(set(candidates_touched or [])),
        "billable_calls": billable_calls,
        "notes": list(notes or []),
    })
    return path


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="写运行清单")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--date", required=True)
    ap.add_argument("--skill", required=True, choices=SKILLS)
    ap.add_argument("--suffix", default=None)
    ap.add_argument("--source-opened", action="append", default=[])
    ap.add_argument("--candidate-touched", action="append", default=[])
    ap.add_argument("--billable-calls", type=int, required=True)
    ap.add_argument("--note", action="append", default=[])
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        p = record(root, date=a.date, skill=a.skill, sources_opened=a.source_opened,
                   candidates_touched=a.candidate_touched, billable_calls=a.billable_calls,
                   notes=a.note, suffix=a.suffix)
    except RunLogError as e:
        print(f"拒收: {e}", file=sys.stderr)
        return 1
    print(f"已写 {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `Ran 32 tests ... OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-simple-workflow/
git commit -m "xinci-simple:run_log 运行清单"
```

---

### Task 6: report_status.py 与 validate_ledger.py

**Files:**
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/report_status.py`
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/validate_ledger.py`
- Test: `xinci-simple-workflow/xinci-simple-core/scripts/tests/test_report_status.py`
- Test: `xinci-simple-workflow/xinci-simple-core/scripts/tests/test_validate_ledger.py`

- [ ] **Step 1: 写失败测试 test_report_status.py**

```python
# report_status:各状态计数、found 按 rank 排序、parked 停留天数与 90 天提醒、verified 报告路径。
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import report_status as S
from helpers import TmpRoot, write_obs, CLUSTER, SEED, PROXY, REVENUE


def reg(root, slug, rank=None):
    ev = write_obs(root, slug, "2026-09-10-scan.json")
    proxy = dict(PROXY)
    if rank is not None:
        proxy["rank_score"] = rank
    L.register(root, slug=slug, primary_keyword=slug, cluster=CLUSTER, seed=SEED, proxy=proxy,
               evidence=[ev], by="t", reason="r")


class ReportStatusTest(unittest.TestCase):
    def test_counts_and_found_order(self):
        with TmpRoot() as root:
            reg(root, "low", rank=0.2)
            reg(root, "high", rank=0.9)
            reg(root, "none")
            rep = S.build_report(root)
            self.assertEqual(rep["counts"], {"found": 3})
            self.assertEqual([r["slug"] for r in rep["found"]], ["high", "low", "none"])

    def test_parked_days_and_stale_flag(self):
        with TmpRoot() as root:
            reg(root, "p")
            ev = write_obs(root, "p", "2026-09-10-verify.json", stage="verify")
            L.transition(root, "p", to="parked", evidence=[ev], by="t", reason="季节性")
            ledger = L.load(root)
            old = (datetime.now(timezone.utc) - timedelta(days=95)).isoformat(timespec="seconds")
            ledger["candidates"]["p"]["history"][-1]["at"] = old
            L.save(root, ledger)
            rep = S.build_report(root)
            self.assertEqual(rep["parked"][0]["days"], 95)
            self.assertTrue(rep["parked"][0]["stale"])
            self.assertIn("超 90 天", S.render_text(rep))

    def test_verified_lists_report_path(self):
        with TmpRoot() as root:
            reg(root, "v")
            ev = write_obs(root, "v", "2026-09-10-verify.json", stage="verify")
            L.transition(root, "v", to="verified", evidence=[ev], by="t", reason="r",
                         form="tool", revenue=REVENUE)
            rep = S.build_report(root)
            self.assertEqual(rep["verified"][0]["report"], "报告/v.md")
            self.assertFalse(rep["verified"][0]["report_exists"])
            (root / "报告" / "v.md").write_text("# v", encoding="utf-8")
            self.assertTrue(S.build_report(root)["verified"][0]["report_exists"])

    def test_render_text_mentions_all_sections(self):
        with TmpRoot() as root:
            reg(root, "a")
            text = S.render_text(S.build_report(root))
            for kw in ("各状态候选数", "待核验", "已验证", "已搁置"):
                self.assertIn(kw, text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 写失败测试 test_validate_ledger.py**

```python
# validate_ledger:状态词汇、证据存在、history 末项==state、verified 有 form/revenue 且报告存在(警告)、孤儿证据目录(警告)。
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import validate_ledger as V
from helpers import TmpRoot, write_obs, CLUSTER, SEED, PROXY, REVENUE


def reg(root, slug):
    ev = write_obs(root, slug, "2026-09-10-scan.json")
    L.register(root, slug=slug, primary_keyword=slug, cluster=CLUSTER, seed=SEED, proxy=PROXY,
               evidence=[ev], by="t", reason="r")


class ValidateLedgerTest(unittest.TestCase):
    def test_clean_ledger_zero_errors(self):
        with TmpRoot() as root:
            reg(root, "a")
            errors, warnings = V.validate(root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

    def test_catches_each_invariant(self):
        with TmpRoot() as root:
            reg(root, "a")
            reg(root, "b")
            ledger = L.load(root)
            ledger["candidates"]["a"]["state"] = "flying"
            ledger["candidates"]["b"]["evidence_refs"].append("证据/b/missing.json")
            ledger["candidates"]["b"]["history"][-1]["to"] = "parked"
            L.save(root, ledger)
            (root / "证据" / "orphan").mkdir()
            errors, warnings = V.validate(root)
            joined = "\n".join(errors)
            self.assertIn("flying", joined)
            self.assertIn("missing.json", joined)
            self.assertIn("history 末项", joined)
            self.assertTrue(any("orphan" in w for w in warnings))

    def test_verified_without_report_is_warning(self):
        with TmpRoot() as root:
            reg(root, "v")
            ev = write_obs(root, "v", "2026-09-10-verify.json", stage="verify")
            L.transition(root, "v", to="verified", evidence=[ev], by="t", reason="r",
                         form="tool", revenue=REVENUE)
            errors, warnings = V.validate(root)
            self.assertEqual(errors, [])
            self.assertTrue(any("报告/v.md" in w for w in warnings))

    def test_verified_missing_form_is_error(self):
        with TmpRoot() as root:
            reg(root, "v")
            ev = write_obs(root, "v", "2026-09-10-verify.json", stage="verify")
            L.transition(root, "v", to="verified", evidence=[ev], by="t", reason="r",
                         form="tool", revenue=REVENUE)
            ledger = L.load(root)
            ledger["candidates"]["v"]["form"] = None
            L.save(root, ledger)
            errors, _ = V.validate(root)
            self.assertTrue(any("form" in e for e in errors))

    def test_cli_exit_codes(self):
        with TmpRoot() as root:
            reg(root, "a")
            self.assertEqual(V.main(["--data-root", str(root)]), 0)
            ledger = L.load(root)
            ledger["candidates"]["a"]["state"] = "flying"
            L.save(root, ledger)
            self.assertEqual(V.main(["--data-root", str(root)]), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: 两个 `ModuleNotFoundError`

- [ ] **Step 4: 写 report_status.py**

```python
#!/usr/bin/env python3
"""只读看板:各状态计数、found 按排序分、parked 停留天数(超 90 天提醒)、verified 报告路径。零写入。"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import ledger as L

STATE_LABELS = {"found": "待核验", "parked": "已搁置", "verified": "已验证", "rejected": "已否决"}
STALE_DAYS = 90


def _days_since(iso):
    then = datetime.fromisoformat(iso)
    return (datetime.now(timezone.utc) - then).days


def build_report(root) -> dict:
    root = Path(root)
    recs = L.list_candidates(root)
    counts = {}
    for r in recs:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    found = sorted((r for r in recs if r["state"] == "found"),
                   key=lambda r: -((r.get("proxy") or {}).get("rank_score") or -1))
    parked = []
    for r in recs:
        if r["state"] == "parked":
            days = _days_since(r["history"][-1]["at"])
            parked.append({"slug": r["slug"], "days": days, "stale": days > STALE_DAYS,
                           "reason": r["history"][-1]["reason"]})
    verified = []
    for r in recs:
        if r["state"] == "verified":
            rel = f"报告/{r['slug']}.md"
            verified.append({"slug": r["slug"], "form": r["form"], "base": (r["revenue"] or {}).get("base"),
                             "report": rel, "report_exists": (root / rel).is_file()})
    return {
        "counts": counts,
        "found": [{"slug": r["slug"], "primary_keyword": r["primary_keyword"],
                   "cluster_volume": r["cluster"]["total_volume"],
                   "rank_score": (r.get("proxy") or {}).get("rank_score")} for r in found],
        "parked": parked, "verified": verified,
    }


def render_text(rep) -> str:
    out = ["== 各状态候选数 =="]
    for state in ("found", "parked", "verified", "rejected"):
        if state in rep["counts"]:
            out.append(f"{STATE_LABELS[state]}：{rep['counts'][state]}")
    out.append("\n== 待核验（按排序分） ==")
    for r in rep["found"]:
        score = f"{r['rank_score']:.2f}" if r["rank_score"] is not None else "未排序"
        out.append(f"{score}  {r['slug']} — {r['primary_keyword']} | 簇量 {r['cluster_volume']:,}")
    if not rep["found"]:
        out.append("（无）")
    out.append("\n== 已搁置 ==")
    for r in rep["parked"]:
        flag = "  ← 超 90 天未动" if r["stale"] else ""
        out.append(f"{r['slug']} | 停留 {r['days']} 天 | {r['reason']}{flag}")
    if not rep["parked"]:
        out.append("（无）")
    out.append("\n== 已验证 ==")
    for r in rep["verified"]:
        exists = "" if r["report_exists"] else "（报告缺失）"
        out.append(f"{r['slug']} | {r['form']} | base ${r['base']} | {r['report']}{exists}")
    if not rep["verified"]:
        out.append("（无）")
    return "\n".join(out)


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="xinci-simple 只读看板")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    rep = build_report(root)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else render_text(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 写 validate_ledger.py**

```python
#!/usr/bin/env python3
"""账本不变式校验。错误非零退出;警告只打印。"""
import argparse
import sys
from pathlib import Path

import ledger as L


def validate(root):
    root = Path(root)
    errors, warnings = [], []
    ledger = L.load(root)
    slugs = set()
    for slug, rec in ledger["candidates"].items():
        slugs.add(slug)
        st = rec.get("state")
        if st not in L.STATES:
            errors.append(f"{slug}: 状态不在词汇表: {st}")
        for ref in rec.get("evidence_refs", []):
            if not (root / ref).is_file():
                errors.append(f"{slug}: 证据文件不存在: {ref}")
        hist = rec.get("history") or []
        if not hist:
            errors.append(f"{slug}: history 为空")
        elif hist[-1].get("to") != st:
            errors.append(f"{slug}: history 末项 {hist[-1].get('to')} != state {st}")
        if st == "verified":
            if rec.get("form") not in L.FORMS:
                errors.append(f"{slug}: verified 缺 form")
            rev = rec.get("revenue") or {}
            if not all(k in rev for k in L.REVENUE_KEYS):
                errors.append(f"{slug}: verified 缺 revenue 字段")
            rel = f"报告/{slug}.md"
            if not (root / rel).is_file():
                warnings.append(f"{slug}: 报告缺失 {rel}")
    ev_dir = root / "证据"
    if ev_dir.is_dir():
        for d in ev_dir.iterdir():
            if d.is_dir() and d.name not in slugs:
                warnings.append(f"孤儿证据目录(账本无此候选): 证据/{d.name}")
    return errors, warnings


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="校验账本不变式")
    ap.add_argument("--data-root", default=None)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    errors, warnings = validate(root)
    for w in warnings:
        print("警告: " + w)
    for e in errors:
        print("错误: " + e)
    print(f"校验完成:{len(errors)} 个错误,{len(warnings)} 个警告")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: 跑测试确认通过**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `Ran 41 tests ... OK`

- [ ] **Step 7: 提交**

```bash
git add xinci-simple-workflow/
git commit -m "xinci-simple:report_status 看板与 validate_ledger 校验"
```

---

### Task 7: build_report.py —— 9 节机会报告

**Files:**
- Create: `xinci-simple-workflow/xinci-simple-core/scripts/build_report.py`
- Test: `xinci-simple-workflow/xinci-simple-core/scripts/tests/test_build_report.py`

- [ ] **Step 1: 写失败测试**

```python
# build_report:9 节齐全、数值来自输入、缺 verify 观察报错、缺 revenue 报错、写到 报告/<slug>.md。
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_report as B
import ledger as L
from helpers import TmpRoot, write_obs, CLUSTER, SEED, PROXY, REVENUE, VERIFY_OBS

SECTIONS = ("## 1. 主关键词与簇", "## 2. 形态与意图", "## 3. 量级证据", "## 4. 竞争现场",
            "## 5. AI Overview 状态", "## 6. 季节性", "## 7. 收入三情景", "## 8. 范围排除复核",
            "## 9. 建议 play 与风险")


def verified(root, slug="heic-to-jpg-converter", volume=182000):
    ev = write_obs(root, slug, "2026-09-10-scan.json", semrush_preview={
        "queried_at": "2026-09-10", "filters": "US, KD<=49, exclude nav", "note": "前 50 行"})
    L.register(root, slug=slug, primary_keyword="heic to jpg converter", cluster=dict(CLUSTER, total_volume=volume),
               seed=SEED, proxy=dict(PROXY, rank_score=0.71), evidence=[ev], by="t", reason="r")
    vev = write_obs(root, slug, "2026-09-11-verify.json", **VERIFY_OBS)
    L.transition(root, slug, to="verified", evidence=[vev], by="t", reason="base 640",
                 form="tool", revenue=dict(REVENUE, base=640))
    return slug


class BuildReportTest(unittest.TestCase):
    def test_nine_sections_and_values(self):
        with TmpRoot() as root:
            slug = verified(root)
            path = B.build(root, slug)
            self.assertEqual(path, root / "报告" / f"{slug}.md")
            text = path.read_text(encoding="utf-8")
            for s in SECTIONS:
                self.assertIn(s, text)
            self.assertIn("heic to jpg converter", text)
            self.assertIn("182,000", text)
            self.assertIn("cloudconvert.com", text)
            self.assertIn("640", text)
            self.assertIn("142,000", text)
            self.assertIn("2026-09-09", text)
            self.assertIn("lists converters", text)
            self.assertIn("single_domain", text)

    def test_play_cluster_expansion_when_large(self):
        with TmpRoot() as root:
            slug = verified(root, volume=400000)
            self.assertIn("cluster_expansion", B.build(root, slug).read_text(encoding="utf-8"))

    def test_requires_verify_observation(self):
        with TmpRoot() as root:
            ev = write_obs(root, "s", "2026-09-10-scan.json")
            L.register(root, slug="s", primary_keyword="s", cluster=CLUSTER, seed=SEED, proxy=PROXY,
                       evidence=[ev], by="t", reason="r")
            with self.assertRaises(B.ReportError):
                B.build(root, "s")

    def test_requires_verified_state(self):
        with TmpRoot() as root:
            ev = write_obs(root, "s", "2026-09-10-scan.json")
            L.register(root, slug="s", primary_keyword="s", cluster=CLUSTER, seed=SEED, proxy=PROXY,
                       evidence=[ev], by="t", reason="r")
            write_obs(root, "s", "2026-09-11-verify.json", **VERIFY_OBS)
            with self.assertRaises(B.ReportError):
                B.build(root, "s")

    def test_uses_latest_verify_observation(self):
        with TmpRoot() as root:
            slug = verified(root)
            write_obs(root, slug, "2026-09-12-verify.json", **dict(VERIFY_OBS, trends_12m="十二月起量"))
            self.assertIn("十二月起量", B.build(root, slug).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `ModuleNotFoundError: No module named 'build_report'`

- [ ] **Step 3: 写 build_report.py**

```python
#!/usr/bin/env python3
"""机会报告:从账本记录 + 最新 verify 观察生成 报告/<slug>.md。9 节固定,不手写。"""
import argparse
import sys
from pathlib import Path

import ledger as L
from _common import load_json

PLAY_SINGLE_MAX = 150000
FORM_LABELS = {"info": "信息", "lookup": "查表", "tool": "工具", "commercial": "商业/联盟", "mixed": "混合"}
SCOPE_LABELS = {"ymyl": "YMYL（健康/金融/法律/安全）", "firsthand": "需亲身体验/一手数据",
                "brand_nav": "纯品牌/导航词", "news": "新闻热点"}


class ReportError(Exception):
    pass


def _latest_obs(root, slug, stage):
    d = Path(root) / "证据" / slug
    files = sorted(d.glob(f"*-{stage}.json")) if d.is_dir() else []
    if not files:
        raise ReportError(f"{slug}: 缺 {stage} 观察文件")
    return load_json(files[-1])


def _fmt(n):
    return f"{n:,}" if isinstance(n, int) else str(n)


def render(rec, scan_obs, verify_obs) -> str:
    slug = rec["slug"]
    cluster = rec["cluster"]
    rev = rec["revenue"]
    aio = verify_obs.get("ai_overview") or {}
    top10 = verify_obs.get("serp_top10") or []
    scope = verify_obs.get("scope_recheck") or {}
    preview = scan_obs.get("semrush_preview") or {}
    strong = [r for r in top10 if r.get("completes_task") and (r.get("dr") or 0) >= 50]
    play = "single_domain" if cluster["total_volume"] < PLAY_SINGLE_MAX else "cluster_expansion"
    lines = [f"# 机会报告：{rec['primary_keyword']}", "",
             f"- slug：`{slug}`", f"- 状态：{rec['state']}", f"- 生成依据：{verify_obs.get('observed_at')} 的 verify 观察", ""]
    lines += ["## 1. 主关键词与簇", "",
              f"- 主关键词：**{rec['primary_keyword']}**",
              f"- 簇量（phrase-match 合计月量）：**{_fmt(cluster['total_volume'])}**",
              f"- 来源：{rec['seed']['type']} — {rec['seed']['value']}（查询于 {rec['seed'].get('queried_at')}）", "",
              "| 支撑词 | 月量 | KD |", "| --- | ---: | ---: |"]
    for kw in cluster.get("keywords", [])[:20]:
        lines.append(f"| {kw['term']} | {_fmt(kw.get('volume'))} | {kw.get('kd')} |")
    lines += ["", "## 2. 形态与意图", "",
              f"- 形态：**{FORM_LABELS.get(rec['form'], rec['form'])}**（`{rec['form']}`）",
              f"- 判断依据：首页 {len(top10)} 条中 {sum(1 for r in top10 if r.get('type') == 'tool')} 条工具、"
              f"{sum(1 for r in top10 if r.get('type') == 'forum')} 条论坛、"
              f"{sum(1 for r in top10 if r.get('type') == 'article')} 条文章", ""]
    lines += ["## 3. 量级证据", "",
              f"- Semrush 预览：{preview.get('note', '见 scan 观察')}",
              f"- 查询日期：{preview.get('queried_at', rec['seed'].get('queried_at'))}",
              f"- 过滤条件：{preview.get('filters', 'US, KD ≤ 49, 排除 Navigational')}",
              f"- 主词 KD：{rec['proxy'].get('kd')}；代理排序分：{rec['proxy'].get('rank_score')}", ""]
    lines += ["## 4. 竞争现场", "", f"查询：`{verify_obs.get('query_url')}`", "",
              "| # | 域名 | DR | 类型 | 完成任务 | 日期 |", "| ---: | --- | ---: | --- | --- | --- |"]
    for r in top10:
        lines.append(f"| {r.get('pos')} | {r.get('domain')} | {r.get('dr')} | {r.get('type')} | "
                     f"{'是' if r.get('completes_task') else '否'} | {r.get('dated') or '-'} |")
    lines += ["", f"- 完整完成任务且 DR ≥ 50 的结果：**{len(strong)}** 个（{', '.join(r['domain'] for r in strong) or '无'}）",
              f"- 第二页：{verify_obs.get('page2_note', '-')}", ""]
    lines += ["## 5. AI Overview 状态", "",
              ("- 无 AI Overview" if not aio.get("present") else
               f"- 有，**未完成任务**；要点：{aio.get('excerpt', '-')}"), ""]
    lines += ["## 6. 季节性", "", f"- Trends 12 个月：{verify_obs.get('trends_12m', '-')}", ""]
    inp = rev.get("inputs", {})
    lines += ["## 7. 收入三情景", "",
              f"- 假设表版本：`{rev['assumptions_version']}`",
              f"- 输入：形态 `{inp.get('form', rec['form'])}`，簇量 {_fmt(inp.get('cluster_volume', cluster['total_volume']))}，"
              f"垂类 `{inp.get('niche', '-')}`，AIO 折减 {'是' if inp.get('aio_present') else '否'}，"
              f"强完整结果 {inp.get('strong_complete_count', len(strong))} 个", "",
              "| 情景 | 月收入 |", "| --- | ---: |",
              f"| downside | ${_fmt(rev['downside'])} |", f"| **base** | **${_fmt(rev['base'])}** |",
              f"| upside | ${_fmt(rev['upside'])} |", "",
              f"- 在当前假设下 base 到 $500 需要簇量：{_fmt(rev['volume_needed_for_500'])}", ""]
    lines += ["## 8. 范围排除复核", ""]
    for k, label in SCOPE_LABELS.items():
        lines.append(f"- [{'x' if not scope.get(k) else ' '}] {label}：{'未命中' if not scope.get(k) else '**命中**'}")
    lines += ["", "## 9. 建议 play 与风险", "",
              f"- play：**{play}**（簇量 {'<' if play == 'single_domain' else '≥'} {_fmt(PLAY_SINGLE_MAX)}）",
              "- 风险：",
              f"  1. AI Overview：{'存在，可能继续扩展覆盖' if aio.get('present') else '暂无，可能出现'}",
              f"  2. 强占位：{len(strong)} 个 DR ≥ 50 的完整答案",
              f"  3. 季节性：{verify_obs.get('trends_12m', '-')}",
              "- 下一步是人的动作：决定建站方式后再做页面地图；本报告不含域名与内容大纲。", ""]
    if verify_obs.get("points"):
        lines += ["## 附：现场要点", ""] + [f"- {p}" for p in verify_obs["points"]] + [""]
    return "\n".join(lines)


def build(root, slug) -> Path:
    root = Path(root)
    ledger = L.load(root)
    if slug not in ledger["candidates"]:
        raise ReportError(f"候选不存在: {slug}")
    rec = ledger["candidates"][slug]
    if rec["state"] != "verified":
        raise ReportError(f"{slug}: 只为 verified 出报告,当前 {rec['state']}")
    if not rec.get("revenue") or not rec.get("form"):
        raise ReportError(f"{slug}: 缺 form/revenue")
    scan_obs = _latest_obs(root, slug, "scan")
    verify_obs = _latest_obs(root, slug, "verify")
    out = root / "报告" / f"{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rec, scan_obs, verify_obs), encoding="utf-8")
    return out


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="生成机会报告")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--slug", required=True)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        print(f"已写 {build(root, a.slug)}")
    except ReportError as e:
        print(f"拒绝: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 5: 提交**

```bash
git add xinci-simple-workflow/
git commit -m "xinci-simple:build_report 九节机会报告"
```

---

### Task 8: 两份 schema

**Files:**
- Create: `xinci-simple-workflow/xinci-simple-core/数据结构/candidate.schema.json`
- Create: `xinci-simple-workflow/xinci-simple-core/数据结构/observation.schema.json`

- [ ] **Step 1: 写 candidate.schema.json**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "xinci-simple 候选记录",
  "type": "object",
  "required": ["slug", "primary_keyword", "cluster", "seed", "state", "proxy", "form", "revenue", "evidence_refs", "history"],
  "additionalProperties": false,
  "properties": {
    "slug": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
    "primary_keyword": {"type": "string", "minLength": 1},
    "cluster": {
      "type": "object", "required": ["total_volume", "keywords"], "additionalProperties": false,
      "properties": {
        "total_volume": {"type": "integer", "minimum": 0},
        "keywords": {"type": "array", "items": {"type": "object", "required": ["term", "volume"],
          "properties": {"term": {"type": "string"}, "volume": {"type": "integer"}, "kd": {"type": ["number", "null"]}}}}
      }
    },
    "seed": {
      "type": "object", "required": ["type", "value"], "additionalProperties": false,
      "properties": {"type": {"enum": ["root", "small_site", "forum"]}, "value": {"type": "string"},
                     "queried_at": {"type": "string"}}
    },
    "state": {"enum": ["found", "parked", "verified", "rejected"]},
    "proxy": {
      "type": "object", "required": ["kd"],
      "properties": {"kd": {"type": "number"}, "low_dr_count": {"type": ["integer", "null"]},
                     "ugc_count": {"type": ["integer", "null"]}, "content_age_median_days": {"type": ["integer", "null"]},
                     "rank_score": {"type": ["number", "null"], "minimum": 0, "maximum": 1}}
    },
    "form": {"enum": ["info", "lookup", "tool", "commercial", "mixed", null]},
    "revenue": {
      "type": ["object", "null"],
      "required": ["downside", "base", "upside", "volume_needed_for_500", "assumptions_version"],
      "properties": {"downside": {"type": "number"}, "base": {"type": "number"}, "upside": {"type": "number"},
                     "volume_needed_for_500": {"type": "integer"}, "assumptions_version": {"type": "string"},
                     "inputs": {"type": "object"}}
    },
    "evidence_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    "history": {"type": "array", "minItems": 1, "items": {"type": "object",
      "required": ["at", "from", "to", "by", "reason"],
      "properties": {"at": {"type": "string"}, "from": {"type": ["string", "null"]}, "to": {"type": "string"},
                     "by": {"type": "string"}, "reason": {"type": "string", "minLength": 1}}}}
  }
}
```

- [ ] **Step 2: 写 observation.schema.json**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "xinci-simple 观察文件（只记录不裁决）",
  "type": "object",
  "required": ["slug", "observed_at", "stage", "source_urls", "points"],
  "properties": {
    "slug": {"type": "string"},
    "observed_at": {"type": "string", "description": "带时区 ISO"},
    "stage": {"enum": ["scan", "verify"]},
    "semrush_preview": {"type": "object", "description": "scan 用：queried_at / filters / note",
      "properties": {"queried_at": {"type": "string"}, "filters": {"type": "string"}, "note": {"type": "string"}}},
    "browser_preflight": {"type": "object", "description": "verify 必填",
      "required": ["controllable", "desktop", "region", "logged_out", "evidence"],
      "properties": {"controllable": {"type": "boolean"}, "desktop": {"type": "boolean"},
                     "region": {"enum": ["us", "other", "unknown"]}, "logged_out": {"type": "boolean"},
                     "evidence": {"type": "string"}}},
    "query_url": {"type": "string"},
    "ai_overview": {"type": "object", "required": ["present"],
      "properties": {"present": {"type": "boolean"}, "completes_task": {"type": "boolean"}, "excerpt": {"type": "string"}}},
    "serp_top10": {"type": "array", "items": {"type": "object", "required": ["pos", "domain", "type", "completes_task"],
      "properties": {"pos": {"type": "integer"}, "domain": {"type": "string"}, "dr": {"type": ["number", "null"]},
                     "type": {"enum": ["tool", "article", "forum", "video", "official", "brand", "other"]},
                     "completes_task": {"type": "boolean"}, "dated": {"type": ["string", "null"]}}}},
    "page2_note": {"type": "string"},
    "trends_12m": {"type": "string"},
    "scope_recheck": {"type": "object", "required": ["ymyl", "firsthand", "brand_nav", "news"],
      "properties": {"ymyl": {"type": "boolean"}, "firsthand": {"type": "boolean"},
                     "brand_nav": {"type": "boolean"}, "news": {"type": "boolean"}}},
    "source_urls": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    "points": {"type": "array", "items": {"type": "string"}}
  }
}
```

- [ ] **Step 3: 校验合法 JSON**

Run: `python3 -c "import json;[json.load(open(p,encoding='utf-8')) for p in ['xinci-simple-workflow/xinci-simple-core/数据结构/candidate.schema.json','xinci-simple-workflow/xinci-simple-core/数据结构/observation.schema.json']];print('ok')"`
Expected: `ok`

- [ ] **Step 4: 提交**

```bash
git add xinci-simple-workflow/
git commit -m "xinci-simple:候选与观察 schema"
```

---

### Task 9: 两份契约 —— 选词契约.md 与 数据采集.md

**Files:**
- Create: `xinci-simple-workflow/xinci-simple-core/选词契约.md`（目标 ≤ 300 行）
- Create: `xinci-simple-workflow/xinci-simple-core/数据采集.md`

**内容源约定：** 下面标注"内容源：设计稿 §N"的节，以 [设计稿](../specs/2026-09-09-xinci-simple-workflow-design.md) 该节为准展开成文，可补措辞但不得改规则语义；数值（阈值、假设表）必须与 Task 4 `revenue_model.py` 常量、Task 7 `PLAY_SINGLE_MAX` 逐字一致。设计稿与本计划同仓、路径固定，这不是占位符。

- [ ] **Step 1: 写 选词契约.md**，章节与内容源：

```
# 选词契约（xinci-simple）
## 0. 一句话与三条硬规则
   - 定位：设计稿 §2.1
   - 硬规则：不注册域名不建站；账本只由 ledger.py 写；产出为零如实说零，不凑数不写 maybe 清单
## 1. 候选单位与范围                         内容源：§2.2、§2.3（四条排除逐条写判法一句话）
## 2. 状态机                                 内容源：§4.1（LEGAL/TERMINAL 表原样）
## 3. 第一层：发现与准入                      内容源：§3.1
   - 三条来源轮换各写"怎么取、记什么"
   - Keyword Magic 固定过滤四项
   - 准入阈值：簇量 ≥ 50,000 或主词 ≥ 5,000（写明"可调默认值，改这里同时改 SKILL.md 命令模板"）
## 4. 第二层：代理排序                        内容源：§3.2（五项、归一化、等权、缺失 0.5、不否决）
## 5. 第三层：现场核验                        内容源：§3.3
   - G1 / G2 / G3 / 季节性 / 排除复核，每门：判什么、否决写什么 reason、通过带什么折减
   - "首页""DR""完整完成任务""新鲜""格式对"五个定义原样
## 6. 第四层：收入模型                        内容源：§6 全部（假设表、折减、三情景、门槛、隐含量级）
   - 明写 assumptions_version = 2026-09-09，改假设先改版本号
## 7. 证据要求                               内容源：§4.2、§4.3（每转移必带哪些字段；观察只记录不裁决）
   - register：scan 观察含 semrush_preview
   - →rejected：reason 写"哪道门 + 现场看到什么"或"base $X 差 $Y"
   - →parked：reason 写季节性读数或缺什么证据
   - →verified：form + revenue + verify 观察含 browser_preflight/ai_overview/serp_top10/scope_recheck
## 8. 机会报告                               内容源：§7（9 节名称原样；play 分界 150,000）
## 9. 错误处理                               内容源：§9
```

- [ ] **Step 2: 写 数据采集.md**，章节与内容源：

```
# 数据采集（xinci-simple）
## 1. 两条浏览器通道                          内容源：设计稿 §5.1 表格
   - Chrome（Claude in Chrome）只用于 Semrush；内置面板只用于 Google/Trends/allintitle
   - 明写：Chrome 已登录 Google，不得用它读 SERP
## 2. Semrush 操作纪律                        内容源：§5.2、§5.3
   - 每次计费查询必须能改变一个决策
   - Keyword Magic：输入种子 → 设四项过滤 → 看前 50 行预览 → 只记要点（词/量/KD 的 top 20 + 合计）→ 不整页转录
   - Keyword Overview 底部 SERP overview 面板取前 10 条 Authority Score（= 本工作流的 DR）
   - Domain Overview 用于小站反推：Authority Score 低（< 30）而月自然流量 > 50K 的站，拉 Top Organic Keywords
   - CSV 只在预览已证明簇值得深看时导；每轮 billable_calls 如实计
## 3. Google SERP 读取规程                    从 xinci 数据采集指南「G1 SERP 读取规程」精简复制，三条：
   - 环境：URL 显式 gl=us&hl=en&pws=0；内置面板未登录
   - 容器自检：用 JS 读 document.body.innerText 整页，不用 get_page_text（它会跳过 AI Overview）；
     文本须从 "Skip to main content" 开头，否则作废重读
   - 等待与占位词：出现 Thinking / Searching 等待后重读；完全没有 "AI Overview" 字样须隔几秒重读一次确认
## 4. 浏览器预检四项                          内容源：§5.4（写进每份 verify 观察 browser_preflight；任一不合规不写 G1–G3）
## 5. Trends 与 allintitle
   - Trends：trends.google.com，US，past 12 months，只记一句话读数（平稳 / 集中在哪几个月）
   - allintitle:"<主词>" 结果数只作参考记进 points，不进任何门
## 6. DataForSEO（可选，首版不接）             内容源：§5.1 第三行
   - 凭据 DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD 环境变量；接入后用于批量取 shortlist 首页域名 rank
```

- [ ] **Step 3: 自查两份契约**

Run: `grep -c "" xinci-simple-workflow/xinci-simple-core/选词契约.md` → ≤ 300
Run: `grep -n "50,000\|5,000\|150,000\|0.07\|0.10\|0.6\|0.7\|2026-09-09" xinci-simple-workflow/xinci-simple-core/选词契约.md | wc -l` → ≥ 8（关键数值都在）
Run: `grep -n "xinci-workflow/\|xinci-core/" xinci-simple-workflow/xinci-simple-core/*.md` → 无输出（零引用 xinci 文件）

- [ ] **Step 4: 提交**

```bash
git add xinci-simple-workflow/
git commit -m "xinci-simple:选词契约与数据采集两份契约"
```

---

### Task 10: 三个 SKILL.md

**Files:**
- Create: `xinci-simple-workflow/xinci-simple-scan/SKILL.md`
- Create: `xinci-simple-workflow/xinci-simple-verify/SKILL.md`
- Create: `xinci-simple-workflow/xinci-simple-status/SKILL.md`

统一骨架（沿 xinci）：frontmatter（`name` + description，中文为主附英文触发词，明确"与 xinci 新词工作流不同"）→ 一句话定位 → 行动前必读（core 两份契约的仓库相对路径）→ 第 0 步数据区（`report_status.py` 正常即已配置；退出码 2 则问用户后 `init_workspace.py --data-root`）→ 工作流步骤 → 硬规则 → 命令模板。判据不写在 SKILL.md。

- [ ] **Step 1: 写 xinci-simple-scan/SKILL.md**

frontmatter：

```yaml
---
name: xinci-simple-scan
description: '流量型选词的发现层:从 Semrush 词根轮换、小站反推、论坛问题三条来源找已有真实搜索量且守得弱的主题簇,零成本排除后注册为 found 并算代理排序。当用户说 simple scan、扫一批老词、找有流量的簇、跑词根时使用。English triggers: simple scan, mature keyword sweep, traffic niche discovery. 这是 xinci-simple-workflow(流量型),不是 xinci 新词工作流;现场核验用 xinci-simple-verify,看板用 xinci-simple-status。'
---
```

步骤：
1. 第 0 步数据区
2. 选来源：用户指定则用指定的；否则按运行清单里上次用过的轮换（词根 → 小站 → 论坛 → 词根…），词根按 `数据采集.md` 词根表顺序，不重复本轮已跑的
3. Chrome 通道打开 Semrush，按 `数据采集.md §2` 取预览；每条候选记：主词、簇量、top 20 支撑词、KD、SERP overview 前 10 的 Authority Score 分布（→ `low_dr_count`）、论坛/UGC 条数、内容年龄中位数（首页可见日期）
4. 零成本排除四条（`选词契约.md §1`）；准入阈值（§3）
5. 写 scan 观察 `证据/<slug>/<日期>-scan.json`（含 `semrush_preview`）→ `ledger.py register`
6. `rank.py` 回写排序分并打印 top 10
7. `run_log.py` 写运行清单（`--billable-calls` 如实）
8. 向用户报告：注册了几个、排序前 10、排除了几个及原因分布、Semrush 用了几次

硬规则：不做现场核验（那是 verify 的事）；一次调用目标 20–50 个 found，来源枯竭如实说；不用 Chrome 读 Google SERP；每次 Semrush 查询能改变决策才跑。

命令模板（三条，含真实参数示例）：

```bash
python3 xinci-simple-workflow/xinci-simple-core/scripts/ledger.py register \
  --slug heic-to-jpg-converter --primary-keyword "heic to jpg converter" \
  --cluster-json '{"total_volume":182000,"keywords":[{"term":"heic to jpg","volume":90500,"kd":38}]}' \
  --seed-json '{"type":"root","value":"Converter","queried_at":"2026-09-10T03:12:00+00:00"}' \
  --proxy-json '{"kd":38,"low_dr_count":4,"ugc_count":2,"content_age_median_days":540}' \
  --evidence "证据/heic-to-jpg-converter/2026-09-10-scan.json" \
  --by xinci-simple-scan --reason "准入:簇量 182K,四条排除未命中"
python3 xinci-simple-workflow/xinci-simple-core/scripts/rank.py --top 10
python3 xinci-simple-workflow/xinci-simple-core/scripts/run_log.py --date 2026-09-10 --skill xinci-simple-scan \
  --source-opened "https://www.semrush.com/analytics/keywordmagic/..." --candidate-touched heic-to-jpg-converter \
  --billable-calls 3 --note "词根 Converter,预览 50 行,注册 7 个"
```

- [ ] **Step 2: 写 xinci-simple-verify/SKILL.md**

frontmatter：

```yaml
---
name: xinci-simple-verify
description: '流量型选词的现场核验层:对 found 候选按排序取前 N,在美区未登录浏览器做 G1 Google 直答、G2 首页结构、G3 可打败性、季节性与范围复核,跑收入模型,通过的出机会报告。当用户说 simple verify、核验前几个、验一下 X、出报告时使用。English triggers: simple verify, verify traffic candidates, opportunity report. 这是 xinci-simple-workflow(流量型),不是 xinci 新词工作流;发现用 xinci-simple-scan。'
---
```

步骤：
1. 第 0 步数据区
2. 取目标：用户指定 slug 则用指定的；否则 `rank.py --no-write --top N`（默认 5）
3. 预检：内置面板打开一次美区查询，按 `数据采集.md §4` 核四项；任一不合规 → 本次不写 G1–G3，只记 points，候选留 found，如实报告
4. 逐候选：按 `数据采集.md §3` 读整页 → G1 → G2 → G3（DR 取 scan 观察记的 SERP overview，缺则本次到 Semrush 补一次并计费）→ Trends 季节性 → 四条排除复核 → 写 verify 观察（字段按 `观察 schema`）
5. 判形态 `form`（`选词契约.md §6.1`）；`revenue_model.py --form ... --cluster-volume ... [--aio-present] --strong-complete-count K`
6. 出口：硬门否决 → `transition --to rejected`；季节性 → `--to parked`；base ≥ 500 → `--to verified --form --revenue-json`，随后 `build_report.py --slug`；base < 500 → `--to rejected`，reason 写"base $X 差 $Y"
7. `run_log.py`（Google 与 Semrush 打开的 URL 都记；`--billable-calls` 只计 Semrush）
8. 向用户报告：每个候选一行（结论 / 门 / base / 报告路径）

硬规则：不得用 Chrome 读 Google SERP；`get_page_text` 不能用于判 G1；不看前三条就下 G2/G3 结论；代理指标不能单独否决；没通过就写 rejected，不留 maybe。

命令模板：

```bash
python3 xinci-simple-workflow/xinci-simple-core/scripts/revenue_model.py --form tool --cluster-volume 182000 --niche tech --aio-present --strong-complete-count 1
python3 xinci-simple-workflow/xinci-simple-core/scripts/ledger.py transition --slug heic-to-jpg-converter --to verified \
  --evidence "证据/heic-to-jpg-converter/2026-09-11-verify.json" --by xinci-simple-verify \
  --reason "G1 pass(AIO 只罗列工具名),G2 pass,G3 强完整 1 个,base $640" \
  --form tool --revenue-json '<revenue_model.py 输出去掉 passes 字段>'
python3 xinci-simple-workflow/xinci-simple-core/scripts/build_report.py --slug heic-to-jpg-converter
python3 xinci-simple-workflow/xinci-simple-core/scripts/ledger.py transition --slug some-term --to rejected \
  --evidence "证据/some-term/2026-09-11-verify.json" --by xinci-simple-verify --reason "G1 直答:AIO 给出完整换算表,用户不必点结果"
```

- [ ] **Step 3: 写 xinci-simple-status/SKILL.md**

frontmatter：

```yaml
---
name: xinci-simple-status
description: '流量型选词工作流的只读看板:各状态计数、待核验候选按排序分、已搁置停留天数、已验证的报告路径。当用户想看 simple 工作流状态、老词账本里有什么时使用。English triggers: simple status, traffic keyword ledger overview. 这是 xinci-simple-workflow,不是 xinci 新词工作流的 xinci-status。'
---
```

正文：第 0 步数据区 → `report_status.py` → 如实转述（先计数，后三段明细）→ 异常或用户要求时 `validate_ledger.py`。只陈述事实，不加驱动性措辞。

- [ ] **Step 4: 自查三个 SKILL.md**

Run: `for f in xinci-simple-workflow/xinci-simple-*/SKILL.md; do python3 -c "import sys,re;t=open('$f',encoding='utf-8').read();m=re.match(r'^---\nname: (\S+)\ndescription: .+\n---\n',t,re.S);print('$f', 'ok' if m else 'BAD frontmatter')"; done`
Expected: 三行 ok
Run: `grep -n "xinci-workflow/xinci-core\|--by xinci-scan\|--by xinci-track" xinci-simple-workflow/xinci-simple-*/SKILL.md` → 无输出

- [ ] **Step 5: 提交**

```bash
git add xinci-simple-workflow/
git commit -m "xinci-simple:scan / verify / status 三个 skill"
```

---

### Task 11: README、symlink、数据区初始化、验收

**Files:**
- Create: `xinci-simple-workflow/README.md`
- Modify: `README.md`（仓库根，加一节指向）

- [ ] **Step 1: 写 xinci-simple-workflow/README.md**

内容：一句话定位（设计稿 §2.1）→ 与 xinci 的关系（冻结、零依赖、独立数据区）→ 单元清单表（3 skill + core）→ 四层漏斗一段（§3）→ 状态机图（§4.1）→ 数据区与首次使用（`init_workspace.py --data-root`）→ symlink 命令 → 测试命令 → 指向设计稿与两份契约。

- [ ] **Step 2: 仓库根 README.md 加一节**

在"## 单元清单"之后插入：

```markdown
## xinci-simple-workflow（流量型选词）

2026-09-09 起新增的第二套工作流：从已有真实搜索量的英文词里找守得弱、AI Overview 吃不掉、base case ≥ $500/月 的主题簇，产出机会报告。与 xinci 新词工作流零运行时依赖、数据区独立。入口见 [xinci-simple-workflow/README.md](xinci-simple-workflow/README.md)。
```

- [ ] **Step 3: 初始化数据区并接入 symlink**

```bash
python3 xinci-simple-workflow/xinci-simple-core/scripts/init_workspace.py --data-root /Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-simple
for s in xinci-simple-scan xinci-simple-verify xinci-simple-status; do
  ln -sfn "$(pwd)/xinci-simple-workflow/$s" ~/.claude/skills/$s
  ln -sfn "$(pwd)/xinci-simple-workflow/$s" ~/.codex/skills/$s
done
readlink ~/.claude/skills/xinci-simple-scan ~/.codex/skills/xinci-simple-scan
```

Expected: 两行同一路径；数据区四目录 + 空账本已建；`.xinci-simple-data-root` 已写且 `git status` 不显示它。

- [ ] **Step 4: 验收**

```bash
python3 -m unittest discover -s xinci-simple-workflow/xinci-simple-core/scripts/tests -t xinci-simple-workflow/xinci-simple-core/scripts/tests -q
python3 xinci-simple-workflow/xinci-simple-core/scripts/validate_ledger.py
python3 xinci-simple-workflow/xinci-simple-core/scripts/report_status.py
python3 xinci-simple-workflow/xinci-simple-core/scripts/revenue_model.py --form info --cluster-volume 714286
git diff --check
```

Expected：全部测试 OK；`校验完成:0 个错误,0 个警告`；看板四段全"（无）"；revenue base ≈ 500 且 `passes: true`；`git diff --check` 无输出。

- [ ] **Step 5: 提交**

```bash
git add README.md xinci-simple-workflow/
git commit -m "xinci-simple:README、双环境接入与验收"
```

验收标准 1–4（首批 scan ≥ 20 个 found、verify 前 5、两条通道各用一次、Semrush 调用如实记）属运行时行为，留待首次真实运行 `xinci-simple-scan` / `xinci-simple-verify` 时执行，在最终报告中明示未完成项。

---

## Self-Review 记录

- **Spec 覆盖**：§2 → Task 9 §0–1、Task 10；§3 → Task 3/4 + Task 9 §3–6 + Task 10；§4 → Task 2/8 + Task 9 §2、§7；§5 → Task 9（数据采集）；§6 → Task 4 + Task 9 §6；§7 → Task 7 + Task 9 §8；§8 → 文件结构 + Task 10/11；§9 → Task 2/4/6/7 的拒收路径 + Task 9 §9；§10 → 各 Task 测试；§11 → Task 11 Step 4。设计稿漏的运行清单脚本已补为 Task 5。
- **占位符**：契约与 SKILL.md 用"内容源：设计稿 §N"绑定同仓固定路径，数值要求与脚本常量逐字一致，非 TBD。
- **类型一致性**：`ledger.register/transition` 签名在 Task 2/3/6/7 测试中一致；`revenue` 五键与 `L.REVENUE_KEYS` 一致；`form` 词汇 `L.FORMS` 与 `revenue_model.FORMS` 一致；观察字段名（`ai_overview` / `serp_top10` / `scope_recheck` / `browser_preflight` / `semrush_preview`）在 helpers、build_report、schema 三处一致；`PLAY_SINGLE_MAX = 150000` 与设计稿 §7 一致。
