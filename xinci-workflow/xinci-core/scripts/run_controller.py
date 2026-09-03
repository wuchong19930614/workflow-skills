#!/usr/bin/env python3
"""xinci-run 可恢复运行会话控制器。

连续模式的授权不再只靠调用者自报 ``--by xinci-run``。每次运行先创建会话，
每轮显式 begin/record-round；registrar 只接受处于 active/current_round 状态的 run_id。
会话文件位于 <数据区>/运行状态/<run-id>.json，并使用原子替换写入。
"""
import argparse
import json
import secrets
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import data_root
from _common import atomic_save as _save, flock as _flock, funlock as _funlock, load_ledger, now as _now
from _constants import GO_STATES

from run_state import (SESSION_DIR, FINAL_STATUSES, ROUND_TYPES, PREFLIGHT_REGIONS,
                       RunStateError, build_preflight, load_session, session_path,
                       validate_session)
from run_manifest import (RunManifestError, append_round, candidates_by_run,
                          candidates_by_round, create_run_manifest, find_run_manifest,
                          finalize_manifest, validate_runs)
from chinese_labels import (humanize_text, normalize_session_status,
                            session_status_label)

# 数据区的定位统一走 data_root 模块:显式参数 > 环境变量 > 仓库配置 > 拒绝执行。
# 这里刻意不再留任何默认值——数据区放哪是用户的决定,脚本不猜(理由见 data_root.py)。
RunControllerError = RunStateError


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
        existing = active_sessions(data_root)
        if existing:
            raise RunControllerError(f"已有活动运行会话: {existing[0]['run_id']};先恢复或结束它")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"run-{stamp}-{secrets.token_hex(4)}"
        obj = {
            "schema_version": 3,
            "run_id": run_id,
            "mode": "continuous",
            "status": "active",
            "started_at": _now(),
            "updated_at": _now(),
            "max_rounds": max_rounds,
            "max_hours": max_hours,
            "rounds_completed": 0,
            "current_round": None,
            "round_executor_id": None,
            "current_round_type": None,
            "current_round_preflight": None,
            "confirmations": {},
            "finish_reason": None,
        }
        validate_session(obj, run_id)
        _save(_path(data_root, run_id), obj)
        return obj


def _discovery_rounds_since_calibration(data_root):
    count = 0
    run_dir = Path(data_root) / "运行"
    for path in sorted(run_dir.glob("*-xinci-run.json")) if run_dir.is_dir() else []:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        for rnd in manifest.get("rounds") or []:
            if (rnd.get("round_type") == "calibration"
                    and (rnd.get("false_negative_audit") or {}).get("status") == "completed"):
                count = 0
            elif rnd.get("round_type") == "discovery":
                count += 1
    return count


def begin_round(data_root, run_id, executor_id=None, round_type="discovery", preflight=None):
    """开始新一轮。preflight 是执行者自报的 G1 浏览器前置四项
    {controllable, desktop, region, logged_out};CLI 强制提供,库级调用可省略
    (省略即本轮无预检,run_policy 判 trigger_only、registrar 拒收 xinci-run 的 G1 结论)。"""
    if preflight is not None:
        if not isinstance(preflight, dict) or set(preflight) != {"controllable", "desktop",
                                                                 "region", "logged_out"}:
            raise RunControllerError("preflight 必须完整包含 controllable/desktop/region/logged_out")
        preflight = build_preflight(**preflight)
    with _locked(data_root):
        obj = load_session(data_root, run_id)
        if obj.get("status") != "active":
            raise RunControllerError(f"运行会话当前不是运行中，而是：{session_status_label(obj.get('status'))}")
        if obj.get("current_round") is not None:
            raise RunControllerError(f"第 {obj['current_round']} 轮尚未结束")
        if round_type not in ROUND_TYPES:
            raise RunControllerError(f"round_type 必须属于 {sorted(ROUND_TYPES)}")
        if (obj.get("schema_version", 1) >= 3 and round_type == "discovery"
                and _discovery_rounds_since_calibration(data_root) >= 10):
            raise RunControllerError("已累计 10 个发现轮；下一轮必须先执行校准轮并提交假阴性审计")
        if obj["rounds_completed"] >= obj["max_rounds"]:
            raise RunControllerError("轮次预算已用完；请结束会话并将状态设为“运行预算已用完”")
        if obj.get("max_hours") is not None:
            started = datetime.fromisoformat(obj["started_at"])
            elapsed_hours = (datetime.now(timezone.utc) - started).total_seconds() / 3600
            if elapsed_hours >= obj["max_hours"]:
                raise RunControllerError("时长预算已用完；请结束会话并将状态设为“运行预算已用完”")
        obj["current_round"] = obj["rounds_completed"] + 1
        obj["round_executor_id"] = executor_id
        obj["current_round_type"] = round_type
        obj["current_round_preflight"] = preflight
        obj["updated_at"] = _now()
        validate_session(obj, run_id)
        _save(_path(data_root, run_id), obj)
        return obj


