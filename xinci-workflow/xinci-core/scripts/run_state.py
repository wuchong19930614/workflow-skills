#!/usr/bin/env python3
"""xinci-run session 的共享契约与载入器。"""
import json
from pathlib import Path

from _constants import ROUND_TYPES, RUN_ID_RE, SLUG_RE
from _common import parse_aware_timestamp


SESSION_DIR = "运行状态"
FINAL_STATUSES = {"go", "quota_exhausted", "budget_reached", "resource_exhausted",
                  "calibration_triggered", "blocked", "cancelled"}
STATUSES = {"active"} | FINAL_STATUSES
FIELDS = {"schema_version", "run_id", "mode", "status", "started_at", "updated_at",
          "finished_at", "max_rounds", "max_hours", "rounds_completed", "current_round",
          "round_executor_id", "current_round_type", "current_round_preflight",
          "confirmations", "finish_reason", "go_candidates", "degraded_rounds"}
REQUIRED = {"schema_version", "run_id", "mode", "status", "started_at", "updated_at",
            "max_rounds", "max_hours", "rounds_completed", "current_round",
            "confirmations", "finish_reason"}
# 窗口赌注确认只写不改:消费与否由候选 history 里带 window_bet_confirmation 的出闸条目决定,
# session 侧不再有 consumed_at / voided_at / history。
CONFIRM_FIELDS = {"risk", "confirmed_at"}
# G1 浏览器前置条件:begin-round 时由执行者自报四项,g1_ready 由四项机器推导
# (可控 + 桌面 + 美区 + 未登录),registrar 与 run_policy 只读它。
PREFLIGHT_INPUTS = ("controllable", "desktop", "region", "logged_out")
PREFLIGHT_FIELDS = set(PREFLIGHT_INPUTS) | {"g1_ready"}
PREFLIGHT_REGIONS = {"us", "other", "unknown"}


class RunStateError(Exception):
    pass


def _timestamp(value, where):
    return parse_aware_timestamp(value, where, RunStateError)


def _confirmation(rec, where):
    if not isinstance(rec, dict) or set(rec) != CONFIRM_FIELDS:
        raise RunStateError(f"{where} 字段必须严格匹配 {sorted(CONFIRM_FIELDS)}")
    if rec.get("risk") != "window_bet":
        raise RunStateError(f"{where}.risk 必须是 window_bet")
    _timestamp(rec.get("confirmed_at"), f"{where}.confirmed_at")


def g1_ready(controllable, desktop, region, logged_out) -> bool:
    return controllable is True and desktop is True and region == "us" and logged_out is True


def build_preflight(controllable, desktop, region, logged_out) -> dict:
    """由四项自报输入组装 current_round_preflight;类型与取值在此处一次校验。"""
    if not all(isinstance(x, bool) for x in (controllable, desktop, logged_out)):
        raise RunStateError("浏览器预检 controllable/desktop/logged_out 必须是布尔值")
    if region not in PREFLIGHT_REGIONS:
        raise RunStateError(f"浏览器预检 region 必须属于 {sorted(PREFLIGHT_REGIONS)}")
    return {"controllable": controllable, "desktop": desktop, "region": region,
            "logged_out": logged_out,
            "g1_ready": g1_ready(controllable, desktop, region, logged_out)}


def _preflight(rec, where):
    if not isinstance(rec, dict) or set(rec) != PREFLIGHT_FIELDS:
        raise RunStateError(f"{where} 字段必须严格匹配 {sorted(PREFLIGHT_FIELDS)}")
    expected = build_preflight(rec["controllable"], rec["desktop"], rec["region"], rec["logged_out"])
    if rec != expected:
        raise RunStateError(f"{where}.g1_ready 与四项输入不一致")


def validate_session(obj, expected_run_id=None, where="运行会话"):
    if not isinstance(obj, dict):
        raise RunStateError(f"{where} 必须是 JSON 对象")
    unknown = sorted(set(obj) - FIELDS)
    missing = sorted(REQUIRED - set(obj))
    if unknown or missing:
        raise RunStateError(f"{where} 字段非法: unknown={unknown}, missing={missing}")
    version = obj.get("schema_version")
    if version not in {1, 2, 3} or obj.get("mode") != "continuous":
        raise RunStateError(f"{where} schema_version/mode 非法")
    if version >= 3 and "current_round_type" not in obj:
        raise RunStateError(f"{where} schema v3 缺 current_round_type")
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
    executor_id = obj.get("round_executor_id")
    round_type = obj.get("current_round_type")
    preflight = obj.get("current_round_preflight")
    if preflight is not None:
        _preflight(preflight, f"{where}.current_round_preflight")
    if executor_id is not None and (not isinstance(executor_id, str) or not executor_id.strip()):
        raise RunStateError(f"{where}.round_executor_id 必须为 null 或非空字符串")
    if round_type is not None and round_type not in ROUND_TYPES:
        raise RunStateError(f"{where}.current_round_type 必须属于 {sorted(ROUND_TYPES)} 或为 null")
    # 降级轮(预检不满足 G1 前置)不消耗预算,所以 rounds_completed 可以超过 max_rounds,
    # 真正受 max_rounds 约束的是"合规轮"= rounds_completed - degraded_rounds。
    degraded = obj.get("degraded_rounds", 0)
    if (not isinstance(degraded, int) or isinstance(degraded, bool) or degraded < 0):
        raise RunStateError(f"{where}.degraded_rounds 必须是非负整数")
    if (not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or max_rounds < 1
            or not isinstance(completed, int) or isinstance(completed, bool)
            or completed < 0 or degraded > completed
            or not 0 <= completed - degraded <= max_rounds):
        raise RunStateError(f"{where} max_rounds/rounds_completed/degraded_rounds 非法")
    max_hours = obj.get("max_hours")
    if max_hours is not None and (isinstance(max_hours, bool)
                                  or not isinstance(max_hours, (int, float)) or max_hours <= 0):
        raise RunStateError(f"{where}.max_hours 必须为 null 或正数")
    if status == "active":
        if current is not None and current != completed + 1:
            raise RunStateError(f"{where}.current_round 必须为 null 或 rounds_completed+1")
        if current is not None and current - degraded > max_rounds:
            raise RunStateError(f"{where}.current_round 超出 max_rounds(降级轮不计入)")
        if current is None and executor_id is not None:
            raise RunStateError(f"{where} 未开始轮次时 round_executor_id 必须为 null")
        if current is None and preflight is not None:
            raise RunStateError(f"{where} 未开始轮次时 current_round_preflight 必须为 null")
        if version >= 3 and ((current is None) != (round_type is None)):
            raise RunStateError(f"{where} current_round 与 current_round_type 必须同时存在或同时为空")
        if obj.get("finished_at") is not None or obj.get("finish_reason") is not None:
            raise RunStateError(f"{where} active 状态不得有 finished_at/finish_reason")
        if obj.get("go_candidates") is not None:
            raise RunStateError(f"{where} active 状态不得有 go_candidates")
    else:
        if executor_id is not None:
            raise RunStateError(f"{where} 结束状态 round_executor_id 必须为 null")
        if round_type is not None:
            raise RunStateError(f"{where} 结束状态 current_round_type 必须为 null")
        if preflight is not None:
            raise RunStateError(f"{where} 结束状态 current_round_preflight 必须为 null")
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
