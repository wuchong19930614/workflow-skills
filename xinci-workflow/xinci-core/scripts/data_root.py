#!/usr/bin/env python3
"""数据区定位:唯一解析入口。

xinci-workflow 只放 skill 与契约,执行产出(账本、证据、淘汰方向索引、去重裁决、
运行清单、运行状态、决策书)住在**本仓库之外**的数据区。数据区在哪必须由用户明确
指定一次并落盘,不允许脚本自己猜。

解析顺序(先命中先用):
  1. 显式 --data-root
  2. 环境变量 XINCI_DATA_ROOT
  3. 仓库内配置文件 .xinci-data-root(由 init_workspace.py 写入,不入库)
  4. 抛 DataRootNotConfigured —— **没有静默回退**

第 4 条是本模块存在的理由。2026-08-24 之前这里有一条"回退到同级 keywords-macdownds"
的默认值,后果是:换一台机器或换一个用户第一次跑这套工作流时,init_workspace.py 会
在一个他从没同意过的位置直接建目录、建空账本,而且不报错。数据区放哪是用户的决定,
不是脚本的默认值——所以现在它宁可拒绝执行,也不猜。
"""
import os
from pathlib import Path

ENV_VAR = "XINCI_DATA_ROOT"
CONFIG_NAME = ".xinci-data-root"

# 配置文件放在 workflow-skills 仓库根:scripts/ 向上三级。
# 数据区与具体 checkout 配对,所以配置是仓库内的、而非全局的。
REPO_ROOT = Path(__file__).resolve().parents[3]


class DataRootNotConfigured(Exception):
    """数据区未配置。异常文案直接面向执行者,包含可照做的下一步。"""


_MESSAGE = f"""数据区未配置,拒绝执行(不猜位置)。

xinci 的执行产出(账本、证据、淘汰方向索引、去重裁决、运行清单、决策书)存在哪里,
必须由用户指定。**先问用户,不要替他选。**

问清之后,任选其一固定下来:

  1) 落盘到仓库配置(推荐,一次生效,后续无需重复):
       python3 xinci-workflow/xinci-core/scripts/init_workspace.py --data-root <用户给的路径>
     它会创建目录结构与空账本,并把路径写进 {REPO_ROOT / CONFIG_NAME}

  2) 只在当前 shell 生效:
       export {ENV_VAR}=<用户给的路径>

  3) 单次调用:给脚本加 --data-root <路径>

已有数据区要接入的,同样用 (1),init_workspace.py 是幂等的,不会动已存在的文件。"""


def config_path() -> Path:
    return REPO_ROOT / CONFIG_NAME


def read_config():
    """读仓库配置;没有或为空返回 None。"""
    p = config_path()
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8").strip()
    return Path(text) if text else None


def save(path) -> Path:
    """把用户确认的数据区落盘,返回配置文件路径。"""
    p = config_path()
    p.write_text(str(Path(path).expanduser().resolve()) + "\n", encoding="utf-8")
    return p


def resolve(explicit=None) -> Path:
    """按顺序解析数据区。全部落空时抛 DataRootNotConfigured。

    注意:本函数只定位,不校验目录是否已初始化——那是 init_workspace 的事。
    """
    for cand in (explicit, os.environ.get(ENV_VAR) or None, read_config()):
        if cand:
            return Path(cand).expanduser()
    raise DataRootNotConfigured(_MESSAGE)


def resolve_or_exit(explicit=None) -> Path:
    """CLI 用:解析失败时打印指引并以 2 退出,而不是抛栈。"""
    import sys
    try:
        return resolve(explicit)
    except DataRootNotConfigured as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(2)