def record_round(data_root, run_id, *, sources_opened=None, sources_blocked=None,
                 billable_calls=0, notes=None, funnel=None, candidates_reviewed=None,
                 false_negative_audit=None):
    """结束当前轮:组装轮记录并原子追加到运行清单。

    本函数只负责组装;字段契约(funnel 加总、reviewed 的 slug/outcome/证据、校准轮的
    假阴性审计、排队候选的 gates/expiry 等)统一由 run_manifest.validate_manifest 与
    validate_round_ledger_contract 在 append_round 里校验一次,不在这里重复。
    candidates_touched 与 trigger_funnel 分别从账本 history 与触发池事件按 run_id/round
    机器推导,不接受自报。"""
    with _locked(data_root):
        obj = load_session(data_root, run_id)
        if obj.get("status") != "active" or obj.get("current_round") is None:
            raise RunControllerError("没有正在执行的轮次")
        current = obj["current_round"]
        # 局部导入避免 trigger_pool -> run_controller 的授权依赖形成模块环。
        from trigger_pool import round_funnel
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
        try:
            trigger_funnel = round_funnel(data_root, run_id, current)
        except Exception as e:
            raise RunControllerError(f"触发池无法生成本轮 trigger_funnel: {e}")
        round_record = {
            "round": current,
            "round_type": obj.get("current_round_type") or "discovery",
            "sources_opened": list(sources_opened or []),
            "sources_blocked": list(sources_blocked or []),
            "candidates_touched": touched,
            "candidates_reviewed": list(candidates_reviewed or []),
            "billable_calls": billable_calls,
            "funnel": dict(funnel) if isinstance(funnel, dict) else funnel,
            "trigger_funnel": trigger_funnel,
            "notes": list(notes or []),
        }
        if false_negative_audit is not None:
            round_record["false_negative_audit"] = false_negative_audit
        try:
            manifest_path, _ = append_round(data_root, obj, round_record)
        except RunManifestError as e:
            raise RunControllerError(str(e))
        obj["rounds_completed"] = obj["current_round"]
        obj["current_round"] = None
        obj["round_executor_id"] = None
        obj["current_round_type"] = None
        obj["current_round_preflight"] = None
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
        obj = load_session(data_root, run_id)
        if obj.get("status") != "active":
            raise RunControllerError("只能给活动运行会话记录确认")
        try:
            ledger = load_ledger(data_root)
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
        if slug in confirmations:
            raise RunControllerError(f"候选 {slug} 已记录过窗口赌注确认;确认不可覆盖或重新激活")
        confirmations[slug] = {"risk": "window_bet", "confirmed_at": _now()}
        obj["updated_at"] = _now()
        validate_session(obj, run_id)
        _save(_path(data_root, run_id), obj)
        return obj


def require_active_round(data_root, run_id):
    obj = load_session(data_root, run_id)
    if obj.get("status") != "active" or obj.get("current_round") is None:
        raise RunControllerError("xinci-run 写入要求活动 run_id 且已 begin-round")
    return obj


