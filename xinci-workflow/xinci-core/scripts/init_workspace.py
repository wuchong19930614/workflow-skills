#!/usr/bin/env python3
"""初始化 数据/新词工作流/ 目录结构与空账本。幂等:已存在的文件与目录不动。"""
import argparse
import json
import sys
from pathlib import Path

# 数据区在仓库根(代码与数据分离):xinci-workflow/xinci-core/scripts/ 向上三级
DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[3] / "数据" / "新词工作流"
SUBDIRS = ("账本", "证据", "决策书", "运行")


def init_workspace(data_root) -> list:
    data_root = Path(data_root)
    created = []
    for name in SUBDIRS:
        d = data_root / name
        if not d.is_dir():
            d.mkdir(parents=True)
            created.append(str(d))
    ledger = data_root / "账本" / "候选账本.json"
    if not ledger.is_file():
        ledger.write_text(
            json.dumps({"schema_version": 1, "candidates": {}}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        created.append(str(ledger))
    index = data_root / "淘汰方向.jsonl"
    if not index.is_file():
        index.write_text("", encoding="utf-8")
        created.append(str(index))
    return created


def main(argv=None):
    ap = argparse.ArgumentParser(description="初始化 xinci 数据区")
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    a = ap.parse_args(argv)
    created = init_workspace(a.data_root)
    print("已创建:" + (", ".join(created) if created else "无(全部已存在)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
