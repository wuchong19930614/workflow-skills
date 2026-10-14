#!/usr/bin/env python3
"""只读看板:置顶待开建的快道 go;各状态数、待深核排序、观察中剩余天数、搁置天数、go 的文档、
到期的验收节点、种子池与原料池余量、待复查淘汰、累计 Semrush 调用。"""
import argparse
import json
import sys
from datetime import date

import data_root
import ledger as L
import quick_model as QM
import quick_pool
import run_log
import seeds
from _common import BenchError, load_ledger, today

PARKED_WARN_DAYS = 90


def _quick_status(root, dirs, on) -> dict:
    pending, launched_due, watching = [], [], []
    for s, r in dirs.items():
        if r.get("lane") != "quick":
            continue
        if r["state"] == "watching":
            left = (date.fromisoformat(r["watch"]["expires_at"]) - date.fromisoformat(on)).days
            watching.append({"slug": s, "days_left": left, "expires_at": r["watch"]["expires_at"],
                             "checks": len(r["watch"]["checks"])})
        if r["state"] != "go":
            continue
        fu, base = r["follow_up"], r["model"]["scenarios"]["base"]
        if fu["status"] == "pending":
            pending.append({"slug": s, "title": r["title"], "base_visits": base["visits"],
                            "base_revenue": base["revenue"], "launch_by": fu["launch_by"],
                            "overdue": on > fu["launch_by"], "doc": str(L.doc_paths(root, s)[0])})
        elif fu["status"] == "launched":
            for m in QM.milestones(fu["launched_at"]):
                if m["date"] <= on:
                    launched_due.append({"slug": s, "day": m["day"], "date": m["date"]})
    return {"pending_go": pending, "watching": sorted(watching, key=lambda w: w["days_left"]),
            "milestones_due": launched_due, "pool_pending": len(quick_pool.pending(root))}


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
           "doc": str(L.doc_paths(root, s)[0])} for s, r in dirs.items()
          if r["state"] == "go" and r.get("lane", "bench") == "bench"]
    quick = _quick_status(root, dirs, on)
    rejected = {}
    for r in dirs.values():
        if r["state"] == "rejected":
            g = r["decision"]["gate"]
            rejected[g] = rejected.get(g, 0) + 1
    rows = run_log.records(root)
    return {"data_root": str(root), "counts": counts, "quick": quick, "found_ranked": L.rank(root, on),
            "parked": parked, "go": go, "rejected_by_gate": rejected, "seeds": seeds.stats(root, on),
            "semrush_calls_total": sum(r["semrush_calls"] for r in rows), "semrush": run_log.semrush_budget(rows)}


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
    c, q = st["counts"], st["quick"]
    for g in q["pending_go"]:
        print(f"【立即建站】{g['slug']}:基准约 {g['base_visits']:,} 次访问、${g['base_revenue']:.2f}/月,"
              f"建议最晚 {g['launch_by']} 上线" + ("(已超期)" if g["overdue"] else "") + f" → {g['doc']}")
    for m in q["milestones_due"]:
        print(f"  验收节点到了:{m['slug']} 上线第 {m['day']} 天({m['date']}),去看 Search Console")
    print(f"数据区:{st['data_root']}")
    print(f"方向:found {c['found']} · go {c['go']} · rejected {c['rejected']} · parked {c['parked']} · 观察中 {c['watching']}")
    for w in q["watching"]:
        print(f"  观察中 {w['slug']}:还剩 {w['days_left']} 天({w['expires_at']} 到期),已复查 {w['checks']} 次")
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
    print(f"快道原料池待看:{q['pool_pending']}")
    b = st["semrush"]
    print(f"今天 Semrush 已用 {b['semrush_calls_today']}/{b['semrush_daily_limit']} 次"
          + ("(到了停止线,今天别再跑 Semrush)" if b["semrush_stop"] else "") + f";累计 {st['semrush_calls_total']} 次")
    return 0


if __name__ == "__main__":
    sys.exit(main())
