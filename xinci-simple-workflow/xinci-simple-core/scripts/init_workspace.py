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
