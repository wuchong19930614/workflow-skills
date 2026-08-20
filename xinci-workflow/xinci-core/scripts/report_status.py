#!/usr/bin/env python3
"""全局状态汇报(只读)。供 xinci-status 使用;只陈述事实,不推荐动作、不调度。

输出:各状态计数;每候选的年龄天数、距上次复查天数、expiry 余量;
"expiry 已过且非终态"清单。--json 输出机器格式。
"""
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from registrar import TERMINAL, DEFAULT_DATA_ROOT
from chinese_labels import candidate_state_label


def _days_since(iso_ts: str) -> int:
    dt = datetime.fromisoformat(iso_ts)
    return (datetime.now(timezone.utc) - dt).days


def build_report(data_root):
    data_root = Path(data_root)
    ledger_path = data_root / "账本" / "候选账本.json"
    if not ledger_path.is_file():
        raise FileNotFoundError(f"账本不存在: {ledger_path}(先运行 init_workspace.py)")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    today = date.today()

    counts, rows, overdue, recheck_due = {}, [], [], []
    for slug, rec in sorted(ledger.get("candidates", {}).items()):
        state = rec["state"]
        counts[state] = counts.get(state, 0) + 1
        expiry = rec.get("expiry")
        expiry_days = (date.fromisoformat(expiry) - today).days if expiry else None
        recheck_after = rec.get("recheck_after")
        recheck_days = (date.fromisoformat(recheck_after) - today).days if recheck_after else None
        row = {
            "slug": slug,
            "term": rec["term"],
            "state": state,
            "age_days": _days_since(rec["first_observed_at"]),
            "days_since_checked": _days_since(rec["last_checked_at"]),
            "expiry": expiry,
            "expiry_days_left": expiry_days,
            "recheck_after": recheck_after,
            "recheck_days_left": recheck_days,
        }
        rows.append(row)
        if expiry_days is not None and expiry_days < 0 and state not in TERMINAL:
            overdue.append(slug)
        if recheck_days is not None and recheck_days <= 0 and state == "rejected":
            recheck_due.append(slug)
    return {"counts": counts, "candidates": rows, "expired_unhandled": overdue,
            "recheck_due": recheck_due}


def render_text(report) -> str:
    lines = ["== 各状态候选数 =="]
    if not report["counts"]:
        lines.append("(账本为空)")
    for state, n in sorted(report["counts"].items()):
        lines.append(f"{candidate_state_label(state)}：{n}")
    lines.append("")
    lines.append("== 候选明细 ==")
    for r in report["candidates"]:
        exp = "无失效日" if r["expiry"] is None else f"失效日 {r['expiry']}（余 {r['expiry_days_left']} 天）"
        lines.append(f"【{candidate_state_label(r['state'])}】{r['slug']} — {r['term']} | 年龄 {r['age_days']} 天 | "
                     f"距上次复查 {r['days_since_checked']} 天 | {exp}")
    if report["expired_unhandled"]:
        lines.append("")
        lines.append("== 失效日已过且仍未终结（待用户决定） ==")
        for slug in report["expired_unhandled"]:
            lines.append(f"- {slug}")
    if report["recheck_due"]:
        lines.append("")
        lines.append("== 可逆搜索结果页型否决已到复核日 ==")
        for slug in report["recheck_due"]:
            lines.append(f"- {slug}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="xinci 全局状态汇报(只读)")
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        report = build_report(a.data_root)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2) if a.json else render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
