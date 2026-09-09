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
