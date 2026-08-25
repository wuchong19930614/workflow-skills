#!/usr/bin/env python3
"""把浏览器、积压与真实决策迁移折叠成每轮运行策略。"""
import argparse
import json
import sys
from pathlib import Path

import data_root
from browser_preflight import BrowserPreflightError, show as show_preflight
from run_manifest import find_run_manifest
from run_state import load_session
from trigger_pool import TriggerPoolError, load as load_triggers, stats as trigger_stats


BACKLOG_HARD_LIMIT = 20
TRIGGER_PENDING_LIMIT = 200
STALL_ROUNDS = 3


def _ledger(root):
    path = Path(root) / "账本" / "候选账本.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {"candidates": {}}


def decision_transitions_by_round(root, run_id):
    counts = {}
    for rec in (_ledger(root).get("candidates") or {}).values():
        for row in rec.get("history", []) if isinstance(rec, dict) else []:
            rnd = row.get("round")
            if (row.get("run_id") == run_id and isinstance(rnd, int)
                    and row.get("from") is not None and row.get("to") != row.get("from")):
                counts[rnd] = counts.get(rnd, 0) + 1
    return counts


def evaluate(root, run_id):
    session = load_session(root, run_id)
    candidates = (_ledger(root).get("candidates") or {}).values()
    backlog = sum(1 for rec in candidates if isinstance(rec, dict)
                  and rec.get("lane", "new") == "new" and rec.get("state") == "captured")
    try:
        preflight = show_preflight(root, run_id); g1_ready = preflight["g1_ready"]
        browser_reason = None if g1_ready else "浏览器预检未满足 US/desktop/logged-out/controllable"
    except BrowserPreflightError:
        preflight = None; g1_ready = False; browser_reason = "缺浏览器预检"
    try:
        tstats = trigger_stats(root)
        run_adds = [row for row in load_triggers(root)
                    if row.get("event") == "add" and row.get("run_id") == run_id]
    except TriggerPoolError as e:
        return {"run_id": run_id, "mode": "paused", "formal_admission": False,
                "g1_ready": g1_ready, "reasons": [f"触发池损坏: {e}"]}
    _, manifest = find_run_manifest(root, run_id)
    rounds = manifest.get("rounds", []) if manifest else []
    transitions = decision_transitions_by_round(root, run_id)
    stall = 0
    for rnd in reversed(rounds):
        n = rnd.get("round")
        if transitions.get(n, 0) == 0 and (rnd.get("funnel") or {}).get("queued", 0) > 0:
            stall += 1
        else:
            break
    reasons = []
    family_counts = {}
    for row in run_adds:
        family = row.get("source_family", "(unknown)")
        family_counts[family] = family_counts.get(family, 0) + 1
    dominant_family = max(family_counts, key=family_counts.get) if family_counts else None
    dominant_share = ((family_counts[dominant_family] / len(run_adds)) if dominant_family else 0)
    source_rotation_due = len(run_adds) >= 5 and dominant_share > 0.40
    if browser_reason: reasons.append(browser_reason)
    if backlog > BACKLOG_HARD_LIMIT: reasons.append(f"new captured 积压 {backlog}>{BACKLOG_HARD_LIMIT}")
    if stall >= STALL_ROUNDS: reasons.append(f"连续 {stall} 轮无真实状态迁移且队列继续增长")
    if source_rotation_due:
        reasons.append(f"source family {dominant_family} 占本 run trigger {dominant_share:.0%}>40%，停止该来源并轮换")
    if tstats["pending"] >= TRIGGER_PENDING_LIMIT:
        reasons.append(f"pending trigger 达上限 {TRIGGER_PENDING_LIMIT}")
    if not g1_ready:
        mode = "trigger_only" if tstats["pending"] < TRIGGER_PENDING_LIMIT else "paused"
    elif backlog > BACKLOG_HARD_LIMIT or stall >= STALL_ROUNDS:
        mode = "debt_only"
    else:
        mode = "full"
    return {
        "run_id": run_id, "rounds_completed": session["rounds_completed"], "mode": mode,
        "formal_admission": mode == "full",
        "trigger_harvest": (mode in {"full", "trigger_only"}
                            and not source_rotation_due
                            and tstats["pending"] < TRIGGER_PENDING_LIMIT),
        "g1_ready": g1_ready, "new_captured_backlog": backlog,
        "carryover_quota": min(10, backlog) if mode == "debt_only" else min(5, backlog),
        "pending_triggers": tstats["pending"], "decision_transitions_by_round": transitions,
        "source_family_counts": family_counts, "source_rotation_due": source_rotation_due,
        "consecutive_decision_stall_rounds": stall, "reasons": reasons,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="计算 xinci 当前轮运行策略")
    ap.add_argument("--data-root", default=None); ap.add_argument("--run-id", required=True)
    a = ap.parse_args(argv); root = data_root.resolve_or_exit(a.data_root)
    try: obj = evaluate(root, a.run_id)
    except Exception as e:
        print(f"run_policy 拒绝: {e}", file=sys.stderr); return 2
    print(json.dumps(obj, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    sys.exit(main())
