#!/usr/bin/env python3
"""运行清单的唯一校验与原子写入实现。"""
import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from run_state import RunStateError, load_session


RUN_FIELDS = {"date", "skill", "run_id", "sources_opened", "sources_blocked",
              "candidates_touched", "billable_calls", "notes", "rounds", "funnel"}
RUN_ROUND_FIELDS = {"round", "sources_opened", "sources_blocked", "candidates_touched",
                    "billable_calls", "notes", "funnel"}
RUN_STR_ARRAYS = ("sources_opened", "sources_blocked", "candidates_touched", "notes")
RUN_SKILLS = {"xinci-scan", "xinci-track", "xinci-qualify", "xinci-decide", "xinci-run"}
RUN_NAME_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})(?:-(\d{4}|\d{6})(?:-([a-f0-9]{8}))?)?-(xinci-[a-z]+)")
FUNNEL_SINKS = ("rejected_zero_cost", "rejected_g1", "deep_audited", "queued")
FUNNEL_FIELDS = ("extracted",) + FUNNEL_SINKS
FUNNEL_CARRYOVER = "carryover_audited"
FUNNEL_ALL_FIELDS = FUNNEL_FIELDS + (FUNNEL_CARRYOVER,)
FUNNEL_REQUIRED_FROM = "2026-08-19"


class RunManifestError(Exception):
    pass


def _atomic_save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _check_str_array(obj, key, where, errors):
    value = obj.get(key)
    if value is not None and not (isinstance(value, list)
                                  and all(isinstance(x, str) and x for x in value)):
        errors.append(f"{where} {key} 必须是非空字符串数组,当前 {value!r}")


def _check_int(obj, key, where, errors):
    value = obj.get(key)
    if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
        errors.append(f"{where} {key} 必须是整数且不得为负,当前 {value!r}")


def _check_funnel(obj, where, errors):
    funnel = obj.get("funnel")
    if funnel is None:
        return
    if not isinstance(funnel, dict):
        errors.append(f"{where} funnel 必须是对象,当前 {type(funnel).__name__}")
        return
    unknown = sorted(set(funnel) - set(FUNNEL_ALL_FIELDS))
    if unknown:
        errors.append(f"{where} funnel 含 schema 外字段 {unknown}")
    missing = [key for key in FUNNEL_FIELDS if key not in funnel]
    if missing:
        errors.append(f"{where} funnel 缺字段 {missing}")
        return
    bad = [key for key in FUNNEL_ALL_FIELDS if key in funnel
           and (not isinstance(funnel[key], int) or isinstance(funnel[key], bool)
                or funnel[key] < 0)]
    if bad:
        errors.append(f"{where} funnel 各项必须是非负整数,不合格: {bad}")
        return
    total = sum(funnel[key] for key in FUNNEL_SINKS)
    if total != funnel["extracted"]:
        errors.append(f"{where} funnel 去向加总 {total} ≠ extracted {funnel['extracted']}"
                      "(每个被提取的方向都要有归宿:秒弃/G1否决/深审/排队,不许无声丢弃)")


