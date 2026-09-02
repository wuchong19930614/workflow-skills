#!/usr/bin/env python3
"""运行清单的唯一校验、单步记录与原子写入实现。"""
import argparse
import json
import os
import re
import tempfile
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import data_root
from run_state import RunStateError, load_session
from chinese_labels import session_status_label


RUN_FIELDS = {"date", "skill", "run_id", "sources_opened", "sources_blocked",
              "candidates_touched", "candidates_reviewed", "billable_calls", "notes",
              "rounds", "funnel", "trigger_funnel", "metrics_summary", "termination"}
RUN_ROUND_FIELDS = {"round", "sources_opened", "sources_blocked", "candidates_touched",
                    "candidates_reviewed", "billable_calls", "notes", "funnel", "trigger_funnel",
                    "round_type", "metrics", "false_negative_audit"}
RUN_STR_ARRAYS = ("sources_opened", "sources_blocked", "candidates_touched", "notes")
RUN_SKILLS = {"xinci-scan", "xinci-track", "xinci-qualify", "xinci-decide", "xinci-run",
              "xinci-mature"}
RUN_NAME_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})(?:-(\d{4}|\d{6})(?:-([a-f0-9]{8}))?)?-(xinci-[a-z]+)")
FUNNEL_SINKS = ("rejected_zero_cost", "rejected_g1", "deep_audited", "queued")
# pooled=方向停在触发层(已写入触发池,未注册为候选)。它是去向之一、参与加总,
# 但不进必填集:既有清单写在它之前,缺这一项按 0 处理。
FUNNEL_OPTIONAL_SINKS = ("pooled",)
FUNNEL_FIELDS = ("extracted",) + FUNNEL_SINKS
FUNNEL_CARRYOVER = "carryover_audited"
FUNNEL_ALL_FIELDS = FUNNEL_FIELDS + FUNNEL_OPTIONAL_SINKS + (FUNNEL_CARRYOVER,)
FUNNEL_REQUIRED_FROM = "2026-08-19"
TRIGGER_FUNNEL_FIELDS = ("harvested", "discarded_preapproval", "discarded_postapproval",
                         "pending", "approved")
REVIEW_OUTCOMES = {"reviewed_no_transition", "same_day_skipped", "not_due",
                   "awaiting_external_evidence", "deferred_existing_evidence"}
ROUND_TYPES = {"discovery", "progression", "tracking", "calibration"}
ROUND_METRIC_FIELDS = {"formal_extracted", "g1_checks", "task_families",
                       "source_family_counts", "source_family_outcomes",
                       "deep_audit_families", "state_transitions"}
SOURCE_OUTCOME_FIELDS = {"formal", "g1_pass", "deep", "tracking"}
TRANSITION_METRIC_FIELDS = {"tracking_added", "formation_confirmed", "qualified",
                            "go_decisions"}
FALSE_NEGATIVE_OUTCOMES = {"valid_reject", "false_negative", "inconclusive"}
CALIBRATION_TARGETS = {"G6": 10, "G7": 10, "G5": 5, "G1": 5, "G3": 5}


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
    total = (sum(funnel[key] for key in FUNNEL_SINKS)
             + sum(funnel.get(key, 0) for key in FUNNEL_OPTIONAL_SINKS))
    if total != funnel["extracted"]:
        errors.append(f"{where} funnel 去向加总 {total} ≠ extracted {funnel['extracted']}"
                      "(每个被提取的方向都要有归宿:秒弃/G1否决/深审/排队/入触发池,不许无声丢弃)")


def _check_trigger_funnel(obj, where, errors):
    funnel = obj.get("trigger_funnel")
    if funnel is None:
        return
    if not isinstance(funnel, dict) or set(funnel) != set(TRIGGER_FUNNEL_FIELDS):
        errors.append(f"{where} trigger_funnel 必须完整包含 {list(TRIGGER_FUNNEL_FIELDS)}")
        return
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in funnel.values()):
        errors.append(f"{where} trigger_funnel 各项必须是非负整数")
        return
    sinks = sum(funnel[k] for k in TRIGGER_FUNNEL_FIELDS if k != "harvested")
    if sinks != funnel["harvested"]:
        errors.append(f"{where} trigger_funnel 去向加总 {sinks} ≠ harvested {funnel['harvested']}")


