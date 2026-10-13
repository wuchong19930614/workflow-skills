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