def _load_ledger(data_root):
    try:
        ledger = json.loads((Path(data_root) / "账本" / "候选账本.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return ledger if isinstance(ledger, dict) else {}


def candidates_by_run(data_root):
    out = {}
    candidates = _load_ledger(data_root).get("candidates", {})
    if not isinstance(candidates, dict):
        return out
    for slug, candidate in candidates.items():
        if not isinstance(candidate, dict):
            continue
        for event in candidate.get("history", []):
            if isinstance(event, dict) and event.get("run_id"):
                out.setdefault(event["run_id"], set()).add(slug)
    return out


def candidates_by_round(data_root):
    out = {}
    candidates = _load_ledger(data_root).get("candidates", {})
    if not isinstance(candidates, dict):
        return out
    for slug, candidate in candidates.items():
        if not isinstance(candidate, dict):
            continue
        for event in candidate.get("history", []):
            if (isinstance(event, dict) and event.get("run_id")
                    and isinstance(event.get("round"), int)):
                out.setdefault((event["run_id"], event["round"]), set()).add(slug)
    return out


def _queued_contract(data_root, run_id, round_number):
    """重建本轮新注册方向的轮末状态，返回 queued slugs 与缺契约字段者。"""
    queued, invalid = set(), set()
    candidates = _load_ledger(data_root).get("candidates", {})
    if not isinstance(candidates, dict):
        return queued, invalid
    for slug, candidate in candidates.items():
        history = candidate.get("history", []) if isinstance(candidate, dict) else []
        events = [event for event in history if isinstance(event, dict)
                  and event.get("run_id") == run_id and event.get("round") == round_number]
        if not events or not any(event.get("from") is None for event in events):
            continue  # 只统计本轮新方向；存量还债不属于 funnel.queued
        last = events[-1]
        if last.get("to") != "captured":
            continue
        gates, expiry = {}, None
        for event in events:
            gates.update(event.get("gates") or {})
            if event.get("expiry"):
                expiry = event["expiry"]
        if gates.get("G2") or gates.get("G3"):
            continue  # 已完成深审但挂在 captured 的窗口赌注计 deep_audited
        queued.add(slug)
        if not gates or not expiry:
            invalid.add(slug)
    return queued, invalid


def validate_round_ledger_contract(data_root, run_id, round_record):
    errors = []
    number = round_record.get("round")
    expected_touched = candidates_by_round(data_root).get((run_id, number), set())
    actual_touched = set(round_record.get("candidates_touched") or [])
    if expected_touched and actual_touched != expected_touched:
        errors.append(f"第 {number} 轮 candidates_touched 与账本 history 不一致:"
                      f" expected={sorted(expected_touched)}, actual={sorted(actual_touched)}")
    queued, invalid = _queued_contract(data_root, run_id, number)
    declared = (round_record.get("funnel") or {}).get("queued")
    if declared is not None and declared != len(queued):
        errors.append(f"第 {number} 轮 funnel.queued={declared} 与账本排队候选数 {len(queued)} 不一致")
    if invalid:
        errors.append(f"第 {number} 轮排队候选缺 gates 或 expiry: {sorted(invalid)}")
    return errors


def validate_manifest(obj, path=None, session=None, run_candidates=None):
    where = f"[运行/{Path(path).name}]" if path else "[运行清单]"
    errors = []
    if not isinstance(obj, dict):
        return [f"{where} 必须是 JSON 对象"]
    name = RUN_NAME_RE.fullmatch(Path(path).stem) if path else None
    if path and not name:
        errors.append(f"{where} 文件名不合约定 <YYYY-MM-DD>[-HHMM[SS][-run-token]]-<skill>.json")
    unknown = sorted(set(obj) - RUN_FIELDS)
    if unknown:
        errors.append(f"{where} 含 schema 外字段 {unknown}(数据极简,勿加仪式性字段)")
    for key in ("date", "skill"):
        if not obj.get(key):
            errors.append(f"{where} 缺必填字段 {key}")
    run_date = obj.get("date")
    if run_date:
        try:
            date.fromisoformat(run_date)
        except (TypeError, ValueError):
            errors.append(f"{where} date 不可解析: {run_date!r}")
        else:
            if name and run_date != name.group(1):
                errors.append(f"{where} date={run_date} 与文件名日期 {name.group(1)} 不一致")
    skill = obj.get("skill")
    if skill and skill not in RUN_SKILLS:
        errors.append(f"{where} skill 必须属于 {sorted(RUN_SKILLS)},当前 {skill!r}")
    elif skill and name and skill != name.group(4):
        errors.append(f"{where} skill={skill!r} 与文件名 {name.group(4)!r} 不一致")
    run_id = obj.get("run_id")
    if (skill == "xinci-run" and run_date and run_date >= "2026-08-20"
            and session is not None and not run_id):
        errors.append(f"{where} 新版 xinci-run 清单必须带 run_id")
    if run_id and skill != "xinci-run":
        errors.append(f"{where} run_id 仅允许用于 xinci-run")
    if session and run_id != session.get("run_id"):
        errors.append(f"{where} run_id 与 session 不一致")
    for key in RUN_STR_ARRAYS:
        _check_str_array(obj, key, where, errors)
    _check_int(obj, "billable_calls", where, errors)
    _check_funnel(obj, where, errors)
    enforce_funnel = bool(run_date) and run_date >= FUNNEL_REQUIRED_FROM
    if enforce_funnel and skill == "xinci-scan" and obj.get("funnel") is None:
        errors.append(f"{where} xinci-scan 清单必须带 funnel(自 {FUNNEL_REQUIRED_FROM} 起强制)")
    rounds = obj.get("rounds")
    if rounds is None:
        if session and session.get("status") != "active" and session.get("rounds_completed", 0) > 0:
            errors.append(f"{where} 已结束运行完成 {session.get('rounds_completed')} 轮,manifest 缺 rounds")
        return errors
    if skill != "xinci-run":
        errors.append(f"{where} rounds 是 xinci-run 专用字段,当前 skill={skill!r}")
    if not isinstance(rounds, list):
        errors.append(f"{where} rounds 必须是数组,当前 {type(rounds).__name__}")
        return errors
    for i, rnd in enumerate(rounds):
        rw = f"{where} rounds[{i}]"
        if not isinstance(rnd, dict):
            errors.append(f"{rw} 必须是对象")
            continue
        extra = sorted(set(rnd) - RUN_ROUND_FIELDS)
        if extra:
            errors.append(f"{rw} 含 schema 外字段 {extra}")
        number = rnd.get("round")
        if not isinstance(number, int) or isinstance(number, bool):
            errors.append(f"{rw} 缺必填字段 round(整数),当前 {number!r}")
        for key in RUN_STR_ARRAYS:
            _check_str_array(rnd, key, rw, errors)
        _check_int(rnd, "billable_calls", rw, errors)
        _check_funnel(rnd, rw, errors)
        if enforce_funnel and rnd.get("funnel") is None:
            errors.append(f"{rw} 必须带 funnel(自 {FUNNEL_REQUIRED_FROM} 起强制)")
    numbers = [rnd.get("round") for rnd in rounds if isinstance(rnd, dict)]
    if numbers != list(range(1, len(rounds) + 1)):
        errors.append(f"{where} rounds 的 round 必须从 1 开始连续且不重复,当前 {numbers}")
    if run_candidates is not None and run_id:
        touched = set(obj.get("candidates_touched") or []) if isinstance(
            obj.get("candidates_touched") or [], list) else set()
        for rnd in rounds:
            if isinstance(rnd, dict) and isinstance(rnd.get("candidates_touched") or [], list):
                touched.update(rnd.get("candidates_touched") or [])
        missing = sorted(run_candidates - {x for x in touched if isinstance(x, str)})
        if missing:
            errors.append(f"{where} candidates_touched 漏记本次 run_id 写过的候选 {missing}")
    if session and session.get("status") != "active" and len(rounds) != session.get("rounds_completed"):
        errors.append(f"{where} rounds 数量 {len(rounds)} 与已结束 session.rounds_completed "
                      f"{session.get('rounds_completed')} 不一致")
    return errors


def validate_runs(data_root):
    data_root = Path(data_root)
    errors = []
    run_dir = data_root / "运行"
    run_candidates = candidates_by_run(data_root)
    manifest_run_ids, counts = set(), {}
    for path in sorted(run_dir.glob("*.json")) if run_dir.is_dir() else []:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"[运行/{path.name}] 不是合法 JSON: {e}")
            continue
        session = None
        run_id = obj.get("run_id") if isinstance(obj, dict) else None
        if run_id:
            if obj.get("skill") == "xinci-run":
                manifest_run_ids.add(run_id)
                counts[run_id] = counts.get(run_id, 0) + 1
            try:
                session = load_session(data_root, run_id)
            except RunStateError as e:
                errors.append(f"[运行/{path.name}] run_id 无效: {e}")
        errors.extend(validate_manifest(obj, path, session, run_candidates.get(run_id, set())))
        if isinstance(obj, dict) and run_id and isinstance(obj.get("rounds"), list):
            for rnd in obj["rounds"]:
                if isinstance(rnd, dict):
                    errors.extend(f"[运行/{path.name}] {e}" for e in
                                  validate_round_ledger_contract(data_root, run_id, rnd))
    for run_id, count in sorted(counts.items()):
        if count != 1:
            errors.append(f"[运行] run_id={run_id} 必须恰好对应一份 xinci-run manifest,当前 {count} 份")
    session_dir = data_root / "运行状态"
    if session_dir.is_dir():
        for path in sorted(session_dir.glob("run-*.json")):
            try:
                session = load_session(data_root, path.stem)
            except RunStateError as e:
                errors.append(f"[运行状态/{path.name}] {e}")
                continue
            if session["status"] != "active" and session["run_id"] not in manifest_run_ids:
                errors.append(f"[运行状态/{path.name}] 已结束会话缺对应 xinci-run manifest"
                              f"(run_id={session['run_id']})")
    return errors


def find_run_manifest(data_root, run_id):
    found = []
    run_dir = Path(data_root) / "运行"
    for path in sorted(run_dir.glob("*.json")) if run_dir.is_dir() else []:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RunManifestError(f"运行清单损坏,停止受控写入: {path.name}: {e}")
        if isinstance(obj, dict) and obj.get("skill") == "xinci-run" and obj.get("run_id") == run_id:
            found.append((path, obj))
    if len(found) > 1:
        raise RunManifestError(f"run_id={run_id} 对应 {len(found)} 份 manifest")
    return found[0] if found else (None, None)


def create_run_manifest(data_root, session):
    existing = find_run_manifest(data_root, session["run_id"])
    if existing[0]:
        return existing
    started = datetime.fromisoformat(session["started_at"]).astimezone(timezone.utc)
    token = session["run_id"].rsplit("-", 1)[-1]
    name = f"{started:%Y-%m-%d-%H%M%S}-{token}-xinci-run.json"
    path = Path(data_root) / "运行" / name
    if path.exists():
        raise RunManifestError(f"manifest 文件名冲突: {path.name}")
    obj = {"date": started.date().isoformat(), "skill": "xinci-run",
           "run_id": session["run_id"], "sources_opened": [], "sources_blocked": [],
           "candidates_touched": [], "billable_calls": 0, "notes": [], "rounds": []}
    errors = validate_manifest(obj, path, session, set())
    if errors:
        raise RunManifestError("; ".join(errors))
    _atomic_save(path, obj)
    return path, obj


def _merge_unique(existing, values):
    out = list(existing or [])
    seen = set(out)
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out


def append_round(data_root, session, round_record):
    path, manifest = create_run_manifest(data_root, session)
    expected = session["current_round"]
    if round_record.get("round") != expected:
        raise RunManifestError(f"round_record.round 必须等于当前轮 {expected}")
    rounds = list(manifest.get("rounds") or [])
    if len(rounds) == expected:
        if rounds[-1] != round_record:
            raise RunManifestError(f"第 {expected} 轮已写入不同内容,拒绝覆盖")
        return path, manifest
    if len(rounds) != expected - 1:
        raise RunManifestError(f"manifest 已有 {len(rounds)} 轮,无法追加第 {expected} 轮")
    rounds.append(round_record)
    manifest["rounds"] = rounds
    for key in ("sources_opened", "sources_blocked", "candidates_touched", "notes"):
        manifest[key] = _merge_unique(manifest.get(key), round_record.get(key) or [])
    manifest["billable_calls"] = sum(r.get("billable_calls", 0) for r in rounds)
    errors = validate_manifest(manifest, path, session, candidates_by_run(data_root).get(session["run_id"], set()))
    errors += validate_round_ledger_contract(data_root, session["run_id"], round_record)
    if errors:
        raise RunManifestError("; ".join(errors))
    _atomic_save(path, manifest)
    return path, manifest