def finish(data_root, run_id, status, reason, evidence_refs=None):
    status = normalize_session_status(status)
    if status not in FINAL_STATUSES:
        allowed = "、".join(session_status_label(x) for x in sorted(FINAL_STATUSES))
        raise RunControllerError(f"结束状态必须是：{allowed}")
    if not reason:
        raise RunControllerError("结束会话时必须填写事实说明")
    evidence_refs = list(evidence_refs or [])
    for ref in evidence_refs:
        rel = Path(ref)
        if (not isinstance(ref, str) or not ref or rel.is_absolute() or ".." in rel.parts
                or not (Path(data_root) / rel).is_file()):
            raise RunControllerError(f"结束证据必须是数据区内已存在的相对文件: {ref!r}")
    with _locked(data_root):
        obj = load_session(data_root, run_id)
        if obj.get("status") != "active":
            raise RunControllerError(f"运行会话已经结束：{session_status_label(obj.get('status'))}")
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
        try:
            ledger = load_ledger(data_root)
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
        elif status == "quota_exhausted":
            if not evidence_refs:
                raise RunControllerError(
                    "查询额度已用完必须提供网页界面实际提示的证据文件 --evidence-ref")
        elif status == "budget_reached":
            started = datetime.fromisoformat(obj["started_at"])
            elapsed_hours = (datetime.now(timezone.utc) - started).total_seconds() / 3600
            rounds_hit = obj["rounds_completed"] >= obj["max_rounds"]
            hours_hit = obj.get("max_hours") is not None and elapsed_hours >= obj["max_hours"]
            if not (rounds_hit or hours_hit):
                raise RunControllerError("运行预算尚未命中，不能以“运行预算已用完”结束")
        elif status == "calibration_triggered":
            from run_policy import evaluate
            policy = evaluate(data_root, run_id)
            if policy.get("consecutive_decision_stall_rounds", 0) < 3:
                raise RunControllerError(
                    "尚未连续三轮无真实决策迁移且 captured 积压净增长，不能触发校准")
        existing_termination = manifest.get("termination")
        if existing_termination is not None:
            if (existing_termination.get("status") != status
                    or existing_termination.get("reason") != reason
                    or existing_termination.get("rounds_completed") != obj["rounds_completed"]
                    or existing_termination.get("max_rounds") != obj["max_rounds"]):
                raise RunControllerError("manifest 已有不同的结束快照；拒绝用新参数覆盖")
            finished_at = existing_termination.get("finished_at")
        else:
            finished_at = _now()
        obj["status"] = status
        obj["finish_reason"] = reason
        obj["finished_at"] = finished_at
        obj["updated_at"] = obj["finished_at"]
        obj["round_executor_id"] = None
        obj["current_round_type"] = None
        obj["current_round_preflight"] = None
        validate_session(obj, run_id)
        try:
            finalize_manifest(data_root, obj, reason, evidence_refs)
        except RunManifestError as e:
            raise RunControllerError(str(e))
        _save(_path(data_root, run_id), obj)
        return obj


def _render_session(obj):
    lines = [
        f"运行编号：{obj['run_id']}",
        f"运行状态：{session_status_label(obj['status'])}",
        f"已完成轮次：{obj.get('rounds_completed', 0)}/{obj.get('max_rounds', '未设置')}",
    ]
    if obj.get("current_round") is not None:
        lines.append(f"当前轮次：第 {obj['current_round']} 轮")
    if obj.get("finish_reason"):
        lines.append(f"终止说明：{humanize_text(obj['finish_reason'])}")
    if obj.get("go_candidates"):
        lines.append("可交付候选：" + "、".join(obj["go_candidates"]))
    return "\n".join(lines)


def render_human_result(cmd, obj):
    """把控制器结果渲染为中文；机器调用可显式要求 JSON。"""
    if cmd == "list":
        active = obj.get("active") or []
        lines = ["活动会话：" + ("、".join(active) if active else "无")]
        sessions = obj.get("sessions") or []
        if sessions:
            lines.append("会话记录：")
            for row in sessions:
                lines.append(
                    f"- {row['run_id']}｜{session_status_label(row['status'])}｜"
                    f"已完成 {row.get('rounds_completed', 0)}/{row.get('max_rounds', '未设置')} 轮"
                )
        return "\n".join(lines)
    if cmd == "record-round":
        session = obj["session"]
        round_record = obj["round"]
        return "\n".join([
            f"第 {round_record['round']} 轮已记录。",
            f"本轮触及候选：{len(round_record.get('candidates_touched') or [])} 个",
            f"计费调用：{round_record.get('billable_calls', 0)} 次",
            f"运行清单：{obj['manifest']}",
            _render_session(session),
        ])
    if isinstance(obj, dict) and "run_id" in obj and "status" in obj:
        return _render_session(obj)
    return "操作已完成。"


def _yes_no(value):
    if value == "yes":
        return True
    if value == "no":
        return False
    raise argparse.ArgumentTypeError("必须是 yes 或 no")


