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
