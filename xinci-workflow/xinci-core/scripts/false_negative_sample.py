#!/usr/bin/env python3
"""为校准轮生成分层假阴性复核清单；只读，不改变账本或候选状态。"""
import argparse
import json
import sys
from pathlib import Path

import data_root
import screen_index


DEFAULT_TARGETS = {"G6": 10, "G7": 10, "G5": 5, "G1": 5, "G3": 5}
AUDIT_GATES = set(DEFAULT_TARGETS)


def _ledger_rejections(root):
    path = Path(root) / "账本" / "候选账本.json"
    try:
        candidates = json.loads(path.read_text(encoding="utf-8")).get("candidates", {})
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    rows = []
    for slug, rec in candidates.items():
        if rec.get("state") != "rejected":
            continue
        gates = rec.get("gates") or {}
        for gate in AUDIT_GATES:
            if str(gates.get(gate, "")).startswith("veto"):
                rows.append({
                    "term": rec.get("term") or slug, "slug": slug, "gate": gate,
                    "reason": "账本正式否决", "date": (rec.get("first_observed_at") or "")[:10],
                    "evidence_refs": list(rec.get("evidence_refs") or []), "origin": "ledger",
                })
    return rows


def build_sample(root, targets=None):
    targets = dict(DEFAULT_TARGETS if targets is None else targets)
    unknown = set(targets) - AUDIT_GATES
    if unknown or any(not isinstance(v, int) or isinstance(v, bool) or v < 0
                      for v in targets.values()):
        raise ValueError(f"gate targets 非法: {sorted(unknown)}")
    rows = []
    for rec in screen_index.load(root):
        if rec.get("gate") in AUDIT_GATES:
            rows.append({
                "term": rec["term"], "gate": rec["gate"], "reason": rec.get("reason", ""),
                "date": rec.get("date", ""), "gate_version": rec.get("gate_version", ""),
                "source_urls": list(rec.get("source_urls") or []), "origin": "screen_index",
            })
    rows.extend(_ledger_rejections(root))
    # 旧闸门优先，其次最近记录；同一词只抽一次。
    rows.sort(key=lambda r: r.get("date", ""), reverse=True)
    rows.sort(key=lambda r: r.get("gate_version") == screen_index.GATE_VERSION)
    selected, seen = [], set()
    coverage = {}
    for gate, target in targets.items():
        pool = [r for r in rows if r["gate"] == gate and r["term"].casefold() not in seen]
        picked = pool[:target] if target else []
        selected.extend(picked)
        seen.update(r["term"].casefold() for r in picked)
        coverage[gate] = {"target": target, "available": len(pool), "selected": len(picked),
                          "shortfall": max(0, target - len(picked))}
    return {
        "schema_version": 1,
        "gate_version": screen_index.GATE_VERSION,
        "selection_rule": "old-gate-priority_then_recent_unique-term",
        "samples": selected,
        "coverage": coverage,
        "untested_gates": sorted(g for g, row in coverage.items() if row["selected"] == 0),
    }


def _parse_target(value):
    gate, sep, count = value.partition("=")
    if not sep:
        raise argparse.ArgumentTypeError("格式必须为 GATE=COUNT")
    try:
        count = int(count)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("COUNT 必须是整数") from exc
    return gate, count


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成校准轮的分层假阴性样本")
    ap.add_argument("--data-root")
    ap.add_argument("--gate-target", action="append", type=_parse_target, default=[])
    args = ap.parse_args(argv)
    root = data_root.resolve_or_exit(args.data_root)
    targets = dict(DEFAULT_TARGETS)
    targets.update(dict(args.gate_target))
    try:
        print(json.dumps(build_sample(root, targets), ensure_ascii=False, indent=2))
    except ValueError as exc:
        print(f"抽样拒绝:{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
