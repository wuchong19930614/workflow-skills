#!/usr/bin/env python3
"""xinci-run session 的共享契约与载入器。"""
import json
import re
from datetime import datetime
from pathlib import Path


SESSION_DIR = "运行状态"
RUN_ID_RE = re.compile(r"^run-\d{8}T\d{6}Z-[a-f0-9]{8}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FINAL_STATUSES = {"go", "quota_exhausted", "budget_reached", "resource_exhausted",
                  "blocked", "cancelled"}
STATUSES = {"active"} | FINAL_STATUSES
FIELDS = {"schema_version", "run_id", "mode", "status", "started_at", "updated_at",
          "finished_at", "max_rounds", "max_hours", "rounds_completed", "current_round",
          "confirmations", "finish_reason", "go_candidates"}
REQUIRED = {"schema_version", "run_id", "mode", "status", "started_at", "updated_at",
            "max_rounds", "max_hours", "rounds_completed", "current_round",
            "confirmations", "finish_reason"}
CONFIRM_FIELDS = {"risk", "confirmed_at", "consumed_at", "voided_at", "history"}
CONFIRM_HISTORY_FIELDS = {"risk", "confirmed_at", "consumed_at", "voided_at"}


class RunStateError(Exception):
    pass


def _timestamp(value, where):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise RunStateError(f"{where} 必须是 ISO 时间")
    if parsed.tzinfo is None:
        raise RunStateError(f"{where} 必须带时区")
    return parsed


def _confirmation(rec, where):
    if not isinstance(rec, dict) or set(rec) != CONFIRM_FIELDS:
        raise RunStateError(f"{where} 字段必须严格匹配 {sorted(CONFIRM_FIELDS)}")
    if rec.get("risk") != "window_bet":
        raise RunStateError(f"{where}.risk 必须是 window_bet")
    confirmed = _timestamp(rec.get("confirmed_at"), f"{where}.confirmed_at")
    consumed = (_timestamp(rec["consumed_at"], f"{where}.consumed_at")
                if rec.get("consumed_at") else None)
    voided = (_timestamp(rec["voided_at"], f"{where}.voided_at")
              if rec.get("voided_at") else None)
    if consumed and consumed < confirmed:
        raise RunStateError(f"{where}.consumed_at 不得早于 confirmed_at")
    if voided and (not consumed or voided < consumed):
        raise RunStateError(f"{where}.voided_at 只可在消费后产生且不得早于 consumed_at")
    history = rec.get("history")
    if not isinstance(history, list):
        raise RunStateError(f"{where}.history 必须是数组")
    for i, old in enumerate(history):
        old_where = f"{where}.history[{i}]"
        if not isinstance(old, dict) or set(old) != CONFIRM_HISTORY_FIELDS:
            raise RunStateError(f"{old_where} 字段非法")
        if old.get("risk") != "window_bet" or not old.get("consumed_at") or not old.get("voided_at"):
            raise RunStateError(f"{old_where} 必须是已消费且已作废的 window_bet 确认")
        old_confirmed = _timestamp(old.get("confirmed_at"), f"{old_where}.confirmed_at")
        old_consumed = _timestamp(old.get("consumed_at"), f"{old_where}.consumed_at")
        old_voided = _timestamp(old.get("voided_at"), f"{old_where}.voided_at")
        if not old_confirmed <= old_consumed <= old_voided:
            raise RunStateError(f"{old_where} 时间顺序非法")


def validate_session(obj, expected_run_id=None, where="运行会话"):
    if not isinstance(obj, dict):
        raise RunStateError(f"{where} 必须是 JSON 对象")
    unknown = sorted(set(obj) - FIELDS)
    missing = sorted(REQUIRED - set(obj))
    if unknown or missing:
        raise RunStateError(f"{where} 字段非法: unknown={unknown}, missing={missing}")
    if obj.get("schema_version") != 1 or obj.get("mode") != "continuous":
        raise RunStateError(f"{where} schema_version/mode 非法")
    run_id = obj.get("run_id")
    if not RUN_ID_RE.fullmatch(run_id or "") or (expected_run_id and run_id != expected_run_id):
        raise RunStateError(f"{where} run_id 与文件名不一致或格式非法")
    status = obj.get("status")
    if status not in STATUSES:
        raise RunStateError(f"{where} status 非法: {status!r}")
    started = _timestamp(obj.get("started_at"), f"{where}.started_at")
    updated = _timestamp(obj.get("updated_at"), f"{where}.updated_at")
    if updated < started:
        raise RunStateError(f"{where}.updated_at 不得早于 started_at")
    max_rounds = obj.get("max_rounds")
    completed = obj.get("rounds_completed")
    current = obj.get("current_round")
    if (not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or max_rounds < 1
            or not isinstance(completed, int) or isinstance(completed, bool)
            or not 0 <= completed <= max_rounds):
        raise RunStateError(f"{where} max_rounds/rounds_completed 非法")
    max_hours = obj.get("max_hours")
    if max_hours is not None and (isinstance(max_hours, bool)
                                  or not isinstance(max_hours, (int, float)) or max_hours <= 0):
        raise RunStateError(f"{where}.max_hours 必须为 null 或正数")
    if status == "active":
        if current is not None and current != completed + 1:
            raise RunStateError(f"{where}.current_round 必须为 null 或 rounds_completed+1")
        if current is not None and current > max_rounds:
            raise RunStateError(f"{where}.current_round 超出 max_rounds")
        if obj.get("finished_at") is not None or obj.get("finish_reason") is not None:
            raise RunStateError(f"{where} active 状态不得有 finished_at/finish_reason")
        if obj.get("go_candidates") is not None:
            raise RunStateError(f"{where} active 状态不得有 go_candidates")
    else:
        if current is not None or not obj.get("finish_reason") or not obj.get("finished_at"):
            raise RunStateError(f"{where} 结束状态要求 current_round=null、finish_reason、finished_at")
        finished = _timestamp(obj["finished_at"], f"{where}.finished_at")
        if not started <= finished <= updated:
            raise RunStateError(f"{where} finished_at 时间顺序非法")
        go_candidates = obj.get("go_candidates")
        if status == "go":
            if (not isinstance(go_candidates, list) or not go_candidates
                    or len(set(go_candidates)) != len(go_candidates)
                    or not all(isinstance(x, str) and SLUG_RE.fullmatch(x) for x in go_candidates)):
                raise RunStateError(f"{where} go 状态要求非空且唯一的 go_candidates")
        elif go_candidates is not None:
            raise RunStateError(f"{where} 非 go 结束状态不得有 go_candidates")
    confirmations = obj.get("confirmations")
    if not isinstance(confirmations, dict):
        raise RunStateError(f"{where}.confirmations 必须是对象")
    for slug, rec in confirmations.items():
        if not SLUG_RE.fullmatch(slug):
            raise RunStateError(f"{where}.confirmations 含非法 slug: {slug!r}")
        _confirmation(rec, f"{where}.confirmations[{slug}]")
    return obj


def session_path(data_root, run_id):
    if not RUN_ID_RE.fullmatch(run_id or ""):
        raise RunStateError(f"非法 run_id: {run_id!r}")
    return Path(data_root) / SESSION_DIR / f"{run_id}.json"


def load_session(data_root, run_id):
    path = session_path(data_root, run_id)
    if not path.is_file():
        raise RunStateError(f"运行会话不存在: {run_id}")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RunStateError(f"运行会话损坏: {run_id}")
    return validate_session(obj, run_id, f"运行会话 {path.name}")
