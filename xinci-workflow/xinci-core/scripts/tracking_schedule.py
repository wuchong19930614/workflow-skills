#!/usr/bin/env python3
"""派生 tracking 候选的 3/7/14 天复查提示；只读，不自动转移状态。"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import data_root
from _common import load_ledger

CHECKPOINT_DAYS = (3, 7, 14)


def _day(value):
    return datetime.fromisoformat(value).date()


def _tracking_start(rec):
    """以首次进入 tracking 的历史事实起算；兼容无 history 的旧记录。"""
    for event in rec.get("history", []):
        if event.get("to") == "tracking" and event.get("from") != "tracking" and event.get("at"):
            return _day(event["at"])
    return _day(rec["first_observed_at"])


def build(root, as_of=None):
    as_of = as_of or date.today()
    try:
        candidates = load_ledger(root).get("candidates", {})
    except FileNotFoundError:
        candidates = {}
    rows = []
    for slug, rec in candidates.items():
        if rec.get("lane", "new") != "new" or rec.get("state") != "tracking":
            continue
        start = _tracking_start(rec)
        checked_days = []
        for ref in rec.get("evidence_refs", []):
            if not str(ref).endswith("-track.json"):
                continue
            try:
                obs = json.loads((Path(root) / ref).read_text(encoding="utf-8"))
                checked_days.append(_day(obs["observed_at"]))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        for number in CHECKPOINT_DAYS:
            due = start + timedelta(days=number)
            satisfied = any(day >= due for day in checked_days)
            if satisfied:
                status = "completed"
            elif due < as_of:
                status = "overdue"
            elif due == as_of:
                status = "due_now"
            else:
                status = "upcoming"
            rows.append({"slug": slug, "checkpoint_day": number, "due_date": due.isoformat(),
                         "status": status})
    return {
        "as_of": as_of.isoformat(),
        "advisory_only": True,
        "counts": {status: sum(r["status"] == status for r in rows)
                   for status in ("due_now", "overdue", "upcoming", "completed")},
        "checkpoints": rows,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="派生 3/7/14 天 tracking 复查提示(只读)")
    ap.add_argument("--data-root")
    ap.add_argument("--as-of", type=date.fromisoformat)
    args = ap.parse_args(argv)
    print(json.dumps(build(data_root.resolve_or_exit(args.data_root), args.as_of),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
