"""连续运行的只读动作路由；时间就绪不代表需求或建站通过。"""
from datetime import date

from _common import load_ledger, formation_eligible_date, track_observation_days
from _constants import MIN_TRACK_SPAN_DAYS, TERMINAL
from tracking_schedule import build as schedule


def build(root, today=None):
    today = today or date.today()
    try:
        candidates = load_ledger(root).get("candidates", {})
    except FileNotFoundError:
        return []
    reminders = schedule(root, today)
    due = {r["slug"] for r in reminders["checkpoints"] if r["status"] in {"due_now", "overdue"}}
    result = []
    for slug, rec in sorted(candidates.items()):
        state, lane = rec.get("state"), rec.get("lane", "new")
        if state in TERMINAL:
            continue
        action, reason, not_due = "review", "核对当前证据后决定动作", False
        eligible = None
        if lane == "mature" and state in {"captured", "screened", "tracking"}:
            action, reason = "handoff_mature", "前半程归 xinci-mature；连续运行无权推进"
        elif rec.get("expiry") and date.fromisoformat(rec["expiry"]) < today and state in {"captured", "screened", "tracking", "fast_grab_ready"}:
            action, reason = "expire", "失效日已过，核对到期出口"
        elif state == "tracking":
            eligible = formation_eligible_date(track_observation_days(root, rec), MIN_TRACK_SPAN_DAYS)
            if eligible and eligible <= today:
                action, reason = "review_formation", "形成时间已达标；还需本次 G1、稳定命名和任务级需求证据"
            elif slug in due:
                action, reason = "track", "复查提醒已到；形成时间仍需独立核对"
            else:
                action, reason, not_due = "track_optional", "尚未到复查提醒或形成时间；仍可按新证据复查", True
        elif state == "formation_confirmed":
            pending = rec.get("qualify_pending") or {}
            if pending.get("pending_until") and date.fromisoformat(pending["pending_until"]) > today:
                action, reason, not_due = "await_evidence", "暂缓日期未到；有新证据时可提前复核", True
            else:
                action, reason = "qualify", "核对收入、竞争及证据缺口，未证明可以出 go"
        elif state in {"qualified", "hold"}:
            action, reason = "decide", "先复核有效证据与风险，再做决策"
        elif state == "captured":
            action, reason = "complete_screen", "补齐缺门后按窗口分流"
        elif state == "screened":
            action = "fast_track" if rec.get("window_estimate") == "days" else "enter_tracking"
        from evidence_index import build as evidence_index
        index = evidence_index(root, slug)
        result.append({"slug": slug, "state": state, "lane": lane, "action": action,
                       "reason": reason, "not_due_allowed": not_due,
                       "formation_eligible_date": eligible.isoformat() if eligible else None,
                       "evidence_refs": rec.get("evidence_refs", [])[-1:],
                       "review_required_gates": index["review_required_gates"],
                       "unknown_income_lines": index["unknown_income_lines"],
                       "evidence_errors": index["errors"]})
    return result
