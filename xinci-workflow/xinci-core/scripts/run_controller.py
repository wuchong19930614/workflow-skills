#!/usr/bin/env python3
"""xinci-run 可恢复运行会话控制器。

连续模式的授权不再只靠调用者自报 ``--by xinci-run``。每次运行先创建会话，
每轮显式 begin/record-round；registrar 只接受处于 active/current_round 状态的 run_id。
会话文件位于 数据/新词工作流/运行状态/<run-id>.json，并使用原子替换写入。
"""
import argparse
import json
import os
import secrets
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from transaction_journal import (TransactionError, recover as recover_transactions,
                                 reconcile as reconcile_transaction, require_clean)
from run_state import (SESSION_DIR, RUN_ID_RE, FINAL_STATUSES, RunStateError,
                       load_session, session_path, validate_session)
from run_manifest import (RunManifestError, append_round, candidates_by_run,
                          candidates_by_round, create_run_manifest, find_run_manifest,
                          validate_runs)

try:
    import fcntl

    def _flock(f):
        fcntl.flock(f, fcntl.LOCK_EX)

    def _funlock(f):
        fcntl.flock(f, fcntl.LOCK_UN)
except ImportError:  # pragma: no cover - Windows fallback
    import msvcrt

    def _flock(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def _funlock(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[3] / "数据" / "新词工作流"
GO_STATES = {"fast_grab_ready", "pilot_ready", "build_ready"}
RunControllerError = RunStateError


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session_dir(data_root):
    return Path(data_root) / SESSION_DIR


def _path(data_root, run_id):
    return session_path(data_root, run_id)


@contextmanager
def _locked(data_root):
    d = _session_dir(data_root)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / ".lock", "w") as f:
        _flock(f)
        try:
            yield
        finally:
            _funlock(f)


def _save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def active_sessions(data_root):
    d = _session_dir(data_root)
    if not d.is_dir():
        return []
    out = []
    for path in sorted(d.glob("run-*.json")):
        try:
            obj = load_session(data_root, path.stem)
        except RunStateError as e:
            raise RunControllerError(f"运行会话损坏,为防止授权绕过已停止写入: {e}")
        if obj.get("status") == "active":
            out.append(obj)
    return out


def list_sessions(data_root):
    d = _session_dir(data_root)
    rows = []
    for path in sorted(d.glob("run-*.json")) if d.is_dir() else []:
        obj = load_session(data_root, path.stem)
        rows.append({key: obj.get(key) for key in
                     ("run_id", "status", "started_at", "updated_at",
                      "rounds_completed", "current_round", "max_rounds")})
    return {"active": [row["run_id"] for row in rows if row["status"] == "active"],
            "sessions": rows}


def start(data_root, max_rounds=6, max_hours=None):
    if not isinstance(max_rounds, int) or max_rounds < 1:
        raise RunControllerError("max_rounds 必须是正整数")
    if max_hours is not None and max_hours <= 0:
        raise RunControllerError("max_hours 必须大于 0")
    with _locked(data_root):
        try:
            require_clean(data_root)
        except TransactionError as e:
            raise RunControllerError(str(e))
        existing = active_sessions(data_root)
        if existing:
            raise RunControllerError(f"已有活动运行会话: {existing[0]['run_id']};先恢复或结束它")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"run-{stamp}-{secrets.token_hex(4)}"
        obj = {
            "schema_version": 1,
            "run_id": run_id,
            "mode": "continuous",
            "status": "active",
            "started_at": _now(),
            "updated_at": _now(),
            "max_rounds": max_rounds,
            "max_hours": max_hours,
            "rounds_completed": 0,
            "current_round": None,
            "confirmations": {},
            "finish_reason": None,
        }
        validate_session(obj, run_id)
        _save(_path(data_root, run_id), obj)
        return obj


def begin_round(data_root, run_id):
    with _locked(data_root):
        try:
            require_clean(data_root)
        except TransactionError as e:
            raise RunControllerError(str(e))
        obj = load_session(data_root, run_id)
        if obj.get("status") != "active":
            raise RunControllerError(f"运行会话不是 active: {obj.get('status')}")
        if obj.get("current_round") is not None:
            raise RunControllerError(f"第 {obj['current_round']} 轮尚未结束")
        if obj["rounds_completed"] >= obj["max_rounds"]:
            raise RunControllerError("轮次预算已命中;请 finish --status budget_reached")
        if obj.get("max_hours") is not None:
            started = datetime.fromisoformat(obj["started_at"])
            elapsed_hours = (datetime.now(timezone.utc) - started).total_seconds() / 3600
            if elapsed_hours >= obj["max_hours"]:
                raise RunControllerError("时长预算已命中;请 finish --status budget_reached")
        obj["current_round"] = obj["rounds_completed"] + 1
        obj["updated_at"] = _now()
        validate_session(obj, run_id)
        _save(_path(data_root, run_id), obj)
        return obj


def end_round(data_root, run_id):
    """兼容 API 的明确拒绝；轮次只能由 record_round 带清单事实原子收尾。"""
    raise RunControllerError("end-round 已停用;使用 record-round 写清单并结束轮次")


def record_round(data_root, run_id, *, sources_opened=None, sources_blocked=None,
                 billable_calls=0, notes=None, funnel=None):
    with _locked(data_root):
        try:
            require_clean(data_root)
        except TransactionError as e:
            raise RunControllerError(str(e))
        obj = load_session(data_root, run_id)
        if obj.get("status") != "active" or obj.get("current_round") is None:
            raise RunControllerError("没有正在执行的轮次")
        for label, values in (("sources_opened", sources_opened or []),
                              ("sources_blocked", sources_blocked or []),
                              ("notes", notes or [])):
            if not isinstance(values, list) or not all(isinstance(x, str) and x for x in values):
                raise RunControllerError(f"{label} 必须是非空字符串数组")
        if not isinstance(billable_calls, int) or isinstance(billable_calls, bool) or billable_calls < 0:
            raise RunControllerError("billable_calls 必须是非负整数")
        if not isinstance(funnel, dict):
            raise RunControllerError("record-round 必须提交 funnel 对象;未扫描时五项都写 0")
        current = obj["current_round"]
        manifest_path, manifest = find_run_manifest(data_root, run_id)
        existing_rounds = manifest.get("rounds", []) if manifest else []
        already = existing_rounds[-1] if len(existing_rounds) == current else None
        if already:
            touched = already.get("candidates_touched") or []
        else:
            round_touched = candidates_by_round(data_root).get((run_id, current), set())
            if round_touched:
                touched = sorted(round_touched)
            else:  # 兼容轮号字段建立前、尚未收尾的活动会话
                all_touched = candidates_by_run(data_root).get(run_id, set())
                prior_touched = set()
                for rnd in existing_rounds:
                    prior_touched.update(rnd.get("candidates_touched") or [])
                touched = sorted(all_touched - prior_touched)
        round_record = {
            "round": current,
            "sources_opened": list(sources_opened or []),
            "sources_blocked": list(sources_blocked or []),
            "candidates_touched": touched,
            "billable_calls": billable_calls,
            "funnel": dict(funnel),
            "notes": list(notes or []),
        }
        try:
            manifest_path, _ = append_round(data_root, obj, round_record)
        except RunManifestError as e:
            raise RunControllerError(str(e))
        obj["rounds_completed"] = obj["current_round"]
        obj["current_round"] = None
        obj["updated_at"] = _now()
        validate_session(obj, run_id)
        _save(_path(data_root, run_id), obj)
        return {"session": obj, "manifest": str(manifest_path), "round": round_record}


def confirm_window_bet(data_root, run_id, slug):
    """记录用户在候选被判为窗口赌注后给出的单步确认。

    本命令只能在用户明确确认后由执行者调用。registrar 会核对候选 slug 与活动 run_id，
    避免连续模式通过伪造 ``--by`` 意外绕过风险边界。
    """
    if not slug:
        raise RunControllerError("slug 不可为空")
    with _locked(data_root):
        try:
            require_clean(data_root)
        except TransactionError as e:
            raise RunControllerError(str(e))
        obj = load_session(data_root, run_id)
        if obj.get("status") != "active":
            raise RunControllerError("只能给活动运行会话记录确认")
        ledger_path = Path(data_root) / "账本" / "候选账本.json"
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise RunControllerError("窗口赌注确认要求候选已写入账本")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RunControllerError("候选账本损坏,不能记录窗口赌注确认")
        candidate = ledger.get("candidates", {}).get(slug)
        if not candidate:
            raise RunControllerError(f"窗口赌注候选不存在: {slug}")
        if candidate.get("state") != "captured" or candidate.get("gates", {}).get("G3") != "veto_window_bet":
            raise RunControllerError(
                f"候选 {slug} 必须先以 captured 且 G3=veto_window_bet 写入账本,再由用户确认")
        confirmations = obj.setdefault("confirmations", {})
        previous = confirmations.get(slug)
        if previous and not previous.get("voided_at"):
            raise RunControllerError(f"候选 {slug} 已记录过窗口赌注确认;确认不可覆盖或重新激活")
        history = []
        if previous:
            history = list(previous.get("history") or [])
            history.append({k: previous.get(k) for k in
                            ("risk", "confirmed_at", "consumed_at", "voided_at")})
        confirmations[slug] = {
            "risk": "window_bet",
            "confirmed_at": _now(),
            "consumed_at": None,
            "voided_at": None,
            "history": history,
        }
        obj["updated_at"] = _now()
        validate_session(obj, run_id)
        _save(_path(data_root, run_id), obj)
        return obj


def consume_window_bet_confirmation(data_root, run_id, slug):
    with _locked(data_root):
        obj = load_session(data_root, run_id)
        rec = obj.get("confirmations", {}).get(slug)
        if (not rec or rec.get("risk") != "window_bet" or rec.get("consumed_at")
                or rec.get("voided_at")):
            raise RunControllerError(f"候选 {slug} 没有未消费的窗口赌注确认")
        rec["consumed_at"] = _now()
        obj["updated_at"] = _now()
        validate_session(obj, run_id)
        _save(_path(data_root, run_id), obj)


def require_active_round(data_root, run_id):
    obj = load_session(data_root, run_id)
    if obj.get("status") != "active" or obj.get("current_round") is None:
        raise RunControllerError("xinci-run 写入要求活动 run_id 且已 begin-round")
    return obj


def recover(data_root, run_id=None):
    """幂等前滚未完成事务；恢复期间持有 session 总锁，避免并发启动/结束。"""
    with _locked(data_root):
        try:
            return recover_transactions(data_root, run_id)
        except TransactionError as e:
            raise RunControllerError(str(e))


def reconcile(data_root, tx_id, decision, reason, actor, confirmation_ref):
    with _locked(data_root):
        try:
            return reconcile_transaction(data_root, tx_id, decision, reason,
                                         actor, confirmation_ref)
        except TransactionError as e:
            raise RunControllerError(str(e))


def finish(data_root, run_id, status, reason):
    if status not in FINAL_STATUSES:
        raise RunControllerError(f"status 必须属于 {sorted(FINAL_STATUSES)}")
    if not reason:
        raise RunControllerError("finish 要求 reason")
    with _locked(data_root):
        try:
            require_clean(data_root)
        except TransactionError as e:
            raise RunControllerError(str(e))
        obj = load_session(data_root, run_id)
        if obj.get("status") != "active":
            raise RunControllerError(f"运行会话已经结束: {obj.get('status')}")
        if obj.get("current_round") is not None:
            raise RunControllerError("当前轮次尚未 record-round")
        try:
            manifest_path, manifest = find_run_manifest(data_root, run_id)
            if manifest_path is None:
                manifest_path, manifest = create_run_manifest(data_root, obj)
        except RunManifestError as e:
            raise RunControllerError(str(e))
        manifest_errors = validate_runs(data_root)
        if manifest_errors:
            raise RunControllerError("manifest 未通过完整校验: " + "; ".join(manifest_errors))
        rounds = manifest.get("rounds")
        if not isinstance(rounds, list) or len(rounds) != obj.get("rounds_completed"):
            raise RunControllerError(
                f"manifest rounds 与 session.rounds_completed 不一致: {manifest_path.name}")
        numbers = [x.get("round") for x in rounds if isinstance(x, dict)]
        if numbers != list(range(1, len(rounds) + 1)):
            raise RunControllerError("manifest round 必须从 1 开始连续且不重复")
        ledger_path = Path(data_root) / "账本" / "候选账本.json"
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            ledger = {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RunControllerError("候选账本损坏,不能结束运行")
        produced_by_run = {
            slug for slug, rec in ledger.get("candidates", {}).items()
            if isinstance(rec, dict)
            and any(isinstance(h, dict) and h.get("run_id") == run_id
                    for h in rec.get("history", []))
        }
        top_touched = manifest.get("candidates_touched") or []
        if (not isinstance(top_touched, list)
                or not all(isinstance(x, str) and x for x in top_touched)):
            raise RunControllerError("manifest candidates_touched 必须是非空字符串数组")
        touched = set(top_touched)
        for rnd in rounds:
            round_touched = rnd.get("candidates_touched") or []
            if (not isinstance(round_touched, list)
                    or not all(isinstance(x, str) and x for x in round_touched)):
                raise RunControllerError("manifest rounds[].candidates_touched 必须是非空字符串数组")
            touched.update(round_touched)
        missing = sorted(produced_by_run - touched)
        if missing:
            raise RunControllerError(
                f"manifest candidates_touched 漏记本次运行写过的候选: {missing}")
        if status == "go":
            if not ledger:
                raise RunControllerError("go 结束要求候选账本中存在本次运行产出的 GO 候选")
            produced = [
                slug for slug, rec in ledger.get("candidates", {}).items()
                if rec.get("state") in GO_STATES
                and any(h.get("run_id") == run_id and h.get("to") in GO_STATES
                        for h in rec.get("history", []))
            ]
            if not produced:
                raise RunControllerError(
                    "go 结束要求至少一个当前仍处于 fast_grab_ready/pilot_ready/build_ready、"
                    "且由本次 run_id 转入该状态的候选")
            obj["go_candidates"] = produced
        obj["status"] = status
        obj["finish_reason"] = reason
        obj["finished_at"] = _now()
        obj["updated_at"] = obj["finished_at"]
        validate_session(obj, run_id)
        _save(_path(data_root, run_id), obj)
        return obj


def main(argv=None):
    ap = argparse.ArgumentParser(description="xinci-run 可恢复运行会话控制器")
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    p.add_argument("--max-rounds", type=int, default=6)
    p.add_argument("--max-hours", type=float)
    sub.add_parser("list", help="列出会话摘要并直接给出 active run_id")
    for name in ("begin-round", "show"):
        p = sub.add_parser(name)
        p.add_argument("--run-id", required=True)
    p = sub.add_parser("record-round", help="原子追加运行清单并结束当前轮")
    p.add_argument("--run-id", required=True)
    p.add_argument("--source-opened", action="append", default=[])
    p.add_argument("--source-blocked", action="append", default=[])
    p.add_argument("--billable-calls", type=int, default=0)
    p.add_argument("--note", action="append", default=[])
    p.add_argument("--funnel", required=True, help="漏斗 JSON 对象;未扫描时五项全 0")
    p = sub.add_parser("confirm-window-bet")
    p.add_argument("--run-id", required=True)
    p.add_argument("--slug", required=True)
    p = sub.add_parser("finish")
    p.add_argument("--run-id", required=True)
    p.add_argument("--status", choices=sorted(FINAL_STATUSES), required=True)
    p.add_argument("--reason", required=True)
    p = sub.add_parser("recover", help="前滚恢复未完成的跨文件事务")
    p.add_argument("--run-id")
    p = sub.add_parser("reconcile", help="人工解决无法自动前滚的分歧事务")
    p.add_argument("--tx-id", required=True)
    p.add_argument("--decision", choices=["keep_current", "apply_after"], required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--by", choices=["user", "xinci-run"], required=True)
    p.add_argument("--confirmation-ref", required=True,
                   help="用户确认消息/任务引用或审计票据 ID")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "start":
            obj = start(a.data_root, a.max_rounds, a.max_hours)
        elif a.cmd == "list":
            obj = list_sessions(a.data_root)
        elif a.cmd == "begin-round":
            obj = begin_round(a.data_root, a.run_id)
        elif a.cmd == "record-round":
            try:
                funnel = json.loads(a.funnel)
            except json.JSONDecodeError as e:
                raise RunControllerError(f"--funnel 不是合法 JSON: {e}")
            obj = record_round(a.data_root, a.run_id,
                               sources_opened=a.source_opened,
                               sources_blocked=a.source_blocked,
                               billable_calls=a.billable_calls,
                               notes=a.note, funnel=funnel)
        elif a.cmd == "confirm-window-bet":
            obj = confirm_window_bet(a.data_root, a.run_id, a.slug)
        elif a.cmd == "finish":
            obj = finish(a.data_root, a.run_id, a.status, a.reason)
        elif a.cmd == "recover":
            obj = {"recovered": recover(a.data_root, a.run_id)}
        elif a.cmd == "reconcile":
            obj = reconcile(a.data_root, a.tx_id, a.decision, a.reason,
                            a.by, a.confirmation_ref)
        else:
            obj = load_session(a.data_root, a.run_id)
    except (RunControllerError, TransactionError) as e:
        print(f"run_controller 拒绝: {e}", file=sys.stderr)
        return 2
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
