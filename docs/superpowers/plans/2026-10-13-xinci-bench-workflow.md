# xinci-bench-workflow 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按设计稿落地 `xinci-bench-workflow/`：4 个 skill + 1 个 core（3 份文档、3 份说明性 schema、15 个脚本、85 个测试），接入双环境，初始化独立数据区并从 xinci-simple 数据区只读导入种子与词库。

**Architecture:** 判据只写在 `xinci-bench-core/选站契约.md`，数值常量写在脚本里，由 `test_documentation.py` 保证两边一致。观察只追加（`write_observation.py` 按 kind 校验）；账本四态由 `ledger.py` 强制；状态只经 `settle.py` 转移（重算模型 → 绑定 SHA → 生成决策书 → 转移 → 校验）；`bench_model.py` 是纯函数。SKILL.md 只串流程。

**Tech Stack:** Python 3 标准库（零第三方依赖）、unittest、Markdown、symlink。

**Spec:** [docs/superpowers/specs/2026-10-13-xinci-bench-workflow-design.md](../specs/2026-10-13-xinci-bench-workflow-design.md)

**计划里的代码全部来自 scratchpad 原型**：写计划时已在原型里跑通 85 个测试，并用命令行把"导入 → 登记 → 补数 → 排序 → 测算 → 结算 → 看板 → 校验"整条流程走过一遍（0 个错误）；还用真实的 xinci-simple 数据区试跑过导入（标杆种子 68、同类站种子 13、旧词库 14,258 词、旧裁决 63）。照抄即可，不要凭记忆改写。

## 目录