def main(argv=None):
    ap = argparse.ArgumentParser(description="xinci-run 可恢复运行会话控制器")
    ap.add_argument("--data-root", default=None,
                    help="数据区路径。不给则按 XINCI_DATA_ROOT 环境变量、再按仓库配置 .xinci-data-root 解析;都没有则拒绝执行并提示先问用户")
    ap.add_argument("--json", action="store_true", help="输出稳定机器格式；面向用户时不要使用")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    p.add_argument("--max-rounds", type=int, default=6,
                   help="轮次上限；始终存在，未传时默认 6")
    p.add_argument("--max-hours", type=float,
                   help="可选时长上限；不替代 max-rounds，两项谁先命中谁生效")
    sub.add_parser("list", help="列出会话摘要并直接给出活动运行编号")
    for name in ("begin-round", "show"):
        p = sub.add_parser(name)
        p.add_argument("--run-id", required=True)
        if name == "begin-round":
            p.add_argument("--executor-id", required=True)
            p.add_argument("--round-type", choices=sorted(ROUND_TYPES), default="discovery",
                           help="本轮类型：发现/推进/跟踪/校准")
            # G1 浏览器前置四项:全部必填,g1_ready 由脚本推导(可控+桌面+美区+未登录)
            p.add_argument("--browser-controllable", type=_yes_no, required=True,
                           help="浏览器是否可被脚本控制 yes|no")
            p.add_argument("--browser-desktop", type=_yes_no, required=True,
                           help="是否桌面版 SERP yes|no")
            p.add_argument("--browser-region", choices=sorted(PREFLIGHT_REGIONS), required=True,
                           help="实际生效的地区:us|other|unknown")
            p.add_argument("--browser-logged-out", type=_yes_no, required=True,
                           help="是否未登录 Google 账号 yes|no")
    p = sub.add_parser("record-round", help="原子追加运行清单并结束当前轮")
    p.add_argument("--run-id", required=True)
    p.add_argument("--source-opened", action="append", default=[])
    p.add_argument("--source-blocked", action="append", default=[])
    p.add_argument("--billable-calls", type=int, default=0)
    p.add_argument("--note", action="append", default=[])
    p.add_argument("--funnel", required=True, help="漏斗 JSON 对象;未扫描时五项全 0")
    p.add_argument("--candidate-reviewed", action="append", default=[],
                   help="只读复核 JSON 对象，可重复；不冒充 candidates_touched")
    p.add_argument("--false-negative-audit",
                   help="校准轮必填的结构化假阴性审计 JSON")
    p = sub.add_parser("confirm-window-bet")
    p.add_argument("--run-id", required=True)
    p.add_argument("--slug", required=True)
    p = sub.add_parser("finish")
    p.add_argument("--run-id", required=True)
    p.add_argument("--status", required=True,
                   help="结束状态；推荐使用中文，如“运行预算已用完”")
    p.add_argument("--reason", required=True)
    p.add_argument("--evidence-ref", action="append", default=[],
                   help="结束状态的事实证据文件，可重复；额度耗尽时必填")
    a = ap.parse_args(argv)
    # 数据区未配置时在这里就停,并打印「先问用户」的指引,
    # 不让空路径流进下游写操作(理由见 data_root.py)。
    a.data_root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "start":
            obj = start(a.data_root, a.max_rounds, a.max_hours)
        elif a.cmd == "list":
            obj = list_sessions(a.data_root)
        elif a.cmd == "begin-round":
            obj = begin_round(a.data_root, a.run_id, a.executor_id, a.round_type,
                              preflight={"controllable": a.browser_controllable,
                                         "desktop": a.browser_desktop,
                                         "region": a.browser_region,
                                         "logged_out": a.browser_logged_out})
        elif a.cmd == "record-round":
            try:
                funnel = json.loads(a.funnel)
            except json.JSONDecodeError as e:
                raise RunControllerError(f"--funnel 不是合法 JSON: {e}")
            try:
                reviewed = [json.loads(x) for x in a.candidate_reviewed]
            except json.JSONDecodeError as e:
                raise RunControllerError(f"--candidate-reviewed 不是合法 JSON: {e}")
            try:
                false_negative_audit = (json.loads(a.false_negative_audit)
                                        if a.false_negative_audit else None)
            except json.JSONDecodeError as e:
                raise RunControllerError(f"--false-negative-audit 不是合法 JSON: {e}")
            obj = record_round(a.data_root, a.run_id,
                               sources_opened=a.source_opened,
                               sources_blocked=a.source_blocked,
                               billable_calls=a.billable_calls,
                               notes=a.note, funnel=funnel,
                               candidates_reviewed=reviewed,
                               false_negative_audit=false_negative_audit)
        elif a.cmd == "confirm-window-bet":
            obj = confirm_window_bet(a.data_root, a.run_id, a.slug)
        elif a.cmd == "finish":
            obj = finish(a.data_root, a.run_id, a.status, a.reason, a.evidence_ref)
        else:
            obj = load_session(a.data_root, a.run_id)
    except RunControllerError as e:
        print(f"run_controller 拒绝: {e}", file=sys.stderr)
        return 2
    print(json.dumps(obj, ensure_ascii=False, indent=2) if a.json
          else render_human_result(a.cmd, obj))
    return 0


if __name__ == "__main__":
    sys.exit(main())