def _check_reviews(obj, where, errors, root=None):
    rows = obj.get("candidates_reviewed")
    if rows is None:
        return
    if not isinstance(rows, list):
        errors.append(f"{where} candidates_reviewed 必须是数组")
        return
    seen = set()
    for i, row in enumerate(rows):
        if (not isinstance(row, dict) or set(row) - {"slug", "outcome", "reason", "evidence_refs"}
                or not isinstance(row.get("slug"), str) or not row["slug"]
                or row.get("outcome") not in REVIEW_OUTCOMES
                or not isinstance(row.get("reason"), str) or not row["reason"].strip()
                or row["slug"] in seen):
            errors.append(f"{where} candidates_reviewed[{i}] 字段、outcome、reason 或 slug 唯一性非法")
            continue
        refs = row.get("evidence_refs", [])
        if not isinstance(refs, list) or not all(isinstance(x, str) and x for x in refs):
            errors.append(f"{where} candidates_reviewed[{i}].evidence_refs 必须是字符串数组")
        elif root is not None:
            for ref in refs:
                rel = Path(ref)
                if rel.is_absolute() or ".." in rel.parts or not (root / rel).is_file():
                    errors.append(f"{where} candidates_reviewed[{i}] 证据不存在或越界: {ref}")
        seen.add(row["slug"])


def _check_round_metrics(rnd, where, errors):
    metrics = rnd.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != ROUND_METRIC_FIELDS:
        errors.append(f"{where} metrics 必须完整包含 {sorted(ROUND_METRIC_FIELDS)}")
        return
    for key in ("formal_extracted", "g1_checks"):
        if (not isinstance(metrics.get(key), int) or isinstance(metrics.get(key), bool)
                or metrics[key] < 0):
            errors.append(f"{where} metrics.{key} 必须是非负整数")
    for key in ("task_families", "deep_audit_families"):
        rows = metrics.get(key)
        if (not isinstance(rows, list) or len(rows) != len(set(rows))
                or not all(isinstance(x, str) and x.strip() for x in rows)):
            errors.append(f"{where} metrics.{key} 必须是唯一非空字符串数组")
    source_counts = metrics.get("source_family_counts")
    if (not isinstance(source_counts, dict)
            or not all(isinstance(k, str) and k.strip()
                       and isinstance(v, int) and not isinstance(v, bool) and v >= 0
                       for k, v in source_counts.items())):
        errors.append(f"{where} metrics.source_family_counts 必须是来源家族到非负整数的对象")
    source_outcomes = metrics.get("source_family_outcomes")
    if (not isinstance(source_outcomes, dict)
            or any(not isinstance(family, str) or not family.strip()
                   or not isinstance(values, dict) or set(values) != SOURCE_OUTCOME_FIELDS
                   or any(not isinstance(v, int) or isinstance(v, bool) or v < 0
                          for v in values.values())
                   for family, values in source_outcomes.items())):
        errors.append(f"{where} metrics.source_family_outcomes 必须逐来源完整包含"
                      f" {sorted(SOURCE_OUTCOME_FIELDS)}")
    transitions = metrics.get("state_transitions")
    if (not isinstance(transitions, dict) or set(transitions) != TRANSITION_METRIC_FIELDS
            or any(not isinstance(v, int) or isinstance(v, bool) or v < 0
                   for v in transitions.values())):
        errors.append(f"{where} metrics.state_transitions 必须完整包含"
                      f" {sorted(TRANSITION_METRIC_FIELDS)} 且值为非负整数")
    funnel = rnd.get("funnel") or {}
    if metrics.get("formal_extracted") != funnel.get("extracted"):
        errors.append(f"{where} metrics.formal_extracted 必须等于 funnel.extracted")
    if len(metrics.get("deep_audit_families") or []) > funnel.get("deep_audited", 0):
        errors.append(f"{where} deep_audit_families 数不得大于 funnel.deep_audited")
    if funnel.get("deep_audited", 0) > 0 and not metrics.get("deep_audit_families"):
        errors.append(f"{where} 有深审时必须记录至少一个 deep_audit_family")
    if funnel.get("extracted", 0) > 0 and not metrics.get("task_families"):
        errors.append(f"{where} 有正式提取时必须记录至少一个 task_family")
    if funnel.get("extracted", 0) > 0:
        counts = metrics.get("source_family_counts") or {}
        if not counts:
            errors.append(f"{where} 有正式提取时必须记录 source_family_counts")
        outcomes = metrics.get("source_family_outcomes") or {}
        if not outcomes:
            errors.append(f"{where} 有正式提取时必须记录 source_family_outcomes")
        elif sum(row.get("formal", 0) for row in outcomes.values()) != funnel["extracted"]:
            errors.append(f"{where} source_family_outcomes.formal 加总必须等于 funnel.extracted")
    outcomes = metrics.get("source_family_outcomes") or {}
    if outcomes:
        counts = metrics.get("source_family_counts") or {}
        missing_count_families = sorted(set(outcomes) - set(counts))
        if missing_count_families:
            errors.append(f"{where} source_family_outcomes 的来源家族必须出现在"
                          f" source_family_counts: {missing_count_families}")
        totals = {field: sum(row.get(field, 0) for row in outcomes.values())
                  for field in SOURCE_OUTCOME_FIELDS}
        for family, row in outcomes.items():
            # 验证型陷阱允许先跑 G3 再补 G1，因此 deep 与 g1_pass 不能互相强排顺序。
            if not (row["tracking"] <= row["deep"] <= row["formal"]
                    and row["g1_pass"] <= row["formal"]):
                errors.append(f"{where} source_family_outcomes[{family!r}] 必须满足"
                              " tracking <= deep <= formal 且 g1_pass <= formal")
            if family in counts and row["formal"] > counts[family]:
                errors.append(f"{where} source_family_outcomes[{family!r}].formal"
                              " 不得大于该来源的提取计数")
        if totals["deep"] != funnel.get("deep_audited", 0):
            errors.append(f"{where} source_family_outcomes.deep 加总必须等于 funnel.deep_audited")
        if totals["g1_pass"] + funnel.get("rejected_g1", 0) > metrics.get("g1_checks", 0):
            errors.append(f"{where} G1 pass 加 G1 否决不得大于 metrics.g1_checks")
        if totals["tracking"] > (metrics.get("state_transitions") or {}).get("tracking_added", 0):
            errors.append(f"{where} source_family_outcomes.tracking 不得大于实际 tracking_added")


