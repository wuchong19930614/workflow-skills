#!/usr/bin/env python3
"""只读看板:各状态计数、found 按排序分、parked 停留天数(超 90 天提醒)、verified 报告路径。零写入。"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import ledger as L

STATE_LABELS = {"found": "待核验", "parked": "已搁置", "verified": "已验证", "rejected": "已否决"}
STALE_DAYS = 90


def _days_since(iso):
    then = datetime.fromisoformat(iso)
    return (datetime.now(timezone.utc) - then).days


def build_report(root) -> dict:
    root = Path(root)
    recs = L.list_candidates(root)
    counts = {}
    for r in recs:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    found = sorted((r for r in recs if r["state"] == "found"),
                   key=lambda r: -((r.get("proxy") or {}).get("rank_score") or -1))
    parked = []
    for r in recs:
        if r["state"] == "parked":
            days = _days_since(r["history"][-1]["at"])
            parked.append({"slug": r["slug"], "days": days, "stale": days > STALE_DAYS,
                           "reason": r["history"][-1]["reason"]})
    verified = []
    for r in recs:
        if r["state"] == "verified":
            rel = f"报告/{r['slug']}.md"
            verified.append({"slug": r["slug"], "form": r["form"], "base": (r["revenue"] or {}).get("base"),
                             "report": rel, "report_exists": (root / rel).is_file()})
    return {
        "counts": counts,
        "found": [{"slug": r["slug"], "primary_keyword": r["primary_keyword"],
                   "cluster_volume": r["cluster"]["total_volume"],
                   "rank_score": (r.get("proxy") or {}).get("rank_score")} for r in found],
        "parked": parked, "verified": verified,
    }


def render_text(rep) -> str:
    out = ["== 各状态候选数 =="]
    for state in ("found", "parked", "verified", "rejected"):
        if state in rep["counts"]:
            out.append(f"{STATE_LABELS[state]}：{rep['counts'][state]}")
    out.append("\n== 待核验（按排序分） ==")
    for r in rep["found"]:
        score = f"{r['rank_score']:.2f}" if r["rank_score"] is not None else "未排序"
        out.append(f"{score}  {r['slug']} — {r['primary_keyword']} | 簇量 {r['cluster_volume']:,}")
    if not rep["found"]:
        out.append("（无）")
    out.append("\n== 已搁置 ==")
    for r in rep["parked"]:
        flag = "  ← 超 90 天未动" if r["stale"] else ""
        out.append(f"{r['slug']} | 停留 {r['days']} 天 | {r['reason']}{flag}")
    if not rep["parked"]:
        out.append("（无）")
    out.append("\n== 已验证 ==")
    for r in rep["verified"]:
        exists = "" if r["report_exists"] else "（报告缺失）"
        out.append(f"{r['slug']} | {r['form']} | base ${r['base']} | {r['report']}{exists}")
    if not rep["verified"]:
        out.append("（无）")
    return "\n".join(out)


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="xinci-simple 只读看板")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    rep = build_report(root)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else render_text(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
