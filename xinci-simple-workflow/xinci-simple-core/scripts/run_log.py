#!/usr/bin/env python3
"""运行清单:每次 scan / verify 结束写一份小 JSON。审计轨迹,不可覆盖。"""
import argparse
import re
import sys
from pathlib import Path

from _common import atomic_save, now

SKILLS = ("xinci-simple-scan", "xinci-simple-verify")


class RunLogError(Exception):
    pass


def record(root, *, date, skill, sources_opened, candidates_touched, billable_calls, notes,
           suffix=None) -> Path:
    if skill not in SKILLS:
        raise RunLogError(f"skill 须为 {SKILLS}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
        raise RunLogError("date 须为 YYYY-MM-DD")
    if not isinstance(billable_calls, int) or billable_calls < 0:
        raise RunLogError("billable_calls 须为非负整数")
    name = f"{date}-{skill}" + (f"-{suffix}" if suffix else "") + ".json"
    path = Path(root) / "运行" / name
    if path.exists():
        raise RunLogError(f"运行清单已存在,同日再次运行请传 --suffix HHMM: {path.name}")
    seen, urls = set(), []
    for u in sources_opened or []:
        if u not in seen:
            seen.add(u)
            urls.append(u)
    atomic_save(path, {
        "date": date, "skill": skill, "recorded_at": now(),
        "sources_opened": urls,
        "candidates_touched": sorted(set(candidates_touched or [])),
        "billable_calls": billable_calls,
        "notes": list(notes or []),
    })
    return path


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="写运行清单")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--date", required=True)
    ap.add_argument("--skill", required=True, choices=SKILLS)
    ap.add_argument("--suffix", default=None)
    ap.add_argument("--source-opened", action="append", default=[])
    ap.add_argument("--candidate-touched", action="append", default=[])
    ap.add_argument("--billable-calls", type=int, required=True)
    ap.add_argument("--note", action="append", default=[])
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        p = record(root, date=a.date, skill=a.skill, sources_opened=a.source_opened,
                   candidates_touched=a.candidate_touched, billable_calls=a.billable_calls,
                   notes=a.note, suffix=a.suffix)
    except RunLogError as e:
        print(f"拒收: {e}", file=sys.stderr)
        return 1
    print(f"已写 {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