def _check_false_negative_audit(rnd, where, errors, root=None):
    audit = rnd.get("false_negative_audit")
    if rnd.get("round_type") != "calibration":
        if audit is not None:
            errors.append(f"{where} false_negative_audit 只允许校准轮填写")
        return
    if not isinstance(audit, dict) or set(audit) != {"status", "reason", "samples", "untested_gates"}:
        errors.append(f"{where} 校准轮必须提交完整 false_negative_audit")
        return
    if audit.get("status") not in {"completed", "blocked"}:
        errors.append(f"{where} false_negative_audit.status 只能是 completed/blocked")
    if not isinstance(audit.get("reason"), str) or not audit["reason"].strip():
        errors.append(f"{where} false_negative_audit.reason 必须非空")
    untested = audit.get("untested_gates")
    if (not isinstance(untested, list) or len(untested) != len(set(untested))
            or not all(x in {"G1", "G3", "G5", "G6", "G7"} for x in untested)):
        errors.append(f"{where} false_negative_audit.untested_gates 非法")
    samples = audit.get("samples")
    if not isinstance(samples, list):
        errors.append(f"{where} false_negative_audit.samples 必须是数组")
        return
    sample_gate_counts = {gate: 0 for gate in CALIBRATION_TARGETS}
    seen_samples = set()
    for i, sample in enumerate(samples):
        sw = f"{where} false_negative_audit.samples[{i}]"
        required = {"term", "gate", "outcome", "reason", "evidence_refs"}
        if not isinstance(sample, dict) or set(sample) != required:
            errors.append(f"{sw} 字段必须严格匹配 {sorted(required)}")
            continue
        if (not isinstance(sample.get("term"), str) or not sample["term"].strip()
                or sample.get("gate") not in {"G1", "G3", "G5", "G6", "G7"}
                or sample.get("outcome") not in FALSE_NEGATIVE_OUTCOMES
                or not isinstance(sample.get("reason"), str) or not sample["reason"].strip()):
            errors.append(f"{sw} term/gate/outcome/reason 非法")
        elif sample.get("gate") in sample_gate_counts:
            sample_gate_counts[sample["gate"]] += 1
            sample_key = (sample["gate"], sample["term"].strip().casefold())
            if sample_key in seen_samples:
                errors.append(f"{sw} 同一 gate 下 term 不得重复")
            seen_samples.add(sample_key)
        refs = sample.get("evidence_refs")
        if not isinstance(refs, list) or not refs or not all(isinstance(x, str) and x for x in refs):
            errors.append(f"{sw}.evidence_refs 必须是非空字符串数组")
        elif root is not None:
            for ref in refs:
                rel = Path(ref)
                if rel.is_absolute() or ".." in rel.parts or not (root / rel).is_file():
                    errors.append(f"{sw} 证据不存在或越界: {ref}")
    expected_untested = sorted(gate for gate, count in sample_gate_counts.items() if count == 0)
    if isinstance(untested, list) and sorted(untested) != expected_untested:
        errors.append(f"{where} false_negative_audit.untested_gates 必须由样本覆盖自动对应"
                      f"，应为 {expected_untested}")
    if audit.get("status") == "completed":
        shortfalls = {gate: target - sample_gate_counts[gate]
                      for gate, target in CALIBRATION_TARGETS.items()
                      if sample_gate_counts[gate] < target}
        if shortfalls:
            errors.append(f"{where} 已完成校准必须满足默认 35 条分层样本，缺口 {shortfalls};"
                          "样本不足时应记录 blocked")


