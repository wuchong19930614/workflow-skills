#!/usr/bin/env python3
"""轮内阶段检查点：让批量扫描在崩溃后从未处理项继续，而不是整批重跑。

检查点只记录处理进度，不替代候选账本、淘汰索引或 record-round。完成轮次前必须先
finish 当前检查点；finish 会拒绝任何仍为 pending 的条目。
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import data_root
from run_state import RunStateError, load_session


STAGE_DIR = "阶段"
OUTCOMES = {"dedup", "zero_cost", "g1_rejected", "deep_audited", "queued", "alias",
            "pooled", "trigger_discarded", "trigger_pending", "trigger_approved"}
TRIGGER_OUTCOMES = {"trigger_discarded", "trigger_pending", "trigger_approved"}
TRIGGER_STATUS_OUTCOME = {"discarded": "trigger_discarded", "pending": "trigger_pending",
                          "approved": "trigger_approved"}


class StageCheckpointError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def checkpoint_path(root, run_id, round_number, stage="scan"):
    return Path(root) / "运行状态" / STAGE_DIR / f"{run_id}-round-{round_number}-{stage}.json"


def _save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _load(path):
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StageCheckpointError(f"阶段检查点不存在: {Path(path).name}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise StageCheckpointError(f"阶段检查点损坏: {Path(path).name}")
    required = {"schema_version", "run_id", "round", "stage", "status", "created_at",
                "updated_at", "items"}
    if (not isinstance(obj, dict) or not required <= set(obj)
            or obj.get("schema_version") != 1 or obj.get("status") not in {"active", "completed"}
            or not isinstance(obj.get("items"), dict)):
        raise StageCheckpointError(f"阶段检查点字段非法: {Path(path).name}")
    for item, row in obj["items"].items():
        if (not isinstance(item, str) or not item or not isinstance(row, dict)
                or row.get("outcome") not in OUTCOMES | {None}):
            raise StageCheckpointError(f"阶段检查点 item 字段非法: {Path(path).name}")
    return obj


def start(root, run_id, round_number, items, stage="scan"):
    if not run_id or not isinstance(round_number, int) or round_number < 1:
        raise StageCheckpointError("start 要求合法 run_id 与正整数 round")
    if stage not in {"scan", "trigger"}:
        raise StageCheckpointError("stage 只能是 scan 或 trigger")
    clean = []
    for item in items:
        item = item.strip() if isinstance(item, str) else ""
        if item and item not in clean:
            clean.append(item)
    if not clean:
        raise StageCheckpointError("阶段检查点至少要有一个 item")
    try:
        session = load_session(root, run_id)
    except RunStateError as e:
        raise StageCheckpointError(f"run_id 无效: {e}")
    if session.get("status") != "active" or session.get("current_round") != round_number:
        raise StageCheckpointError("检查点要求活动 run 且 round 等于 current_round")
    path = checkpoint_path(root, run_id, round_number, stage)
    if path.exists():
        obj = _load(path)
        if obj["status"] == "active":
            return obj
        raise StageCheckpointError("已完成的阶段检查点不可覆盖")
    now = _now()
    obj = {
        "schema_version": 1, "run_id": run_id, "round": round_number, "stage": stage,
        "status": "active", "created_at": now, "updated_at": now,
        "items": {item: {"outcome": None, "note": None, "updated_at": None} for item in clean},
    }
    _save(path, obj)
    return obj


def mark(root, run_id, round_number, item, outcome, note=None, stage="scan"):
    if outcome not in OUTCOMES:
        raise StageCheckpointError(f"outcome 必须属于 {sorted(OUTCOMES)}")
    if stage == "trigger" and outcome not in TRIGGER_OUTCOMES:
        raise StageCheckpointError(f"trigger 检查点 outcome 必须属于 {sorted(TRIGGER_OUTCOMES)}")
    if stage != "trigger" and outcome in TRIGGER_OUTCOMES:
        raise StageCheckpointError("trigger_* outcome 只允许用于 stage=trigger")
    path = checkpoint_path(root, run_id, round_number, stage)
    obj = _load(path)
    if obj["status"] != "active":
        raise StageCheckpointError("已完成的阶段检查点不可修改")
    if item not in obj["items"]:
        raise StageCheckpointError(f"item 不在检查点: {item}")
    if obj["items"][item]["outcome"] is not None:
        raise StageCheckpointError(f"item 已有结果，不可覆盖: {item}")
    now = _now()
    obj["items"][item] = {"outcome": outcome, "note": note, "updated_at": now}
    obj["updated_at"] = now
    _save(path, obj)
    return obj


def finish(root, run_id, round_number, stage="scan"):
    path = checkpoint_path(root, run_id, round_number, stage)
    obj = _load(path)
    pending = [item for item, row in obj["items"].items() if row.get("outcome") is None]
    if pending:
        raise StageCheckpointError(f"阶段检查点仍有 {len(pending)} 个 pending item")
    if stage == "trigger":
        from trigger_pool import TriggerPoolError, round_states
        try:
            actual = round_states(root, run_id, round_number)
        except TriggerPoolError as e:
            raise StageCheckpointError(f"触发池无法核对 trigger 检查点: {e}")
        if set(obj["items"]) != set(actual):
            raise StageCheckpointError(
                f"trigger 检查点 items 与本轮 harvest 不一致: "
                f"checkpoint={sorted(obj['items'])}, actual={sorted(actual)}")
        mismatched = [item for item, row in obj["items"].items()
                      if row["outcome"] != TRIGGER_STATUS_OUTCOME[actual[item]]]
        if mismatched:
            raise StageCheckpointError(f"trigger 检查点结果与触发池状态不一致: {mismatched}")
    if obj["status"] == "active":
        obj["status"] = "completed"
        obj["updated_at"] = _now()
        obj["completed_at"] = obj["updated_at"]
        _save(path, obj)
    return obj


def list_open(root, run_id=None, round_number=None):
    directory = Path(root) / "运行状态" / STAGE_DIR
    out = []
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.json")):
        obj = _load(path)
        if (obj["status"] == "active" and (run_id is None or obj["run_id"] == run_id)
                and (round_number is None or obj["round"] == round_number)):
            out.append(obj)
    return out


def require_no_open(root, run_id, round_number):
    open_rows = list_open(root, run_id, round_number)
    if open_rows:
        pending = sum(1 for obj in open_rows for row in obj["items"].values()
                      if row.get("outcome") is None)
        raise StageCheckpointError(
            f"当前轮次有未完成阶段检查点({pending} 个 pending item)；先 mark 并 finish")


def require_trigger_checkpoint(root, run_id, round_number, harvested):
    """本轮产生 raw trigger 时，必须存在已完成且已交叉核验的 trigger 检查点。"""
    if harvested == 0:
        return
    try:
        # finish 对 completed 检查点也是只读幂等校验，会再次交叉核对触发池状态。
        obj = finish(root, run_id, round_number, "trigger")
    except StageCheckpointError as e:
        raise StageCheckpointError(f"本轮 raw trigger 缺 trigger 检查点: {e}")
    if obj.get("status") != "completed" or len(obj.get("items") or {}) != harvested:
        raise StageCheckpointError("本轮 raw trigger 缺已完成且数量一致的 trigger 检查点")


def main(argv=None):
    ap = argparse.ArgumentParser(description="xinci 轮内阶段检查点")
    ap.add_argument("--data-root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    p.add_argument("--run-id", required=True); p.add_argument("--round", type=int, required=True)
    p.add_argument("--stage", default="scan")
    p = sub.add_parser("mark")
    p.add_argument("--run-id", required=True); p.add_argument("--round", type=int, required=True)
    p.add_argument("--stage", default="scan"); p.add_argument("--item", required=True)
    p.add_argument("--outcome", choices=sorted(OUTCOMES), required=True); p.add_argument("--note")
    for name in ("show", "finish"):
        p = sub.add_parser(name)
        p.add_argument("--run-id", required=True); p.add_argument("--round", type=int, required=True)
        p.add_argument("--stage", default="scan")
    p = sub.add_parser("list-open"); p.add_argument("--run-id"); p.add_argument("--round", type=int)
    args = ap.parse_args(argv)
    root = data_root.resolve_or_exit(args.data_root)
    try:
        if args.cmd == "start":
            obj = start(root, args.run_id, args.round,
                        [line for line in sys.stdin.read().splitlines() if line.strip()], args.stage)
        elif args.cmd == "mark":
            obj = mark(root, args.run_id, args.round, args.item, args.outcome, args.note, args.stage)
        elif args.cmd == "finish":
            obj = finish(root, args.run_id, args.round, args.stage)
        elif args.cmd == "list-open":
            obj = list_open(root, args.run_id, args.round)
        else:
            obj = _load(checkpoint_path(root, args.run_id, args.round, args.stage))
    except StageCheckpointError as e:
        print(f"stage_checkpoint 拒绝: {e}", file=sys.stderr)
        return 2
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
