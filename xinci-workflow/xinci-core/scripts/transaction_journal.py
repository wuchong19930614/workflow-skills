#!/usr/bin/env python3
"""账本与运行会话跨文件写入的前滚事务日志。

当前唯一跨文件事务是窗口赌注出闸：消费 session confirmation 与写候选账本必须
作为一个逻辑操作。若进程在两次原子写之间崩溃，pending journal 会阻止后续写入，
`run_controller.py recover` 根据 before hash 幂等前滚到 candidate_after。
"""
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from run_state import RunStateError, load_session, session_path as get_session_path, validate_session


TX_DIR = "事务"
TX_FIELDS = {"schema_version", "tx_id", "kind", "status", "run_id", "slug",
             "prepared_at", "committed_at", "candidate_before_sha256",
             "candidate_after_sha256", "candidate_after", "reconciliation"}
TX_ID_RE = re.compile(r"^tx-(run-\d{8}T\d{6}Z-[a-f0-9]{8})-"
                      r"([a-z0-9][a-z0-9-]*)-(\d+)$")


class TransactionError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _digest(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _dir(data_root) -> Path:
    return Path(data_root) / "运行状态" / TX_DIR


def _timestamp(value, where):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise TransactionError(f"{where} 必须是 ISO 时间")
    if parsed.tzinfo is None:
        raise TransactionError(f"{where} 必须带时区")
    return parsed


def validate_transaction(obj, expected_name=None):
    if not isinstance(obj, dict) or set(obj) - TX_FIELDS:
        raise TransactionError("事务日志字段非法")
    required = TX_FIELDS - {"reconciliation"}
    missing = sorted(required - set(obj))
    if missing:
        raise TransactionError(f"事务日志缺字段 {missing}")
    if obj.get("schema_version") != 2 or obj.get("kind") != "window_bet_transition":
        raise TransactionError("事务日志 schema_version/kind 非法")
    match = TX_ID_RE.fullmatch(obj.get("tx_id") or "")
    if (not match or match.group(1) != obj.get("run_id") or match.group(2) != obj.get("slug")
            or (expected_name and f"{obj['tx_id']}.json" != expected_name)):
        raise TransactionError("事务 tx_id/run_id/slug/文件名不一致")
    if obj.get("status") not in {"prepared", "committed", "reconciled"}:
        raise TransactionError("事务 status 非法")
    prepared = _timestamp(obj.get("prepared_at"), "事务 prepared_at")
    committed = (_timestamp(obj["committed_at"], "事务 committed_at")
                 if obj.get("committed_at") else None)
    if committed and committed < prepared:
        raise TransactionError("事务 committed_at 不得早于 prepared_at")
    for field in ("candidate_before_sha256", "candidate_after_sha256"):
        if not re.fullmatch(r"[a-f0-9]{64}", obj.get(field) or ""):
            raise TransactionError(f"事务 {field} 非法")
    after = obj.get("candidate_after")
    history = after.get("history") if isinstance(after, dict) else None
    if (not isinstance(after, dict) or after.get("slug") != obj.get("slug")
            or after.get("state") != "screened" or not isinstance(history, list) or not history
            or history[-1].get("to") != "screened" or history[-1].get("run_id") != obj.get("run_id")):
        raise TransactionError("事务 candidate_after 不是本次 run 的合法窗口出闸快照")
    if _digest(after) != obj.get("candidate_after_sha256"):
        raise TransactionError("事务 candidate_after 哈希不匹配,疑似被改写")
    reconciliation = obj.get("reconciliation")
    if obj["status"] == "prepared" and (committed or reconciliation):
        raise TransactionError("prepared 事务不得有 committed_at/reconciliation")
    if obj["status"] == "committed" and (not committed or reconciliation):
        raise TransactionError("committed 事务要求 committed_at 且不得有 reconciliation")
    if obj["status"] == "reconciled":
        required_recon = {"decision", "reason", "actor", "confirmation_ref", "at"}
        if not isinstance(reconciliation, dict) or set(reconciliation) != required_recon:
            raise TransactionError("reconciled 事务缺完整 reconciliation")
        if (reconciliation.get("decision") not in {"keep_current", "apply_after"}
                or reconciliation.get("actor") not in {"user", "xinci-run"}
                or not reconciliation.get("reason") or not reconciliation.get("confirmation_ref")):
            raise TransactionError("事务 reconciliation 内容非法")
        reconciled_at = _timestamp(reconciliation.get("at"), "事务 reconciliation.at")
        if reconciled_at < prepared:
            raise TransactionError("事务 reconciliation.at 不得早于 prepared_at")
    return obj


def _load_transaction(path):
    path = Path(path)
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise TransactionError(f"事务日志损坏: {path.name}")
    return validate_transaction(obj, path.name)


def list_pending(data_root, run_id=None):
    out = []
    d = _dir(data_root)
    if not d.is_dir():
        return out
    for path in sorted(d.glob("tx-*.json")):
        obj = _load_transaction(path)
        if obj.get("status") == "prepared" and (run_id is None or obj.get("run_id") == run_id):
            obj["_path"] = str(path)
            out.append(obj)
    return out


def require_clean(data_root):
    pending = list_pending(data_root)
    if pending:
        ids = [x.get("tx_id") for x in pending]
        raise TransactionError(f"存在未恢复事务 {ids};先执行 run_controller.py recover")


def prepare_window_bet(data_root, run_id, slug, candidate_before, candidate_after):
    require_clean(data_root)
    tx_id = f"tx-{run_id}-{slug}-{len(candidate_after.get('history', []))}"
    path = _dir(data_root) / f"{tx_id}.json"
    obj = {
        "schema_version": 2,
        "tx_id": tx_id,
        "kind": "window_bet_transition",
        "status": "prepared",
        "run_id": run_id,
        "slug": slug,
        "prepared_at": _now(),
        "committed_at": None,
        "candidate_before_sha256": _digest(candidate_before),
        "candidate_after_sha256": _digest(candidate_after),
        "candidate_after": candidate_after,
    }
    validate_transaction(obj, path.name)
    _atomic_save(path, obj)
    return path


def mark_committed(path):
    path = Path(path)
    obj = _load_transaction(path)
    obj["status"] = "committed"
    obj["committed_at"] = _now()
    validate_transaction(obj, path.name)
    _atomic_save(path, obj)


def recover(data_root, run_id=None):
    recovered = []
    for tx in list_pending(data_root, run_id):
        if tx.get("kind") != "window_bet_transition":
            raise TransactionError(f"不认识的事务类型: {tx.get('kind')}")
        slug = tx["slug"]
        session_file = get_session_path(data_root, tx["run_id"])
        ledger_path = Path(data_root) / "账本" / "候选账本.json"
        try:
            session = load_session(data_root, tx["run_id"])
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except FileNotFoundError as e:
            raise TransactionError(f"事务恢复缺文件: {e.filename}")
        except (json.JSONDecodeError, UnicodeDecodeError, RunStateError):
            raise TransactionError("事务恢复所需的 session 或账本损坏")
        confirmation = session.get("confirmations", {}).get(slug)
        if (not confirmation or confirmation.get("risk") != "window_bet"
                or confirmation.get("voided_at")):
            raise TransactionError(f"事务 {tx['tx_id']} 缺有效窗口赌注确认")
        current = ledger.get("candidates", {}).get(slug)
        after = tx["candidate_after"]
        if current != after and _digest(current) != tx["candidate_before_sha256"]:
            raise TransactionError(f"事务 {tx['tx_id']} 的候选已发生非预期变化,拒绝覆盖")
        if not confirmation.get("consumed_at"):
            confirmation["consumed_at"] = _now()
        session["updated_at"] = _now()
        validate_session(session, tx["run_id"])
        ledger.setdefault("candidates", {})[slug] = after
        _atomic_save(session_file, session)
        _atomic_save(ledger_path, ledger)
        mark_committed(tx["_path"])
        recovered.append(tx["tx_id"])
    return recovered


def reconcile(data_root, tx_id, decision, reason, actor, confirmation_ref):
    """显式解决无法自动前滚的分歧；只允许人工选择保留当前或应用事务后快照。"""
    if decision not in {"keep_current", "apply_after"}:
        raise TransactionError("reconcile decision 必须是 keep_current 或 apply_after")
    if not reason:
        raise TransactionError("reconcile 要求 reason")
    if actor not in {"user", "xinci-run"} or not confirmation_ref:
        raise TransactionError("reconcile 要求 actor=user|xinci-run 与 confirmation_ref")
    path = _dir(data_root) / f"{tx_id}.json"
    if not path.is_file():
        raise TransactionError(f"事务不存在: {tx_id}")
    tx = _load_transaction(path)
    if tx.get("status") != "prepared":
        raise TransactionError(f"事务不是 prepared: {tx.get('status')}")
    if decision == "apply_after":
        session_file = get_session_path(data_root, tx["run_id"])
        ledger_path = Path(data_root) / "账本" / "候选账本.json"
        try:
            session = load_session(data_root, tx["run_id"])
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, RunStateError) as e:
            raise TransactionError(f"reconcile 读取 session/账本失败: {e}")
        confirmation = session.get("confirmations", {}).get(tx["slug"])
        if (not confirmation or confirmation.get("risk") != "window_bet"
                or confirmation.get("voided_at")):
            raise TransactionError("apply_after 缺原窗口赌注确认")
        if not confirmation.get("consumed_at"):
            confirmation["consumed_at"] = _now()
        session["updated_at"] = _now()
        validate_session(session, tx["run_id"])
        ledger.setdefault("candidates", {})[tx["slug"]] = tx["candidate_after"]
        _atomic_save(session_file, session)
        _atomic_save(ledger_path, ledger)
    else:
        session_file = get_session_path(data_root, tx["run_id"])
        try:
            session = load_session(data_root, tx["run_id"])
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, RunStateError) as e:
            raise TransactionError(f"reconcile 读取 session 失败: {e}")
        confirmation = session.get("confirmations", {}).get(tx["slug"])
        if confirmation and confirmation.get("consumed_at"):
            confirmation["voided_at"] = _now()
            session["updated_at"] = _now()
            validate_session(session, tx["run_id"])
            _atomic_save(session_file, session)
    tx["status"] = "reconciled"
    tx["reconciliation"] = {
        "decision": decision, "reason": reason, "actor": actor,
        "confirmation_ref": confirmation_ref, "at": _now(),
    }
    validate_transaction(tx, path.name)
    _atomic_save(path, tx)
    return tx