def aggregate_metrics(rounds):
    summary = {
        "rounds_by_type": {key: 0 for key in sorted(ROUND_TYPES)},
        "formal_extracted": 0, "g1_checks": 0, "deep_audited": 0,
        "task_families": [], "source_family_counts": {},
        "source_family_outcomes": {},
        "state_transitions": {key: 0 for key in sorted(TRANSITION_METRIC_FIELDS)},
        "false_negative_samples": 0, "false_negatives": 0,
    }
    task_families = set()
    for rnd in rounds:
        round_type = rnd.get("round_type")
        if round_type in summary["rounds_by_type"]:
            summary["rounds_by_type"][round_type] += 1
        metrics = rnd.get("metrics") or {}
        summary["formal_extracted"] += metrics.get("formal_extracted", 0)
        summary["g1_checks"] += metrics.get("g1_checks", 0)
        summary["deep_audited"] += (rnd.get("funnel") or {}).get("deep_audited", 0)
        task_families.update(metrics.get("task_families") or [])
        for family, count in (metrics.get("source_family_counts") or {}).items():
            summary["source_family_counts"][family] = (
                summary["source_family_counts"].get(family, 0) + count)
        for family, values in (metrics.get("source_family_outcomes") or {}).items():
            target = summary["source_family_outcomes"].setdefault(
                family, {key: 0 for key in sorted(SOURCE_OUTCOME_FIELDS)})
            for key, count in values.items():
                target[key] += count
        for key, count in (metrics.get("state_transitions") or {}).items():
            if key in summary["state_transitions"]:
                summary["state_transitions"][key] += count
        samples = (rnd.get("false_negative_audit") or {}).get("samples") or []
        summary["false_negative_samples"] += len(samples)
        summary["false_negatives"] += sum(
            1 for sample in samples if sample.get("outcome") == "false_negative")
    summary["task_families"] = sorted(task_families)
    return summary


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
    _check_trigger_funnel(obj, where, errors)
    root = Path(path).parent.parent if path else None
    _check_reviews(obj, where, errors, root)
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
        _check_trigger_funnel(rnd, rw, errors)
        _check_reviews(rnd, rw, errors, root)
        if session and session.get("schema_version", 1) >= 3:
            if rnd.get("round_type") not in ROUND_TYPES:
                errors.append(f"{rw} schema v3 必须填写 round_type={sorted(ROUND_TYPES)}")
            _check_round_metrics(rnd, rw, errors)
            _check_false_negative_audit(rnd, rw, errors, root)
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
    if session and session.get("schema_version", 1) >= 3:
        expected_metrics = aggregate_metrics(rounds)
        if obj.get("metrics_summary") != expected_metrics:
            errors.append(f"{where} metrics_summary 必须由 rounds 机器汇总生成")
    termination = obj.get("termination")
    if termination is not None:
        legacy_required = {"status", "status_label", "reason", "finished_at", "rounds_completed",
                           "max_rounds", "go_candidates"}
        current_required = legacy_required | {"evidence_refs"}
        v3_required = current_required | {"metrics_summary"}
        if not isinstance(termination, dict) or frozenset(termination) not in {
                frozenset(legacy_required), frozenset(current_required), frozenset(v3_required)}:
            errors.append(f"{where} termination 字段必须匹配当前或历史契约")
        elif (not all(termination.get(k) for k in ("status", "status_label", "reason", "finished_at"))
              or not isinstance(termination.get("rounds_completed"), int)
              or not isinstance(termination.get("max_rounds"), int)
              or not isinstance(termination.get("go_candidates"), list)
              or not isinstance(termination.get("evidence_refs", []), list)
              or not all(isinstance(x, str) and x for x in termination.get("evidence_refs", []))):
            errors.append(f"{where} termination 值非法")
        elif (session and session.get("schema_version", 1) >= 3
              and termination.get("metrics_summary") != aggregate_metrics(rounds)):
            errors.append(f"{where} termination.metrics_summary 必须由 rounds 机器汇总生成")
        elif session and session.get("status") != "active":
            expected = {
                "status": session.get("status"),
                "status_label": session_status_label(session.get("status")),
                "reason": session.get("finish_reason"),
                "finished_at": session.get("finished_at"),
                "rounds_completed": session.get("rounds_completed"),
                "max_rounds": session.get("max_rounds"),
                "go_candidates": list(session.get("go_candidates") or []),
            }
            actual_core = {key: termination.get(key) for key in expected}
            if actual_core != expected:
                errors.append(f"{where} termination 与已结束 session 不一致")
            for ref in termination.get("evidence_refs", []):
                rel = Path(ref)
                root = Path(path).parent.parent if path else None
                if (rel.is_absolute() or ".." in rel.parts
                        or (root is not None and not (root / rel).is_file())):
                    errors.append(f"{where} termination 证据不存在或越界: {ref}")
    elif (session and session.get("status") != "active"
          and session.get("schema_version", 1) >= 2):
        errors.append(f"{where} 已结束 session 必须固化 termination 快照")
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
           "candidates_touched": [], "candidates_reviewed": [], "billable_calls": 0,
           "notes": [], "rounds": []}
    if session.get("schema_version", 1) >= 3:
        obj["metrics_summary"] = aggregate_metrics([])
    errors = validate_manifest(obj, path, session, set())
    if errors:
        raise RunManifestError("; ".join(errors))
    _atomic_save(path, obj)
    return path, obj


