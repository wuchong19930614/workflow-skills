#!/usr/bin/env python3
"""把浏览器、积压与真实决策迁移折叠成每轮运行策略。"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import data_root
from _common import load_ledger
from _constants import MIN_TRACK_SPAN_DAYS
from run_manifest import find_run_manifest
from run_state import load_session
from trigger_pool import TriggerPoolError, source_rotation_status, stats as trigger_stats


BACKLOG_HARD_LIMIT = 20
TRIGGER_PENDING_LIMIT = 200
STALL_ROUNDS = 3


def _ledger(root):
    try:
        return load_ledger(root)
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


def captured_backlog_delta_by_round(root, run_id):
    """按 history 重放本次 run 对 new/captured 积压造成的净变化。

    register(无来源态→captured)记 +1；从 captured 真正离开记 -1。amend/checked
    不改变积压。这样“队列增长”描述的是净积压增长，而不是本轮碰巧 queued>0。
    """
    deltas = {}
    for rec in (_ledger(root).get("candidates") or {}).values():
        if not isinstance(rec, dict) or rec.get("lane", "new") != "new":
            continue
        for row in rec.get("history", []):
            rnd = row.get("round")
            if row.get("run_id") != run_id or not isinstance(rnd, int):
                continue
            frm, to = row.get("from"), row.get("to")
            delta = (1 if to == "captured" and frm != "captured" else 0)
            delta -= (1 if frm == "captured" and to != "captured" else 0)
            if delta:
                deltas[rnd] = deltas.get(rnd, 0) + delta
    return deltas


def _track_days(root, rec):
    """该候选已登记的 -track 观察日期;读不出的证据跳过,策略计算不因证据损坏而崩。"""
    days = []
    for ref in rec.get("evidence_refs", []) or []:
        if not str(ref).endswith("-track.json"):
            continue
        try:
            obs = json.loads((Path(root) / ref).read_text(encoding="utf-8"))
            days.append(datetime.fromisoformat(obs["observed_at"]).date())
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return days


def reachable_ceiling(root, mode, today=None):
    """本次运行在当前账本下最远能推进到哪一步。

    这是预算提示,不是许可或禁止:天花板为 tracking 不表示不该扫描——本轮新扫出的、
    窗口以天计的候选照样可以走快道直达 go。它要回答的只是"存量能不能出结论",
    好让执行者一开始就知道该把轮次花在推存量还是补触发池,而不是跑几轮才发现。
    """
    today = today or date.today()
    if mode in {"trigger_only", "paused"}:
        return {"state": "trigger_only", "enablers": [],
                "why": "浏览器不满足 G1 前置或触发池已满,本轮不能注册正式候选,"
                       "只能维护触发池"}
    candidates = (_ledger(root).get("candidates") or {})
    go_ready, formation_ready = [], []
    for slug, rec in candidates.items():
        if not isinstance(rec, dict):
            continue
        state = rec.get("state")
        lane = rec.get("lane", "new")
        # mature 前半程不属于连续运行；到 formation_confirmed 后与 new 共用认定/决策。
        if lane == "mature" and state in {"captured", "screened", "tracking"}:
            continue
        if state in {"qualified", "hold", "formation_confirmed"}:
            go_ready.append(slug)
        elif state == "screened" and rec.get("window_estimate") == "days":
            go_ready.append(slug)
        elif state == "tracking":
            days = _track_days(root, rec)
            # 本次复查会新增一份观察,故只要最早那份已满 7 天就够跨度
            if days and (today - min(days)).days >= MIN_TRACK_SPAN_DAYS:
                formation_ready.append(slug)
    if go_ready:
        return {"state": "go", "enablers": sorted(go_ready),
                "why": "存在可在本次运行内走到 go 决策的候选(qualified/hold/"
                       "formation_confirmed,或窗口以天计的 screened)"}
    if formation_ready:
        return {"state": "go", "enablers": sorted(formation_ready),
                "why": f"追踪中候选的最早 -track 观察已满 {MIN_TRACK_SPAN_DAYS} 天,"
                       "本次复查即可凑齐形成跨度,之后可一路走到 go"}
    return {"state": "tracking", "enablers": [],
            "why": f"存量里没有能满足 {MIN_TRACK_SPAN_DAYS} 天形成跨度的候选,"
                   "存量侧本次最远只能推进到 tracking;新扫出窗口以天计的候选仍可走快道到 go"}


def evaluate(root, run_id):
    session = load_session(root, run_id)
    target_round = session.get("current_round") or session["rounds_completed"] + 1
    candidates = (_ledger(root).get("candidates") or {}).values()
    backlog = sum(1 for rec in candidates if isinstance(rec, dict)
                  and rec.get("lane", "new") == "new" and rec.get("state") == "captured")
    # 预检随 begin-round 写进 session 当前轮;轮次未开始或本轮没报预检都按"缺预检"处理
    preflight = session.get("current_round_preflight")
    if preflight is None:
        g1_ready = False; browser_reason = "缺浏览器预检(begin-round 时提交 --browser-* 四项)"
    else:
        g1_ready = preflight["g1_ready"]
        browser_reason = None if g1_ready else "浏览器预检未满足 US/desktop/logged-out/controllable"
    try:
        tstats = trigger_stats(root)
    except TriggerPoolError as e:
        return {"run_id": run_id, "mode": "paused", "formal_admission": False,
                "g1_ready": g1_ready, "reasons": [f"触发池损坏: {e}"]}
    _, manifest = find_run_manifest(root, run_id)
    rounds = manifest.get("rounds", []) if manifest else []
    transitions = decision_transitions_by_round(root, run_id)
    backlog_deltas = captured_backlog_delta_by_round(root, run_id)
    stall = 0
    for rnd in reversed(rounds):
        n = rnd.get("round")
        if transitions.get(n, 0) == 0 and backlog_deltas.get(n, 0) > 0:
            stall += 1
        else:
            break
    reasons = []
    rotation = source_rotation_status(root, run_id, target_round)
    family_counts = rotation["family_counts"]
    blocked_source_families = rotation["blocked_source_families"]
    source_rotation_due = bool(blocked_source_families)
    if browser_reason: reasons.append(browser_reason)
    if backlog > BACKLOG_HARD_LIMIT: reasons.append(f"new captured 积压 {backlog}>{BACKLOG_HARD_LIMIT}")
    if stall >= STALL_ROUNDS: reasons.append(f"连续 {stall} 轮无真实状态迁移且队列继续增长")
    total_family_count = sum(family_counts.values())
    for family in blocked_source_families:
        share = family_counts.get(family, 0) / total_family_count if total_family_count else 0
        if share > 0.40:
            reasons.append(f"source family {family} 占本 run trigger {share:.0%}>40%，停止该来源并轮换")
    if rotation["consecutive_family"]:
        reasons.append(f"source family {rotation['consecutive_family']} 已连续主导两轮，本轮必须轮换")
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
                            and tstats["pending"] < TRIGGER_PENDING_LIMIT),
        "g1_ready": g1_ready, "new_captured_backlog": backlog,
        "carryover_quota": min(10, backlog) if mode == "debt_only" else min(5, backlog),
        "pending_triggers": tstats["pending"], "decision_transitions_by_round": transitions,
        "captured_backlog_delta_by_round": backlog_deltas,
        "source_family_counts": family_counts, "source_rotation_due": source_rotation_due,
        "blocked_source_families": blocked_source_families,
        "consecutive_decision_stall_rounds": stall,
        "reachable_ceiling": reachable_ceiling(root, mode), "reasons": reasons,
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
