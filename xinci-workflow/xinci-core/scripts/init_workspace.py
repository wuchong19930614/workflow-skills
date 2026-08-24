#!/usr/bin/env python3
"""初始化数据区目录结构与空账本。幂等:已存在的文件与目录不动。"""
import os
import argparse
import json
import sys
from pathlib import Path

import data_root

# 数据区的定位统一走 data_root 模块:显式参数 > 环境变量 > 仓库配置 > 拒绝执行。
# 这里刻意不再留任何默认值——数据区放哪是用户的决定,脚本不猜(理由见 data_root.py)。
SUBDIRS = ("账本", "证据", "决策书", "运行", "运行状态", "运行状态/事务")


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
    decisions = data_root / "去重裁决.jsonl"
    if not decisions.is_file():
        decisions.write_text("", encoding="utf-8")
        created.append(str(decisions))
    return created


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="初始化 xinci 数据区。这是「数据区放哪」这个决定被落盘的地方——"
                    "显式给了 --data-root 就把它写进仓库配置,之后所有脚本都按它走。")
    ap.add_argument("--data-root", default=None,
                    help="数据区路径。不给则按 XINCI_DATA_ROOT 环境变量、再按仓库配置 .xinci-data-root 解析;都没有则拒绝执行并提示先问用户")
    ap.add_argument("--no-save", action="store_true",
                    help="只创建目录,不把路径写进仓库配置(一次性用途)")
    a = ap.parse_args(argv)
    explicit = a.data_root
    root = data_root.resolve_or_exit(explicit)
    created = init_workspace(root)
    print("数据区:" + str(root))
    print("已创建:" + (", ".join(created) if created else "无(全部已存在)"))
    # 只有用户显式给了路径才落盘:那一次调用就是他做出决定的时刻。
    # 从环境变量或既有配置解析出来的不重复写。
    if explicit and not a.no_save:
        print("已记入仓库配置:" + str(data_root.save(root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