def record_single(data_root, *, run_date, skill, suffix=None, sources_opened=None,
                  sources_blocked=None, candidates_touched=None, billable_calls=0,
                  notes=None, funnel=None):
    """原子创建单步 skill 清单；拒绝覆盖，重跑时由调用者显式给 HHMM/HHMMSS 后缀。"""
    if skill == "xinci-run" or skill not in RUN_SKILLS:
        raise RunManifestError("record-single 只接受非 xinci-run 的已知 skill")
    try:
        date.fromisoformat(run_date)
    except (TypeError, ValueError):
        raise RunManifestError("record-single --date 必须是 YYYY-MM-DD")
    if suffix is not None and not re.fullmatch(r"\d{4}|\d{6}", suffix):
        raise RunManifestError("record-single --suffix 必须是 HHMM 或 HHMMSS")
    name = f"{run_date}{'-' + suffix if suffix else ''}-{skill}.json"
    path = Path(data_root) / "运行" / name
    if path.exists():
        raise RunManifestError(f"运行清单已存在，拒绝覆盖；同日重跑请传 --suffix: {name}")
    obj = {
        "date": run_date, "skill": skill,
        "sources_opened": list(sources_opened or []),
        "sources_blocked": list(sources_blocked or []),
        "candidates_touched": list(candidates_touched or []),
        "billable_calls": billable_calls,
        "notes": list(notes or []),
    }
    if funnel is not None:
        if "pooled" in funnel:
            raise RunManifestError("新单步清单不得写 funnel.pooled；该字段仅供历史读取")
        obj["funnel"] = funnel
    errors = validate_manifest(obj, path)
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


