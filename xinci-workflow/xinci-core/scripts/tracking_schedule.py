#!/usr/bin/env python3
"""派生 tracking 候选的 3/7/14 天复查提示与"最早可提交形成确认的日子";只读，不自动转移状态。"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import data_root
from _common import (formation_eligible_date, load_ledger, span_days,
                     track_observation_days)
from _constants import MIN_TRACK_SPAN_DAYS

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
    rows, formation = [], []
    for slug, rec in candidates.items():
        if rec.get("lane", "new") != "new" or rec.get("state") != "tracking":
            continue
        start = _tracking_start(rec)
        checked_days = track_observation_days(root, rec)
        # 提醒说的是"该再看一眼了",形成确认说的是"够不够跨度",两者此前各按不同锚点算,
        # 于是看板显示"3 日提醒已逾期"而候选其实还差几天才能推进。这里把后者一并算出来,
        # 与 registrar 的判据同源(最早 -track 观察那天 + 7 个自然日)。
        eligible = formation_eligible_date(checked_days, MIN_TRACK_SPAN_DAYS)
        formation.append({
            "slug": slug,
            "track_observations": len(checked_days),
            "earliest_track_day": checked_days[0].isoformat() if checked_days else None,
            "current_span_days": span_days(checked_days) if checked_days else None,
            "formation_eligible_date": eligible.isoformat() if eligible else None,
            "formation_eligible": bool(eligible and eligible <= as_of),
        })
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
        "formation_eligible_now": sorted(f["slug"] for f in formation if f["formation_eligible"]),
        "formation": sorted(formation, key=lambda f: f["slug"]),
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
