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
        if rec.get("decision") is not None or rec.get("bindings") is not None:
            errs.append(f"{slug}: found 不应带 decision/bindings,说明结算未完成;用同一条 settle.py 命令重跑")
        return errs
    dec = rec.get("decision") or {}
    if dec.get("verdict") != rec["state"]:
        errs.append(f"{slug}: decision.verdict 与状态不一致")
    if not L.docs_consistent(root, slug):
        errs.append(f"{slug}: 决策书 md/html 缺失,或 html 内嵌的源 SHA 与 md 不符")
    elif sha256_file(L.doc_paths(root, slug)[0]) != dec.get("doc_sha256"):
        errs.append(f"{slug}: 决策书 md 与账本不一致(md 的 SHA 不等于结算时记录的 doc_sha256,疑似被手改);"
                    "事实没变时用同一条 settle.py 命令重跑重建")
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