def _merge_reviews(existing, values):
    out = list(existing or [])
    positions = {row.get("slug"): i for i, row in enumerate(out) if isinstance(row, dict)}
    for row in values:
        if row["slug"] in positions:
            out[positions[row["slug"]]] = row
        else:
            positions[row["slug"]] = len(out); out.append(row)
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
    manifest["candidates_reviewed"] = _merge_reviews(
        manifest.get("candidates_reviewed"), round_record.get("candidates_reviewed") or [])
    manifest["trigger_funnel"] = {
        key: sum((r.get("trigger_funnel") or {}).get(key, 0) for r in rounds)
        for key in TRIGGER_FUNNEL_FIELDS
    }
    manifest["billable_calls"] = sum(r.get("billable_calls", 0) for r in rounds)
    if session.get("schema_version", 1) >= 3:
        manifest["metrics_summary"] = aggregate_metrics(rounds)
    errors = validate_manifest(manifest, path, session, candidates_by_run(data_root).get(session["run_id"], set()))
    errors += validate_round_ledger_contract(data_root, session["run_id"], round_record)
    if errors:
        raise RunManifestError("; ".join(errors))
    _atomic_save(path, manifest)
    return path, manifest


def finalize_manifest(data_root, session, reason, evidence_refs=None):
    path, manifest = find_run_manifest(data_root, session["run_id"])
    if path is None:
        path, manifest = create_run_manifest(data_root, session)
    termination = {
        "status": session["status"],
        "status_label": session_status_label(session["status"]),
        "reason": reason,
        "finished_at": session["finished_at"],
        "rounds_completed": session["rounds_completed"],
        "max_rounds": session["max_rounds"],
        "go_candidates": list(session.get("go_candidates") or []),
        "evidence_refs": list(evidence_refs or []),
    }
    if session.get("schema_version", 1) >= 3:
        termination["metrics_summary"] = aggregate_metrics(manifest.get("rounds") or [])
    existing = manifest.get("termination")
    if existing is not None and existing != termination:
        raise RunManifestError("manifest 已有不同 termination，拒绝覆盖")
    manifest["termination"] = termination
    errors = validate_manifest(manifest, path, session,
                               candidates_by_run(data_root).get(session["run_id"], set()))
    if errors:
        raise RunManifestError("; ".join(errors))
    _atomic_save(path, manifest)
    return path, manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="xinci 运行清单校验与单步原子写入")
    ap.add_argument("--data-root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("record-single")
    p.add_argument("--date", required=True)
    p.add_argument("--skill", choices=sorted(RUN_SKILLS - {"xinci-run"}), required=True)
    p.add_argument("--suffix")
    p.add_argument("--source-opened", action="append", default=[])
    p.add_argument("--source-blocked", action="append", default=[])
    p.add_argument("--candidate-touched", action="append", default=[])
    p.add_argument("--billable-calls", type=int, default=0)
    p.add_argument("--note", action="append", default=[])
    p.add_argument("--funnel", help="xinci-scan 必填的漏斗 JSON")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        funnel = json.loads(a.funnel) if a.funnel is not None else None
        path, _ = record_single(
            root, run_date=a.date, skill=a.skill, suffix=a.suffix,
            sources_opened=a.source_opened, sources_blocked=a.source_blocked,
            candidates_touched=a.candidate_touched, billable_calls=a.billable_calls,
            notes=a.note, funnel=funnel)
    except (json.JSONDecodeError, RunManifestError) as e:
        print(f"run_manifest 拒绝: {e}", file=sys.stderr)
        return 2
    print(f"已写运行清单: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