- [与设计稿的差异（本计划补的，最后一个任务写回设计稿）](#与设计稿的差异本计划补的最后一个任务写回设计稿)
- [Global Constraints](#global-constraints)
- [Review Focus](#review-focus)
- [文件结构](#文件结构)
- [任务](#任务)
  - [Task 1: 基建——gitignore、共用原语、数据区解析、初始化、测试 helper](#task-1-基建gitignore共用原语数据区解析初始化测试-helper)
  - [Task 2: 观察写入与校验](#task-2-观察写入与校验)
  - [Task 3: 种子池与淘汰索引](#task-3-种子池与淘汰索引)
  - [Task 4: 旧数据只读导入与旧词库查询](#task-4-旧数据只读导入与旧词库查询)
  - [Task 5: 标杆份额法收入模型](#task-5-标杆份额法收入模型)
  - [Task 6: 方向账本](#task-6-方向账本)
  - [Task 7: 决策书生成](#task-7-决策书生成)
  - [Task 8: 账本校验与结算](#task-8-账本校验与结算)
  - [Task 9: 运行清单与看板](#task-9-运行清单与看板)
  - [Task 10: 选站契约、数据采集规程、命令与观察](#task-10-选站契约数据采集规程命令与观察)
  - [Task 11: 四个 SKILL.md、README 与双环境接入](#task-11-四个-skillmdreadme-与双环境接入)
  - [Task 12: 真实数据区初始化、旧数据导入与验收](#task-12-真实数据区初始化旧数据导入与验收)

## 与设计稿的差异（本计划补的，最后一个任务写回设计稿）

1. 观察新增 `brief` 一类：设计稿 §7.3 的建站简报要从结构化字段生成，但 §5.2 没给简报素材的落点。
2. benchmark 观察新增 `curve`（起量后第 3/6/12 个月读数）：§7.3 第 10 节的里程碑要用标杆曲线形状。第 12 个月的预期点击按定义等于基准情景。
3. 方向记录新增 `decision` 字段（结论、gate、理由、最大未知、命中项、时间）：结算与决策书都要用，§5.1 的示例里漏了。
4. delivery 读数字段定名为 `hours{dev,data,content}`、`cash_first_year`、`monthly_hours`；demand 的 `competitor_traffic` 每项定为 `{domain, traffic, basis}`。
5. 手工种子的 RDAP 核对由执行者在写 `种子/手工种子.json` 前用 curl 做（`数据采集.md` §3），脚本不联网。
6. B1–B3 的数值门槛由 `write_observation.py` 强制：标"通过"但数字不达标的 scan 观察直接拒收。
7. 旧数据导入实测条数：标杆种子 68 个（设计稿写"约 71"，其中 pinterest、play.google、scribd 三个平台被黑名单去掉），同类站种子 13 个。

## Global Constraints

- 只用 Python 3 标准库与 unittest，不加第三方依赖。
- 与 xinci、xinci-simple 零运行时依赖：不 import 它们的脚本；xinci-simple 数据区只读，导入前后 SHA-256 必须一致。
- 数据区解析顺序：`--data-root` > 环境变量 `XINCI_BENCH_DATA_ROOT` > 仓库根 `.xinci-bench-data-root` > 退出码 2；指针文件不入库。
- 冒烟测试一律 `init_workspace.py --data-root <临时目录> --no-save` 或只导出环境变量；跑完确认三个指针文件 `.xinci-data-root`、`.xinci-simple-data-root`、`.xinci-bench-data-root` 都没被改。
- 初核门槛：注册 ≤ 24 个月（或 `aged_domain=true`）、AS ≤ 30、去品牌词与定位词后美区自然流量 ≥ 5,000/月。
- 假设表 `2026-10-13.1`：后来者系数 0.25 / 0.5 / 1.0（crowding ≥ 3 时基准 0.33）、上限 15%、near me ×0.2、AdSense $4/千访问（< 10,000 访问）、Mediavine Journey $16/千访问（≥ 10,000）、付费转化率 0.1% / 0.2% / 0.5%、门槛基准 ≥ $100。
- 注释、文档、提交信息用中文；代码标识符用英文。文档目录要列出所有层级标题。
- 提交只 `git add` 明确路径；不碰用户未提交的 `xinci-simple-workflow/xinci-simple-core/选词契约.md`；不 push。

## Review Focus

- 结算时某个引用的观察文件已被删除：应拒收并提示"观察不存在"，而不是抛出未捕获的文件错误（Task 8 `test_deleted_observation_gives_clear_refusal`）。
- 标杆 `covered_demand` 为 0 或标杆流量为 0：应拒收或得到 $0，而不是除零崩溃（Task 5 `test_zero_covered_demand_refused_zero_traffic_ok`）。
- 域名写法五花八门（大写、带 `https://www.`、端口、末尾点、路径）：应规范化成同一个，种子池不重复（Task 3 `test_normalize`、`test_add_take_and_dedup`）。
- 旧证据目录里有损坏的 JSON：应跳过该文件、照常导入其余数据（Task 4 `test_corrupt_legacy_evidence_skipped`）。
- 执行者把 `observed_at` 写成"2026-10-13 下午"这类估计值：应拒收（Task 2 `test_observed_at_must_be_iso`）；同一秒内连写多条运行清单时恢复位置不能乱（Task 9，`recorded_at` 用微秒精度，`test_full_round_then_done` 在同一秒内连写 8 条）。

---

## 文件结构

```
xinci-bench-workflow/
├── README.md                         单元清单、首次使用、检查命令、本地接入
├── xinci-bench-scan/SKILL.md          找标杆
├── xinci-bench-assess/SKILL.md        深核与决策
├── xinci-bench-status/SKILL.md        只读看板
├── xinci-bench-run/SKILL.md           连续运行,暗号 xinci_bench_run
└── xinci-bench-core/
    ├── 选站契约.md                     唯一判据
    ├── 数据采集.md                     通道、Semrush 模块取法、导入规则、已知的坑
    ├── 命令与观察.md                   脚本调用与各类观察的字段
    ├── 数据结构/
    │   ├── observation.schema.json
    │   ├── direction.schema.json
    │   └── seeds.schema.json
    └── scripts/
        ├── _common.py          路径常量、BenchError/require、now/today/stamp、atomic_save、load_json、sha256_file、load/save_ledger
        ├── data_root.py        数据区解析
        ├── init_workspace.py   建目录与空文件;--no-save
        ├── write_observation.py 按 kind 校验并追加观察;read 读回重验
        ├── seeds.py            种子池与淘汰索引
        ├── seed_import.py      xinci-simple 数据区只读导入
        ├── lexicon.py          旧词库与旧裁决查询
        ├── bench_model.py      标杆份额法与里程碑
        ├── ledger.py           四态账本:register/update/rank/transition
        ├── build_doc_html.py   md → html(内嵌源 SHA)
        ├── build_doc.py        账本 + 绑定观察 → 决策书 md(+html)
        ├── validate_ledger.py  不变式校验
        ├── settle.py           结算与恢复
        ├── run_log.py          运行清单、--plan、--finish
        ├── report_status.py    看板
        └── tests/              helpers.py + 11 个测试文件
```

所有命令在仓库根 `/Users/vito.wu/IdeaProjects/workflow-skills` 执行。测试命令固定为：

```bash
python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q
```

**开工前**：在 main 上新建分支 `git switch -c xinci-bench-workflow`（用户未提交的 `选词契约.md` 改动会跟过来，不要提交它）。每个 Task 结束提交一次。

## 任务

### Task 1: 基建——gitignore、共用原语、数据区解析、初始化、测试 helper

**Files:**
- Modify: `.gitignore`（末尾追加）
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/_common.py`
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/data_root.py`
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py`
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/tests/__init__.py`（空文件）
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/tests/helpers.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_data_root.py`

**Interfaces:**
- Consumes: 无
- Produces: `_common` 的 `LEDGER_REL/SEEDS_REL/MANUAL_SEEDS_REL/REJECTS_REL/LEXICON_REL/VERDICTS_REL`、`SLUG_RE`、`BenchError`、`require(cond, msg)`、`now()->str`、`today()->str`、`stamp()->str`、`atomic_save(path, obj)`、`load_json(path)`、`sha256_file(path)->str`、`load_ledger(root)->dict`、`save_ledger(root, ledger)`；`data_root.resolve(explicit=None)->Path`、`resolve_or_exit(explicit=None)->Path`、`save(path)`、`config_path()`、`ENV_VAR`、`REPO_ROOT`；`init_workspace.init_workspace(root)->list`、`SUBDIRS`
- Produces（测试用）: `helpers.TmpRoot`、`scan_obs/benchmark_obs/demand_obs/serp_obs/diff_obs/delivery_obs/brief_obs`、`benchmark_record/cluster_record/model_record`、`setup_direction(root, slug='example-county', us_organic_m12=20000, stale=False)->(slug, refs)`、`write_json`、`deep`。helper 里引用后续任务模块的函数（如 `setup_direction`）都在函数体内 import，本任务不会因此报错

- [ ] **Step 0: `.gitignore` 末尾追加**

```
# xinci-bench 的数据区配置同样是本地选择,不入库
.xinci-bench-data-root
```

建空文件 `xinci-bench-workflow/xinci-bench-core/scripts/tests/__init__.py`。

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_data_root.py`：

```python
# 数据区解析:显式 > 环境变量 > 仓库配置 > 拒绝。不猜位置。
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import data_root as D
import init_workspace


class DataRootTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._cfg = mock.patch.object(D, "REPO_ROOT", self.tmp)
        self._cfg.start()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(D.ENV_VAR, None)

    def tearDown(self):
        self._env.stop()
        self._cfg.stop()
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
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            D.resolve_or_exit(None)
        self.assertEqual(cm.exception.code, 2)

    def test_init_no_save_leaves_pointer_alone(self):
        target = self.tmp / "ws"
        with contextlib.redirect_stdout(io.StringIO()):
            init_workspace.main(["--data-root", str(target), "--no-save"])
        self.assertFalse(D.config_path().exists())
        self.assertTrue((target / "账本" / "方向账本.json").is_file())

    def test_init_is_idempotent_and_creates_all(self):
        target = self.tmp / "ws"
        first = init_workspace.init_workspace(target)
        self.assertEqual(init_workspace.init_workspace(target), [])
        for sub in init_workspace.SUBDIRS:
            self.assertTrue((target / sub).is_dir(), sub)
        self.assertTrue(any(p.endswith("淘汰索引/域名.json") for p in first))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，报 `ImportError: No module named 'data_root'`（本任务的模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/_common.py`：

```python
#!/usr/bin/env python3
"""共用原语:时间戳、原子写、SHA-256、数据区内固定路径。不依赖任何其他工作流模块。"""
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

LEDGER_REL = "账本/方向账本.json"
SEEDS_REL = "种子/种子池.json"
MANUAL_SEEDS_REL = "种子/手工种子.json"
REJECTS_REL = "淘汰索引/域名.json"
LEXICON_REL = "词库/旧词库.json"
VERDICTS_REL = "词库/旧裁决.json"

SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


class BenchError(Exception):
    """所有脚本共用的拒收错误;文案直接给执行者看。"""


def require(cond, msg):
    if not cond:
        raise BenchError(msg)


def now() -> str:
    """UTC 秒级 ISO 时间戳,所有落盘时间字段统一用它。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def stamp() -> str:
    """文件名用的 UTC 时间戳,精确到微秒。"""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def atomic_save(path, obj) -> None:
    """先写同目录临时文件再 os.replace,读者永远看不到半截 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_ledger(root) -> dict:
    p = Path(root) / LEDGER_REL
    require(p.is_file(), f"账本不存在: {p}(先运行 init_workspace.py)")
    return load_json(p)


def save_ledger(root, ledger) -> None:
    atomic_save(Path(root) / LEDGER_REL, ledger)
```

`xinci-bench-workflow/xinci-bench-core/scripts/data_root.py`：

```python
#!/usr/bin/env python3
"""数据区定位:唯一解析入口。不猜位置。

解析顺序:1. 显式 --data-root  2. 环境变量 XINCI_BENCH_DATA_ROOT
3. 仓库根配置 .xinci-bench-data-root  4. 抛 DataRootNotConfigured。
"""
import os
import sys
from pathlib import Path

ENV_VAR = "XINCI_BENCH_DATA_ROOT"
CONFIG_NAME = ".xinci-bench-data-root"
# scripts/ → xinci-bench-core/ → xinci-bench-workflow/ → 仓库根
REPO_ROOT = Path(__file__).resolve().parents[3]


class DataRootNotConfigured(Exception):
    """数据区未配置。文案面向执行者,含可照做的下一步。"""


_MESSAGE = f"""数据区未配置,拒绝执行(不猜位置)。

xinci-bench 的执行产出(账本、种子、证据、文档、运行清单)存在哪里,必须由用户指定。
**先问用户,不要替他选。**问清之后任选其一:

  1) 落盘到仓库配置(推荐):
       python3 xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py --data-root <路径>
     它会创建目录结构与空文件,并把路径写进仓库根的 {CONFIG_NAME}
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

`xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py`：

```python
#!/usr/bin/env python3
"""初始化数据区目录结构与空文件。幂等:已存在的不动。"""
import argparse
import sys
from pathlib import Path

import data_root
from _common import (LEDGER_REL, MANUAL_SEEDS_REL, REJECTS_REL, SEEDS_REL,
                     atomic_save)

SUBDIRS = ("账本", "种子", "淘汰索引", "词库", "证据/_scan", "文档/历史", "运行", "反馈")
EMPTY_FILES = {
    LEDGER_REL: {"schema_version": 1, "directions": {}},
    SEEDS_REL: {"schema_version": 1, "seeds": {}},
    MANUAL_SEEDS_REL: {"schema_version": 1, "seeds": []},
    REJECTS_REL: {"schema_version": 1, "domains": {}},
}


def init_workspace(root) -> list:
    root = Path(root)
    created = []
    for name in SUBDIRS:
        d = root / name
        if not d.is_dir():
            d.mkdir(parents=True)
            created.append(str(d))
    for rel, empty in EMPTY_FILES.items():
        p = root / rel
        if not p.is_file():
            atomic_save(p, empty)
            created.append(str(p))
    return created


def main(argv=None):
    ap = argparse.ArgumentParser(description="初始化 xinci-bench 数据区;显式 --data-root 会落盘到仓库配置")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--no-save", action="store_true", help="只建目录,不写仓库配置(冒烟测试必须加)")
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

`xinci-bench-workflow/xinci-bench-core/scripts/tests/helpers.py`：

```python
"""测试共用:临时数据区、各 kind 的合法观察、走到可结算状态的方向。"""
import copy
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


def _all_pass(**over):
    checks = {k: {"pass": True, "basis": f"{k} 依据"} for k in ("B1", "B2", "B3", "B4", "B5")}
    checks.update(over)
    return checks


BASE = {"observed_at": "2026-10-13T08:00:00+00:00", "source_urls": ["https://example.org/x"],
        "semrush_calls": 1, "points": ["要点"]}


def scan_obs(*domains, failing=None):
    """domains 全部 B1–B5 通过;failing={域名: {"B3": False}} 让指定项不过、其后留 null。"""
    items = []
    for d in domains:
        items.append({"domain": d, "registered_at": "2025-12-29", "aged_domain": False,
                      "authority_score": 11, "us_organic_now": 5400, "checks": _all_pass()})
    for d, fails in (failing or {}).items():
        checks = _all_pass()
        for k, v in fails.items():
            checks[k] = {"pass": v, "basis": f"{k} 读数"}
        items.append({"domain": d, "registered_at": "2025-01-01", "aged_domain": False,
                      "authority_score": 20, "us_organic_now": 1200, "checks": checks})
    return {**BASE, "slug": None, "stage": "scan", "kind": "scan", "readings": {"domains": items}}


def benchmark_obs(slug, domain="example-bench.com", **over):
    r = {"domain": domain, "traffic_start": "2026-04", "us_organic_now": 5400, "us_organic_m12": None,
         "curve": {"3": 500, "6": 5400, "12": None}, "referring_domains": 40,
         "anchor_summary": "品牌词与网址为主", "link_driven": False, "algo_risk": False,
         "update_readings": "3/6/8 月更新前后平稳", "ads_txt": "google.com, pub-1, DIRECT", "pricing": None}
    r.update(over)
    return {**BASE, "slug": slug, "stage": "assess", "kind": "benchmark", "readings": r}


def demand_obs(slug, clusters=None):
    clusters = clusters or [{"id": "core", "seed_term": "what county am i in", "volume": 100000,
                             "measured_at": "2026-10-13", "coverage": "benchmark", "near_me": False}]
    return {**BASE, "slug": slug, "stage": "assess", "kind": "demand",
            "readings": {"clusters": clusters, "keyword_count": 1500,
                         "competitor_traffic": [{"domain": "example-big.com", "traffic": 21000,
                                                 "basis": "Organic Research 按 /county/ 筛"}],
                         "crowding": 2, "new_sites": ["example-bench.com"]}}


PREFLIGHT = {"controllable": True, "desktop": True, "region": "us", "logged_out": True,
             "evidence": "Sign in 可见;页脚 United States"}


def serp_obs(slug, cluster_id="core", answered=False, **over):
    r = {"query": "what county am i in", "cluster_id": cluster_id, "answered": answered,
         "answered_basis": "AI 概览只推荐工具,不给县名", "benchmark_position": 4,
         "ai_overview": {"present": True, "completes_task": answered, "cited_domains": ["example-bench.com"],
                         "recommends_tools": True},
         "top10": [{"pos": 1, "domain": "example-big.com", "type": "tool", "authority_score": 38}]}
    r.update(over)
    return {**BASE, "slug": slug, "stage": "assess", "kind": "serp", "browser_preflight": dict(PREFLIGHT),
            "source_urls": ["https://www.google.com/search?q=what+county+am+i+in&gl=us&hl=en&pws=0"], "readings": r}


def diff_obs(slug, copy_only=False):
    gaps = [] if copy_only else [{"benchmark_now": "只查县", "ours": "同时给学区与选区",
                                  "evidence": "证据/example/serp 观察里标杆页只有县"}]
    return {**BASE, "slug": slug, "stage": "assess", "kind": "differentiation",
            "readings": {"copy_only": copy_only, "gaps": gaps}}


def delivery_obs(slug, feasible=True):
    return {**BASE, "slug": slug, "stage": "assess", "kind": "delivery",
            "readings": {"data_sources": ["Census Geocoder(公有领域)"], "license": "美国联邦政府作品,公有领域",
                         "hours": {"dev": 20, "data": 5, "content": 10}, "cash_first_year": 15,
                         "monthly_hours": 2, "feasible": feasible, "basis": "接口实测可用"}}


def brief_obs(slug):
    return {**BASE, "slug": slug, "stage": "assess", "kind": "brief",
            "readings": {"positioning": "按当前位置或地址一次给出县、学区和选区",
                         "pages": [{"path": "/", "target_query": "what county am i in", "volume": 74000,
                                    "page_type": "tool", "deliverable": "定位后给出县名与边界"}],
                         "tech_hosting": "Astro 静态站 + Cloudflare Pages 免费版",
                         "monetization_plan": "先接 AdSense,第 12 个月过 1 万访问后申请 Mediavine Journey",
                         "seo_notes": ["县名页不做批量模板"], "geo_notes": ["首屏给一句可引用的答案"],
                         "risks": ["同方向已有 2 个新站"]}}


def benchmark_record(domain="example-bench.com", **over):
    b = {"domain": domain, "registered_at": "2025-12-29", "aged_domain": False, "traffic_start": "2026-04",
         "authority_score": 11, "us_organic_now": 5400, "us_organic_m12": None, "covered_demand": 100000,
         "link_driven": False, "algo_risk": False, "monetization": ["adsense"], "clean": True}
    b.update(over)
    return b


def cluster_record(**over):
    c = {"id": "core", "seed_term": "what county am i in", "volume": 100000, "measured_at": "2026-10-13",
         "coverage": "benchmark", "near_me": False, "answered": False, "counted": True}
    c.update(over)
    return c


def model_record(benchmarks=None, clusters=None, crowding=1, paid=None, site_type="tool"):
    """给 bench_model.compute 用的最小方向记录。"""
    return {"site_type": site_type, "benchmarks": benchmarks or [benchmark_record()],
            "clusters": clusters or [cluster_record()], "crowding": crowding,
            "paid": paid or {"applicable": False, "price_month": None, "evidence": None}}


def deep(obj):
    return copy.deepcopy(obj)


def setup_direction(root, slug="example-county", us_organic_m12=20000, stale=False):
    """登记 + 写齐六类观察 + 补数,返回 (slug, 引用列表)。us_organic_m12=20000 时基准恰好 1 万访问(过线)。

    每个方向用自己的标杆域名 <slug>.example.com,避免触发"同标杆须写理由"。
    """
    import ledger
    import write_observation as W
    domain = f"{slug}.example.com"
    scan_ref = W.write(root, scan_obs(domain))
    ledger.register(root, slug, "按地址查所属县", "tool", domain, scan_ref, "初核全过")
    refs = [W.write(root, o) for o in (benchmark_obs(slug, domain, us_organic_m12=us_organic_m12), demand_obs(slug),
                                        serp_obs(slug), diff_obs(slug), delivery_obs(slug), brief_obs(slug))]
    measured = "2026-01-01" if stale else "2026-10-13"
    ledger.update(root, slug, {"benchmarks": [benchmark_record(domain, us_organic_m12=us_organic_m12)],
                               "clusters": [cluster_record(measured_at=measured)], "crowding": 2}, refs)
    return slug, [scan_ref] + refs


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 7 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_data_root.py" "xinci-bench-workflow/xinci-bench-core/scripts/_common.py" "xinci-bench-workflow/xinci-bench-core/scripts/data_root.py" "xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py" "xinci-bench-workflow/xinci-bench-core/scripts/tests/helpers.py" ".gitignore" "xinci-bench-workflow/xinci-bench-core/scripts/tests/__init__.py"
git commit -m "xinci-bench:基建——共用原语、数据区解析、初始化与测试 helper" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 观察写入与校验

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/write_observation.py`
- Create: `xinci-bench-workflow/xinci-bench-core/数据结构/observation.schema.json`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_write_observation.py`

**Interfaces:**
- Consumes: `_common.SLUG_RE/BenchError/load_json/require/stamp`、`data_root.resolve_or_exit`
- Produces: `write_observation.KINDS`（scan/benchmark/demand/serp/differentiation/delivery/brief）、`CHECKS`（B1–B5）、`LIMITS={'max_age_months':24,'max_authority_score':30,'min_us_organic':5000}`、`REQUIRED`（每个 kind 的必填读数键）、`validate(obs)`、`write(root, obs)->str`（返回 `证据/_scan/...-scan.json` 或 `证据/<slug>/...-<kind>.json`）、`read(root, ref)->dict`（只接受 `证据/` 下的路径，读回重验）

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_write_observation.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import write_observation as W
from _common import BenchError
from helpers import (TmpRoot, benchmark_obs, brief_obs, deep, delivery_obs, demand_obs, diff_obs,
                     scan_obs, serp_obs)


class WriteObservationTest(unittest.TestCase):
    def test_every_kind_round_trips(self):
        with TmpRoot() as root:
            for obs in (scan_obs("a.com"), benchmark_obs("s"), demand_obs("s"), serp_obs("s"),
                        diff_obs("s"), delivery_obs("s"), brief_obs("s")):
                ref = W.write(root, obs)
                self.assertEqual(W.read(root, ref)["kind"], obs["kind"])
                folder = "_scan" if obs["kind"] == "scan" else "s"
                self.assertTrue(ref.startswith(f"证据/{folder}/") and ref.endswith(f"-{obs['kind']}.json"))

    def test_never_overwrites(self):
        with TmpRoot() as root:
            refs = {W.write(root, demand_obs("s")) for _ in range(5)}
            self.assertEqual(len(refs), 5)

    def test_missing_reading_rejected(self):
        obs = benchmark_obs("s")
        del obs["readings"]["curve"]
        with self.assertRaisesRegex(BenchError, "缺字段"):
            W.validate(obs)

    def test_scan_null_only_after_a_failure(self):
        ok = scan_obs(failing={"x.com": {"B3": False, "B4": None, "B5": None}})
        W.validate(ok)
        bad = scan_obs(failing={"x.com": {"B4": None}})
        with self.assertRaisesRegex(BenchError, "null"):
            W.validate(bad)

    def test_numeric_limits_enforced_on_pass(self):
        old = scan_obs("old.com")
        old["readings"]["domains"][0]["registered_at"] = "2024-09-01"     # 25 个月前
        with self.assertRaisesRegex(BenchError, "24 个月"):
            W.validate(old)
        old["readings"]["domains"][0]["aged_domain"] = True              # 老域名重新起量,允许
        W.validate(old)
        high = scan_obs("high.com")
        high["readings"]["domains"][0]["authority_score"] = 31
        with self.assertRaisesRegex(BenchError, "AS"):
            W.validate(high)
        small = scan_obs("small.com")
        small["readings"]["domains"][0]["us_organic_now"] = 4999
        with self.assertRaisesRegex(BenchError, "5000"):
            W.validate(small)

    def test_serp_needs_passing_preflight(self):
        obs = serp_obs("s")
        obs["browser_preflight"]["logged_out"] = False
        with self.assertRaisesRegex(BenchError, "preflight"):
            W.validate(obs)

    def test_observed_at_must_be_iso(self):
        obs = demand_obs("s")
        obs["observed_at"] = "2026-10-13 下午"
        with self.assertRaisesRegex(BenchError, "observed_at"):
            W.validate(obs)

    def test_stage_must_match_kind(self):
        obs = deep(demand_obs("s"))
        obs["stage"] = "scan"
        with self.assertRaisesRegex(BenchError, "stage"):
            W.validate(obs)

    def test_differentiation_needs_gaps_unless_copy_only(self):
        W.validate(diff_obs("s", copy_only=True))
        obs = diff_obs("s")
        obs["readings"]["gaps"] = []
        with self.assertRaisesRegex(BenchError, "gaps"):
            W.validate(obs)

    def test_competitor_traffic_needs_basis(self):
        obs = demand_obs("s")
        obs["readings"]["competitor_traffic"] = [{"domain": "a.com", "traffic": 10}]
        with self.assertRaisesRegex(BenchError, "basis"):
            W.validate(obs)

    def test_read_refuses_paths_outside_evidence(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "证据/"):
                W.read(root, "账本/方向账本.json")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，报 `ImportError: No module named 'write_observation'`（本任务的模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/write_observation.py`：

```python
#!/usr/bin/env python3
"""观察只追加:按 kind 校验必填读数,文件名带时间与随机后缀,永不覆盖旧文件。"""
import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

import data_root
from _common import SLUG_RE, BenchError, load_json, require, stamp

KINDS = ("scan", "benchmark", "demand", "serp", "differentiation", "delivery", "brief")
CHECKS = ("B1", "B2", "B3", "B4", "B5")
# 初核数值门槛(选站契约 §3.2);标"通过"但数字不达标的观察直接拒收
LIMITS = {"max_age_months": 24, "max_authority_score": 30, "min_us_organic": 5000}
# 每个 kind 的 readings 必填键;值的类型在 _check_<kind> 里再细查
REQUIRED = {
    "scan": ("domains",),
    "benchmark": ("domain", "traffic_start", "us_organic_now", "us_organic_m12", "curve",
                  "referring_domains", "anchor_summary", "link_driven", "algo_risk",
                  "update_readings", "ads_txt", "pricing"),
    "demand": ("clusters", "competitor_traffic", "crowding", "new_sites"),
    "serp": ("query", "cluster_id", "answered", "answered_basis", "ai_overview",
             "benchmark_position", "top10"),
    "differentiation": ("copy_only", "gaps"),
    "delivery": ("data_sources", "license", "hours", "cash_first_year", "monthly_hours",
                 "feasible", "basis"),
    "brief": ("positioning", "pages", "tech_hosting", "monetization_plan", "seo_notes",
              "geo_notes", "risks"),
}
_YM = re.compile(r"\d{4}-\d{2}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso(ts):
    try:
        datetime.fromisoformat(ts)
        return True
    except (TypeError, ValueError):
        return False


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


def _check_scan(r, observed_at):
    require(isinstance(r["domains"], list) and r["domains"], "scan.domains 须为非空列表")
    for d in r["domains"]:
        require(isinstance(d.get("domain"), str) and d["domain"], "scan.domains[].domain 缺失")
        checks = d.get("checks") or {}
        require(set(checks) == set(CHECKS), f"{d['domain']}: checks 须恰好含 B1–B5")
        verdicts = []
        for k in CHECKS:
            c = checks[k]
            require(c.get("pass") in (True, False, None), f"{d['domain']}.{k}.pass 须为 true/false/null")
            require(isinstance(c.get("basis"), str) and c["basis"].strip(), f"{d['domain']}.{k}.basis 缺失")
            verdicts.append(c["pass"])
        # null 只表示"前面已不过、为省额度没查",全过时不允许有 null
        require(False in verdicts or None not in verdicts, f"{d['domain']}: 没有不过项时 B1–B5 不能留 null")
        _check_limits(d, observed_at)


def _months_between(earlier, later):
    a, b = date.fromisoformat(earlier[:10]), date.fromisoformat(later[:10])
    return (b.year - a.year) * 12 + b.month - a.month - (b.day < a.day)


def _check_limits(d, observed_at):
    c, name = d["checks"], d["domain"]
    if c["B1"]["pass"] is True and not d.get("aged_domain"):
        reg = d.get("registered_at")
        require(isinstance(reg, str) and _DATE.fullmatch(reg[:10]),
                f"{name}: B1 判通过须有 registered_at,或标 aged_domain=true 并在 basis 写 24 个月前流量≈0 的依据")
        require(_months_between(reg, observed_at) <= LIMITS["max_age_months"],
                f"{name}: 注册已超过 {LIMITS['max_age_months']} 个月,B1 不能判通过")
    if c["B2"]["pass"] is True:
        a = d.get("authority_score")
        require(_num(a) and a <= LIMITS["max_authority_score"], f"{name}: AS 须 ≤ {LIMITS['max_authority_score']} 才能判 B2 通过")
    if c["B3"]["pass"] is True:
        t = d.get("us_organic_now")
        require(_num(t) and t >= LIMITS["min_us_organic"],
                f"{name}: 去品牌词与定位词后的美区自然流量须 ≥ {LIMITS['min_us_organic']} 才能判 B3 通过")


def _check_benchmark(r):
    require(isinstance(r["domain"], str) and r["domain"], "benchmark.domain 缺失")
    require(r["traffic_start"] is None or _YM.fullmatch(str(r["traffic_start"])), "traffic_start 须为 YYYY-MM 或 null")
    require(_num(r["us_organic_now"]), "us_organic_now 须为非负数")
    require(r["us_organic_m12"] is None or _num(r["us_organic_m12"]), "us_organic_m12 须为非负数或 null")
    curve = r["curve"]
    require(isinstance(curve, dict) and set(curve) == {"3", "6", "12"}, "curve 须恰好含键 3/6/12")
    require(all(v is None or _num(v) for v in curve.values()), "curve 值须为非负数或 null")
    require(r["referring_domains"] is None or _num(r["referring_domains"]), "referring_domains 须为非负数或 null")
    for k in ("link_driven", "algo_risk"):
        require(isinstance(r[k], bool), f"{k} 须为布尔")
    for k in ("anchor_summary", "update_readings", "ads_txt"):
        require(isinstance(r[k], str) and r[k].strip(), f"{k} 须为非空文字")


def _check_demand(r):
    require(isinstance(r["clusters"], list) and r["clusters"], "demand.clusters 须为非空列表")
    for c in r["clusters"]:
        require(isinstance(c.get("id"), str) and SLUG_RE.fullmatch(c["id"]), "cluster.id 无效")
        require(isinstance(c.get("seed_term"), str) and c["seed_term"].strip(), f"{c['id']}: seed_term 缺失")
        require(_num(c.get("volume")), f"{c['id']}: volume 须为非负数")
        require(_DATE.fullmatch(str(c.get("measured_at"))), f"{c['id']}: measured_at 须为 YYYY-MM-DD")
        require(c.get("coverage") in ("benchmark", "ours"), f"{c['id']}: coverage 须为 benchmark/ours")
        require(isinstance(c.get("near_me"), bool), f"{c['id']}: near_me 须为布尔")
    require(isinstance(r["competitor_traffic"], list), "competitor_traffic 须为列表")
    for t in r["competitor_traffic"]:
        require(isinstance(t, dict) and isinstance(t.get("domain"), str) and _num(t.get("traffic"))
                and isinstance(t.get("basis"), str) and t["basis"].strip(),
                "competitor_traffic[] 须含 domain、traffic(非负数)、basis(按网址筛选的依据)")
    require(isinstance(r["crowding"], int) and r["crowding"] >= 1, "crowding 须为 ≥1 的整数(含标杆本身)")
    require(isinstance(r["new_sites"], list), "new_sites 须为列表")


def _check_serp(r):
    require(isinstance(r["query"], str) and r["query"].strip(), "serp.query 缺失")
    require(isinstance(r["cluster_id"], str) and r["cluster_id"], "serp.cluster_id 缺失")
    require(isinstance(r["answered"], bool), "serp.answered 须为布尔")
    require(isinstance(r["answered_basis"], str) and r["answered_basis"].strip(), "answered_basis 缺失")
    aio = r["ai_overview"]
    require(isinstance(aio, dict) and {"present", "completes_task", "cited_domains", "recommends_tools"} <= set(aio),
            "ai_overview 须含 present/completes_task/cited_domains/recommends_tools")
    require(r["benchmark_position"] is None or (isinstance(r["benchmark_position"], int) and r["benchmark_position"] >= 1),
            "benchmark_position 须为 ≥1 的整数或 null")
    require(isinstance(r["top10"], list), "top10 须为列表")


def _check_differentiation(r):
    require(isinstance(r["copy_only"], bool), "copy_only 须为布尔")
    require(isinstance(r["gaps"], list), "gaps 须为列表")
    if r["copy_only"]:
        return
    require(r["gaps"], "copy_only=false 时 gaps 不能为空")
    for g in r["gaps"]:
        for k in ("benchmark_now", "ours", "evidence"):
            require(isinstance(g.get(k), str) and g[k].strip(), f"gap.{k} 缺失")


def _check_delivery(r):
    require(isinstance(r["data_sources"], list), "data_sources 须为列表")
    require(isinstance(r["license"], str) and r["license"].strip(), "license 缺失")
    h = r["hours"]
    require(isinstance(h, dict) and set(h) == {"dev", "data", "content"} and all(_num(v) for v in h.values()),
            "hours 须恰好含 dev/data/content 三个非负数")
    require(_num(r["cash_first_year"]) and _num(r["monthly_hours"]), "cash_first_year/monthly_hours 须为非负数")
    require(isinstance(r["feasible"], bool), "feasible 须为布尔")
    require(isinstance(r["basis"], str) and r["basis"].strip(), "basis 缺失")


def _check_brief(r):
    require(isinstance(r["positioning"], str) and r["positioning"].strip(), "positioning 缺失")
    require(isinstance(r["pages"], list) and r["pages"], "pages 须为非空列表")
    for p in r["pages"]:
        for k in ("path", "target_query", "page_type", "deliverable"):
            require(isinstance(p.get(k), str) and p[k].strip(), f"page.{k} 缺失")
        require(_num(p.get("volume")), "page.volume 须为非负数")
    for k in ("tech_hosting", "monetization_plan"):
        require(isinstance(r[k], str) and r[k].strip(), f"{k} 缺失")
    for k in ("seo_notes", "geo_notes", "risks"):
        require(isinstance(r[k], list), f"{k} 须为列表")


def validate(obs: dict) -> None:
    kind, stage = obs.get("kind"), obs.get("stage")
    require(kind in KINDS, f"kind 须为 {KINDS}")
    require(stage == ("scan" if kind == "scan" else "assess"), "kind=scan 时 stage=scan,其余 stage=assess")
    if kind == "scan":
        require(obs.get("slug") is None, "scan 批次观察 slug 须为 null")
    else:
        require(isinstance(obs.get("slug"), str) and SLUG_RE.fullmatch(obs["slug"]), "slug 无效")
    require(isinstance(obs.get("observed_at"), str) and _iso(obs["observed_at"]),
            "observed_at 须为 ISO 时间;写观察前先取系统时间,不要估")
    urls = obs.get("source_urls")
    require(isinstance(urls, list) and urls and all(isinstance(u, str) and u for u in urls), "source_urls 须为非空列表")
    require(isinstance(obs.get("semrush_calls"), int) and obs["semrush_calls"] >= 0, "semrush_calls 须为非负整数")
    require(isinstance(obs.get("points"), list), "points 须为列表")
    if kind == "serp":
        pf = obs.get("browser_preflight") or {}
        require(all(pf.get(k) is True for k in ("controllable", "desktop", "logged_out")) and pf.get("region") == "us"
                and isinstance(pf.get("evidence"), str) and pf["evidence"].strip(),
                "serp 观察须有通过的 browser_preflight(可控、桌面、美区、未登录、依据)")
    r = obs.get("readings")
    require(isinstance(r, dict), "readings 须为对象")
    missing = [k for k in REQUIRED[kind] if k not in r]
    require(not missing, f"{kind}.readings 缺字段: {missing}")
    if kind == "scan":
        _check_scan(r, obs["observed_at"])
    else:
        globals()[f"_check_{kind}"](r)


def write(root, obs: dict) -> str:
    validate(obs)
    folder = "_scan" if obs["kind"] == "scan" else obs["slug"]
    ref = f"证据/{folder}/{stamp()}-{uuid.uuid4().hex[:8]}-{obs['kind']}.json"
    path = Path(root) / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(obs, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return ref


def read(root, ref: str) -> dict:
    """读回并重新校验;路径必须在 证据/ 下。"""
    require(ref.startswith("证据/") and ".." not in ref, f"观察路径须在 证据/ 下: {ref}")
    p = Path(root) / ref
    require(p.is_file(), f"观察不存在: {ref}")
    obs = load_json(p)
    validate(obs)
    return obs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--input", required=True, help="观察 JSON 文件")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        print(write(root, json.loads(Path(a.input).read_text(encoding="utf-8"))))
    except (BenchError, OSError, ValueError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`xinci-bench-workflow/xinci-bench-core/数据结构/observation.schema.json`：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "xinci-bench 观察文件",
  "description": "说明性 schema;强制校验在 write_observation.py。kind=scan 时 stage=scan、slug=null,其余 stage=assess。",
  "type": "object",
  "required": ["slug", "observed_at", "stage", "kind", "source_urls", "semrush_calls", "points", "readings"],
  "properties": {
    "slug": {"type": ["string", "null"]},
    "observed_at": {"type": "string", "description": "ISO 时间,写之前先取系统时间"},
    "stage": {"enum": ["scan", "assess"]},
    "kind": {"enum": ["scan", "benchmark", "demand", "serp", "differentiation", "delivery", "brief"]},
    "source_urls": {"type": "array", "minItems": 1, "items": {"type": "string"}},
    "semrush_calls": {"type": "integer", "minimum": 0},
    "points": {"type": "array", "items": {"type": "string"}},
    "browser_preflight": {"description": "kind=serp 时必填且四项通过",
      "required": ["controllable", "desktop", "region", "logged_out", "evidence"]},
    "readings": {"type": "object"}
  },
  "readings_required": {
    "scan": ["domains"],
    "benchmark": ["domain", "traffic_start", "us_organic_now", "us_organic_m12", "curve", "referring_domains",
                  "anchor_summary", "link_driven", "algo_risk", "update_readings", "ads_txt", "pricing"],
    "demand": ["clusters", "competitor_traffic", "crowding", "new_sites"],
    "serp": ["query", "cluster_id", "answered", "answered_basis", "ai_overview", "benchmark_position", "top10"],
    "differentiation": ["copy_only", "gaps"],
    "delivery": ["data_sources", "license", "hours", "cash_first_year", "monthly_hours", "feasible", "basis"],
    "brief": ["positioning", "pages", "tech_hosting", "monetization_plan", "seo_notes", "geo_notes", "risks"]
  }
}
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 18 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_write_observation.py" "xinci-bench-workflow/xinci-bench-core/scripts/write_observation.py" "xinci-bench-workflow/xinci-bench-core/数据结构/observation.schema.json"
git commit -m "xinci-bench:观察写入——按 kind 校验、初核数值门槛、只追加" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 种子池与淘汰索引

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/seeds.py`
- Create: `xinci-bench-workflow/xinci-bench-core/数据结构/seeds.schema.json`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_seeds.py`

**Interfaces:**
- Consumes: `_common.REJECTS_REL/SEEDS_REL/atomic_save/load_json/now/require/today`
- Produces: `seeds.SOURCES=('legacy','sibling','serp','geo','community')`、`ROLES=('benchmark','sibling')`、`RECHECK_DAYS=90`、`normalize_domain(text)->str`、`add(root, domain, source, source_ref, role='benchmark')->bool`、`take(root, source, n=16, role='benchmark')->list[dict]`（按登记顺序、只读）、`mark_checked(root, domains)`、`reject(root, domain, failed, readings, observation, on=None)->dict`（只有单独 B3 设 `recheck_after`）、`requeue(root, on=None)->list`、`stats(root, on=None)->dict`

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_seeds.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import seeds as S
from _common import BenchError, REJECTS_REL, load_json
from helpers import TmpRoot

OBS = "证据/_scan/20261013T080000000000Z-abcd1234-scan.json"


class SeedsTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(S.normalize_domain("https://www.Example.com/a?b=1"), "example.com")
        self.assertEqual(S.normalize_domain("sub.example.co.uk"), "sub.example.co.uk")
        self.assertEqual(S.normalize_domain("Example.COM.:443"), "example.com")
        with self.assertRaises(BenchError):
            S.normalize_domain("not a domain")

    def test_add_take_and_dedup(self):
        with TmpRoot() as root:
            self.assertTrue(S.add(root, "a.com", "serp", "查询 x 的首页"))
            self.assertFalse(S.add(root, "www.a.com", "serp", "重复"))
            S.add(root, "b.com", "serp", "查询 y")
            S.add(root, "c.com", "geo", "AI 概览推荐")
            self.assertEqual([s["domain"] for s in S.take(root, "serp")], ["a.com", "b.com"])
            S.mark_checked(root, ["a.com"])
            self.assertEqual([s["domain"] for s in S.take(root, "serp")], ["b.com"])

    def test_reject_sets_recheck_only_for_b3(self):
        with TmpRoot() as root:
            only_b3 = S.reject(root, "a.com", ["B3"], "美区 2,100", OBS, on="2026-10-13")
            self.assertEqual(only_b3["recheck_after"], "2027-01-11")
            mixed = S.reject(root, "b.com", ["B2", "B3"], "AS 45", OBS, on="2026-10-13")
            self.assertIsNone(mixed["recheck_after"])
            self.assertFalse(S.add(root, "a.com", "serp", "淘汰过的不重复登记"))

    def test_requeue_due(self):
        with TmpRoot() as root:
            S.add(root, "a.com", "serp", "x")
            S.reject(root, "a.com", ["B3"], "美区 2,100", OBS, on="2026-10-13")
            self.assertEqual(S.requeue(root, on="2027-01-10"), [])
            self.assertEqual(S.requeue(root, on="2027-01-11"), ["a.com"])
            self.assertEqual([s["domain"] for s in S.take(root, "serp")], ["a.com"])
            self.assertEqual(load_json(root / REJECTS_REL)["domains"], {})

    def test_reject_needs_scan_observation(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "scan 观察"):
                S.reject(root, "a.com", ["B3"], "x", "证据/s/a.json")

    def test_stats(self):
        with TmpRoot() as root:
            S.add(root, "a.com", "serp", "x")
            S.add(root, "b.com", "legacy", "y", role="sibling")
            S.reject(root, "c.com", ["B3"], "z", OBS, on="2026-01-01")
            st = S.stats(root, on="2026-10-13")
            self.assertEqual(st["pending"], {"serp/benchmark": 1, "legacy/sibling": 1})
            self.assertEqual(st["recheck_due"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，报 `ImportError: No module named 'seeds'`（本任务的模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/seeds.py`：

```python
#!/usr/bin/env python3
"""种子池与淘汰索引:取一批待初核域名、登记新发现、记初核不过、到期回池。"""
import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import data_root
from _common import REJECTS_REL, SEEDS_REL, BenchError, atomic_save, load_json, now, require, today

SOURCES = ("legacy", "sibling", "serp", "geo", "community")
ROLES = ("benchmark", "sibling")
RECHECK_DAYS = 90
_DOMAIN = re.compile(r"[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*\.[a-z]{2,}")


def normalize_domain(text: str) -> str:
    """https://www.Example.com/a?b → example.com;不是域名就拒收。"""
    d = (text or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d).split("/")[0].split("?")[0].split(":")[0]
    d = d.rstrip(".").removeprefix("www.")
    require(_DOMAIN.fullmatch(d), f"不是有效域名: {text!r}")
    return d


def _load(root):
    return load_json(Path(root) / SEEDS_REL), load_json(Path(root) / REJECTS_REL)


def add(root, domain, source, source_ref, role="benchmark") -> bool:
    """登记新种子;已在池里或在淘汰索引里的不重复登记,返回是否新增。"""
    require(source in SOURCES, f"source 须为 {SOURCES}")
    require(role in ROLES, f"role 须为 {ROLES}")
    require(isinstance(source_ref, str) and source_ref.strip(), "source_ref 须写明从哪发现的")
    d = normalize_domain(domain)
    pool, rejects = _load(root)
    if d in pool["seeds"] or d in rejects["domains"]:
        return False
    pool["seeds"][d] = {"source": source, "source_ref": source_ref, "role": role,
                        "added_at": now(), "status": "pending"}
    atomic_save(Path(root) / SEEDS_REL, pool)
    return True


def take(root, source, n=16, role="benchmark") -> list:
    """按登记顺序取 n 个待初核种子,只读不标记。"""
    require(source in SOURCES and role in ROLES, "source 或 role 无效")
    pool, _ = _load(root)
    picked = [{"domain": d, **s} for d, s in pool["seeds"].items()
              if s["source"] == source and s["role"] == role and s["status"] == "pending"]
    return picked[:n]


def mark_checked(root, domains) -> None:
    pool, _ = _load(root)
    for raw in domains:
        d = normalize_domain(raw)
        require(d in pool["seeds"], f"种子池里没有 {d}")
        pool["seeds"][d]["status"] = "checked"
        pool["seeds"][d]["checked_at"] = now()
    atomic_save(Path(root) / SEEDS_REL, pool)


def reject(root, domain, failed, readings, observation, on=None) -> dict:
    """记初核不过;只有 B3 不过的才设 90 天复查(新站还会长)。"""
    require(failed and set(failed) <= {"B1", "B2", "B3", "B4", "B5"}, "failed 须为 B1–B5 的非空子集")
    require(isinstance(readings, str) and readings.strip(), "readings 须写读数摘要")
    require(isinstance(observation, str) and observation.startswith("证据/_scan/"), "observation 须为 scan 观察路径")
    d = normalize_domain(domain)
    on = on or today()
    pool, rejects = _load(root)
    entry = {"failed": sorted(set(failed)), "readings": readings, "at": on,
             "recheck_after": (date.fromisoformat(on) + timedelta(days=RECHECK_DAYS)).isoformat()
             if set(failed) == {"B3"} else None,
             "observation": observation}
    rejects["domains"][d] = entry
    atomic_save(Path(root) / REJECTS_REL, rejects)
    if d in pool["seeds"]:
        pool["seeds"][d]["status"] = "checked"
        pool["seeds"][d]["checked_at"] = now()
        atomic_save(Path(root) / SEEDS_REL, pool)
    return entry


def requeue(root, on=None) -> list:
    """把复查日已到的 B3 淘汰域名放回种子池(状态 pending),并移出淘汰索引。"""
    on = on or today()
    pool, rejects = _load(root)
    due = [d for d, e in rejects["domains"].items() if e["recheck_after"] and e["recheck_after"] <= on]
    for d in due:
        e = rejects["domains"].pop(d)
        seed = pool["seeds"].get(d) or {"source": "legacy", "source_ref": e["observation"],
                                         "role": "benchmark", "added_at": now()}
        seed.update(status="pending", requeued_at=now(), requeued_from=e)
        pool["seeds"][d] = seed
    if due:
        atomic_save(Path(root) / SEEDS_REL, pool)
        atomic_save(Path(root) / REJECTS_REL, rejects)
    return due


def stats(root, on=None) -> dict:
    on = on or today()
    pool, rejects = _load(root)
    pending = {}
    for s in pool["seeds"].values():
        if s["status"] == "pending":
            key = f"{s['source']}/{s['role']}"
            pending[key] = pending.get(key, 0) + 1
    due = sum(1 for e in rejects["domains"].values() if e["recheck_after"] and e["recheck_after"] <= on)
    return {"pending": pending, "checked": sum(s["status"] == "checked" for s in pool["seeds"].values()),
            "rejected": len(rejects["domains"]), "recheck_due": due}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("take")
    t.add_argument("--source", required=True, choices=SOURCES)
    t.add_argument("--role", default="benchmark", choices=ROLES)
    t.add_argument("--n", type=int, default=16)
    ad = sub.add_parser("add")
    ad.add_argument("--domain", required=True)
    ad.add_argument("--source", required=True, choices=SOURCES)
    ad.add_argument("--source-ref", required=True)
    ad.add_argument("--role", default="benchmark", choices=ROLES)
    m = sub.add_parser("checked")
    m.add_argument("--domain", action="append", required=True)
    r = sub.add_parser("reject")
    r.add_argument("--domain", required=True)
    r.add_argument("--failed", action="append", required=True)
    r.add_argument("--readings", required=True)
    r.add_argument("--observation", required=True)
    sub.add_parser("requeue")
    sub.add_parser("stats")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "take":
            out = take(root, a.source, a.n, a.role)
        elif a.cmd == "add":
            out = {"added": add(root, a.domain, a.source, a.source_ref, a.role)}
        elif a.cmd == "checked":
            mark_checked(root, a.domain)
            out = {"checked": a.domain}
        elif a.cmd == "reject":
            out = reject(root, a.domain, a.failed, a.readings, a.observation)
        elif a.cmd == "requeue":
            out = {"requeued": requeue(root)}
        else:
            out = stats(root)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`xinci-bench-workflow/xinci-bench-core/数据结构/seeds.schema.json`：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "xinci-bench 种子池与淘汰索引",
  "description": "说明性 schema;强制校验在 seeds.py 与 validate_ledger.py。",
  "definitions": {
    "seed_pool": {"required": ["schema_version", "seeds"], "properties": {"seeds": {"additionalProperties": {
      "required": ["source", "source_ref", "role", "added_at", "status"],
      "properties": {"source": {"enum": ["legacy", "sibling", "serp", "geo", "community"]},
                     "role": {"enum": ["benchmark", "sibling"]},
                     "status": {"enum": ["pending", "checked"]}}}}}},
    "rejects": {"required": ["schema_version", "domains"], "properties": {"domains": {"additionalProperties": {
      "required": ["failed", "readings", "at", "recheck_after", "observation"],
      "properties": {"failed": {"type": "array", "items": {"enum": ["B1", "B2", "B3", "B4", "B5"]}},
                     "recheck_after": {"type": ["string", "null"], "description": "只有单独 B3 不过才设,为 at + 90 天"}}}}}},
    "manual_seeds": {"required": ["schema_version", "seeds"], "properties": {"seeds": {"type": "array",
      "items": {"required": ["domain"], "properties": {"role": {"enum": ["benchmark", "sibling"], "default": "benchmark"},
                                                        "note": {"type": "string"}}}}}}
  }
}
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 24 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_seeds.py" "xinci-bench-workflow/xinci-bench-core/scripts/seeds.py" "xinci-bench-workflow/xinci-bench-core/数据结构/seeds.schema.json"
git commit -m "xinci-bench:种子池与淘汰索引——登记、取批、B3 九十天复查" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 旧数据只读导入与旧词库查询

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/seed_import.py`
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/lexicon.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_seed_import.py`

**Interfaces:**
- Consumes: `seeds.normalize_domain`、`_common` 的路径常量与 `sha256_file/atomic_save/load_json`
- Produces: `seed_import.AS_LIMIT=30`、`EXCLUDED_TYPES`、`PLATFORMS`（8 个平台域名）、`benchmark_candidates(legacy_root)->dict`、`sibling_candidates(ledger)->dict`、`lexicon(ledger)->dict`、`verdicts(ledger)->dict`、`import_legacy(root, legacy_root)->dict`（幂等、前后 SHA 一致；手工种子可带 `role`，默认 benchmark）；`lexicon.match(root, text, limit=50)->dict`（keywords 按量降序、volume_sum、verdicts）

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_seed_import.py`：

```python
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lexicon
import seed_import as I
from _common import BenchError, MANUAL_SEEDS_REL, SEEDS_REL, LEXICON_REL, VERDICTS_REL, load_json, sha256_file
from helpers import TmpRoot, write_json

LEDGER = {"schema_version": 1, "candidates": {
    "tide-chart": {"slug": "tide-chart", "primary_keyword": "tide chart", "state": "parked",
                   "seed": {"type": "root", "value": "Chart", "queried_at": "2026-09-10T03:00:00+00:00"},
                   "cluster": {"keywords": [{"term": "Tide Chart", "volume": 1000, "kd": 11},
                                            {"term": "tide times", "volume": 500}]},
                   "history": [{"to": "found", "from": None, "reason": "准入"},
                               {"to": "parked", "from": "found", "reason": "季节性"}]},
    "bus-schedule": {"slug": "bus-schedule", "primary_keyword": "bus schedule", "state": "rejected",
                     "seed": {"type": "small_site", "value": "transitapp.com(AS 63) 与 Example.org 反推",
                              "queried_at": "2026-09-11T03:00:00+00:00"},
                     "cluster": {"keywords": [{"term": "tide chart", "volume": 1200, "kd": 12}]},
                     "history": [{"to": "found", "from": None, "reason": "准入"},
                                 {"to": "rejected", "from": "found", "gate": "G3", "reason": "K=3"}]}}}


def legacy_root(tmp):
    root = Path(tmp)
    write_json(root / "账本" / "候选账本.json", LEDGER)
    rows = [
        {"url": "https://www.small-tool.com/a", "dr": 11, "type": "tool"},      # 保留
        {"domain": "unknown-as.com", "dr": 0, "type": "tool"},                    # 0 视为未测,保留
        {"domain": "big.com", "dr": 45, "type": "tool"},                          # AS 过高
        {"domain": "denvergov.org", "dr": 14, "type": "other"},                   # 政府
        {"domain": "city.gov", "dr": 10, "type": "tool"},                         # .gov
        {"domain": "pinterest.com", "dr": 0, "type": "other"},                    # 平台
        {"domain": "no-as.com", "dr": None, "type": "tool"},                      # 没有 AS 记录
        {"domain": "mixed.com", "dr": 12, "type": "tool"},
    ]
    write_json(root / "证据" / "tide-chart" / "a-verify.json", {"serp_top10": rows})
    write_json(root / "证据" / "bus-schedule" / "b-verify.json",
               {"serp_top10": [{"domain": "mixed.com", "dr": 12, "type": "official"}]})  # 出现过 official → 排除
    return root


class SeedImportTest(unittest.TestCase):
    def test_filters_and_counts(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            legacy = legacy_root(tmp)
            out = I.import_legacy(root, legacy)
            pool = load_json(root / SEEDS_REL)["seeds"]
            bench = sorted(d for d, s in pool.items() if s["role"] == "benchmark")
            self.assertEqual(bench, ["small-tool.com", "unknown-as.com"])
            self.assertIsNone(pool["unknown-as.com"]["as_recorded"])
            self.assertEqual(sorted(d for d, s in pool.items() if s["role"] == "sibling"),
                             ["example.org", "transitapp.com"])
            self.assertEqual(out["lexicon_words"], 2)
            self.assertEqual(out["verdicts"], 2)

    def test_lexicon_keeps_latest_and_verdict_gate(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            I.import_legacy(root, legacy_root(tmp))
            words = load_json(root / LEXICON_REL)["words"]
            self.assertEqual(words["tide chart"]["volume"], 1200)
            self.assertEqual(words["tide chart"]["slug"], "bus-schedule")
            ver = load_json(root / VERDICTS_REL)["candidates"]
            self.assertEqual(ver["bus-schedule"]["gate"], "G3")
            self.assertIsNone(ver["tide-chart"]["gate"])

    def test_idempotent_and_legacy_untouched(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            legacy = legacy_root(tmp)
            before = {p: sha256_file(p) for p in legacy.rglob("*.json")}
            I.import_legacy(root, legacy)
            again = I.import_legacy(root, legacy)
            self.assertEqual(again["seeds_added"], {"benchmark": 0, "sibling": 0, "manual": 0})
            self.assertEqual(before, {p: sha256_file(p) for p in legacy.rglob("*.json")})

    def test_manual_seeds_imported_first(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            write_json(root / MANUAL_SEEDS_REL, {"schema_version": 1, "seeds": [
                {"domain": "https://www.wisconsinpropertymap.com/", "note": "AS 11,9 个月到 5.4K"},
                {"domain": "geocodify.com", "role": "sibling", "note": "AS 38,只查同类站"}]})
            I.import_legacy(root, legacy_root(tmp))
            pool = load_json(root / SEEDS_REL)["seeds"]
            self.assertEqual(next(iter(pool)), "wisconsinpropertymap.com")
            self.assertEqual(pool["geocodify.com"]["role"], "sibling")
            write_json(root / MANUAL_SEEDS_REL, {"schema_version": 1, "seeds": [{"domain": "x.com", "role": "boss"}]})
            with self.assertRaisesRegex(BenchError, "role"):
                I.import_legacy(root, legacy_root(tmp))

    def test_corrupt_legacy_evidence_skipped(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            legacy = legacy_root(tmp)
            (legacy / "证据" / "tide-chart" / "broken.json").write_text("{坏的", encoding="utf-8")
            self.assertEqual(I.import_legacy(root, legacy)["benchmark_candidates"], 2)

    def test_missing_legacy_ledger(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(BenchError, "旧账本不存在"):
                I.import_legacy(root, tmp)

    def test_lexicon_match(self):
        with TmpRoot() as root, tempfile.TemporaryDirectory() as tmp:
            I.import_legacy(root, legacy_root(tmp))
            out = lexicon.match(root, "tide")
            self.assertEqual([k["term"] for k in out["keywords"]], ["tide chart", "tide times"])
            self.assertEqual(out["volume_sum"], 1700)
            self.assertIn("tide-chart", out["verdicts"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，报 `ImportError: No module named 'lexicon'`（本任务的模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/seed_import.py`：

```python
#!/usr/bin/env python3
"""从 xinci-simple 数据区只读导入:标杆种子、同类站种子、旧词库、旧裁决。幂等。

旧数据区路径必须显式传入;导入前后对读过的旧文件逐个算 SHA-256,不一致就报错。
"""
import argparse
import json
import re
import sys
from pathlib import Path

import data_root
from _common import (LEXICON_REL, MANUAL_SEEDS_REL, SEEDS_REL, VERDICTS_REL, BenchError,
                     atomic_save, load_json, now, require, sha256_file)
from seeds import ROLES, normalize_domain

AS_LIMIT = 30
EXCLUDED_TYPES = {"official", "brand", "forum", "video"}
PLATFORMS = {"pinterest.com", "play.google.com", "scribd.com", "reddit.com", "facebook.com",
             "youtube.com", "quora.com", "amazon.com"}
_GOV = re.compile(r"(^|\.)[a-z0-9-]*gov(\.|$)|\.(edu|mil)$")
_HOST = re.compile(r"^(?:https?://)?([^/\s?#]+)")
_DOMAIN_IN_TEXT = re.compile(r"\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b")


def _legacy_files(legacy_root: Path) -> list:
    files = [legacy_root / "账本" / "候选账本.json"]
    require(files[0].is_file(), f"旧账本不存在: {files[0]}")
    files += sorted((legacy_root / "证据").glob("*/*.json"))
    return files


def _host(row) -> str:
    m = _HOST.match(row.get("url") or row.get("domain") or "")
    if not m:
        return ""
    try:
        return normalize_domain(m.group(1))
    except BenchError:
        return ""


def benchmark_candidates(legacy_root: Path) -> dict:
    """旧证据 serp_top10 → {域名: {source_ref, as_recorded}};规则见设计稿 §5.4。"""
    seen = {}
    for f in sorted((legacy_root / "证据").glob("*/*.json")):
        try:
            obs = load_json(f)
        except ValueError:
            continue
        for row in obs.get("serp_top10") or []:
            h = _host(row)
            if not h:
                continue
            info = seen.setdefault(h, {"types": set(), "as": [], "ref": f"{f.parent.name}/{f.name}"})
            info["types"].add(row.get("type"))
            if row.get("dr") is not None:
                info["as"].append(row["dr"])
    out = {}
    for h, info in seen.items():
        if not info["as"] or _GOV.search(h) or h in PLATFORMS or info["types"] & EXCLUDED_TYPES:
            continue
        known = [v for v in info["as"] if v != 0]          # 0 视为未测
        if known and min(known) >= AS_LIMIT:
            continue
        out[h] = {"source_ref": "xinci-simple:证据/" + info["ref"],
                  "as_recorded": min(known) if known else None}
    return out


def sibling_candidates(ledger: dict) -> dict:
    out = {}
    for slug, c in ledger["candidates"].items():
        seed = c.get("seed") or {}
        if seed.get("type") != "small_site":
            continue
        for m in _DOMAIN_IN_TEXT.findall(str(seed.get("value", "")).lower()):
            try:
                out.setdefault(normalize_domain(m), {"source_ref": f"xinci-simple:账本/{slug}.seed"})
            except BenchError:
                pass
    return out


def lexicon(ledger: dict) -> dict:
    """旧账本全部逐词量,按小写词去重;重复时保留测量更晚的那条。"""
    words = {}
    for slug, c in ledger["candidates"].items():
        measured = str((c.get("seed") or {}).get("queried_at", ""))[:10] or None
        for k in (c.get("cluster") or {}).get("keywords") or []:
            term = str(k.get("term", "")).strip().lower()
            if not term:
                continue
            row = {"volume": k.get("volume"), "kd": k.get("kd"), "slug": slug, "measured_at": measured}
            old = words.get(term)
            if old is None or (measured or "") > (old["measured_at"] or ""):
                words[term] = row
    return words


def verdicts(ledger: dict) -> dict:
    out = {}
    for slug, c in ledger["candidates"].items():
        final = [h for h in c.get("history") or [] if h.get("to") == c["state"]]
        last = final[-1] if final else {}
        gated = [h for h in final if h.get("gate")]
        out[slug] = {"primary_keyword": c.get("primary_keyword"), "state": c["state"],
                     "gate": gated[-1]["gate"] if gated else None, "reason": last.get("reason")}
    return out


def import_legacy(root, legacy_root) -> dict:
    root, legacy_root = Path(root), Path(legacy_root)
    files = _legacy_files(legacy_root)
    before = {str(f): sha256_file(f) for f in files}
    ledger = load_json(files[0])
    bench, sib = benchmark_candidates(legacy_root), sibling_candidates(ledger)
    manual = load_json(root / MANUAL_SEEDS_REL)["seeds"]
    pool = load_json(root / SEEDS_REL)
    added = {"benchmark": 0, "sibling": 0, "manual": 0}

    def put(domain, role, ref, key, extra=None):
        if domain in pool["seeds"]:
            return
        pool["seeds"][domain] = {"source": "legacy", "source_ref": ref, "role": role,
                                 "added_at": now(), "status": "pending", **(extra or {})}
        added[key] += 1

    for item in manual:
        role = item.get("role", "benchmark")     # 不满足 B2、只用来查同类站的写 sibling
        require(role in ROLES, f"手工种子 {item.get('domain')} 的 role 须为 {ROLES}")
        put(normalize_domain(item["domain"]), role, MANUAL_SEEDS_REL, "manual", {"note": item.get("note")})
    for d, info in bench.items():
        put(d, "benchmark", info["source_ref"], "benchmark", {"as_recorded": info["as_recorded"]})
    for d, info in sib.items():
        put(d, "sibling", info["source_ref"], "sibling")
    words, ver = lexicon(ledger), verdicts(ledger)
    after = {str(f): sha256_file(f) for f in files}
    require(before == after, "旧数据区在导入期间被改动,已停止;请检查是否有其他进程在写 xinci-simple 数据区")
    digest = sha256_file(files[0])
    atomic_save(root / SEEDS_REL, pool)
    atomic_save(root / LEXICON_REL, {"schema_version": 1, "imported_from": str(legacy_root),
                                     "ledger_sha256": digest, "words": words})
    atomic_save(root / VERDICTS_REL, {"schema_version": 1, "imported_from": str(legacy_root),
                                      "ledger_sha256": digest, "candidates": ver})
    return {"seeds_added": added, "seeds_total": len(pool["seeds"]),
            "benchmark_candidates": len(bench), "sibling_candidates": len(sib),
            "lexicon_words": len(words), "verdicts": len(ver), "legacy_files_checked": len(files)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--legacy-root", required=True, help="xinci-simple 数据区路径,只读")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        print(json.dumps(import_legacy(root, a.legacy_root), ensure_ascii=False, indent=2))
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`xinci-bench-workflow/xinci-bench-core/scripts/lexicon.py`：

```python
#!/usr/bin/env python3
"""旧词库与旧裁决查询,只读:按包含匹配,词按量降序。"""
import argparse
import json
import sys
from pathlib import Path

import data_root
from _common import LEXICON_REL, VERDICTS_REL, BenchError, load_json, require


def match(root, text, limit=50) -> dict:
    q = (text or "").strip().lower()
    require(q, "查询词不能为空")
    lex_p, ver_p = Path(root) / LEXICON_REL, Path(root) / VERDICTS_REL
    require(lex_p.is_file() and ver_p.is_file(), "旧词库未导入,先运行 seed_import.py")
    words = load_json(lex_p)["words"]
    hits = sorted(((t, w) for t, w in words.items() if q in t),
                  key=lambda x: (-(x[1]["volume"] or 0), x[0]))
    ver = load_json(ver_p)["candidates"]
    vhits = {s: v for s, v in ver.items()
             if q in s.replace("-", " ") or q in str(v.get("primary_keyword") or "").lower()}
    return {"query": q, "keyword_count": len(hits),
            "volume_sum": sum(w["volume"] or 0 for _, w in hits),
            "keywords": [{"term": t, **w} for t, w in hits[:limit]], "verdicts": vhits}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--match", required=True)
    ap.add_argument("--limit", type=int, default=50)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        print(json.dumps(match(root, a.match, a.limit), ensure_ascii=False, indent=2))
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 31 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_seed_import.py" "xinci-bench-workflow/xinci-bench-core/scripts/seed_import.py" "xinci-bench-workflow/xinci-bench-core/scripts/lexicon.py"
git commit -m "xinci-bench:旧数据只读导入——标杆与同类站种子、旧词库、旧裁决" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 标杆份额法收入模型

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/bench_model.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_bench_model.py`

**Interfaces:**
- Consumes: `_common.BenchError/load_json/load_ledger/require`、`data_root`
- Produces: `bench_model.ASSUMPTIONS`（版本 `2026-10-13.1`，键见 Global Constraints）、`ModelError(BenchError)`、`covered_demand(clusters)->float`、`visits_needed_for_threshold(paid)->int`、`compute(record)->dict`（键：assumptions_version、threshold、share_rate、covered_demand、crowding、ramping、scenarios{low,base,high: coef, visits_m12, network, ads, paid, total}、passes、visits_needed_for_threshold、benchmark_fraction_needed、unconfirmed_assumptions）、`milestones(record, model, curve)->dict`（键 '3'/'6'/'12' 与 stop_line_m6）

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_bench_model.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bench_model as M
from _common import BenchError
from helpers import benchmark_record, cluster_record, model_record


class BenchModelTest(unittest.TestCase):
    def test_wisconsin_example_is_about_11_dollars(self):
        # 设计稿 §4.5:当前 5,400、仍在爬坡、照搬单标杆 → 基准 2,700 访问 → AdSense $10.80
        out = M.compute(model_record())
        base = out["scenarios"]["base"]
        self.assertEqual((base["visits_m12"], base["network"], base["total"]), (2700, "adsense", 10.8))
        self.assertTrue(out["ramping"])
        self.assertFalse(out["passes"])

    def test_threshold_is_ten_thousand_visits(self):
        ok = M.compute(model_record(benchmarks=[benchmark_record(us_organic_m12=20000)]))
        self.assertEqual(ok["scenarios"]["base"]["visits_m12"], 10000)
        self.assertEqual(ok["scenarios"]["base"]["network"], "mediavine_journey")
        self.assertEqual(ok["scenarios"]["base"]["total"], 160.0)
        self.assertTrue(ok["passes"])
        just_under = M.compute(model_record(benchmarks=[benchmark_record(us_organic_m12=19998)]))
        self.assertEqual(just_under["scenarios"]["base"]["total"], 40.0)
        self.assertFalse(just_under["passes"])

    def test_visits_needed_and_fraction(self):
        out = M.compute(model_record())
        self.assertEqual(out["visits_needed_for_threshold"], 10000)
        self.assertEqual(out["benchmark_fraction_needed"], 1.85)

    def test_cap_at_fifteen_percent(self):
        out = M.compute(model_record(benchmarks=[benchmark_record(us_organic_m12=50000)]))
        self.assertEqual(out["scenarios"]["high"]["visits_m12"], 15000)

    def test_crowding_lowers_base_coef(self):
        out = M.compute(model_record(benchmarks=[benchmark_record(us_organic_m12=20000)], crowding=3))
        self.assertEqual(out["scenarios"]["base"]["coef"], 0.33)
        self.assertEqual(out["scenarios"]["base"]["visits_m12"], 6600)

    def test_near_me_and_answered_clusters(self):
        clusters = [cluster_record(), cluster_record(id="near", volume=50000, near_me=True),
                    cluster_record(id="gone", volume=90000, answered=True)]
        out = M.compute(model_record(clusters=clusters))
        self.assertEqual(out["covered_demand"], 110000)

    def test_paid_only_when_applicable(self):
        paid = {"applicable": True, "price_month": 5, "evidence": "定价页 + 评价数"}
        out = M.compute(model_record(paid=paid))
        self.assertEqual(out["scenarios"]["base"]["paid"], 27.0)   # 2,700 × 0.2% × $5
        self.assertIn("付费转化率 0.1%/0.2%/0.5%", out["unconfirmed_assumptions"])
        self.assertEqual(M.visits_needed_for_threshold(paid), 7143)

    def test_link_driven_benchmarks_ignored_median_of_clean(self):
        bs = [benchmark_record(domain="a.com", us_organic_m12=10000),
              benchmark_record(domain="b.com", us_organic_m12=30000),
              benchmark_record(domain="c.com", us_organic_m12=90000, clean=False, link_driven=True)]
        out = M.compute(model_record(benchmarks=bs))
        self.assertEqual(out["share_rate"], 0.2)

    def test_content_site_flags_unconfirmed_rpm(self):
        out = M.compute(model_record(site_type="game"))
        self.assertTrue(any("游戏" in x for x in out["unconfirmed_assumptions"]))

    def test_zero_covered_demand_refused_zero_traffic_ok(self):
        with self.assertRaisesRegex(BenchError, "covered_demand"):
            M.compute(model_record(benchmarks=[benchmark_record(covered_demand=0)]))
        out = M.compute(model_record(benchmarks=[benchmark_record(us_organic_now=0)]))
        self.assertEqual(out["scenarios"]["base"]["total"], 0.0)
        self.assertIsNone(out["benchmark_fraction_needed"])

    def test_no_clean_benchmark_refused(self):
        with self.assertRaisesRegex(BenchError, "干净标杆"):
            M.compute(model_record(benchmarks=[benchmark_record(clean=False)]))

    def test_milestones_use_curve_then_linear(self):
        rec = model_record(benchmarks=[benchmark_record(us_organic_m12=20000)])
        model = M.compute(rec)
        ms = M.milestones(rec, model, {"3": 2000, "6": 8000, "12": None})
        self.assertEqual(ms["3"], {"expected_clicks": 1000, "basis": "标杆曲线"})
        self.assertEqual(ms["6"]["expected_clicks"], 4000)
        self.assertEqual(ms["12"], {"expected_clicks": 10000, "basis": "第 12 个月即基准情景"})
        self.assertEqual(M.milestones(rec, model, {})["3"], {"expected_clicks": 2500, "basis": "线性补"})
        self.assertEqual(ms["stop_line_m6"], 1000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，报 `ImportError: No module named 'bench_model'`（本任务的模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/bench_model.py`：

```python
#!/usr/bin/env python3
"""标杆份额法:第 12 个月访问与收入三档。纯函数 + CLI,假设表只由用户改(改时升版本)。

我们第 12 个月访问 = min(系数 × 标杆份额率 × 我们覆盖的需求, 上限 × 我们覆盖的需求)
"""
import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import data_root
from _common import BenchError, load_json, load_ledger, require

ASSUMPTIONS = {
    "version": "2026-10-13.1",
    "coef": {"low": 0.25, "base": 0.5, "high": 1.0},
    "crowded_base_coef": 0.33,
    "crowded_at": 3,
    "share_cap": 0.15,
    "near_me_factor": 0.2,
    "journey_min_visits": 10000,
    "rpm": {"adsense": 4.0, "mediavine_journey": 16.0},
    "paid_conversion": {"low": 0.001, "base": 0.002, "high": 0.005},
    "threshold": 100.0,
}
UNCONFIRMED_RPM_TYPES = ("content", "game", "mixed")
SCENARIOS = ("low", "base", "high")


class ModelError(BenchError):
    pass


def _bench_traffic(b):
    return b["us_organic_m12"] if b.get("us_organic_m12") is not None else b["us_organic_now"]


def covered_demand(clusters, a=ASSUMPTIONS) -> float:
    """计入且未被首屏答完的簇量合计;near me 簇 ×0.2。"""
    return sum(c["volume"] * (a["near_me_factor"] if c.get("near_me") else 1)
               for c in clusters if c.get("counted") and not c.get("answered"))


def _network(visits, a):
    return "mediavine_journey" if visits >= a["journey_min_visits"] else "adsense"


def _paid_per_visit(paid, scenario, a):
    if not (paid or {}).get("applicable"):
        return 0.0
    return a["paid_conversion"][scenario] * paid["price_month"]


def visits_needed_for_threshold(paid, a=ASSUMPTIONS) -> int:
    """基准付费转化率下,达到门槛所需的最少第 12 个月访问(网络分档会跳变)。"""
    extra = _paid_per_visit(paid, "base", a)
    per_adsense = a["rpm"]["adsense"] / 1000 + extra
    v = math.ceil(a["threshold"] / per_adsense)
    if v < a["journey_min_visits"]:
        return v
    per_journey = a["rpm"]["mediavine_journey"] / 1000 + extra
    return max(math.ceil(a["threshold"] / per_journey), a["journey_min_visits"])


def compute(record: dict, a=ASSUMPTIONS) -> dict:
    clean = [b for b in record.get("benchmarks") or [] if b.get("clean") is True]
    require(clean, "没有干净标杆,不能测算")
    for b in clean:
        if not b.get("covered_demand"):
            raise ModelError(f"标杆 {b['domain']} 缺 covered_demand")
    clusters = record.get("clusters") or []
    require(clusters, "没有簇,不能测算")
    paid = record.get("paid") or {"applicable": False}
    if paid.get("applicable"):
        require(isinstance(paid.get("price_month"), (int, float)) and paid["price_month"] > 0,
                "付费适用时 price_month 须为正数")
    rates = [_bench_traffic(b) / b["covered_demand"] for b in clean]
    share = statistics.median(rates)
    covered = covered_demand(clusters, a)
    crowding = record.get("crowding") or 1
    coefs = dict(a["coef"])
    if crowding >= a["crowded_at"]:
        coefs["base"] = a["crowded_base_coef"]
    scenarios = {}
    for s in SCENARIOS:
        visits = math.floor(min(coefs[s] * share * covered, a["share_cap"] * covered))
        net = _network(visits, a)
        ads = round(visits * a["rpm"][net] / 1000, 2)
        paid_rev = round(visits * _paid_per_visit(paid, s, a), 2)
        scenarios[s] = {"coef": coefs[s], "visits_m12": visits, "network": net,
                        "ads": ads, "paid": paid_rev, "total": round(ads + paid_rev, 2)}
    unconfirmed = []
    if record.get("site_type") in UNCONFIRMED_RPM_TYPES:
        unconfirmed.append("内容类/游戏类每千访问收入(暂按工具类 $4)")
    if any(v["network"] == "mediavine_journey" for v in scenarios.values()):
        unconfirmed.append("Mediavine Journey 每千访问 $16")
    if paid.get("applicable"):
        unconfirmed.append("付费转化率 0.1%/0.2%/0.5%")
    needed = visits_needed_for_threshold(paid, a)
    bench_median = statistics.median(_bench_traffic(b) for b in clean)
    return {
        "assumptions_version": a["version"], "threshold": a["threshold"],
        "share_rate": round(share, 6), "covered_demand": round(covered, 2),
        "crowding": crowding, "ramping": any(b.get("us_organic_m12") is None for b in clean),
        "scenarios": scenarios, "passes": scenarios["base"]["total"] >= a["threshold"],
        "visits_needed_for_threshold": needed,
        "benchmark_fraction_needed": round(needed / bench_median, 2) if bench_median else None,
        "unconfirmed_assumptions": unconfirmed,
    }


def milestones(record: dict, model: dict, curve: dict) -> dict:
    """第 3/6/12 个月预期点击与止损线;标杆曲线缺的月份按线性补。"""
    clean = [b for b in record["benchmarks"] if b.get("clean") is True]
    ref = statistics.median(_bench_traffic(b) for b in clean)
    base = model["scenarios"]["base"]["visits_m12"]
    out = {}
    for k in ("3", "6"):
        v = (curve or {}).get(k)
        frac = min(v / ref, 1.0) if (v is not None and ref) else int(k) / 12
        out[k] = {"expected_clicks": math.floor(base * frac),
                  "basis": "标杆曲线" if v is not None and ref else "线性补"}
    out["12"] = {"expected_clicks": base, "basis": "第 12 个月即基准情景"}
    out["stop_line_m6"] = math.floor(out["6"]["expected_clicks"] * 0.25)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--direction", help="读账本里该方向的记录")
    g.add_argument("--input", help="读一个方向记录 JSON 文件")
    a = ap.parse_args(argv)
    try:
        if a.direction:
            rec = load_ledger(data_root.resolve_or_exit(a.data_root))["directions"].get(a.direction)
            require(rec, f"账本里没有方向 {a.direction}")
        else:
            rec = load_json(Path(a.input))
        print(json.dumps(compute(rec), ensure_ascii=False, indent=2))
    except (BenchError, OSError, ValueError, KeyError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 43 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_bench_model.py" "xinci-bench-workflow/xinci-bench-core/scripts/bench_model.py"
git commit -m "xinci-bench:标杆份额法——三档访问与收入、网络分档、里程碑" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 方向账本

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/ledger.py`
- Create: `xinci-bench-workflow/xinci-bench-core/数据结构/direction.schema.json`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_ledger.py`

**Interfaces:**
- Consumes: `bench_model.compute`、`write_observation.read/CHECKS`、`_common`
- Produces: `ledger.STATES`、`LEGAL`、`GATES=('scope','benchmark','answered','revenue')`、`SITE_TYPES=('tool','content','game','mixed')`、`SCOPE_ITEMS=('ymyl','brand_nav','news','adult_gambling','infringement')`、`BENCH_KEYS`、`CLUSTER_KEYS`、`PATCHABLE`、`FRESH_DAYS=90`、`register(root, slug, title, site_type, domain, scan_ref, reason, by='xinci-bench-scan', confirm_distinct=None)->dict`、`update(root, slug, patch, refs=())->dict`（清空 model）、`rank(root, on=None)->list[{slug, speed, authority_score}]`、`doc_paths(root, slug)->(md, html)`、`docs_consistent(root, slug)->bool`、`transition(root, slug, to, gate=None, reason='', by='xinci-bench-assess', on=None)->dict`（要求 `decision` 一致、决策书一致、按 gate 的最小证据）。CLI 只开放 register/update/rank/show，状态转移只经 settle.py

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_ledger.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import write_observation as W
from _common import BenchError, load_ledger
from helpers import TmpRoot, benchmark_record, cluster_record, demand_obs, scan_obs, setup_direction


class RegisterTest(unittest.TestCase):
    def test_register_copies_scan_readings(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs("example-bench.com"))
            rec = L.register(root, "example-county", "按地址查县", "tool", "example-bench.com", ref, "初核全过")
            b = rec["benchmarks"][0]
            self.assertEqual((b["authority_score"], b["us_organic_now"], b["clean"]), (11, 5400, None))
            self.assertEqual(rec["state"], "found")

    def test_register_refuses_failed_domain(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs(failing={"bad.com": {"B3": False, "B4": None, "B5": None}}))
            with self.assertRaisesRegex(BenchError, "B1–B5 全过"):
                L.register(root, "bad", "x", "tool", "bad.com", ref, "r")

    def test_same_benchmark_needs_confirm_distinct(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs("example-bench.com"))
            L.register(root, "a", "方向 A", "tool", "example-bench.com", ref, "r")
            with self.assertRaisesRegex(BenchError, "confirm-distinct"):
                L.register(root, "b", "方向 B", "tool", "example-bench.com", ref, "r")
            L.register(root, "b", "方向 B", "tool", "example-bench.com", ref, "r", confirm_distinct="B 是学区不是县")

    def test_duplicate_slug_and_bad_site_type(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs("example-bench.com"))
            L.register(root, "a", "x", "tool", "example-bench.com", ref, "r")
            with self.assertRaisesRegex(BenchError, "已存在"):
                L.register(root, "a", "x", "tool", "example-bench.com", ref, "r", confirm_distinct="y")
            with self.assertRaisesRegex(BenchError, "site_type"):
                L.register(root, "c", "x", "blog", "example-bench.com", ref, "r", confirm_distinct="y")


class UpdateRankTest(unittest.TestCase):
    def test_clean_requires_scan_pass_and_not_link_driven(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs("example-bench.com"))
            L.register(root, "a", "x", "tool", "example-bench.com", ref, "r")
            with self.assertRaisesRegex(BenchError, "外链驱动"):
                L.update(root, "a", {"benchmarks": [benchmark_record(link_driven=True)]})
            with self.assertRaisesRegex(BenchError, "B1–B5 全过"):
                L.update(root, "a", {"benchmarks": [benchmark_record(domain="other.com")]})

    def test_update_clears_model_and_adds_refs(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual(rec["evidence_refs"], refs)
            self.assertIsNone(rec["model"])
            with self.assertRaisesRegex(BenchError, "不可补"):
                L.update(root, slug, {"state": "go"})

    def test_update_rejects_other_directions_observation(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            other = W.write(root, demand_obs("someone-else"))
            with self.assertRaisesRegex(BenchError, "别的方向"):
                L.update(root, slug, {}, [other])

    def test_cluster_shape_checked(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            bad = cluster_record()
            del bad["counted"]
            with self.assertRaisesRegex(BenchError, "缺字段"):
                L.update(root, slug, {"clusters": [bad]})

    def test_rank_by_speed(self):
        with TmpRoot() as root:
            ref = W.write(root, scan_obs("slow.com", "fast.com"))
            L.register(root, "slow", "x", "tool", "slow.com", ref, "r")
            L.register(root, "fast", "y", "tool", "fast.com", ref, "r")
            L.update(root, "fast", {"benchmarks": [benchmark_record(domain="fast.com", traffic_start="2026-08",
                                                                   us_organic_now=9000)]})
            rows = L.rank(root, on="2026-10-13")
            self.assertEqual([r["slug"] for r in rows], ["fast", "slow"])
            self.assertEqual(rows[0]["speed"], 4500.0)


class TransitionTest(unittest.TestCase):
    def test_illegal_and_gate_rules(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "gate"):
                L.transition(root, slug, "rejected", None, "r")
            with self.assertRaisesRegex(BenchError, "非法转移"):
                L.transition(root, slug, "found", None, "r")

    def test_transition_requires_settle_decision(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "settle"):
                L.transition(root, slug, "parked", None, "证据拿不到")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，报 `ImportError: No module named 'ledger'`（本任务的模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/ledger.py`：

```python
#!/usr/bin/env python3
"""方向账本:四态合法转移、登记、补数、排序、转移前的最小证据复核。账本只由本脚本写。"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import bench_model
import data_root
import write_observation as W
from _common import SLUG_RE, BenchError, load_json, load_ledger, now, require, save_ledger, sha256_file, today

STATES = ("found", "go", "rejected", "parked")
LEGAL = {"found": {"go", "rejected", "parked"}, "parked": {"go", "rejected"}}
GATES = ("scope", "benchmark", "answered", "revenue")
SITE_TYPES = ("tool", "content", "game", "mixed")
SCOPE_ITEMS = ("ymyl", "brand_nav", "news", "adult_gambling", "infringement")
BENCH_KEYS = ("domain", "registered_at", "aged_domain", "traffic_start", "authority_score",
              "us_organic_now", "us_organic_m12", "covered_demand", "link_driven", "algo_risk",
              "monetization", "clean")
CLUSTER_KEYS = ("id", "seed_term", "volume", "measured_at", "coverage", "near_me", "answered", "counted")
PATCHABLE = ("title", "site_type", "benchmarks", "clusters", "crowding", "paid")
FRESH_DAYS = 90


def _observations(root, refs):
    return [(ref, W.read(root, ref)) for ref in refs]


def _scan_domain(root, refs, domain):
    """在引用的 scan 观察里找该域名的初核记录;找不到返回 None。"""
    for _, obs in _observations(root, [r for r in refs if r.startswith("证据/_scan/")]):
        for d in obs["readings"]["domains"]:
            if d["domain"] == domain:
                return d
    return None


def _all_pass(item):
    return item is not None and all(item["checks"][k]["pass"] is True for k in W.CHECKS)


def register(root, slug, title, site_type, domain, scan_ref, reason, by="xinci-bench-scan",
             confirm_distinct=None) -> dict:
    require(isinstance(slug, str) and SLUG_RE.fullmatch(slug), "slug 须为小写字母数字连字符")
    require(isinstance(title, str) and title.strip(), "title 须写方向一句话")
    require(site_type in SITE_TYPES, f"site_type 须为 {SITE_TYPES}")
    require(isinstance(reason, str) and reason.strip(), "reason 不能为空")
    ledger = load_ledger(root)
    require(slug not in ledger["directions"], f"方向已存在: {slug}")
    W.read(root, scan_ref)
    item = _scan_domain(root, [scan_ref], domain)
    require(_all_pass(item), f"{domain} 在 {scan_ref} 里没有 B1–B5 全过的记录,不能登记")
    same = [s for s, r in ledger["directions"].items() if any(b["domain"] == domain for b in r["benchmarks"])]
    require(not same or (confirm_distinct or "").strip(),
            f"标杆 {domain} 已用于方向 {same};确属不同方向请用 --confirm-distinct 写理由")
    rec = {
        "slug": slug, "title": title.strip(), "site_type": site_type, "state": "found",
        "benchmarks": [{"domain": domain, "registered_at": item.get("registered_at"),
                        "aged_domain": bool(item.get("aged_domain", False)), "traffic_start": None,
                        "authority_score": item.get("authority_score"),
                        "us_organic_now": item.get("us_organic_now"), "us_organic_m12": None,
                        "covered_demand": None, "link_driven": None, "algo_risk": None,
                        "monetization": [], "clean": None}],
        "clusters": [], "crowding": None,
        "paid": {"applicable": False, "price_month": None, "evidence": None},
        "model": None, "decision": None, "evidence_refs": [scan_ref], "bindings": None,
        "history": [{"at": now(), "from": None, "to": "found", "by": by, "reason": reason.strip(),
                     **({"confirm_distinct": confirm_distinct.strip()} if same else {})}],
    }
    ledger["directions"][slug] = rec
    save_ledger(root, ledger)
    return rec


def _check_benchmarks(root, refs, benchmarks):
    require(isinstance(benchmarks, list) and benchmarks, "benchmarks 须为非空列表")
    for b in benchmarks:
        missing = [k for k in BENCH_KEYS if k not in b]
        require(not missing, f"标杆 {b.get('domain')} 缺字段 {missing}")
        require(b["clean"] in (True, False, None), "clean 须为 true/false/null")
        if b["clean"] is True:
            require(b["link_driven"] is False, f"{b['domain']}: 外链驱动的标杆不能标 clean")
            require(_all_pass(_scan_domain(root, refs, b["domain"])),
                    f"{b['domain']}: 引用的 scan 观察里没有 B1–B5 全过的记录,不能标 clean")


def _check_clusters(clusters):
    require(isinstance(clusters, list), "clusters 须为列表")
    ids = [c.get("id") for c in clusters]
    require(len(ids) == len(set(ids)), "簇 id 重复")
    for c in clusters:
        missing = [k for k in CLUSTER_KEYS if k not in c]
        require(not missing, f"簇 {c.get('id')} 缺字段 {missing}")
        require(c["coverage"] in ("benchmark", "ours"), f"簇 {c['id']}: coverage 须为 benchmark/ours")
        for k in ("near_me", "answered", "counted"):
            require(isinstance(c[k], bool), f"簇 {c['id']}: {k} 须为布尔")


def update(root, slug, patch: dict, refs=()) -> dict:
    """补数:只对 found/parked;改了输入就清掉旧模型结果(避免陈旧数字)。"""
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    require(rec["state"] in ("found", "parked"), f"{slug} 已是 {rec['state']},不能补数")
    bad = [k for k in patch if k not in PATCHABLE]
    require(not bad, f"不可补的字段: {bad}(可补: {PATCHABLE})")
    new_refs = list(rec["evidence_refs"])
    for ref in refs:
        obs = W.read(root, ref)
        require(obs["slug"] in (None, slug), f"{ref} 属于别的方向")
        if ref not in new_refs:
            new_refs.append(ref)
    if "site_type" in patch:
        require(patch["site_type"] in SITE_TYPES, f"site_type 须为 {SITE_TYPES}")
    if "benchmarks" in patch:
        _check_benchmarks(root, new_refs, patch["benchmarks"])
    if "clusters" in patch:
        _check_clusters(patch["clusters"])
    if "crowding" in patch:
        require(isinstance(patch["crowding"], int) and patch["crowding"] >= 1, "crowding 须为 ≥1 的整数")
    if "paid" in patch:
        p = patch["paid"]
        require(isinstance(p, dict) and isinstance(p.get("applicable"), bool), "paid.applicable 须为布尔")
        if p["applicable"]:
            require(isinstance(p.get("price_month"), (int, float)) and p["price_month"] > 0
                    and isinstance(p.get("evidence"), str) and p["evidence"].strip(),
                    "付费适用时须有正数 price_month 与有用户的 evidence")
    rec.update(patch)
    rec["evidence_refs"] = new_refs
    rec["model"] = None
    save_ledger(root, ledger)
    return rec


def _months_since(ym, on):
    y, m = map(int, ym.split("-")[:2])
    d = date.fromisoformat(on)
    return max((d.year - y) * 12 + d.month - m, 1)


def rank(root, on=None) -> list:
    """found 排序:起量速度(流量 ÷ 起量月数)降序,同分 AS 低的在前。只排序不否决。"""
    on = on or today()
    rows = []
    for slug, rec in load_ledger(root)["directions"].items():
        if rec["state"] != "found":
            continue
        best = None
        for b in rec["benchmarks"]:
            if b.get("link_driven") is True or b.get("us_organic_now") is None:
                continue
            start = b.get("traffic_start") or (b.get("registered_at") or "")[:7] or None
            months = _months_since(start, on) if start else 24
            speed = b["us_organic_now"] / months
            if best is None or speed > best[0]:
                best = (speed, b.get("authority_score") if b.get("authority_score") is not None else 99)
        if best:
            rows.append({"slug": slug, "speed": round(best[0], 1), "authority_score": best[1]})
    return sorted(rows, key=lambda r: (-r["speed"], r["authority_score"], r["slug"]))


def doc_paths(root, slug):
    base = Path(root) / "文档"
    return base / f"{slug}.md", base / f"{slug}.html"


def docs_consistent(root, slug) -> bool:
    md, html = doc_paths(root, slug)
    if not (md.is_file() and html.is_file()):
        return False
    return f'content="{sha256_file(md)}"' in html.read_text(encoding="utf-8")


def _require_evidence(root, rec, to, gate, on):
    obs = _observations(root, rec["evidence_refs"])
    kinds = {o["kind"] for _, o in obs}
    dec = rec.get("decision") or {}
    require(dec.get("verdict") == to and dec.get("gate") == gate,
            "账本里的 decision 与本次转移不一致;请用 settle.py 结算")
    require(docs_consistent(root, rec["slug"]), "决策书 md/html 缺失或不一致;请用 settle.py 结算")
    if to == "parked":
        return
    if to == "go" or gate == "revenue":
        model = bench_model.compute(rec)
        require(rec.get("model") == model, "账本里的模型结果与现场重算不一致")
        require(model["passes"] is (to == "go"), "模型结论与转移方向不符")
    if to == "go":
        need = {"benchmark", "demand", "serp", "differentiation", "delivery", "brief"}
        require(need <= kinds, f"go 缺观察: {sorted(need - kinds)}")
        delivery = [o for _, o in obs if o["kind"] == "delivery"][-1]
        require(delivery["readings"]["feasible"] is True, "交付依据不成立(最新 delivery.feasible=false)")
        stale = [c["id"] for c in rec["clusters"] if c["counted"]
                 and (date.fromisoformat(on) - date.fromisoformat(c["measured_at"])).days > FRESH_DAYS]
        require(not stale, f"计入需求的簇测量超过 {FRESH_DAYS} 天: {stale}")
        require(rec.get("bindings"), "go 须有绑定")
    elif gate == "benchmark":
        require("benchmark" in kinds, "benchmark 否决须有起量手段观察")
    elif gate == "answered":
        require(rec["clusters"] and all(c["answered"] for c in rec["clusters"]),
                "answered 否决要求所有簇都被首屏答完")
        answered_ids = {o["readings"]["cluster_id"] for _, o in obs
                        if o["kind"] == "serp" and o["readings"]["answered"]}
        missing = [c["id"] for c in rec["clusters"] if c["id"] not in answered_ids]
        require(not missing, f"这些簇没有首屏答完的 serp 观察: {missing}")
    elif gate == "scope":
        require(dec.get("scope_hit") in SCOPE_ITEMS, f"scope 否决须写命中项 {SCOPE_ITEMS}")


def transition(root, slug, to, gate=None, reason="", by="xinci-bench-assess", on=None) -> dict:
    on = on or today()
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    frm = rec["state"]
    require(to in LEGAL.get(frm, set()), f"非法转移 {frm} → {to}")
    require((gate in GATES) if to == "rejected" else gate is None,
            f"rejected 须带 gate {GATES};go/parked 不带 gate")
    require(isinstance(reason, str) and reason.strip(), "reason 不能为空")
    _require_evidence(root, rec, to, gate, on)
    rec["state"] = to
    rec["history"].append({"at": now(), "from": frm, "to": to, "by": by, "reason": reason.strip(),
                           **({"gate": gate} if gate else {})})
    save_ledger(root, ledger)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    r.add_argument("--slug", required=True)
    r.add_argument("--title", required=True)
    r.add_argument("--site-type", required=True, choices=SITE_TYPES)
    r.add_argument("--domain", required=True)
    r.add_argument("--scan", required=True, help="scan 观察路径")
    r.add_argument("--reason", required=True)
    r.add_argument("--by", default="xinci-bench-scan")
    r.add_argument("--confirm-distinct")
    u = sub.add_parser("update")
    u.add_argument("--slug", required=True)
    u.add_argument("--patch", required=True, help="补数 JSON 文件")
    u.add_argument("--ref", action="append", default=[], help="新增引用的观察路径")
    sub.add_parser("rank")
    s = sub.add_parser("show")
    s.add_argument("--slug", required=True)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "register":
            out = register(root, a.slug, a.title, a.site_type, a.domain, a.scan, a.reason, a.by, a.confirm_distinct)
        elif a.cmd == "update":
            out = update(root, a.slug, load_json(Path(a.patch)), a.ref)
        elif a.cmd == "rank":
            out = rank(root)
        else:
            out = load_ledger(root)["directions"].get(a.slug)
            require(out, f"没有方向 {a.slug}")
    except (BenchError, OSError, ValueError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`xinci-bench-workflow/xinci-bench-core/数据结构/direction.schema.json`：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "xinci-bench 方向记录",
  "description": "说明性 schema;强制校验在 ledger.py 与 validate_ledger.py。账本结构 {schema_version: 1, directions: {slug: 本记录}}。",
  "type": "object",
  "required": ["slug", "title", "site_type", "state", "benchmarks", "clusters", "crowding", "paid",
               "model", "decision", "evidence_refs", "bindings", "history"],
  "properties": {
    "slug": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
    "title": {"type": "string"},
    "site_type": {"enum": ["tool", "content", "game", "mixed"]},
    "state": {"enum": ["found", "go", "rejected", "parked"]},
    "benchmarks": {"type": "array", "minItems": 1, "items": {"required": [
      "domain", "registered_at", "aged_domain", "traffic_start", "authority_score", "us_organic_now",
      "us_organic_m12", "covered_demand", "link_driven", "algo_risk", "monetization", "clean"]}},
    "clusters": {"type": "array", "items": {"required": [
      "id", "seed_term", "volume", "measured_at", "coverage", "near_me", "answered", "counted"]}},
    "crowding": {"type": ["integer", "null"], "minimum": 1},
    "paid": {"required": ["applicable", "price_month", "evidence"]},
    "model": {"type": ["object", "null"], "description": "bench_model.compute 的输出,结算时写入"},
    "decision": {"type": ["object", "null"],
      "required": ["verdict", "gate", "reason", "biggest_unknown", "scope_hit", "decided_at"]},
    "evidence_refs": {"type": "array", "items": {"type": "string"}},
    "bindings": {"type": ["object", "null"], "required": ["bound_at", "files"]},
    "history": {"type": "array", "minItems": 1}
  }
}
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 54 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_ledger.py" "xinci-bench-workflow/xinci-bench-core/scripts/ledger.py" "xinci-bench-workflow/xinci-bench-core/数据结构/direction.schema.json"
git commit -m "xinci-bench:方向账本——四态、登记、补数、排序、转移前最小证据" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 决策书生成

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/build_doc_html.py`
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/build_doc.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_build_doc.py`

**Interfaces:**
- Consumes: `bench_model.compute/covered_demand/milestones`、`write_observation.read`、`_common.load_ledger`
- Produces: `build_doc_html.render(md_path)->str`、`build(md_path)->Path`（html 内嵌 `<meta name="xinci-bench-source-sha256" content="<md 的 SHA-256>">`）；`build_doc.render_md(root, rec)->str`、`build(root, slug)->(md_path, html_path)`。决策书结构：`## 结论`（一句话：**…**）、`## 第一部分 决策`（### 1–5）、go 时 `## 第二部分 建站简报`（### 1–11）、`## 附：证据清单`
- 说明: `build_doc_html.py` 由 `xinci-simple-workflow/xinci-simple-core/scripts/build_report_html.py` 改写而来（换了文档说明、`_decorate`、meta 名与页脚），两份各存一份、互不 import

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_build_doc.py`：

```python
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bench_model
import build_doc as B
from _common import BenchError, load_ledger, save_ledger
from helpers import TmpRoot, setup_direction


def decide(root, slug, verdict, gate=None):
    """不经 settle,直接写 decision 与 model,只测文档生成。"""
    ledger = load_ledger(root)
    rec = ledger["directions"][slug]
    rec["model"] = bench_model.compute(rec)
    rec["decision"] = {"verdict": verdict, "gate": gate, "reason": "测试理由", "biggest_unknown": "测试未知",
                       "scope_hit": None, "decided_at": "2026-10-13T08:00:00+00:00"}
    save_ledger(root, ledger)


class BuildDocTest(unittest.TestCase):
    def test_go_doc_has_both_parts_and_bold_leads(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            decide(root, slug, "go")
            md, html = B.build(root, slug)
            body = md.read_text(encoding="utf-8")
            for h in ("## 结论", "## 第一部分 决策", "### 4. 12 个月流量与收入", "## 第二部分 建站简报",
                      "### 10. 里程碑与止损", "## 附：证据清单"):
                self.assertIn(h, body)
            self.assertIn("一句话：**值得做（go）**", body)
            # 每个三级标题后的第一段以粗体开头
            for block in body.split("\n### ")[1:]:
                first = [ln for ln in block.split("\n")[1:] if ln.strip()][0]
                self.assertTrue(first.startswith("**"), block.split("\n")[0])

    def test_html_embeds_md_sha_and_lede(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            decide(root, slug, "go")
            md, html = B.build(root, slug)
            h = html.read_text(encoding="utf-8")
            self.assertIn(hashlib.sha256(md.read_bytes()).hexdigest(), h)
            self.assertIn('<div class="lede">', h)
            self.assertIn("<details><summary>附：证据清单", h)

    def test_rejected_doc_has_no_brief(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root, us_organic_m12=5400)
            decide(root, slug, "rejected", "revenue")
            body = B.build(root, slug)[0].read_text(encoding="utf-8")
            self.assertIn("否决（收入不足）", body)
            self.assertNotIn("建站简报", body)

    def test_requires_decision(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "decision"):
                B.build(root, slug)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，报 `ImportError: No module named 'build_doc'`（本任务的模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/build_doc_html.py`：

```python
#!/usr/bin/env python3
"""决策书的 html 生成器:从 md 单向生成同名 html(单文件、内联样式、双击即开)。

md 是唯一事实来源;html 永不手写、永不手改——由 build_doc.py 重建 md 后重跑本脚本。
只覆盖决策书实际用到的 Markdown 子集:h1/h2/h3、表格、有序与无序列表、
粗体、行内代码、链接、水平线。渲染保持确定性:锚点按标题顺序编号,不含时间戳。

单栏;开篇结论加底色,「附：证据清单」折进 details。
"""
import argparse
import hashlib
import html as html_mod
import re
import sys
from pathlib import Path

STYLE = """
:root {
  color-scheme: light dark;
  --bg:#fff; --surface:#f6f7f9; --text:#2c333c; --heading:#0b0f14;
  --muted:#66707d; --border:#dfe3e8; --accent:#0a5ca8; --accent-soft:#eaf2fb;
  --code-bg:#eef1f5; --good:#0f7a52;
}
@media (prefers-color-scheme: dark) {
  :root { --bg:#10141a; --surface:#1a2028; --text:#c1cad5; --heading:#fff;
    --muted:#8b95a3; --border:#2a3138; --accent:#6cb2f5; --accent-soft:#16222f;
    --code-bg:#232b35; --good:#4cc38a; }
}
*{box-sizing:border-box} html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);
 font:17px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
 "Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
 -webkit-font-smoothing:antialiased}
.wrap{max-width:46rem;margin:0 auto;padding:2.5rem 1.5rem 5rem}
main{min-width:0} .doc-h{grid-column:1/-1} .doc-h h1{margin-bottom:0}
p,li{max-width:44rem}
h1{font-size:1.85rem;line-height:1.25;letter-spacing:-.01em;color:var(--heading);
 margin:0 0 1.6rem;padding-bottom:.9rem;
 background:linear-gradient(90deg,var(--accent) 0 5rem,var(--border) 5rem) bottom left/100% 2px no-repeat}
h2{font-size:1.3rem;letter-spacing:-.005em;color:var(--heading);margin:3rem 0 1rem;
 padding-bottom:.4rem;border-bottom:1px solid var(--border)}
h3{font-size:1.06rem;color:var(--heading);margin:2rem 0 .6rem}
h1:first-child,h2:first-child{margin-top:0}
main>.a:first-child+h2{margin-top:0}
strong{font-weight:650;color:var(--heading)}
a{color:var(--accent);text-underline-offset:.18em}
ul,ol{padding-left:1.4rem;margin:.9rem 0} li{margin:.45rem 0}
li::marker{color:var(--muted)}
.tw{overflow-x:auto;margin:1.3rem 0}
table{border-collapse:collapse;width:100%;font-size:.95rem}
th{text-align:left;font-weight:650;color:var(--heading);background:var(--surface);
 border-bottom:2px solid var(--border);padding:.55rem .7rem;white-space:nowrap}
td{padding:.55rem .7rem;border-bottom:1px solid var(--border);vertical-align:top}
table tr:hover td{background:var(--accent-soft)}
code{font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
 font-size:.89em;background:var(--code-bg);color:var(--heading);padding:.12em .4em;
 border-radius:4px;overflow-wrap:break-word}
hr{border:0;border-top:1px solid var(--border);margin:2.5rem 0}
/* 开篇那句结论单独立起来,读者第一眼只看它 */
.lede{background:var(--accent-soft);border-left:3px solid var(--accent);
 border-radius:0 6px 6px 0;padding:1rem 1.2rem;margin:1.4rem 0;max-width:44rem}
.lede p{margin:0}
details{margin:1.4rem 0;border:1px solid var(--border);border-radius:6px;
 background:var(--surface);padding:.4rem .9rem}
details summary{cursor:pointer;font-weight:650;color:var(--heading);padding:.5rem 0}
details[open] summary{border-bottom:1px solid var(--border);margin-bottom:.6rem}
footer{margin-top:4rem;padding-top:1.2rem;border-top:1px solid var(--border);
 color:var(--muted);font-size:.85rem;max-width:44rem}
"""

_STASH = "\x00"


def _inline(text: str) -> str:
    """行内标记 → html。先把行内代码挖出来,避免其中的 * 与 _ 被当成强调。"""
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return f"{_STASH}{len(codes) - 1}{_STASH}"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html_mod.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(rf"{_STASH}(\d+){_STASH}",
                  lambda m: f"<code>{html_mod.escape(codes[int(m.group(1))])}</code>", text)
    return text


def _table(rows: list) -> str:
    head, body = rows[0], rows[2:]          # rows[1] 是 |---| 分隔行
    th = "".join(f"<th>{_inline(c)}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_to_html_body(md: str):
    out, headings, i = [], [], 0
    lines = md.split("\n")
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1:
                out.append(f"<h1>{_inline(text)}</h1>")
            else:
                idx = len(headings)
                headings.append((level, text, f"s{idx}"))
                out.append(f'<span class="a" id="s{idx}"></span><h{level}>{_inline(text)}</h{level}>')
            i += 1
            continue
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            out.append(_table(rows))
            continue
        if re.match(r"^\d+\.\s", line.strip()):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            out.append("<ol>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ol>")
            continue
        if line.strip().startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:])
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
            continue
        if re.match(r"^-{3,}$", line.strip()):
            out.append("<hr>")
            i += 1
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,3}\s|\||- |\d+\.\s|-{3,}$)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        if not para:
            # 该行以块级符号开头却没被任何分支消费(如缺表头的孤立表格行),
            # 当普通段落输出并强制前进,避免 i 原地不动导致死循环。
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out), headings


def _decorate(body: str) -> str:
    """html 独有的两处排版:开篇结论加底色;证据清单折起来(它是给人反查的)。"""
    body = re.sub(r"(<h2>结论</h2>)\s*(<p>一句话：.*?</p>)",
                  lambda m: f'{m.group(1)}<div class="lede">{m.group(2)}</div>',
                  body, count=1, flags=re.S)
    m = re.search(r'<span class="a" id="s\d+"></span><h2>附：证据清单</h2>', body)
    if m:
        body = (body[:m.start()]
                + '<details><summary>附：证据清单（本决策绑定的观察文件与 SHA-256）</summary>'
                + body[m.end():] + "</details>")
    return body


def render(md_path: Path) -> str:
    raw = md_path.read_bytes()
    md = raw.decode("utf-8")
    source_sha256 = hashlib.sha256(raw).hexdigest()
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    title = html_mod.escape(m.group(1).strip()) if m else md_path.stem
    body, _ = md_to_html_body(md)
    header = ""
    if body.startswith("<h1>"):
        cut = body.find("</h1>") + len("</h1>")
        header = f'<header class="doc-h">{body[:cut]}</header>\n'
        body = body[cut:].lstrip("\n")
    body = _decorate(body)
    return ("<!doctype html>\n<html lang=\"zh\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<meta name=\"xinci-bench-source-sha256\" content=\"{source_sha256}\">\n"
            f"<title>{title}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n"
            f"<div class=\"wrap\">\n{header}<main>\n{body}\n"
            f"<footer>本页由 build_doc_html.py 生成自 {html_mod.escape(md_path.name)}"
            "（md 是唯一事实来源）；勿手改本文件，由 build_doc.py 重建 md 后重新生成。</footer>\n"
            "</main>\n</div>\n</body>\n</html>\n")


def build(md_path: Path) -> Path:
    out = Path(md_path).with_suffix(".html")
    out.write_text(render(Path(md_path)), encoding="utf-8")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="从决策书 md 生成同名单文件 html")
    ap.add_argument("md", help="决策书 md 路径")
    a = ap.parse_args(argv)
    md_path = Path(a.md)
    if not (md_path.is_file() and md_path.suffix == ".md"):
        print(f"不是可读的 md 文件: {a.md}", file=sys.stderr)
        return 2
    print(f"已生成: {build(md_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`xinci-bench-workflow/xinci-bench-core/scripts/build_doc.py`：

```python
#!/usr/bin/env python3
"""决策书(go 时含建站简报):账本 + 绑定观察 → 文档/<slug>.md,再生成同名 html。

只读绑定的观察;每节第一句是加粗的大白话结论,数字都从结构化字段派生。
"""
import argparse
import sys
from pathlib import Path

import bench_model
import build_doc_html
import data_root
import write_observation as W
from _common import BenchError, load_ledger, require

VERDICT_CN = {"go": "值得做（go）", "rejected": "否决", "parked": "搁置"}
GATE_CN = {"scope": "范围排除", "benchmark": "标杆不成立", "answered": "首屏已答完", "revenue": "收入不足"}
NET_CN = {"adsense": "AdSense", "mediavine_journey": "Mediavine Journey"}
SCEN_CN = {"low": "保守", "base": "基准", "high": "乐观"}
SEO_RULES = ["网址按任务分层,一个页面只服务一个主查询", "每页必须有独有数据或独有功能,不按模板批量复制,避开规模化内容滥用与 doorway 页",
             "页面之间按簇做内链,首页链到每个簇的入口页", "提交 sitemap,按页面类型加结构化数据"]
GEO_RULES = ["每页开头先给答案或工具入口,再展开说明(可被 AI 引用的段落)", "结构化数据与页面可见内容一致",
             "根目录放 llms.txt,列出站点用途与主要页面", "robots.txt 放行主要 AI 爬虫",
             "上线后每月抽查目标查询的 AI 概览是否引用本站"]


def _fmt(n):
    return "—" if n is None else (f"{n:,.0f}" if isinstance(n, (int, float)) else str(n))


def _money(x):
    return f"${x:,.2f}"


def _yn(v):
    return {True: "是", False: "否", None: "未查"}[v]


def _table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows]
    return out


def _observations(root, rec):
    refs = [f["ref"] for f in (rec.get("bindings") or {}).get("files", [])] or rec["evidence_refs"]
    by_kind = {}
    for ref in refs:
        obs = W.read(root, ref)
        by_kind.setdefault(obs["kind"], []).append((ref, obs))
    return refs, by_kind


def _section_benchmarks(rec, by_kind):
    bs = rec["benchmarks"]
    clean = [b for b in bs if b.get("clean") is True]
    lines = ["### 1. 标杆证据", ""]
    lines.append(f"**{len(bs)} 个标杆，其中 {len(clean)} 个干净（初核全过且不靠垃圾外链）。**流量均为 Semrush 估算的美区自然流量。")
    lines.append("")
    lines += _table(["域名", "注册日", "起量月", "当前", "第 12 个月", "AS", "外链驱动", "算法风险", "变现", "干净"],
                    [[b["domain"], b.get("registered_at") or "—", b.get("traffic_start") or "—",
                      _fmt(b.get("us_organic_now")), _fmt(b.get("us_organic_m12")), _fmt(b.get("authority_score")),
                      _yn(b.get("link_driven")), _yn(b.get("algo_risk")),
                      "、".join(b.get("monetization") or []) or "—", _yn(b.get("clean"))] for b in bs])
    for _, o in by_kind.get("benchmark", []):
        r = o["readings"]
        lines += ["", f"- **{r['domain']}**：引荐域名 {_fmt(r['referring_domains'])}；锚文本 {r['anchor_summary']}；"
                      f"垃圾更新前后 {r['update_readings']}；ads.txt {r['ads_txt']}；定价页 {r['pricing'] or '无'}"]
    return lines + [""]


def _section_demand(rec, by_kind):
    cs = rec["clusters"]
    counted = [c for c in cs if c["counted"] and not c["answered"]]
    covered = bench_model.covered_demand(cs)
    lines = ["### 2. 方向需求与对手", ""]
    if not cs:
        return lines + ["**本方向没有做到需求测算这一步。**", ""]
    lines.append(f"**计入需求约 {_fmt(covered)}/月（{len(counted)} 个簇计入，"
                 f"{sum(c['answered'] for c in cs)} 个簇被首屏答完不计）；同方向 {_fmt(rec.get('crowding'))} 个新站在抢（含标杆）。**")
    lines.append("")
    lines += _table(["簇", "种子词", "月量", "测量日", "覆盖", "near me", "首屏答完", "计入"],
                    [[c["id"], c["seed_term"], _fmt(c["volume"]), c["measured_at"],
                      "标杆已做" if c["coverage"] == "benchmark" else "我们额外做",
                      _yn(c["near_me"]), _yn(c["answered"]), _yn(c["counted"])] for c in cs])
    lines.append("")
    for _, o in by_kind.get("demand", []):
        for t in o["readings"]["competitor_traffic"]:
            lines.append(f"- 对手 {t['domain']}：约 {_fmt(t['traffic'])}/月（{t['basis']}）")
        if o["readings"]["new_sites"]:
            lines.append("- 同方向新站：" + "、".join(o["readings"]["new_sites"]))
    return lines + [""]


def _section_serp(by_kind):
    serps = [o["readings"] for _, o in by_kind.get("serp", [])]
    lines = ["### 3. 现场与 GEO", ""]
    if not serps:
        return lines + ["**本方向没有做到现场抽检这一步。**", ""]
    aio = [s for s in serps if s["ai_overview"]["present"]]
    rec_tools = [s for s in aio if s["ai_overview"]["recommends_tools"]]
    pos = [s["benchmark_position"] for s in serps if s["benchmark_position"]]
    lines.append(f"**抽检 {len(serps)} 个查询：{sum(s['answered'] for s in serps)} 个被首屏答完；AI 概览出现 {len(aio)} 次，"
                 f"其中 {len(rec_tools)} 次点名推荐工具站；标杆最好排第 {min(pos) if pos else '—'} 位。**")
    lines.append("")
    lines += _table(["查询", "簇", "首屏答完", "AI 概览", "AI 引用", "推荐工具", "标杆排名"],
                    [[s["query"], s["cluster_id"], _yn(s["answered"]), _yn(s["ai_overview"]["present"]),
                      "、".join(s["ai_overview"]["cited_domains"]) or "—", _yn(s["ai_overview"]["recommends_tools"]),
                      _fmt(s["benchmark_position"])] for s in serps])
    return lines + [""]


def _section_model(model):
    lines = ["### 4. 12 个月流量与收入", ""]
    if not model:
        return lines + ["**本方向没有完成测算。**", ""]
    base = model["scenarios"]["base"]
    lines.append(f"**基准情景第 12 个月约 {_fmt(base['visits_m12'])} 次美区访问、{_money(base['total'])}/月（模型估算），"
                 f"{'过' if model['passes'] else '不过'} ${model['threshold']:.0f} 门槛。**")
    lines.append("")
    lines += _table(["情景", "后来者系数", "第 12 个月访问", "广告网络", "广告", "付费", "合计"],
                    [[SCEN_CN[k], v["coef"], _fmt(v["visits_m12"]), NET_CN[v["network"]], _money(v["ads"]),
                      _money(v["paid"]), _money(v["total"])] for k, v in model["scenarios"].items()])
    lines += ["", f"- 标杆份额率 {model['share_rate']:.4f}；我们覆盖的需求约 {_fmt(model['covered_demand'])}/月；拥挤度 {model['crowding']}",
              f"- 达到 ${model['threshold']:.0f} 需要第 12 个月约 {_fmt(model['visits_needed_for_threshold'])} 次访问，"
              f"相当于标杆流量的 {model['benchmark_fraction_needed']} 倍",
              f"- 假设表版本 {model['assumptions_version']}" + ("；标杆还不满 12 个月，用的是当前值，偏保守" if model["ramping"] else "")]
    if model["unconfirmed_assumptions"]:
        lines.append("- 用到的未确认假设：" + "；".join(model["unconfirmed_assumptions"]))
    return lines + [""]


def _risks(rec, by_kind, model):
    out = [f"标杆 {b['domain']} 靠垃圾外链起量" for b in rec["benchmarks"] if b.get("link_driven")]
    out += [f"标杆 {b['domain']} 在 2026 年垃圾内容更新后掉过一半以上" for b in rec["benchmarks"] if b.get("algo_risk")]
    for _, o in by_kind.get("delivery", [])[-1:]:
        out.append(f"数据授权：{o['readings']['license']}")
    if model and model["unconfirmed_assumptions"]:
        out.append("收入依赖未确认假设：" + "；".join(model["unconfirmed_assumptions"]))
    return out


def _section_risk(rec, by_kind, model):
    dec = rec["decision"]
    lines = ["### 5. 风险与最大未知", "", f"**最大的未知：{dec['biggest_unknown']}。**", ""]
    lines += [f"- {x}" for x in _risks(rec, by_kind, model)] or ["- 未发现额外风险"]
    return lines + [""]


def _lead_curve(rec, by_kind):
    """里程碑用流量最高的干净标杆的曲线;没有对应观察时返回空(全部按线性补)。"""
    clean = sorted((b for b in rec["benchmarks"] if b.get("clean") is True),
                   key=lambda b: -(b.get("us_organic_m12") or b.get("us_organic_now") or 0))
    curves = {o["readings"]["domain"]: o["readings"]["curve"] for _, o in by_kind.get("benchmark", [])}
    return curves.get(clean[0]["domain"], {}) if clean else {}


def _brief(rec, by_kind, model):
    b = by_kind["brief"][-1][1]["readings"]
    dif = by_kind["differentiation"][-1][1]["readings"]
    dl = by_kind["delivery"][-1][1]["readings"]
    curve = _lead_curve(rec, by_kind)
    ms = bench_model.milestones(rec, model, curve)
    base = model["scenarios"]["base"]
    hours = sum(dl["hours"].values())
    total_hours = hours + 12 * dl["monthly_hours"]
    # 线性爬坡:第 k 个月收入 = 第 12 个月收入 × k/12,第 12 个月后持平
    monthly = [base["total"] * min(k, 12) / 12 for k in range(1, 37)]
    cum12 = sum(monthly[:12])
    payback = next((k for k in range(1, 37) if sum(monthly[:k]) >= dl["cash_first_year"]), None)
    lines = ["## 第二部分 建站简报", "", "### 1. 定位", "", f"**{b['positioning']}**", "",
             f"- 站型：{rec['site_type']}", "",
             "### 2. 首版页面清单", "",
             f"**首版 {len(b['pages'])} 个页面，目标查询合计约 {_fmt(sum(p['volume'] for p in b['pages']))}/月。**", ""]
    lines += _table(["路径", "目标查询", "月量", "页面类型", "要交付的内容或功能"],
                    [[p["path"], p["target_query"], _fmt(p["volume"]), p["page_type"], p["deliverable"]] for p in b["pages"]])
    lines += ["", "### 3. 差异点", ""]
    if dif["copy_only"]:
        lines.append("**没有差异点，照搬标杆；后来者系数照常适用。**")
    else:
        lines.append(f"**{len(dif['gaps'])} 条差异点，每条都对照了标杆现状并有现场证据。**")
        lines.append("")
        lines += _table(["标杆现状", "我们做什么", "证据"], [[g["benchmark_now"], g["ours"], g["evidence"]] for g in dif["gaps"]])
    lines += ["", "### 4. 数据", "", f"**数据来自 {len(dl['data_sources'])} 个来源；授权：{dl['license']}。**", ""]
    lines += [f"- {s}" for s in dl["data_sources"]]
    lines += ["", "### 5. 技术与托管", "", "**展示广告须先按托管方条款确认允许商业用途（如 Vercel Hobby 禁止含广告的商业用途）。**", "",
              b["tech_hosting"], "",
              "### 6. SEO 规范", "", "**按下面几条做，重点是每页都有独有内容。**", ""]
    lines += [f"- {x}" for x in SEO_RULES + b["seo_notes"]]
    lines += ["", "### 7. GEO 规范", "", "**让 AI 能直接引用本站的答案，并每月抽查是否被引用。**", ""]
    lines += [f"- {x}" for x in GEO_RULES + b["geo_notes"]]
    lines += ["", "### 8. 变现计划", "",
              f"**基准情景第 12 个月走 {NET_CN[base['network']]}"
              + ("，并计入付费功能。**" if rec["paid"]["applicable"] else "，不计付费功能。**"), "",
              b["monetization_plan"], "",
              "### 9. 投入", "",
              f"**首版约 {_fmt(hours)} 小时、首年现金约 {_money(dl['cash_first_year'])}、每月维护 {_fmt(dl['monthly_hours'])} 小时；"
              f"基准情景 12 个月累计收入约 {_money(cum12)}，折合约 {_money(cum12 / total_hours if total_hours else 0)}/小时（按线性爬坡估算）。**", ""]
    lines += _table(["开发", "数据", "内容", "首年现金", "每月维护", "现金回本"],
                    [[_fmt(dl["hours"]["dev"]), _fmt(dl["hours"]["data"]), _fmt(dl["hours"]["content"]),
                      _money(dl["cash_first_year"]), _fmt(dl["monthly_hours"]),
                      f"第 {payback} 个月" if payback else "36 个月内回不了本"]])
    lines += ["", "### 10. 里程碑与止损", "",
              f"**第 6 个月 Search Console 点击低于 {_fmt(ms['stop_line_m6'])} 就停（基准曲线的 25%）。**", ""]
    lines += _table(["上线后月份", "预期月点击（基准）", "依据"],
                    [[k, _fmt(ms[k]["expected_clicks"]), ms[k]["basis"]] for k in ("3", "6", "12")])
    lines += ["", "### 11. 风险清单", "", "**上线前把下面几条逐一确认。**", ""]
    lines += [f"- {x}" for x in b["risks"] + _risks(rec, by_kind, model)] or ["- 未发现额外风险"]
    return lines + [""]


def render_md(root, rec) -> str:
    dec = rec.get("decision")
    require(dec, f"{rec['slug']} 还没有 decision;用 settle.py 结算")
    refs, by_kind = _observations(root, rec)
    model = rec.get("model")
    verdict = VERDICT_CN[dec["verdict"]] + (f"（{GATE_CN[dec['gate']]}）" if dec.get("gate") else "")
    lines = [f"# {rec['title']}：方向决策书", "",
             f"- 方向 `{rec['slug']}` · 站型 {rec['site_type']} · 结论 {verdict} · 决定于 {dec['decided_at']}", "",
             "## 结论", "", f"一句话：**{verdict}**。{dec['reason']}", ""]
    if model:
        base = model["scenarios"]["base"]
        lines += [f"- 基准情景第 12 个月约 {_fmt(base['visits_m12'])} 次访问、{_money(base['total'])}/月（模型估算）",
                  f"- 达标需要约 {_fmt(model['visits_needed_for_threshold'])} 次访问（标杆的 {model['benchmark_fraction_needed']} 倍）"]
    lines += [f"- 最大的未知：{dec['biggest_unknown']}", "", "## 第一部分 决策", ""]
    lines += _section_benchmarks(rec, by_kind) + _section_demand(rec, by_kind) + _section_serp(by_kind)
    lines += _section_model(model) + _section_risk(rec, by_kind, model)
    if dec["verdict"] == "go":
        lines += _brief(rec, by_kind, model)
    files = (rec.get("bindings") or {}).get("files") or [{"ref": r, "sha256": ""} for r in refs]
    lines += ["## 附：证据清单", ""]
    lines += _table(["观察文件", "SHA-256 前 12 位"], [[f"`{f['ref']}`", f["sha256"][:12] or "未绑定"] for f in files])
    return "\n".join(lines) + "\n"


def build(root, slug):
    rec = load_ledger(root)["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    md = Path(root) / "文档" / f"{slug}.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_md(root, rec), encoding="utf-8")
    return md, build_doc_html.build(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--slug", required=True)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        md, html = build(root, a.slug)
    except (BenchError, KeyError, IndexError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(f"已生成: {md}\n已生成: {html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 58 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_build_doc.py" "xinci-bench-workflow/xinci-bench-core/scripts/build_doc_html.py" "xinci-bench-workflow/xinci-bench-core/scripts/build_doc.py"
git commit -m "xinci-bench:决策书生成——md 为唯一事实来源,html 内嵌源 SHA,go 时附建站简报" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 账本校验与结算

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py`
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/settle.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_settle.py`

**Interfaces:**
- Consumes: `ledger.LEGAL/STATES/docs_consistent/doc_paths/transition/GATES/SCOPE_ITEMS`、`build_doc.build`、`bench_model.compute`、`write_observation.read`
- Produces: `validate_ledger.REQUIRED`（方向记录必填字段）、`check_direction(root, slug, rec)->list[str]`、`check_seeds(root)->list[str]`、`check_all(root)->list[str]`；`settle.settle(root, slug, verdict, gate=None, reason='', biggest_unknown='', by='xinci-bench-assess', scope_hit=None, on=None)->dict`（已转移时只补文档与校验；parked 改判时旧文档归档到 `文档/历史/`）

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_settle.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import settle as S
import validate_ledger as V
import write_observation as W
from _common import BenchError, load_ledger, sha256_file
from helpers import TmpRoot, cluster_record, serp_obs, setup_direction

ON = "2026-10-20"


class SettleTest(unittest.TestCase):
    def test_go_builds_doc_with_brief_and_validates(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            rec = S.settle(root, slug, "go", None, "标杆 9 个月到 2 万", "Journey 实际 RPM", on=ON)
            self.assertEqual(rec["state"], "go")
            self.assertEqual(len(rec["bindings"]["files"]), len(refs))
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn("## 第二部分 建站简报", md)
            self.assertIn("第 6 个月 Search Console 点击低于", md)
            self.assertEqual(V.check_all(root), [])

    def test_revenue_reject_has_no_brief(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root, us_organic_m12=5400)
            with self.assertRaisesRegex(BenchError, "模型结论"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            rec = S.settle(root, slug, "rejected", "revenue", "基准只有 $10.80", "标杆是否还会涨", on=ON)
            self.assertEqual(rec["state"], "rejected")
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertNotIn("建站简报", md)
            self.assertIn("收入不足", md)

    def test_go_refuses_stale_clusters(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root, stale=True)
            with self.assertRaisesRegex(BenchError, "90 天"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            self.assertEqual(load_ledger(root)["directions"][slug]["state"], "found")

    def test_answered_requires_all_clusters_and_serp(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "所有簇"):
                S.settle(root, slug, "rejected", "answered", "r", "u", on=ON)
            ref = W.write(root, serp_obs(slug, answered=True))
            L.update(root, slug, {"clusters": [cluster_record(answered=True)]}, [ref])
            rec = S.settle(root, slug, "rejected", "answered", "AI 概览直接给县名", "定位后是否仍答", on=ON)
            self.assertEqual(rec["state"], "rejected")

    def test_scope_needs_hit(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "命中项"):
                S.settle(root, slug, "rejected", "scope", "r", "u", on=ON)
            rec = S.settle(root, slug, "rejected", "scope", "克隆受版权游戏", "无", scope_hit="infringement", on=ON)
            self.assertEqual(rec["decision"]["scope_hit"], "infringement")

    def test_recovery_rebuilds_docs_without_new_history(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            (root / "文档" / f"{slug}.html").unlink()
            n = len(load_ledger(root)["directions"][slug]["history"])
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            self.assertEqual(len(load_ledger(root)["directions"][slug]["history"]), n)
            self.assertTrue((root / "文档" / f"{slug}.html").is_file())
            with self.assertRaisesRegex(BenchError, "不一致"):
                S.settle(root, slug, "go", "revenue", "r", "u", on=ON)

    def test_parked_then_go_archives_old_doc(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            S.settle(root, slug, "parked", None, "曲线读不出", "Semrush 域名模块恢复后的读数", on=ON)
            S.settle(root, slug, "go", None, "补到曲线后过线", "Journey RPM", on=ON)
            self.assertEqual(len(list((root / "文档" / "历史").glob(f"{slug}-*.md"))), 1)
            self.assertEqual(V.check_all(root), [])


    def test_deleted_observation_gives_clear_refusal(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            (root / refs[3]).unlink()
            with self.assertRaisesRegex(BenchError, "观察不存在"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)


class ValidateTest(unittest.TestCase):
    def test_detects_tampering(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            md = root / "文档" / f"{slug}.md"
            md.write_text(md.read_text(encoding="utf-8") + "手改\n", encoding="utf-8")
            self.assertTrue(any("md/html" in e for e in V.check_all(root)))

    def test_detects_changed_observation(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            p = root / refs[2]
            p.write_text(p.read_text(encoding="utf-8").replace("Organic Research", "Organic  Research"), encoding="utf-8")
            self.assertTrue(any("绑定观察已变动" in e for e in V.check_all(root)))

    def test_detects_bad_recheck(self):
        with TmpRoot() as root:
            import json
            from _common import REJECTS_REL
            (root / REJECTS_REL).write_text(json.dumps({"schema_version": 1, "domains": {
                "a.com": {"failed": ["B2"], "readings": "x", "at": "2026-10-13", "recheck_after": "2027-01-11",
                          "observation": "证据/_scan/x.json"}}}), encoding="utf-8")
            self.assertTrue(any("复查" in e for e in V.check_all(root)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，报 `ImportError: No module named 'settle'`（本任务的模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py`：

```python
#!/usr/bin/env python3
"""账本、种子池、淘汰索引的不变式校验;有错非零退出。单元测试通过不能代替它。"""
import argparse
import sys
from pathlib import Path

import bench_model
import data_root
import ledger as L
import write_observation as W
from _common import REJECTS_REL, SEEDS_REL, BenchError, load_json, load_ledger, sha256_file

REQUIRED = ("slug", "title", "site_type", "state", "benchmarks", "clusters", "crowding", "paid",
            "model", "decision", "evidence_refs", "bindings", "history")


def _history_errors(slug, rec):
    errs, hist = [], rec["history"]
    if not hist or hist[0].get("from") is not None or hist[0].get("to") != "found":
        return [f"{slug}: history 须以 null → found 开始"]
    for h in hist[1:]:
        if h.get("to") not in L.LEGAL.get(h.get("from"), set()):
            errs.append(f"{slug}: history 含非法转移 {h.get('from')} → {h.get('to')}")
    if hist[-1]["to"] != rec["state"]:
        errs.append(f"{slug}: 状态 {rec['state']} 与 history 末条 {hist[-1]['to']} 不一致")
    return errs


def check_direction(root, slug, rec) -> list:
    missing = [k for k in REQUIRED if k not in rec]
    if missing:
        return [f"{slug}: 缺字段 {missing}"]
    errs = []
    if rec["slug"] != slug:
        errs.append(f"{slug}: 记录里的 slug 是 {rec['slug']}")
    if rec["state"] not in L.STATES:
        errs.append(f"{slug}: 未知状态 {rec['state']}")
    errs += _history_errors(slug, rec)
    for ref in rec["evidence_refs"]:
        try:
            W.read(root, ref)
        except BenchError as exc:
            errs.append(f"{slug}: 观察不可用 {ref}: {exc}")
    if rec["state"] == "found":
        return errs
    dec = rec.get("decision") or {}
    if dec.get("verdict") != rec["state"]:
        errs.append(f"{slug}: decision.verdict 与状态不一致")
    if not L.docs_consistent(root, slug):
        errs.append(f"{slug}: 决策书 md/html 缺失,或 html 内嵌的源 SHA 与 md 不符")
    for f in (rec.get("bindings") or {}).get("files", []):
        p = Path(root) / f["ref"]
        if not p.is_file() or sha256_file(p) != f["sha256"]:
            errs.append(f"{slug}: 绑定观察已变动或丢失 {f['ref']}")
    if not rec.get("bindings"):
        errs.append(f"{slug}: 终态或搁置须有绑定")
    if rec["state"] == "go" or dec.get("gate") == "revenue":
        try:
            model = bench_model.compute(rec)
            if model != rec.get("model"):
                errs.append(f"{slug}: 模型重算与账本不一致")
            elif model["passes"] is not (rec["state"] == "go"):
                errs.append(f"{slug}: 模型结论与状态不符")
        except BenchError as exc:
            errs.append(f"{slug}: 模型无法重算: {exc}")
    return errs


def check_seeds(root) -> list:
    errs = []
    pool = load_json(Path(root) / SEEDS_REL)
    for d, s in pool.get("seeds", {}).items():
        if s.get("source") not in ("legacy", "sibling", "serp", "geo", "community"):
            errs.append(f"种子 {d}: 来源无效")
        if s.get("role") not in ("benchmark", "sibling") or s.get("status") not in ("pending", "checked"):
            errs.append(f"种子 {d}: role 或 status 无效")
    rejects = load_json(Path(root) / REJECTS_REL)
    for d, e in rejects.get("domains", {}).items():
        if (e.get("recheck_after") is not None) != (e.get("failed") == ["B3"]):
            errs.append(f"淘汰 {d}: 只有单独 B3 不过才设复查日期")
        if not str(e.get("observation", "")).startswith("证据/_scan/"):
            errs.append(f"淘汰 {d}: 缺 scan 观察引用")
    return errs


def check_all(root) -> list:
    ledger = load_ledger(root)
    errs = [] if ledger.get("schema_version") == 1 else ["账本 schema_version 须为 1"]
    for slug, rec in ledger.get("directions", {}).items():
        errs += check_direction(root, slug, rec)
    return errs + check_seeds(root)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    errs = check_all(root)
    for e in errs:
        print("错误: " + e)
    print(f"校验完成:{len(errs)} 个错误")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
```

`xinci-bench-workflow/xinci-bench-core/scripts/settle.py`：

```python
#!/usr/bin/env python3
"""结算一个方向:重算模型 → 固定绑定 → 生成决策书 → 转移状态 → 校验。

中断后用同一条命令重跑即可恢复:已转移的只补文档与校验,不重复写 history。
"""
import argparse
import shutil
import sys
from pathlib import Path

import bench_model
import build_doc
import data_root
import ledger as L
import validate_ledger
import write_observation as W
from _common import BenchError, load_ledger, now, require, save_ledger, sha256_file


def _archive_docs(root, slug):
    md, html = L.doc_paths(root, slug)
    if not md.is_file():
        return
    tag = sha256_file(md)[:12]
    dest = Path(root) / "文档" / "历史"
    dest.mkdir(parents=True, exist_ok=True)
    for p in (md, html):
        if p.is_file():
            shutil.move(str(p), str(dest / f"{slug}-{tag}{p.suffix}"))


def settle(root, slug, verdict, gate=None, reason="", biggest_unknown="", by="xinci-bench-assess",
           scope_hit=None, on=None) -> dict:
    require(verdict in ("go", "rejected", "parked"), "verdict 须为 go/rejected/parked")
    require(isinstance(biggest_unknown, str) and biggest_unknown.strip(), "biggest_unknown 须写最可能让结论翻转的一项")
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    if rec["state"] == verdict:            # 恢复:已转移,只补文档与校验
        dec = rec.get("decision") or {}
        require(dec.get("verdict") == verdict and dec.get("gate") == gate, "已结算的结论与本次参数不一致,不能覆盖")
        if not L.docs_consistent(root, slug):
            build_doc.build(root, slug)
    else:
        require(rec["state"] in L.LEGAL and verdict in L.LEGAL[rec["state"]], f"非法结算 {rec['state']} → {verdict}")
        for ref in rec["evidence_refs"]:      # 先确认引用的观察都在且合规,再算绑定
            W.read(root, ref)
        try:
            rec["model"] = bench_model.compute(rec)
        except BenchError:
            require(verdict != "go" and gate != "revenue", "go 与收入否决必须能完成测算")
            rec["model"] = None
        rec["decision"] = {"verdict": verdict, "gate": gate, "reason": reason.strip(),
                           "biggest_unknown": biggest_unknown.strip(), "scope_hit": scope_hit,
                           "decided_at": now()}
        rec["bindings"] = {"bound_at": now(), "files": [
            {"ref": ref, "sha256": sha256_file(Path(root) / ref)} for ref in rec["evidence_refs"]]}
        save_ledger(root, ledger)
        if rec["state"] == "parked":
            _archive_docs(root, slug)
        build_doc.build(root, slug)
        L.transition(root, slug, verdict, gate, reason, by, on)
    rec = load_ledger(root)["directions"][slug]
    errs = validate_ledger.check_direction(root, slug, rec)
    require(not errs, "结算后校验失败: " + "; ".join(errs))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--verdict", required=True, choices=("go", "rejected", "parked"))
    ap.add_argument("--gate", choices=L.GATES)
    ap.add_argument("--scope-hit", choices=L.SCOPE_ITEMS)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--biggest-unknown", required=True)
    ap.add_argument("--by", default="xinci-bench-assess")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        rec = settle(root, a.slug, a.verdict, a.gate, a.reason, a.biggest_unknown, a.by, a.scope_hit)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    md, html = L.doc_paths(root, a.slug)
    print(f"{a.slug}: {rec['state']}\n决策书: {md}\n        {html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 69 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_settle.py" "xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py" "xinci-bench-workflow/xinci-bench-core/scripts/settle.py"
git commit -m "xinci-bench:账本校验与结算——绑定 SHA、生成决策书、转移、可恢复" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 运行清单与看板

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/run_log.py`
- Create: `xinci-bench-workflow/xinci-bench-core/scripts/report_status.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_run_log.py`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py`

**Interfaces:**
- Consumes: `seeds.SOURCES/take/stats`、`ledger.STATES/rank/doc_paths`、`_common`
- Produces: `run_log.SKILLS=('xinci-bench-scan','xinci-bench-assess')`、`ROTATION=('sibling','serp','geo','community')`、`FOUND_TARGET=3`、`records(root)`、`record(root, *, skill, progress, sources_opened=(), directions_touched=(), semrush_calls=0, notes=())->Path`、`plan(root, run_id=None)->dict`（found_count、action、scan_outcome、resume、conflict、active_run_ids、next_source、source_reason、latest_log、semrush_calls_total）、`finish(root, *, run_id, outcome='completed', ...)->Path`；`report_status.status(root, on=None)->dict`

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_run_log.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_log as R
import seeds
from _common import BenchError
from helpers import TmpRoot, setup_direction


def start(root, run_id="run-a", rnd=1, max_rounds=2, source="legacy"):
    return R.record(root, skill="xinci-bench-scan", progress={
        "run_id": run_id, "round": rnd, "max_rounds": max_rounds, "source_kind": source,
        "seed_value": "种子池 legacy 前 16 个", "outcome": "started", "next_step": "scan"})


def start_assess(root, run_id="run-a", rnd=1, max_rounds=2, source="legacy"):
    return R.record(root, skill="xinci-bench-assess", progress={
        "run_id": run_id, "round": rnd, "max_rounds": max_rounds, "source_kind": source,
        "seed_value": "rank 前 2", "outcome": "started", "next_step": "assess"})


class RunLogTest(unittest.TestCase):
    def test_full_round_then_done(self):
        with TmpRoot() as root:
            start(root)
            R.finish(root, run_id="run-a", semrush_calls=5)
            self.assertEqual(R.plan(root)["action"], "assess")
            start_assess(root)
            R.finish(root, run_id="run-a", semrush_calls=10)
            p = R.plan(root)
            self.assertEqual((p["action"], p["resume"]["round"]), ("scan", 2))
            start(root, rnd=2)
            R.finish(root, run_id="run-a", outcome="skipped")
            start_assess(root, rnd=2)
            R.finish(root, run_id="run-a")
            self.assertEqual(R.plan(root, "run-a")["action"], "done")
            p = R.plan(root)                      # 没有未完运行:可以开新运行
            self.assertEqual((p["action"], p["resume"]), ("scan", None))
            self.assertEqual(p["semrush_calls_total"], 15)

    def test_cannot_finish_twice_or_skip_assess(self):
        with TmpRoot() as root:
            start(root)
            R.finish(root, run_id="run-a")
            with self.assertRaisesRegex(BenchError, "finish"):
                R.finish(root, run_id="run-a")
            start_assess(root)
            with self.assertRaisesRegex(BenchError, "跳过"):
                R.finish(root, run_id="run-a", outcome="skipped")

    def test_new_run_blocked_while_another_active(self):
        with TmpRoot() as root:
            start(root)
            with self.assertRaisesRegex(BenchError, "未完成运行"):
                start(root, run_id="run-b")

    def test_new_run_must_start_with_scan_round_1(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "第 1 轮 scan"):
                start_assess(root)

    def test_blocked_keeps_position_and_source(self):
        with TmpRoot() as root:
            start(root, source="serp")
            R.finish(root, run_id="run-a", outcome="blocked", notes=["Semrush 额度用完"])
            p = R.plan(root)
            self.assertEqual((p["action"], p["next_source"]), ("scan", "serp"))
            R.finish(root, run_id="run-a")
            self.assertEqual(R.plan(root)["action"], "assess")

    def test_source_rotation(self):
        with TmpRoot() as root:
            self.assertEqual(R.plan(root)["next_source"], "sibling")
            seeds.add(root, "a.com", "legacy", "旧证据")
            self.assertEqual(R.plan(root)["next_source"], "legacy")
            seeds.mark_checked(root, ["a.com"])
            start(root, source="serp")
            R.finish(root, run_id="run-a")
            self.assertEqual(R.plan(root)["next_source"], "geo")

    def test_skipped_when_three_found(self):
        with TmpRoot() as root:
            for slug in ("d0", "d1"):
                setup_direction(root, slug=slug)
            self.assertIsNone(R.plan(root)["scan_outcome"])
            setup_direction(root, slug="d2")
            self.assertEqual(R.plan(root)["scan_outcome"], "skipped")

    def test_budget_cannot_change(self):
        with TmpRoot() as root:
            start(root)
            R.finish(root, run_id="run-a")
            with self.assertRaisesRegex(BenchError, "预算"):
                start_assess(root, max_rounds=5)


if __name__ == "__main__":
    unittest.main()
```

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import report_status as RS
import settle
from helpers import TmpRoot, setup_direction


class ReportStatusTest(unittest.TestCase):
    def test_counts_go_and_parked(self):
        with TmpRoot() as root:
            setup_direction(root, slug="good")
            settle.settle(root, "good", "go", None, "r", "u", on="2026-10-20")
            setup_direction(root, slug="later")
            settle.settle(root, "later", "parked", None, "曲线读不出", "u", on="2026-10-20")
            st = RS.status(root, on="2027-02-01")
            self.assertEqual(st["counts"], {"found": 0, "go": 1, "rejected": 0, "parked": 1})
            self.assertEqual(st["go"][0]["base_total"], 160.0)
            self.assertTrue(st["parked"][0]["overdue"])

    def test_empty_workspace(self):
        with TmpRoot() as root:
            st = RS.status(root)
            self.assertEqual(st["semrush_calls_total"], 0)
            self.assertEqual(st["found_ranked"], [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，报 `ImportError: No module named 'run_log'`（本任务的模块还不存在）

- [ ] **Step 3: 实现**

`xinci-bench-workflow/xinci-bench-core/scripts/run_log.py`：

```python
#!/usr/bin/env python3
"""运行清单:阶段进度只追加,保存预算、恢复位置与来源;--plan 推导下一步,--finish 结束阶段。"""
import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import data_root
import seeds
from _common import BenchError, atomic_save, load_json, load_ledger, require, today

SKILLS = ("xinci-bench-scan", "xinci-bench-assess")
STAGE = {"xinci-bench-scan": "scan", "xinci-bench-assess": "assess"}
ROTATION = ("sibling", "serp", "geo", "community")
OUTCOMES = ("started", "completed", "blocked", "skipped")
FOUND_TARGET = 3


def records(root) -> list:
    rows = []
    for path in (Path(root) / "运行").glob("*.json"):
        row = load_json(path)
        row["_path"] = str(path)
        rows.append(row)
    return sorted(rows, key=lambda r: (r["recorded_at"], r["_path"]))


def latest_runs(rows) -> dict:
    latest = {}
    for row in rows:
        latest[row["progress"]["run_id"]] = row
    return latest


def next_position(row):
    """该运行下一阶段的位置;运行已结束返回 None。"""
    p = row["progress"]
    if p["next_step"] == "done":
        return None
    bump = STAGE[row["skill"]] == "assess" and p["outcome"] == "completed"
    return {"stage": p["next_step"], "round": p["round"] + int(bump)}


def _expected_next(stage, outcome, rnd, max_rounds):
    if outcome in ("started", "blocked"):
        return stage
    if stage == "scan":
        return "assess"
    return "done" if rnd == max_rounds else "scan"


def record(root, *, skill, progress, sources_opened=(), directions_touched=(), semrush_calls=0, notes=()) -> Path:
    require(skill in SKILLS, f"skill 须为 {SKILLS}")
    keys = ("run_id", "round", "max_rounds", "source_kind", "seed_value", "outcome", "next_step")
    require(all(k in progress for k in keys), f"progress 须含 {keys}")
    p = progress
    require(re.fullmatch(r"[a-zA-Z0-9-]+", str(p["run_id"])), "run_id 只能用字母数字连字符")
    require(type(p["round"]) is int and type(p["max_rounds"]) is int and 1 <= p["round"] <= p["max_rounds"],
            "轮次或预算无效")
    require(p["source_kind"] in seeds.SOURCES, f"source_kind 须为 {seeds.SOURCES}")
    require(isinstance(p["seed_value"], str) and p["seed_value"].strip(), "seed_value 须写本阶段从哪取种子")
    require(p["outcome"] in OUTCOMES, f"outcome 须为 {OUTCOMES}")
    require(isinstance(semrush_calls, int) and semrush_calls >= 0, "semrush_calls 须为非负整数")
    stage = STAGE[skill]
    require(not (p["outcome"] == "skipped" and stage != "scan"), "只能跳过发现阶段")
    require(p["next_step"] == _expected_next(stage, p["outcome"], p["round"], p["max_rounds"]),
            "next_step 与阶段、结果、轮次不一致")
    history = records(root)
    same = [r for r in history if r["progress"]["run_id"] == p["run_id"]]
    if same:
        cursor = next_position(same[-1])
        require(cursor is not None, "该运行已结束,不能追加")
        require(cursor == {"stage": stage, "round": p["round"]}, f"恢复位置应为 {cursor}")
        require(all(r["progress"]["max_rounds"] == p["max_rounds"] for r in same), "同一 run_id 的预算不能改")
        last = same[-1]["progress"]
        if last["outcome"] in ("started", "blocked"):
            require(p["outcome"] != "started", "该阶段已开始,结束请用 --finish")
    else:
        require(not any(next_position(r) for r in latest_runs(history).values()),
                "存在未完成运行,须先恢复;不能创建新 run_id")
        require(p["round"] == 1 and stage == "scan" and p["outcome"] == "started", "新运行须从第 1 轮 scan started 开始")
    path = Path(root) / "运行" / f"{today()}-{skill}-{p['run_id']}-r{p['round']}-{uuid.uuid4().hex[:8]}.json"
    # 微秒精度:同一秒内写多条时排序仍确定,恢复位置才不会读错
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    atomic_save(path, {"skill": skill, "recorded_at": recorded_at, "progress": dict(p),
                       "sources_opened": list(dict.fromkeys(sources_opened)),
                       "directions_touched": sorted(set(directions_touched)),
                       "semrush_calls": semrush_calls, "notes": list(notes)})
    return path


def _next_source(root, rows):
    if seeds.take(root, "legacy", 1):
        return "legacy", "旧数据导入的标杆种子还有待初核的,先用完"
    done = [r for r in rows if STAGE[r["skill"]] == "scan" and r["progress"]["outcome"] == "completed"
            and r["progress"]["source_kind"] in ROTATION]
    if not done:
        return ROTATION[0], "legacy 已用完,按固定轮换从 sibling 开始"
    last = done[-1]["progress"]["source_kind"]
    nxt = ROTATION[(ROTATION.index(last) + 1) % len(ROTATION)]
    return nxt, f"上次完成的发现来源是 {last},按固定轮换下一个是 {nxt}"


def plan(root, run_id=None) -> dict:
    rows = records(root)
    latest = latest_runs(rows)
    active = {k: r for k, r in latest.items() if next_position(r)}
    require(run_id is None or run_id in latest, "指定的 run_id 不存在")
    conflict = run_id is None and len(active) > 1
    selected = latest.get(run_id) if run_id else (next(iter(active.values())) if len(active) == 1 else None)
    found = sum(r["state"] == "found" for r in load_ledger(root)["directions"].values())
    source, reason = _next_source(root, rows)
    resume, action = None, "scan"
    if selected:
        cursor = next_position(selected)
        if cursor:
            resume = dict(selected["progress"], round=cursor["round"], next_step=cursor["stage"])
            action = cursor["stage"]
            if STAGE[selected["skill"]] == cursor["stage"]:
                source, reason = selected["progress"]["source_kind"], "恢复已开始的阶段,保持原来源与 seed_value"
        else:
            action = "done"
    return {"found_count": found, "action": None if conflict else action,
            "scan_outcome": "skipped" if action == "scan" and found >= FOUND_TARGET and not conflict else None,
            "resume": resume, "conflict": conflict, "active_run_ids": sorted(active),
            "next_source": source, "source_reason": reason,
            "latest_log": selected["_path"] if selected else None,
            "semrush_calls_total": sum(r["semrush_calls"] for r in rows)}


def finish(root, *, run_id, outcome="completed", sources_opened=(), directions_touched=(), semrush_calls=0,
           notes=()) -> Path:
    row = latest_runs(records(root)).get(run_id)
    require(row and row["progress"]["outcome"] in ("started", "blocked"),
            "finish 只针对 started/blocked 阶段;阶段已结束时不要重记调用数")
    require(outcome in ("completed", "blocked", "skipped"), "finish 的 outcome 须为 completed/blocked/skipped")
    p = dict(row["progress"], outcome=outcome)
    p["next_step"] = _expected_next(STAGE[row["skill"]], outcome, p["round"], p["max_rounds"])
    return record(root, skill=row["skill"], progress=p, sources_opened=sources_opened,
                  directions_touched=directions_touched, semrush_calls=semrush_calls, notes=notes)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--finish", action="store_true")
    ap.add_argument("--run-id")
    ap.add_argument("--skill", choices=SKILLS)
    ap.add_argument("--round", type=int)
    ap.add_argument("--max-rounds", type=int)
    ap.add_argument("--source-kind", choices=seeds.SOURCES)
    ap.add_argument("--seed-value")
    ap.add_argument("--outcome", choices=OUTCOMES)
    ap.add_argument("--next-step", choices=("scan", "assess", "done"))
    ap.add_argument("--source-opened", action="append", default=[])
    ap.add_argument("--direction-touched", action="append", default=[])
    ap.add_argument("--semrush-calls", type=int, default=0)
    ap.add_argument("--note", action="append", default=[])
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.plan:
            print(json.dumps(plan(root, a.run_id), ensure_ascii=False, indent=2))
            return 0
        if a.finish:
            out = finish(root, run_id=a.run_id, outcome=a.outcome or "completed", sources_opened=a.source_opened,
                         directions_touched=a.direction_touched, semrush_calls=a.semrush_calls, notes=a.note)
        else:
            progress = {"run_id": a.run_id, "round": a.round, "max_rounds": a.max_rounds,
                        "source_kind": a.source_kind, "seed_value": a.seed_value,
                        "outcome": a.outcome, "next_step": a.next_step}
            require(all(v is not None for v in progress.values()) and a.skill,
                    "写清单须提供 --skill/--run-id/--round/--max-rounds/--source-kind/--seed-value/--outcome/--next-step")
            out = record(root, skill=a.skill, progress=progress, sources_opened=a.source_opened,
                         directions_touched=a.direction_touched, semrush_calls=a.semrush_calls, notes=a.note)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(f"已写 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`xinci-bench-workflow/xinci-bench-core/scripts/report_status.py`：

```python
#!/usr/bin/env python3
"""只读看板:各状态数、found 排序、搁置天数、go 的文档、种子池余量、待复查淘汰、累计 Semrush 调用。"""
import argparse
import json
import sys
from datetime import date

import data_root
import ledger as L
import run_log
import seeds
from _common import BenchError, load_ledger, today

PARKED_WARN_DAYS = 90


def status(root, on=None) -> dict:
    on = on or today()
    dirs = load_ledger(root)["directions"]
    counts = {s: sum(r["state"] == s for r in dirs.values()) for s in L.STATES}
    parked = []
    for slug, r in dirs.items():
        if r["state"] == "parked":
            days = (date.fromisoformat(on) - date.fromisoformat(r["history"][-1]["at"][:10])).days
            parked.append({"slug": slug, "days": days, "overdue": days > PARKED_WARN_DAYS,
                           "reason": r["history"][-1]["reason"]})
    go = [{"slug": s, "title": r["title"], "base_total": r["model"]["scenarios"]["base"]["total"],
           "doc": str(L.doc_paths(root, s)[0])} for s, r in dirs.items() if r["state"] == "go"]
    rejected = {}
    for r in dirs.values():
        if r["state"] == "rejected":
            g = r["decision"]["gate"]
            rejected[g] = rejected.get(g, 0) + 1
    return {"data_root": str(root), "counts": counts, "found_ranked": L.rank(root, on),
            "parked": parked, "go": go, "rejected_by_gate": rejected, "seeds": seeds.stats(root, on),
            "semrush_calls_total": sum(r["semrush_calls"] for r in run_log.records(root))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        st = status(root)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    c = st["counts"]
    print(f"数据区:{st['data_root']}")
    print(f"方向:found {c['found']} · go {c['go']} · rejected {c['rejected']} · parked {c['parked']}")
    for row in st["found_ranked"]:
        print(f"  待深核 {row['slug']}:起量速度 {row['speed']}/月,AS {row['authority_score']}")
    for g in st["go"]:
        print(f"  go {g['slug']}:基准 ${g['base_total']}/月 → {g['doc']}")
    for p in st["parked"]:
        print(f"  搁置 {p['slug']}:{p['days']} 天" + (" (超过 90 天,请复核)" if p["overdue"] else ""))
    if st["rejected_by_gate"]:
        print("  否决按门:" + "、".join(f"{k} {v}" for k, v in st["rejected_by_gate"].items()))
    s = st["seeds"]
    print(f"种子池待初核:{s['pending'] or '无'};已初核 {s['checked']};淘汰 {s['rejected']}(到期可复查 {s['recheck_due']})")
    print(f"累计 Semrush 调用:{st['semrush_calls_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 79 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_run_log.py" "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_report_status.py" "xinci-bench-workflow/xinci-bench-core/scripts/run_log.py" "xinci-bench-workflow/xinci-bench-core/scripts/report_status.py"
git commit -m "xinci-bench:运行清单与看板——恢复位置、固定轮换来源、found≥3 跳过发现" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 10: 选站契约、数据采集规程、命令与观察

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-core/选站契约.md`
- Create: `xinci-bench-workflow/xinci-bench-core/数据采集.md`
- Create: `xinci-bench-workflow/xinci-bench-core/命令与观察.md`
- Test: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py`

**Interfaces:**
- Consumes: `bench_model.ASSUMPTIONS`、`write_observation.LIMITS/KINDS/REQUIRED`、`ledger.GATES/SCOPE_ITEMS/BENCH_KEYS/CLUSTER_KEYS/SITE_TYPES`、`validate_ledger.REQUIRED`、`seed_import.PLATFORMS`、三份 schema
- Produces: 三份文档（判据唯一来源、采集纪律、命令手册）；`test_documentation.py` 的 `ContractTest`、`SchemaTest`（Task 11 再加 `SkillTest`）

- [ ] **Step 1: 写失败的测试**

`xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py`：

```python
# 文档与代码的数值、字段、代码表必须一致:改一边忘了另一边时这里会失败。
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bench_model as M
import ledger as L
import seed_import as I
import validate_ledger as V
import write_observation as W

CORE = Path(__file__).resolve().parents[2]
WORKFLOW = CORE.parent


def text(name):
    return (CORE / name).read_text(encoding="utf-8")


class ContractTest(unittest.TestCase):
    def test_contract_numbers_match_code(self):
        c = text("选站契约.md")
        a = M.ASSUMPTIONS
        self.assertIn(f"**{a['version']}**", c)
        self.assertIn(f"{W.LIMITS['max_age_months']} 个月", c)
        self.assertIn(f"≤ {W.LIMITS['max_authority_score']}", c)
        self.assertIn(f"≥ {W.LIMITS['min_us_organic']:,}/月", c)
        self.assertIn(f"{a['coef']['low']} / {a['coef']['base']} / {a['coef']['high']}", c)
        self.assertIn(f"{a['crowded_base_coef']}（crowding ≥ {a['crowded_at']}）", c)
        self.assertIn(f"{a['share_cap']:.0%}", c)
        self.assertIn(f"{a['journey_min_visits']:,}", c)
        self.assertIn(f"${a['rpm']['adsense']:.0f}", c)
        self.assertIn(f"${a['rpm']['mediavine_journey']:.0f}", c)
        p = a["paid_conversion"]
        self.assertIn(f"{p['low']:.1%} / {p['base']:.1%} / {p['high']:.1%}", c)
        self.assertIn(f"${a['threshold']:.0f}", c)

    def test_contract_lists_every_gate_and_scope_code(self):
        c = text("选站契约.md")
        for code in L.GATES + L.SCOPE_ITEMS:
            self.assertIn(f"`{code}`", c)

    def test_platform_blacklist_documented(self):
        doc = text("数据采集.md")
        for d in I.PLATFORMS:
            self.assertIn(d, doc)


class SchemaTest(unittest.TestCase):
    def test_observation_schema_matches_validator(self):
        s = json.loads(text("数据结构/observation.schema.json"))
        self.assertEqual(tuple(s["properties"]["kind"]["enum"]), W.KINDS)
        self.assertEqual({k: tuple(v) for k, v in s["readings_required"].items()}, W.REQUIRED)

    def test_direction_schema_matches_ledger(self):
        s = json.loads(text("数据结构/direction.schema.json"))
        self.assertEqual(tuple(s["required"]), V.REQUIRED)
        self.assertEqual(tuple(s["properties"]["benchmarks"]["items"]["required"]), L.BENCH_KEYS)
        self.assertEqual(tuple(s["properties"]["clusters"]["items"]["required"]), L.CLUSTER_KEYS)
        self.assertEqual(tuple(s["properties"]["site_type"]["enum"]), L.SITE_TYPES)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，`FileNotFoundError: ... 选站契约.md`（文档还不存在）

- [ ] **Step 3: 写三份文档**

`xinci-bench-workflow/xinci-bench-core/选站契约.md`：

````markdown
# 选站契约（xinci-bench）

本文件是判据的唯一来源；Skill 只串流程。设计依据见 `docs/superpowers/specs/2026-10-13-xinci-bench-workflow-design.md`。

## 目录

- [0. 定位与边界](#0-定位与边界)
- [1. 范围与排除](#1-范围与排除)
- [2. 状态机](#2-状态机)
- [3. 找标杆](#3-找标杆)
  - [3.1 来源与顺序](#31-来源与顺序)
  - [3.2 初核五条](#32-初核五条)
  - [3.3 登记与淘汰](#33-登记与淘汰)
- [4. 深核六步](#4-深核六步)
- [5. 判定](#5-判定)
- [6. 标杆份额法与假设表](#6-标杆份额法与假设表)
  - [6.1 流量](#61-流量)
  - [6.2 收入](#62-收入)
  - [6.3 假设表](#63-假设表)
- [7. 证据与结算](#7-证据与结算)
- [8. 决策书与建站简报](#8-决策书与建站简报)
- [9. 停机与错误](#9-停机与错误)

## 0. 定位与边界

从近 24 个月起量的低权重小站倒推建站方向，判断"上线后 12 个月内单站做到 $100/月"的把握；产出决策书，go 时附建站简报。

用户 2026-10-13 定的口径（改之前先问用户）：

- 达标 = 单站、上线后 12 个月内 $100/月。
- 站型不限：tool、content、game、mixed。
- 变现只算展示广告、付费功能/订阅；不算联盟佣金和捐赠。
- GEO 用作筛选信号和建站规范；收入只按 Google 自然点击算。
- 投入不设上限，决策书写清工时、现金、维护量，由用户拍板。
- 工作流到"决策书 + 建站简报"为止：不注册域名、不建站、不写内容、不上线。
- 连续运行出 go 不停，跑满预算。

门槛和假设表只由用户改；改时升 §6.3 的版本号并写变更依据。零产出如实报零，不凑数。

## 1. 范围与排除

英文站。收入只按标杆的美区自然流量算；其他英语国家的流量在决策书里列出，只作加分。SERP 现场一律用 `gl=us&hl=en&pws=0`。

排除项，scan 初判（B5），assess 复核；命中任一即排除（结算 gate=`scope`，`--scope-hit` 取括号里的代码）：

| 排除 | 判法 |
| --- | --- |
| YMYL（`ymyl`） | 任务影响健康、金融、法律权利或人身安全。按用户拿结果去做什么判，不按话题词判：结果用于选型、计算或决定危险操作（线径、断路器、刹车、气囊、燃油系统、剂量、贷款等）→ 命中，不能因"只是查表/计算"豁免；结果只是定位或识别厂商原厂规格、安全动作是按原规格原样替换（如保险丝位置与原厂额定、皮带走向）→ 不命中，交付须附原厂安全提示；高压系统维修（混动/电动车动力电池、高压保险丝）仍按危险操作命中 |
| 纯品牌/导航（`brand_nav`） | 用户只想去某站，如 login、customer service、单独品牌名 |
| 新闻热点（`news`） | 具体事件导致、几周内会消失的短暂尖峰 |
| 成人/赌博（`adult_gambling`） | 成人内容、博彩、彩票预测等 |
| 侵权（`infringement`） | 克隆有版权或商标的游戏、搬运受版权保护的内容或数据库、绕过付费墙；数据授权禁止再发布的同样命中 |

不能靠换个说法、改写成工具来规避排除。

## 2. 状态机

```
found → go | rejected | parked
parked → go | rejected
```

- `go`：§5 四条全满足，决策书与建站简报的 md/html 都已生成。
- `rejected`：带 gate，取值 `scope`、`benchmark`、`answered`、`revenue`。
- `parked`：关键证据拿不到。拿不到证据不等于通过；超过 90 天看板提醒，不自动转移。

账本只由 `ledger.py` 写；状态只由 `settle.py` 转移。初核不过的域名不登记，只进淘汰索引。进入 go、rejected、parked 都必须有决策书。

## 3. 找标杆

### 3.1 来源与顺序

| 来源 | 做法 |
| --- | --- |
| `legacy` | 旧数据导入的种子池（`seed_import.py`），按登记顺序用 |
| `sibling` | 对已核实的标杆，或种子池里 `role=sibling` 的小站，查 Semrush 自然搜索"竞争对手"列表找同类小站 |
| `serp` | 拿种子查询读 Google 首页，挑低 AS 第三方站 |
| `geo` | AI 概览里点名推荐或引用的小站 |
| `community` | r/juststart、r/SideProject、Indie Hackers 等自曝流量的复盘帖；自报数字只当线索，必须回 Semrush 核实 |

顺序由 `run_log.py --plan` 给出：`legacy` 还有待初核的就先用 `legacy`；用完后按 `sibling → serp → geo → community` 固定轮换。用户指定优先。新发现的域名用 `seeds.py add` 登记，再按批初核。

### 3.2 初核五条

五条全过才登记。数值由 `write_observation.py` 强制：标"通过"但数字不达标的观察会被拒收。

| 编号 | 判据 | 数值 |
| --- | --- | --- |
| B1 年轻 | RDAP 注册日在 24 个月内；或 Semrush 曲线显示 24 个月前自然流量接近 0（标 `aged_domain=true`，basis 写依据） | 24 个月 |
| B2 低权重 | Semrush 域级 Authority Score | ≤ 30 |
| B3 有量 | 美区自然流量（Semrush 估算），**去掉标杆自身品牌词和 near me 类定位词之后**，填在 `us_organic_now` | ≥ 5,000/月 |
| B4 不是假象 | 流量分散在多个词、多个页面，不是"单个抓取点把全国量算给一个页面"的失真；basis 写依据 | 定性 |
| B5 范围 | §1 排除项全部未命中 | — |

批量分析的"每月访问量"是全球全渠道，只能粗筛；B3 必须用 Domain Overview 或 Backlink Analytics 概览给出的美区自然流量。前面一条已不过时，后面几条可以填 `pass: null` 省额度，basis 写"前项已不过，未查"。

### 3.3 登记与淘汰

- 全过：`ledger.py register` 登记方向（found），引用本批 scan 观察。同一标杆域名已用于别的方向时，须 `--confirm-distinct` 写清两个方向的差别。
- 有不过的：`seeds.py reject` 写淘汰索引。只有单独 B3 不过的设 90 天后复查（新站会长）；`seeds.py requeue` 把到期的放回种子池。

## 4. 深核六步

assess 对每个方向按顺序走，每步一份观察（kind 见括号），用 `ledger.py update --ref` 引用，并把结构化结果补进方向记录。

1. **起量手段**（`benchmark`，每个标杆一份）：引荐域名与锚文本，靠 PBN/垃圾锚文本起量的标 `link_driven=true`，不能单独当证据；看 2026 年 3、6、8 月垃圾内容更新前后，任一次后掉 50% 以上标 `algo_risk=true`；读 `ads.txt` 与定价页；记起量月、当前流量、起量后第 12 个月流量（不满 12 个月填 null）、起量后第 3/6/12 个月的曲线读数。干净标杆 = B1–B5 全过且 `link_driven=false`。
2. **方向需求**（`demand`）：从标杆排名词提炼主题簇，用 Keyword Magic 取量，种子只用名词性主题词，量地方查询不排除导航意图；旧词库（`lexicon.py`）里有的可直接用，但判 go 时所有计入需求的簇测量都须在 90 天内。记每簇代表种子、量、测量日、`coverage`（benchmark 标杆已做 / ours 我们额外做）、`near_me`；对手流量一律按网址筛；记 `crowding`（同方向近 24 个月新站数，含标杆）。
3. **现场与 GEO**（`serp`，每个查询一份）：每个方向 3–5 个代表查询，每个计入需求的簇至少 1 个。AI 概览、精选摘要或原生组件已完成任务 → 该簇 `answered=true`，不计入需求（单个查询只有一个答案的，AI 概览会直接答掉）。记 AI 概览引用了谁、是否点名推荐工具站（GEO 加分，只写进决策书，不进收入）、标杆排第几。
4. **流量与收入**：`bench_model.py --direction <slug>` 按 §6 计算，结果由 `settle.py` 写入。
5. **差异点**（`differentiation`）：每条写"标杆现状 → 我们做什么 → 证据观察"。不接受"体验更好""SEO 做好"这类无对照证据的说法；允许照搬（`copy_only=true`），但要明说。
6. **交付依据**（`delivery`）：数据源、获取方式、授权要点、工时（开发/数据/内容）、首年现金、每月维护、`feasible`。投入不设门；数据拿不到或授权禁止再发布 → `feasible=false`。

判 go 前还要写建站简报素材（`brief`）：定位、首版页面清单、技术与托管建议、变现计划、SEO/GEO 补充、风险。

## 5. 判定

**go**，四条同时满足：

1. 基准情景上线第 12 个月收入 ≥ $100（§6）；
2. 至少一个干净标杆；
3. 差异点有证据，或明说照搬；
4. 交付依据成立（最新 delivery `feasible=true`）。

**rejected**：

| gate | 条件 | 最小证据 |
| --- | --- | --- |
| `scope` | §1 任一排除命中 | `--scope-hit` 命中项与理由 |
| `benchmark` | 流量是假象，或只有外链驱动的标杆、找不到第二个 | 至少一份 benchmark 观察 |
| `answered` | 所有簇都被首屏答完，计入需求为 0；只有部分簇被答完的，由收入判定 | 每个簇都有 answered=true 的 serp 观察 |
| `revenue` | 基准情景 < $100 | 模型现场重算一致 |

**parked**：关键证据拿不到，如 Semrush 域名模块故障、曲线读不出、数据授权说不清、标杆站被 Cloudflare 拦且摘要不足以判断。

早期否决不要求补齐后续步骤。

## 6. 标杆份额法与假设表

### 6.1 流量

```
我们第 12 个月访问 = min(后来者系数 × 标杆份额率 × 我们覆盖的需求, 15% × 我们覆盖的需求)
```

- 标杆份额率 = 标杆起量后第 12 个月美区自然流量 ÷ 它覆盖的全部簇量（`covered_demand`，不做剔除和折减，从严）。不满 12 个月用当前值，不外推。多个干净标杆取中位数；外链驱动的不参与。
- 我们覆盖的需求 = `counted=true` 且 `answered=false` 的簇量合计；`near_me=true` 的簇 ×0.2。
- 后来者系数：保守 0.25、基准 0.5、乐观 1.0；`crowding ≥ 3` 时基准 0.33。

### 6.2 收入

- 广告 = 月访问 × 每千次访问收入 ÷ 1000，只算美区访问。第 12 个月访问 < 10,000 走 AdSense，≥ 10,000 走 Mediavine Journey。
- 付费 = 月访问 × 付费转化率 × 月价；只有同方向有对手在卖付费版、且有用户证据时才算（`paid.applicable=true`），月价取对手定价中位数。
- 达标：基准情景合计 ≥ $100。按起点值，无付费时达标等价于基准第 12 个月访问 ≥ 10,000；Journey 的实际每千访问收入是最敏感的未确认项，决策书须披露。

### 6.3 假设表

版本 **2026-10-13.1**（用户 2026-10-13 接受起点值）。数值写在 `bench_model.py` 的 `ASSUMPTIONS`，两边必须一致。

| 项目 | 值 | 状态 |
| --- | --- | --- |
| 后来者系数 保守/基准/乐观 | 0.25 / 0.5 / 1.0 | 起点假设，未校准 |
| 拥挤时基准系数 | 0.33（crowding ≥ 3） | 起点假设 |
| 覆盖需求份额上限 | 15% | 起点假设 |
| near me 簇折减 | 0.2 | 沿用 xinci-simple 2026-10-02.1 |
| AdSense 每千访问 | $4 | 第三方方向性数据，工具类可能偏高 |
| Mediavine Journey 每千访问 | $16 | 未确认，最敏感 |
| 内容类/游戏类每千访问 | 暂按 $4 | 未确认 |
| 付费转化率 保守/基准/乐观 | 0.1% / 0.2% / 0.5% | 未确认，占位 |
| 达标门槛 | 基准 ≥ $100 | 用户定 |

标"未确认"的项，运行中取到证据时交用户决定是否升版；执行者不自行改表。用户上线的站可把 Search Console 点击与广告收入记进数据区 `反馈/`，用来校准，但不自动改表。

## 7. 证据与结算

- 观察只用 `write_observation.py` 追加，不覆盖、不手改；`observed_at` 写之前先取系统时间。
- 结算只用 `settle.py`：先确认引用的观察都在且合规 → 重算模型 → 固定绑定（路径 + SHA-256）→ 生成决策书 → 转移状态 → 校验。中断后同一条命令可恢复，不重复写 history。parked 改判时旧决策书归档到 `文档/历史/`。
- 运行清单只用 `run_log.py` 写：每阶段 started 与结束各一条；`semrush_calls` 只记本条新增调用，不重复累计。
- `validate_ledger.py` 非零表示真实数据有问题，须先修，不能拿单元测试通过代替。

## 8. 决策书与建站简报

只由 `build_doc.py` 生成（`settle.py` 会调用），md 是唯一事实来源，html 从 md 单向生成并内嵌源 SHA-256；两份都不手改。每节第一句是加粗的大白话结论，数字标"模型估算"或"Semrush 估算"，不写排名保证。

第一部分（go/rejected/parked 都有）：结论、标杆证据、方向需求与对手、现场与 GEO、12 个月流量与收入、风险与最大未知。

第二部分（只在 go 时）：定位、首版页面清单、差异点、数据、技术与托管、SEO 规范、GEO 规范、变现计划、投入、里程碑与止损（第 6 个月 Search Console 点击低于基准曲线 25% 就停）、风险清单。

## 9. 停机与错误

- Semrush 登录失效、额度用完、验证码，或浏览器预检重试仍失败：写 blocked 清单，保留恢复位置。
- Semrush 域名分析模块故障：改走 Backlink Analytics 概览取 AS 与自然流量；曲线也拿不到 → parked，不判否决。
- Google /sorry：两次请求间隔 ≥ 60 秒；已触发就静置约 1 小时，仍触发记 blocked。
- 数据区未配置：脚本退出码 2，先问用户，不猜位置。
````

`xinci-bench-workflow/xinci-bench-core/数据采集.md`：

```markdown
# 数据采集（xinci-bench）

怎么取数据、用哪条通道、什么算合规观察。判据在 `选站契约.md`，本文件只管采集纪律。

## 目录

- [1. 通道分工](#1-通道分工)
- [2. Semrush](#2-semrush)
  - [2.1 额度纪律](#21-额度纪律)
  - [2.2 各模块怎么用](#22-各模块怎么用)
- [3. 免费来源](#3-免费来源)
- [4. Google SERP 读取规程](#4-google-serp-读取规程)
  - [4.1 环境与预检](#41-环境与预检)
  - [4.2 读什么](#42-读什么)
- [5. 旧数据导入规则](#5-旧数据导入规则)
- [6. 已知的坑](#6-已知的坑)

## 1. 通道分工

| 用途 | 通道 | 原因 |
| --- | --- | --- |
| Semrush 各模块 | 当前环境的 Chrome 控制工具，复用用户已登录的 Semrush 标签页 | 需要登录态 |
| Google SERP 现场、读标杆站页面 | 内置浏览器面板（美区、桌面、未登录） | 避免登录个性化 |
| RDAP 注册日、`ads.txt`、`robots.txt`、`llms.txt` | `curl` | 不需要浏览器 |

SERP 只用通过预检的内置面板，不用已登录 Google 的 Chrome 代替。连续运行由主会话亲自执行 Semrush 部分：子代理访问 Semrush 曾被自动模式分类器拦截，被拦时不要转达授权重试，停下问用户（加放行规则，或切"逐条询问"模式）。

## 2. Semrush

### 2.1 额度纪律

- 每次查询都要能改变一个决策；决策不变，查询不跑。
- 代理站每天约一百来次查询，域名类与关键词类分开计。预计单日超过约 100 次时分天跑，先查最关键的。
- 每条运行清单如实记 `semrush_calls`（本条新增数）；每份观察也记本观察新增的 `semrush_calls`。
- 登录失效、验证码、额度提示 → 停下写 blocked 清单，不绕、不猜数。

### 2.2 各模块怎么用

| 用途 | 模块与做法 |
| --- | --- |
| 粗筛 AS 与流量（scan） | 批量分析，每批 ≤ 16 个域名。页面刚载入时同一批次内的输入都不生效，要另起一次调用再输；超过约 15 行时比较按钮会下移，用 find 拿元素引用点击。这里的"每月访问量"是全球全渠道，只用来粗筛 |
| B2、B3 与流量曲线（scan/assess） | Domain Overview（美区）：域级 AS、美区自然流量、流量曲线（读起量月、第 3/6/12 个月、2026 年 3/6/8 月更新前后）。B3 用"去掉品牌词与 near me 类定位词后"的美区自然流量：在 Organic Research 里排除品牌词与定位词后取合计，basis 写筛法 |
| 域名分析模块故障时 | 改走 `/analytics/backlinks/overview/?q=<域名>&searchType=domain`，同样给 AS、每月访问量与自然流量；曲线也拿不到 → parked |
| 起量手段（assess） | Backlink Analytics：引荐域名数、锚文本分布、引荐域名质量 |
| 标杆排名词、对手按网址筛流量（assess） | Organic Research。筛选写在网址的 filter 参数里（URL 编码的 JSON，如 `{"search":"/county/",...}`），可直接拼网址；页面刚载入时输入会被吞，读表头前等 8–10 秒 |
| 同类站（sibling） | Organic Research 的"竞争对手"列表 |
| 簇量（assess） | Keyword Magic：US、phrase match。种子只用名词性主题词；量地方查询时不要排除导航意图。长尾簇可导出 CSV（下载要用户当次允许；放进 scratchpad 的独立目录，用 `python3 -I` 解析） |

## 3. 免费来源

- **RDAP 注册日**：`curl -s https://rdap.org/domain/<域名>`，取 `events` 里 `eventAction=registration` 的日期。404 表示查不到，B1 改看 Semrush 曲线并标 `aged_domain`。
- **变现方式**：`curl -s https://<域名>/ads.txt` 看广告网络（google.com=AdSense，ezoic、mediavine、raptive/adthrive 等）；找 `/pricing` 或页脚里的付费入口。被 Cloudflare 拦时改读 Google 摘要并注明。
- **GEO 现状**：`curl -s https://<域名>/robots.txt` 与 `/llms.txt`，看标杆是否放行 AI 爬虫。
- **手工种子**：往 `种子/手工种子.json` 写域名前，先用 RDAP 确认域名存在；查不到的不写。

## 4. Google SERP 读取规程

### 4.1 环境与预检

- 内置浏览器面板、未登录；搜索网址显式带 `https://www.google.com/search?q=<查询>&gl=us&hl=en&pws=0`。
- 每次读 SERP 前核对四项，写进 serp 观察的 `browser_preflight`：

| 项 | 怎么核 |
| --- | --- |
| `controllable` | 能读到完整页面，含自然结果上方区域 |
| `desktop` | `#rcnt` / `#center_col` 在场，或 UA 与布局为桌面版 |
| `region` | 网址三参齐备 → `us`；页脚位置写进 `evidence`，不凭 `gl` 声称美国 IP |
| `logged_out` | 页面有 `Sign in`，没有 Google 账号头像元素 |

- 任一不合规 → 不写 `answered` 结论；重试一次仍失败记 blocker。
- 两次 Google 请求间隔 ≥ 60 秒；几分钟内 7–8 次会触发 /sorry。

### 4.2 读什么

- AI 概览在页面载入后异步生成：等几秒再读整页；出现 `Thinking`、`Searching` 时继续等；没看到 `AI Overview` 字样时隔几秒重读一次确认。
- 只返回自然结果列表时，不能据此判断没有 AI 概览，要补读整页或截图。
- 记：AI 概览/精选摘要/原生组件是否已完成任务（`answered` 与 `answered_basis`）、AI 概览引用的域名（`cited_domains`）、是否点名推荐工具站（`recommends_tools`）、标杆排第几（`benchmark_position`，不在前 10 填 null）、前 10 条自然结果（位置、域名、类型、AS）。
- 判"已完成任务"看的是：用户不点结果是否已拿到要的东西。单个查询只有一个答案的（某车型的孔距、某城市的时区）通常会被答掉；单个查询有多个可能答案、要按地点或型号再查的（这趟车几点、这个地址属于哪个县）通常答不了。

## 5. 旧数据导入规则

`seed_import.py --legacy-root <xinci-simple 数据区>` 只读导入，幂等：

- **标杆种子**：旧证据 `serp_top10` 里有 AS 记录、最小 AS < 30 的域名。排除：`.gov/.edu/.mil` 及域名标签以 gov 结尾的政府域名；出现过 official/brand/forum/video 类型的；平台黑名单。AS 记为 0 的当作未测，照样导入、初核时重测。
- **平台黑名单**（`seed_import.PLATFORMS`，增删须在本节写理由）：pinterest.com、play.google.com、scribd.com、reddit.com、facebook.com、youtube.com、quora.com、amazon.com。
- **同类站种子**：旧账本里 `seed.type=small_site` 的种子文字里出现的域名，`role=sibling`，只用来查同类站。
- **手工种子**：`种子/手工种子.json` 里的条目最先导入；不满足 B2、只用来查同类站的写 `"role": "sibling"`，默认 `benchmark`。
- **旧词库/旧裁决**：旧账本全部逐词量（按小写词去重，保留测量更晚的那条）与 63 个候选的终态、gate、理由，供 `lexicon.py` 查询。
- 导入前后对读过的旧文件逐个算 SHA-256，不一致就报错停止。

## 6. 已知的坑

- 代理站对超宽泛种子返回截断数据；对介词或疑问短语种子（`substitute for`、`why is my`）返回残缺数据集。
- Semrush 对 near me 词按单一抓取点估流量，会把全国量算给一个城市页，不能当真实分流。
- 竞品在某个州或某类页面上的流量，要在"主要页面"或 Organic Research 里按网址筛选再加总；从全站前 100 页里挑会严重低估。
- Chrome JS 返回超过约 1,000 字会截断，含 `=` 或 `location.href` 会被拦；长表分段读。
- 同一会话第二次起 Chrome 可能拦"多次下载"，要用户在 Chrome 里允许；翻页可替代导出（每页 100 行算 1 次调用）。
- 面板和 Chrome 的出口 IP 不在美国，部分站被 Cloudflare 拦。
- 写观察前先用 `date -u +%Y-%m-%dT%H:%M:%S+00:00` 取系统时间，不要估。
```

`xinci-bench-workflow/xinci-bench-core/命令与观察.md`：

````markdown
# 命令与观察（xinci-bench）

脚本怎么调、观察怎么写。所有命令在仓库根执行，脚本目录记为 `$S=xinci-bench-workflow/xinci-bench-core/scripts`。数据区按 `--data-root` > `XINCI_BENCH_DATA_ROOT` > `.xinci-bench-data-root` 解析；未配置时退出码 2，先问用户。

下面的 JSON 带 `//` 注释只为说明字段；写文件时去掉注释。

## 目录

- [1. 初始化与导入](#1-初始化与导入)
- [2. 运行清单](#2-运行清单)
- [3. scan 阶段](#3-scan-阶段)
  - [3.1 scan 观察](#31-scan-观察)
  - [3.2 登记与淘汰](#32-登记与淘汰)
- [4. assess 阶段](#4-assess-阶段)
  - [4.1 benchmark 观察](#41-benchmark-观察)
  - [4.2 demand 观察](#42-demand-观察)
  - [4.3 serp 观察](#43-serp-观察)
  - [4.4 differentiation 观察](#44-differentiation-观察)
  - [4.5 delivery 观察](#45-delivery-观察)
  - [4.6 brief 观察](#46-brief-观察)
  - [4.7 补数与测算](#47-补数与测算)
- [5. 结算](#5-结算)
- [6. 看板与校验](#6-看板与校验)

## 1. 初始化与导入

```bash
python3 $S/init_workspace.py --data-root <用户指定的数据区>
python3 $S/seed_import.py --legacy-root /Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-simple
python3 $S/lexicon.py --match "county"
```

冒烟测试一律加 `--no-save`（或只导出环境变量），不能改仓库根的指针文件。

## 2. 运行清单

```bash
python3 $S/run_log.py --plan
python3 $S/run_log.py --skill xinci-bench-scan --run-id run-20261014-a --round 1 --max-rounds 3 \
  --source-kind legacy --seed-value "种子池 legacy 前 16 个" --outcome started --next-step scan
python3 $S/run_log.py --finish --run-id run-20261014-a --outcome completed --semrush-calls 5 \
  --direction-touched example-county --note "16 个初核,2 个登记"
```

- 每阶段先写 started，结束用 `--finish`（completed / blocked / skipped），脚本推导下一步。
- found 已有 ≥ 3 个时 `--plan` 返回 `scan_outcome=skipped`：照样先写 scan started，再 `--finish --outcome skipped`。
- `--semrush-calls` 只填本条新增的调用数。

## 3. scan 阶段

```bash
python3 $S/seeds.py take --source legacy --n 16
python3 $S/seeds.py add --domain example.com --source serp --source-ref "查询 what county am i in 首页第 4"
```

### 3.1 scan 观察

一批一份，写好后 `python3 $S/write_observation.py --input <文件>`，打印出的相对路径就是观察引用。

```json
{
  "slug": null,                                   // scan 批次观察固定为 null
  "observed_at": "2026-10-14T02:10:00+00:00",     // 先 date -u 取系统时间
  "stage": "scan",
  "kind": "scan",
  "source_urls": ["<实际打开的网址>"],
  "semrush_calls": 3,                             // 本观察新增的 Semrush 调用
  "points": ["批量分析 16 个,3 个过粗筛"],          // 要点,不转录原文
  "readings": {
    "domains": [
      {
        "domain": "example-bench.com",            // 去 www 的域名
        "registered_at": "2025-12-29",            // RDAP 注册日;查不到为 null
        "aged_domain": false,                     // 老域名重新起量时为 true
        "authority_score": 11,                    // Semrush 域级 AS
        "us_organic_now": 5400,                   // 去品牌词与定位词后的美区自然流量
        "checks": {                               // 恰好 B1–B5;pass 为 true/false/null(前项已不过才可 null)
          "B1": {"pass": true, "basis": "RDAP 2025-12-29 注册"},
          "B2": {"pass": true, "basis": "Domain Overview AS 11"},
          "B3": {"pass": true, "basis": "Organic Research 排除品牌词后 5,400"},
          "B4": {"pass": true, "basis": "前 20 词分布在 9 个页面"},
          "B5": {"pass": true, "basis": "按地址查县,不涉排除项"}
        }
      }
    ]
  }
}
```

### 3.2 登记与淘汰

```bash
python3 $S/ledger.py register --slug example-county --title "按地址查所属县" --site-type tool \
  --domain example-bench.com --scan 证据/_scan/<文件名> --reason "B1–B5 全过"
python3 $S/seeds.py checked --domain example-bench.com
python3 $S/seeds.py reject --domain weak.com --failed B3 --readings "美区 1,200" --observation 证据/_scan/<文件名>
python3 $S/seeds.py requeue
```

## 4. assess 阶段

```bash
python3 $S/ledger.py rank
python3 $S/ledger.py show --slug example-county
```

assess 观察的公共字段与 scan 相同，`stage` 固定为 `assess`，`slug` 为方向 slug；下面只列 `kind` 与 `readings`。

### 4.1 benchmark 观察

```json
{
  "kind": "benchmark",
  "readings": {
    "domain": "example-bench.com",
    "traffic_start": "2026-04",                   // 起量月 YYYY-MM;读不出为 null
    "us_organic_now": 5400,                       // 当前美区自然流量
    "us_organic_m12": null,                       // 起量后第 12 个月;不满 12 个月为 null
    "curve": {"3": 500, "6": 5400, "12": null},   // 起量后第 3/6/12 个月读数;读不到为 null
    "referring_domains": 40,                      // 引荐域名数
    "anchor_summary": "品牌词与网址为主",           // 锚文本概况
    "link_driven": false,                         // 主要靠垃圾外链起量为 true
    "algo_risk": false,                           // 2026 年任一次垃圾更新后掉 50% 以上为 true
    "update_readings": "3/6/8 月更新前后平稳",      // 三次更新前后的读数
    "ads_txt": "google.com, pub-xxx, DIRECT",     // ads.txt 要点;没有写"无 ads.txt"
    "pricing": null                               // 定价页要点;没有付费版为 null
  }
}
```

### 4.2 demand 观察

```json
{
  "kind": "demand",
  "readings": {
    "clusters": [
      {
        "id": "core",                             // 方向内唯一,小写连字符
        "seed_term": "what county am i in",       // Keyword Magic 种子
        "volume": 100700,                         // 簇量
        "measured_at": "2026-10-14",              // 测量日
        "coverage": "benchmark",                  // benchmark 标杆已做 | ours 我们额外做
        "near_me": false                          // 代表查询含 near me 类定位措辞
      }
    ],
    "competitor_traffic": [
      {"domain": "example-big.com", "traffic": 21000, "basis": "Organic Research 按 /county/ 筛"}
    ],
    "crowding": 2,                                // 同方向近 24 个月新站数,含标杆
    "new_sites": ["example-bench.com", "example-new.com"]
  }
}
```

### 4.3 serp 观察

每个查询一份，必须带通过的 `browser_preflight`。

```json
{
  "kind": "serp",
  "browser_preflight": {"controllable": true, "desktop": true, "region": "us", "logged_out": true,
                        "evidence": "Sign in 可见;页脚 United States"},
  "readings": {
    "query": "what county am i in",
    "cluster_id": "core",                         // 对应 demand 里的簇
    "answered": false,                            // 首屏已完成任务为 true
    "answered_basis": "AI 概览只推荐工具,不给县名",
    "ai_overview": {"present": true, "completes_task": false,
                    "cited_domains": ["example-bench.com"], "recommends_tools": true},
    "benchmark_position": 4,                      // 标杆排第几;不在前 10 为 null
    "top10": [{"pos": 1, "domain": "example-big.com", "type": "tool", "authority_score": 38}]
  }
}
```

### 4.4 differentiation 观察

```json
{
  "kind": "differentiation",
  "readings": {
    "copy_only": false,                           // 照搬标杆时为 true,gaps 可为空
    "gaps": [
      {"benchmark_now": "只查县", "ours": "同时给学区与选区", "evidence": "证据/<slug>/<serp 观察文件名>"}
    ]
  }
}
```

### 4.5 delivery 观察

```json
{
  "kind": "delivery",
  "readings": {
    "data_sources": ["Census Geocoder(公有领域)"],
    "license": "美国联邦政府作品,公有领域",
    "hours": {"dev": 20, "data": 5, "content": 10}, // 首版工时
    "cash_first_year": 15,                        // 首年现金,美元
    "monthly_hours": 2,                           // 每月维护工时
    "feasible": true,                             // 数据拿不到或授权禁止再发布为 false
    "basis": "接口实测可用"
  }
}
```

### 4.6 brief 观察

只在准备判 go 时写。

```json
{
  "kind": "brief",
  "readings": {
    "positioning": "按当前位置或地址一次给出县、学区和选区",
    "pages": [{"path": "/", "target_query": "what county am i in", "volume": 74000,
               "page_type": "tool", "deliverable": "定位后给出县名与边界"}],
    "tech_hosting": "Astro 静态站 + Cloudflare Pages 免费版",
    "monetization_plan": "先接 AdSense,第 12 个月过 1 万访问后申请 Mediavine Journey",
    "seo_notes": ["县名页不做批量模板"],
    "geo_notes": ["首屏给一句可引用的答案"],
    "risks": ["同方向已有 2 个新站"]
  }
}
```

### 4.7 补数与测算

把观察里的结构化结果补进方向记录（补数 JSON 只写要改的字段），同时引用新观察：

```json
{
  "benchmarks": [{"domain": "example-bench.com", "registered_at": "2025-12-29", "aged_domain": false,
                  "traffic_start": "2026-04", "authority_score": 11, "us_organic_now": 5400,
                  "us_organic_m12": null, "covered_demand": 100700, "link_driven": false,
                  "algo_risk": false, "monetization": ["adsense"], "clean": true}],
  "clusters": [{"id": "core", "seed_term": "what county am i in", "volume": 100700,
                "measured_at": "2026-10-14", "coverage": "benchmark", "near_me": false,
                "answered": false, "counted": true}],
  "crowding": 2,
  "paid": {"applicable": false, "price_month": null, "evidence": null}
}
```

```bash
python3 $S/ledger.py update --slug example-county --patch <补数文件> --ref 证据/example-county/<文件名> --ref ...
python3 $S/bench_model.py --direction example-county
```

## 5. 结算

```bash
python3 $S/settle.py --slug example-county --verdict go --reason "标杆 9 个月到 2 万,首屏只推荐工具" \
  --biggest-unknown "Mediavine Journey 的实际每千访问收入"
python3 $S/settle.py --slug example-county --verdict rejected --gate revenue --reason "基准 $10.80" \
  --biggest-unknown "标杆是否还会涨"
python3 $S/settle.py --slug example-county --verdict rejected --gate scope --scope-hit infringement \
  --reason "克隆受版权游戏" --biggest-unknown "无"
python3 $S/settle.py --slug example-county --verdict parked --reason "流量曲线读不出" \
  --biggest-unknown "域名模块恢复后的读数"
```

中断后用同一条命令重跑即可恢复。

## 6. 看板与校验

```bash
python3 $S/report_status.py
python3 $S/validate_ledger.py
python3 -m unittest discover -s $S/tests -t $S/tests -q
```
````

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 84 tests` 与 `OK`

- [ ] **Step 5: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-core/选站契约.md" "xinci-bench-workflow/xinci-bench-core/数据采集.md" "xinci-bench-workflow/xinci-bench-core/命令与观察.md" "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py"
git commit -m "xinci-bench:选站契约、数据采集规程、命令与观察,文档与代码数值一致性测试" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 11: 四个 SKILL.md、README 与双环境接入

**Files:**
- Create: `xinci-bench-workflow/xinci-bench-scan/SKILL.md`
- Create: `xinci-bench-workflow/xinci-bench-assess/SKILL.md`
- Create: `xinci-bench-workflow/xinci-bench-status/SKILL.md`
- Create: `xinci-bench-workflow/xinci-bench-run/SKILL.md`
- Create: `xinci-bench-workflow/README.md`
- Modify: `README.md`（仓库根）
- Modify: `xinci-simple-workflow/README.md`（标题下加冻结说明）
- Modify: `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py`（加 `SkillTest`）

**Interfaces:**
- Consumes: 契约与命令文档的章节号（SKILL.md 按章节号引用）
- Produces: 四个可被 Claude Code 与 Codex 发现的 skill（软链到 `~/.claude/skills/` 与 `~/.codex/skills/`）

- [ ] **Step 1: 写失败的测试**

在 `xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py` 的 `if __name__ == "__main__":` 之前插入：

```python
class SkillTest(unittest.TestCase):
    def test_skills_named_and_point_to_contract(self):
        for name in ("xinci-bench-scan", "xinci-bench-assess", "xinci-bench-status", "xinci-bench-run"):
            body = (WORKFLOW / name / "SKILL.md").read_text(encoding="utf-8")
            m = re.match(r"---\nname: (\S+)\ndescription: '(.+)'\n---\n", body)
            self.assertIsNotNone(m, name)
            self.assertEqual(m.group(1), name)
            if name != "xinci-bench-status":
                self.assertIn("选站契约.md", body)
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: FAIL，`FileNotFoundError: ... xinci-bench-scan/SKILL.md`

- [ ] **Step 3: 写四个 SKILL.md 与新工作流 README**

`xinci-bench-workflow/xinci-bench-scan/SKILL.md`：

```markdown
---
name: xinci-bench-scan
description: '标杆倒推选站的发现阶段：从种子池或 sibling/serp/geo/community 来源取一批域名，初核"近 24 个月注册、AS≤30、美区自然流量≥5,000"的低权重新站，合格的登记为方向。用于 bench scan、找标杆站、找新起量小站；深核用 xinci-bench-assess，不是 xinci 或 xinci-simple 工作流。'
---

# 找标杆

行动前读 `xinci-bench-workflow/xinci-bench-core/选站契约.md` §1–3、§7 与 `数据采集.md` §1–3、§6；写观察和清单的命令见 `命令与观察.md` §2–3。脚本都在 `xinci-bench-workflow/xinci-bench-core/scripts/`。

1. `report_status.py` 确认数据区；退出码 2 才问用户路径，再 `init_workspace.py --data-root <路径>`。种子池为空且从未导入时，先 `seed_import.py --legacy-root <xinci-simple 数据区>`。
2. `run_log.py --plan` 读恢复位置与 `next_source`；conflict=true 时显式确定 run_id。用户指定的来源优先；恢复 started/blocked 阶段沿用原来源与 seed_value。写 scan started 清单。
3. 取一批种子：`legacy` 用 `seeds.py take --source legacy --n 16`；其他来源先按 `选站契约.md` §3.1 的做法发现域名，`seeds.py add` 登记后再取。`seeds.py requeue` 把复查日已到的 B3 淘汰域名放回池。
4. 批量分析粗筛 AS 与流量（每批 ≤ 16 个）；过粗筛的逐个做 B1–B5：RDAP 注册日、Domain Overview 的域级 AS 与美区自然流量、Organic Research 去品牌词和定位词后的流量与词/页分布、范围排除。前项已不过的，后项填 null 省额度。
5. 整批写一份 scan 观察（`write_observation.py`）。全过的 `ledger.py register` 登记方向（同一标杆已用于别的方向须 `--confirm-distinct`）并 `seeds.py checked`；不过的 `seeds.py reject`。
6. `run_log.py --finish --run-id <ID> --outcome completed --semrush-calls <本阶段新增>`，`--direction-touched` 写本阶段登记的方向。汇报：初核数、登记数、淘汰按编号分布、Semrush 调用数、下次来源。

连续运行时 found 已有 ≥ 3 个：不查 Semrush，写 started 后 `--finish --outcome skipped`，交给 assess。

不做深核与 SERP 现场；不改门槛；登录失效、额度用完或验证码时 `--finish --outcome blocked` 并报告现象。
```

`xinci-bench-workflow/xinci-bench-assess/SKILL.md`：

```markdown
---
name: xinci-bench-assess
description: '标杆倒推选站的深核与决策：对已登记的方向核起量手段、测方向需求、读 Google 首屏与 AI 概览、写差异点与交付依据，用标杆份额法算上线第 12 个月访问与收入，出 go/否决/搁置决策书，go 时附建站简报。用于 bench assess、深核方向、出建站简报；发现标杆用 xinci-bench-scan。'
---

# 深核与决策

行动前读 `xinci-bench-workflow/xinci-bench-core/选站契约.md` §1、§4–8 与 `数据采集.md` 全文；观察字段与命令见 `命令与观察.md` §4–5。脚本都在 `xinci-bench-workflow/xinci-bench-core/scripts/`。

1. `run_log.py --plan` 核对恢复位置，写 assess started 清单。`ledger.py rank` 取前 2 个 found（用户指定优先；不足 2 个核全部）。
2. 每个方向按契约 §4 六步走，每步先 `date -u` 取时间、写观察、记本观察的 Semrush 调用数：
   1. 每个标杆一份 benchmark：曲线、引荐域名与锚文本、三次垃圾更新前后、ads.txt、定价页；
   2. 一份 demand：先 `lexicon.py --match <主题词>` 查旧词库与旧裁决，再按需用 Keyword Magic 补测，对手流量按网址筛；
   3. 3–5 份 serp：内置面板预检通过后读首屏，两次请求间隔 ≥ 60 秒；
   4. 一份 differentiation、一份 delivery；准备判 go 时再写一份 brief。
3. 每步之后用 `ledger.py update --patch <补数> --ref <观察>` 把结构化结果补进方向记录；clean 只能给初核全过且非外链驱动的标杆。
4. `bench_model.py --direction <slug>` 看三档。可以提前否决：范围命中、标杆不成立、所有簇被答完，或基准明显 < $100，都不必走完六步。
5. `settle.py` 结算（go / rejected+gate / parked），`--reason` 写一句结论理由，`--biggest-unknown` 写最可能让结论翻转的一项。它会生成决策书 md/html 并校验；失败按报错补证据后用同一命令重跑。
6. 全部方向结束后 `validate_ledger.py`，再 `run_log.py --finish`。汇报每个方向的结论、基准第 12 个月访问与收入、决策书路径、用到的未确认假设和 Semrush 调用数。

不改门槛和假设表；取到"内容类/游戏类 RPM""Journey RPM""付费转化率"的证据时，写进观察 points 并在汇报里单独列出，由用户决定是否升版。建不建站由用户决定。
```

`xinci-bench-workflow/xinci-bench-status/SKILL.md`：

```markdown
---
name: xinci-bench-status
description: '标杆倒推选站工作流的只读看板：各状态方向数、待深核排序、搁置天数、go 的决策书路径、种子池余量、待复查淘汰数、累计 Semrush 调用。用于 bench status、看 bench 工作流状态；不是 xinci-status 或 xinci-simple-status。'
---

# 看板

只读，不写任何文件。

1. `python3 xinci-bench-workflow/xinci-bench-core/scripts/report_status.py`；需要结构化数据时加 `--json`。退出码 2 表示数据区未配置，告诉用户需要先指定数据区，不替用户选。
2. 需要时再跑 `run_log.py --plan` 看恢复位置、下次来源；跑 `validate_ledger.py` 看账本是否有错。
3. 汇报时先给结论（有没有 go、下一步该做什么），再列数字；搁置超过 90 天的单独提醒；validator 有错时如实列出，不当作正常状态。
```

`xinci-bench-workflow/xinci-bench-run/SKILL.md`：

```markdown
---
name: xinci-bench-run
description: '标杆倒推选站的连续运行：暗号 xinci_bench_run（可带 max_rounds=N，默认3）或 /xinci-bench-run。每轮先补足 3 个待深核方向，再深核排序前 2 个；出 go 不停、跑满预算。不是 xinci_run 或 xinci_simple_run。'
---

# 连续运行

串联 scan 与 assess，不复制判据。行动前读 `xinci-bench-workflow/xinci-bench-core/选站契约.md` §0、§2、§7、§9，阶段步骤读对应 Skill。启动暗号即授权既定的观察、账本、种子池和清单写入，不重复确认。

## 启动与恢复

1. `report_status.py` 确认数据区；未配置才问路径。
2. `run_log.py --plan`：一个未完运行就恢复同一 run_id、轮号和预算；多个则返回 conflict，必须显式选定 `--run-id`；有未完运行时不能新建。
3. 没有未完运行才建立新 run_id（字母数字连字符），预算用用户给的 N，否则 3。
4. Semrush 部分由主会话亲自执行。开跑前确认 Chrome 工具可用；被自动模式分类器拦时不要转达授权重试，停下请用户加放行规则或切"逐条询问"模式。

## 每轮

1. **scan**：按 `--plan` 的 action 与 next_source 执行 xinci-bench-scan；`scan_outcome=skipped` 时写 started 后 finish skipped。
2. **assess**：执行 xinci-bench-assess，深核 `rank` 前 2 个；没有 found 时也要写 assess 清单并如实记零。
3. 每阶段结束都用 `run_log.py --finish`，只填本阶段新增调用；核对清单、账本、决策书与 `validate_ledger.py` 一致后，才算一轮完成。

## 停机

- 跑满 N 轮停。出 go 不停（用户 2026-10-13 定）。
- Semrush 登录失效、额度用完、验证码，或浏览器预检重试仍失败：写 blocked 清单，保留恢复位置，报告现象；同一 run_id 之后可以接着跑。

收尾汇报：k/N 轮、初核域名数与通过数、登记方向数、go/rejected（按 gate）/parked 数、每个 go 的方向与基准收入与决策书路径、取到的未确认假设证据、Semrush 累计调用、种子池余量、下次来源。建不建站由用户决定。
```

`xinci-bench-workflow/README.md`：

````markdown
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
````

- [ ] **Step 4: 改仓库根 README 与 xinci-simple README**

仓库根 `README.md`：把这一段

```markdown
2026-09-09 起新增的第二套工作流：从已有真实搜索量的英文词里找守得弱、AI Overview 吃不掉、base case ≥ $200/月 的主题簇，产出机会报告。与 xinci 新词工作流零运行时依赖、数据区独立。入口见 [xinci-simple-workflow/README.md](xinci-simple-workflow/README.md)。
```

替换为

```markdown
2026-09-09 起新增的第二套工作流：从已有真实搜索量的英文词里找守得弱、AI Overview 吃不掉、base case ≥ $200/月 的主题簇，产出机会报告。与 xinci 新词工作流零运行时依赖、数据区独立。入口见 [xinci-simple-workflow/README.md](xinci-simple-workflow/README.md)。

**2026-10-13 起冻结**：不删、不再跑，脚本与契约不再修改；它的数据区由 xinci-bench 只读引用。
```

再在 `## 仓库边界` 之前插入：

```markdown
## xinci-bench-workflow（标杆倒推选站）

2026-10-13 起的第三套工作流：从近 24 个月起量的低权重小站倒推建站方向，判断"上线后 12 个月内单站做到 $100/月"的把握，产出决策书，go 时附建站简报。与另外两套零运行时依赖、数据区独立。入口见 [xinci-bench-workflow/README.md](xinci-bench-workflow/README.md)。

| 单元 | 职责 |
| --- | --- |
| [xinci-bench-scan](xinci-bench-workflow/xinci-bench-scan/SKILL.md) | 找标杆：取种子域名初核 B1–B5，合格的登记为方向 |
| [xinci-bench-assess](xinci-bench-workflow/xinci-bench-assess/SKILL.md) | 六步深核、标杆份额法测算、结算并生成决策书与建站简报 |
| [xinci-bench-status](xinci-bench-workflow/xinci-bench-status/SKILL.md) | 只读看板 |
| [xinci-bench-run](xinci-bench-workflow/xinci-bench-run/SKILL.md) | 连续运行驱动器，暗号 `xinci_bench_run max_rounds=N` |
| [xinci-bench-core](xinci-bench-workflow/xinci-bench-core/) | 选站契约、数据采集、命令与观察、schema、脚本 |

```

`xinci-simple-workflow/README.md`：在第一行标题之后插入一行空行和

```markdown
> **2026-10-13 起冻结**：不删、不再跑，脚本与契约不再修改；数据区由 xinci-bench 只读引用。新的选站工作流见 [xinci-bench-workflow](../xinci-bench-workflow/README.md)。
```

- [ ] **Step 5: 运行确认通过**

Run: `python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q`
Expected: `Ran 85 tests` 与 `OK`

- [ ] **Step 6: 软链到两个环境并核对**

```bash
for s in xinci-bench-scan xinci-bench-assess xinci-bench-status xinci-bench-run; do
  ln -sfn "$(pwd)/xinci-bench-workflow/$s" ~/.claude/skills/$s
  ln -sfn "$(pwd)/xinci-bench-workflow/$s" ~/.codex/skills/$s
done
for s in xinci-bench-scan xinci-bench-assess xinci-bench-status xinci-bench-run; do
  test "$(readlink -f ~/.claude/skills/$s/SKILL.md)" = "$(readlink -f ~/.codex/skills/$s/SKILL.md)" && echo "ok $s"
done
```

Expected: 四行 `ok`。xinci-simple 的软链保持不动（冻结不等于删除）。

- [ ] **Step 7: 提交**

```bash
git add "xinci-bench-workflow/xinci-bench-scan/SKILL.md" "xinci-bench-workflow/xinci-bench-assess/SKILL.md" "xinci-bench-workflow/xinci-bench-status/SKILL.md" "xinci-bench-workflow/xinci-bench-run/SKILL.md" "xinci-bench-workflow/README.md" "README.md" "xinci-simple-workflow/README.md" "xinci-bench-workflow/xinci-bench-core/scripts/tests/test_documentation.py"
git commit -m "xinci-bench:四个 skill、README 与双环境接入;xinci-simple 标注冻结" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


---

### Task 12: 真实数据区初始化、旧数据导入与验收

**Files:**
- 数据区（不入库）：`/Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-bench/`
- Create（不入库）：`.xinci-bench-data-root`
- Modify: `docs/superpowers/specs/2026-10-13-xinci-bench-workflow-design.md`（末尾加"实现时的调整"一节，并补目录）

**Interfaces:**
- Consumes: Task 1–11 的全部脚本
- Produces: 可直接开跑的真实数据区；设计稿与实现一致

- [ ] **Step 1: 记录另两个指针文件的当前内容（验收时对比）**

```bash
cat .xinci-data-root .xinci-simple-data-root
```

Expected: 分别是 `/Users/vito.wu/IdeaProjects/keywords-macdownds/数据/新词工作流` 与 `/Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-simple`。

- [ ] **Step 2: 初始化真实数据区（这次要写指针，不加 --no-save）**

```bash
python3 xinci-bench-workflow/xinci-bench-core/scripts/init_workspace.py --data-root /Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-bench
cat .xinci-bench-data-root
```

Expected: 打印已创建的 8 个目录和 4 个空文件，指针内容为该路径。

- [ ] **Step 3: 写手工种子（先用 RDAP 核对域名存在）**

```bash
for d in wisconsinpropertymap.com flpropertycheck.com parcelvision.app county-cad.org freeparceldata.com offleashfinder.com geocodify.com dittobase.com; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://rdap.org/domain/$d"); echo "$d $code"
done
```

只把返回 200（或 rdap.org 302 跳转后 200）的写进 `/Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-bench/种子/手工种子.json`，格式：

```json
{
  "schema_version": 1,
  "seeds": [
    {"domain": "wisconsinpropertymap.com", "note": "AS 11,2025-12 注册,约 9 个月到 5.4K/月(记忆 country-gis)"},
    {"domain": "flpropertycheck.com", "note": "AS 12,2026-03 注册,7 个月约 5,200/月"},
    {"domain": "parcelvision.app", "note": "AS 12,自然流量约 9.8K/月"},
    {"domain": "county-cad.org", "note": "2026-05 注册,约 5,200/月,大头来自单页"},
    {"domain": "freeparceldata.com", "note": "地块数据新入局者"},
    {"domain": "offleashfinder.com", "note": "AS 2,自然流量≈0 但被 AI 搜索提及,反面样本"},
    {"domain": "geocodify.com", "role": "sibling", "note": "AS 38,查县主词第 1,不满足 B2,只查同类站"},
    {"domain": "dittobase.com", "role": "sibling", "note": "AS 35,342.9K/月,不满足 B2,只查同类站"}
  ]
}
```

`role` 不写时默认 `benchmark`；AS 已知高于 30、只用来查同类站的写 `sibling`。RDAP 查不到的从清单删掉，并在提交说明里写明。网络不通时停下问用户，不要跳过核对直接写入。

- [ ] **Step 4: 导入旧数据并核对条数**

```bash
python3 xinci-bench-workflow/xinci-bench-core/scripts/seed_import.py --legacy-root /Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-simple
python3 xinci-bench-workflow/xinci-bench-core/scripts/seed_import.py --legacy-root /Users/vito.wu/IdeaProjects/keywords-macdownds/数据/xinci-simple
```

Expected：第一次 `benchmark_candidates` 68、`sibling_candidates` 13、`lexicon_words` 14258、`verdicts` 63、`seeds_added.manual` 等于 Step 3 写入的条数（手工种子里与旧证据重复的域名只算一次，`seeds_total` = 68 + 13 + 手工条数 − 重复数）；第二次 `seeds_added` 全为 0。条数对不上时停下排查，不要改脚本去凑数。

- [ ] **Step 5: 全量验收**

```bash
python3 -m unittest discover -s xinci-bench-workflow/xinci-bench-core/scripts/tests -t xinci-bench-workflow/xinci-bench-core/scripts/tests -q
python3 xinci-bench-workflow/xinci-bench-core/scripts/validate_ledger.py
python3 xinci-bench-workflow/xinci-bench-core/scripts/report_status.py
python3 xinci-bench-workflow/xinci-bench-core/scripts/run_log.py --plan
python3 xinci-bench-workflow/xinci-bench-core/scripts/lexicon.py --match "county" --limit 3
cat .xinci-data-root .xinci-simple-data-root
git status --short
```

Expected：85 个测试 OK；`校验完成:0 个错误`；看板显示种子池 `legacy/benchmark` 与 `legacy/sibling` 待初核；`--plan` 的 `next_source` 为 `legacy`；lexicon 返回 446 个含 county 的词；两个旧指针与 Step 1 一致；`git status` 里除了用户原有的 `选词契约.md` 改动外没有未提交文件（`.xinci-bench-data-root` 已被 gitignore）。

- [ ] **Step 6: 设计稿补"实现时的调整"**

在设计稿 `## 12. 设计决策记录` 一节之后追加 `## 13. 实现时的调整`，内容照抄本计划开头"与设计稿的差异"的 7 条；并在设计稿目录末尾加一行 `- [13. 实现时的调整](#13-实现时的调整)`。

- [ ] **Step 7: 提交**

```bash
git add docs/superpowers/specs/2026-10-13-xinci-bench-workflow-design.md
git commit -m "xinci-bench:设计稿补实现时的调整;真实数据区已初始化并导入旧数据" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

数据区在 `keywords-macdownds` 仓库里，本计划不提交那边；是否提交由用户决定。分支是否合并进 main、是否 push，交给 superpowers:finishing-a-development-branch 按用户选择处理。
