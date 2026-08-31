#!/usr/bin/env python3
"""记录 G1 浏览器前置条件；运行策略只读取该机器证据，不靠口头假设。"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import data_root
from run_state import RunStateError, load_session


class BrowserPreflightError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def path_for(root, run_id):
    return Path(root) / "运行状态" / "浏览器" / f"{run_id}.json"


def _save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2); f.write("\n")
    os.replace(tmp, path)


def record(root, run_id, *, channel, controllable, desktop, region, logged_out, note=None,
           executor_id="orchestrator"):
    try:
        session = load_session(root, run_id)
    except RunStateError as e:
        raise BrowserPreflightError(f"run_id 无效: {e}")
    if session.get("status") != "active":
        raise BrowserPreflightError("只能为活动 run 记录浏览器预检")
    if channel not in {"chrome", "in-app"} or region not in {"us", "other", "unknown"}:
        raise BrowserPreflightError("channel/region 非法")
    if not all(isinstance(x, bool) for x in (controllable, desktop, logged_out)):
        raise BrowserPreflightError("controllable/desktop/logged_out 必须是布尔值")
    if not isinstance(executor_id, str) or not executor_id.strip():
        raise BrowserPreflightError("executor_id 必须是非空字符串")
    target_round = session["current_round"] or session["rounds_completed"] + 1
    path = path_for(root, run_id)
    history = []
    if path.is_file():
        previous = show(root, run_id)
        history = list(previous.get("history") or [])
        history.append({k: previous.get(k) for k in
                        ("checked_at", "executor_id", "target_round", "channel", "controllable",
                         "desktop", "region", "logged_out", "g1_ready", "note")})
    obj = {"schema_version": 2, "run_id": run_id, "checked_at": _now(),
           "executor_id": executor_id, "target_round": target_round,
           "channel": channel, "controllable": controllable, "desktop": desktop,
           "region": region, "logged_out": logged_out,
           "g1_ready": controllable and desktop and region == "us" and logged_out,
           "note": note, "history": history}
    _save(path, obj); return obj


def show(root, run_id, executor_id=None, target_round=None):
    path = path_for(root, run_id)
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BrowserPreflightError("当前 run 尚无浏览器预检")
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BrowserPreflightError("浏览器预检文件损坏")
    expected = (obj.get("controllable") is True and obj.get("desktop") is True
                and obj.get("region") == "us" and obj.get("logged_out") is True)
    if obj.get("run_id") != run_id or obj.get("g1_ready") is not expected:
        raise BrowserPreflightError("浏览器预检字段或 g1_ready 不一致")
    if executor_id is not None and obj.get("executor_id") != executor_id:
        raise BrowserPreflightError(
            f"浏览器预检执行者不匹配: expected={executor_id}, actual={obj.get('executor_id')}")
    if target_round is not None and obj.get("target_round") != target_round:
        raise BrowserPreflightError(
            f"浏览器预检轮次不匹配: expected={target_round}, actual={obj.get('target_round')}")
    return obj


def _bool(value):
    if value == "yes": return True
    if value == "no": return False
    raise argparse.ArgumentTypeError("必须是 yes 或 no")


def main(argv=None):
    ap = argparse.ArgumentParser(description="记录/读取 xinci 浏览器预检")
    ap.add_argument("--data-root", default=None); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("record"); p.add_argument("--run-id", required=True)
    p.add_argument("--channel", choices=["chrome", "in-app"], required=True)
    p.add_argument("--controllable", type=_bool, required=True); p.add_argument("--desktop", type=_bool, required=True)
    p.add_argument("--region", choices=["us", "other", "unknown"], required=True)
    p.add_argument("--logged-out", type=_bool, required=True); p.add_argument("--note")
    p.add_argument("--executor-id", required=True)
    p = sub.add_parser("show"); p.add_argument("--run-id", required=True)
    p.add_argument("--executor-id"); p.add_argument("--target-round", type=int)
    a = ap.parse_args(argv); root = data_root.resolve_or_exit(a.data_root)
    try:
        obj = (record(root, a.run_id, channel=a.channel, controllable=a.controllable,
                      desktop=a.desktop, region=a.region, logged_out=a.logged_out, note=a.note,
                      executor_id=a.executor_id)
               if a.cmd == "record" else show(root, a.run_id, a.executor_id, a.target_round))
    except BrowserPreflightError as e:
        print(f"browser_preflight 拒绝: {e}", file=sys.stderr); return 2
    print(json.dumps(obj, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    sys.exit(main())
