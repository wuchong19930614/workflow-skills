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

import data_root
from _common import (formation_eligible_date, ledger_path, load_ledger, span_days,
                     track_observation_days)
from _constants import MIN_TRACK_SPAN_DAYS, TERMINAL
from chinese_labels import candidate_state_label


def _days_since(iso_ts: str) -> int:
    dt = datetime.fromisoformat(iso_ts)
    return (datetime.now(timezone.utc) - dt).days


def build_report(data_root):
    data_root = Path(data_root)
    if not ledger_path(data_root).is_file():
        raise FileNotFoundError(f"账本不存在: {ledger_path(data_root)}(先运行 init_workspace.py)")
    ledger = load_ledger(data_root)
    today = date.today()

    counts, rows, overdue, recheck_due = {}, [], [], []
    for slug, rec in sorted(ledger.get("candidates", {}).items()):
        state = rec["state"]
        counts[state] = counts.get(state, 0) + 1
        expiry = rec.get("expiry")
        expiry_days = (date.fromisoformat(expiry) - today).days if expiry else None
        recheck_after = rec.get("recheck_after")
        recheck_days = (date.fromisoformat(recheck_after) - today).days if recheck_after else None
        # 追踪中候选额外报"最早可提交形成确认的自然日":与 registrar 判据同源,
        # 免得再拿 history 时间戳或 3/7/14 天提醒去推断能不能推进。
        track_days = track_observation_days(data_root, rec) if state == "tracking" else []
        eligible = formation_eligible_date(track_days, MIN_TRACK_SPAN_DAYS)
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
            "track_observations": len(track_days) or None,
            "formation_span_days": span_days(track_days) if track_days else None,
            "formation_eligible_date": eligible.isoformat() if eligible else None,
            "formation_eligible_days_left": (eligible - today).days if eligible else None,
            "qualify_pending": rec.get("qualify_pending"),
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
        formation = ""
        if r["formation_eligible_date"]:
            left = r["formation_eligible_days_left"]
            formation = (f" | 形成跨度 {r['formation_span_days']}/{MIN_TRACK_SPAN_DAYS} 天"
                         + (f"，可推进（自 {r['formation_eligible_date']}）" if left <= 0
                            else f"，{r['formation_eligible_date']} 起可推进（余 {left} 天）"))
        pending = r.get("qualify_pending")
        if pending:
            left = (date.fromisoformat(pending["pending_until"]) - today).days
            formation += (f" | 认定暂缓至 {pending['pending_until']}"
                          + ("（已到期，该按现有证据出结论）" if left < 0 else f"（余 {left} 天）")
                          + "，待补：" + "、".join(pending["pending_evidence"]))
        lines.append(f"【{candidate_state_label(r['state'])}】{r['slug']} — {r['term']} | 年龄 {r['age_days']} 天 | "
                     f"距上次复查 {r['days_since_checked']} 天 | {exp}{formation}")
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
    ap.add_argument("--data-root", default=None,
                    help="数据区路径。不给则按 XINCI_DATA_ROOT 环境变量、再按仓库配置 .xinci-data-root 解析;都没有则拒绝执行并提示先问用户")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    # 数据区未配置时在这里就停,并打印「先问用户」的指引,
    # 不让空路径流进下游写操作(理由见 data_root.py)。
    a.data_root = data_root.resolve_or_exit(a.data_root)
    try:
        report = build_report(a.data_root)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2) if a.json else render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
