#!/usr/bin/env python3
"""数据区定位:唯一解析入口。不猜位置。

解析顺序:1. 显式 --data-root  2. 环境变量 XINCI_SIMPLE_DATA_ROOT
3. 仓库根配置 .xinci-simple-data-root  4. 抛 DataRootNotConfigured。
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
