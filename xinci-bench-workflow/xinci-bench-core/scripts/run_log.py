#!/usr/bin/env python3
"""运行清单:阶段进度只追加,保存预算、恢复位置与来源;--plan 推导下一步,--finish 结束阶段。"""
import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import data_root
import seeds
from _common import BenchError, atomic_save, load_json, load_ledger, require, today

SKILLS = ("xinci-bench-scan", "xinci-bench-assess", "xinci-bench-quick")
STAGE = {"xinci-bench-scan": "scan", "xinci-bench-assess": "assess", "xinci-bench-quick": "quick"}
LANE_OF = {"xinci-bench-scan": "bench", "xinci-bench-assess": "bench", "xinci-bench-quick": "quick"}
SOURCE_KINDS = seeds.SOURCES + ("quick",)
ROTATION = ("sibling", "serp", "geo", "community")
OUTCOMES = ("started", "completed", "blocked", "skipped")
FOUND_TARGET = 3


def records(root) -> list:
    rows = []
    for path in (Path(root) / "运行").glob("*.json"):
        row = load_json(path)
        row["_path"] = str(path)
        rows.append(row)
    return sorted(rows, key=lambda r: (r["recorded_at"], r["_path"]))


def latest_runs(rows, lane=None) -> dict:
    """每个运行编号的最新一条;给了 lane 就只看这条道的运行(两条道互不阻塞)。"""
    latest = {}
    for row in rows:
        if lane is None or LANE_OF[row["skill"]] == lane:
            latest[row["progress"]["run_id"]] = row
    return latest


def next_position(row):
    """该运行下一阶段的位置;运行已结束返回 None。"""
    p = row["progress"]
    if p["next_step"] == "done":
        return None
    if STAGE[row["skill"]] == "quick":
        return {"stage": "quick", "round": 1}
    bump = STAGE[row["skill"]] == "assess" and p["outcome"] == "completed"
    return {"stage": p["next_step"], "round": p["round"] + int(bump)}


def _expected_next(stage, outcome, rnd, max_rounds):
    if outcome in ("started", "blocked"):
        return stage
    if stage == "quick":
        return "done"
    if stage == "scan":
        return "assess"
    return "done" if rnd == max_rounds else "scan"


def record(root, *, skill, progress, sources_opened=(), directions_touched=(), semrush_calls=0, notes=()) -> Path:
    require(skill in SKILLS, f"skill 须为 {SKILLS}")
    keys = ("run_id", "round", "max_rounds", "source_kind", "seed_value", "outcome", "next_step")
    require(all(k in progress for k in keys), f"progress 须含 {keys}")
    p = progress
    require(re.fullmatch(r"[a-zA-Z0-9-]+", str(p["run_id"])), "run_id 只能用字母数字连字符")
    require(type(p["round"]) is int and type(p["max_rounds"]) is int and 1 <= p["round"] <= p["max_rounds"],
            "轮次或预算无效")
    require(p["source_kind"] in SOURCE_KINDS, f"source_kind 须为 {SOURCE_KINDS}")
    lane = LANE_OF[skill]
    require((p["source_kind"] == "quick") == (lane == "quick"), "快道运行的 source_kind 固定为 quick,标杆道不能用 quick")
    require(lane == "bench" or p["max_rounds"] == 1, "快道运行一次只走一遍,max_rounds 固定为 1")
    require(isinstance(p["seed_value"], str) and p["seed_value"].strip(), "seed_value 须写本阶段从哪取种子")
    require(p["outcome"] in OUTCOMES, f"outcome 须为 {OUTCOMES}")
    require(isinstance(semrush_calls, int) and semrush_calls >= 0, "semrush_calls 须为非负整数")
    stage = STAGE[skill]
    require(not (p["outcome"] == "skipped" and stage != "scan"), "只能跳过标杆道的发现阶段")
    require(p["next_step"] == _expected_next(stage, p["outcome"], p["round"], p["max_rounds"]),
            "next_step 与阶段、结果、轮次不一致")
    history = records(root)
    same = [r for r in history if r["progress"]["run_id"] == p["run_id"]]
    if same:
        cursor = next_position(same[-1])
        require(cursor is not None, "该运行已结束,不能追加")
        require(cursor == {"stage": stage, "round": p["round"]}, f"恢复位置应为 {cursor}")
        require(all(r["progress"]["max_rounds"] == p["max_rounds"] for r in same), "同一 run_id 的预算不能改")
        last = same[-1]["progress"]
        if last["outcome"] in ("started", "blocked"):
            require(p["outcome"] != "started", "该阶段已开始,结束请用 --finish")
    else:
        require(not any(next_position(r) for r in latest_runs(history, lane).values()),
                "这条道存在未完成运行,须先恢复;不能创建新 run_id")
        first = "quick" if lane == "quick" else "scan"
        require(p["round"] == 1 and stage == first and p["outcome"] == "started",
                f"新运行须从第 1 轮 {first} started 开始")
    path = Path(root) / "运行" / f"{today()}-{skill}-{p['run_id']}-r{p['round']}-{uuid.uuid4().hex[:8]}.json"
    # 微秒精度:同一秒内写多条时排序仍确定,恢复位置才不会读错
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    atomic_save(path, {"skill": skill, "recorded_at": recorded_at, "progress": dict(p),
                       "sources_opened": list(dict.fromkeys(sources_opened)),
                       "directions_touched": sorted(set(directions_touched)),
                       "semrush_calls": semrush_calls, "notes": list(notes)})
    return path


def _next_source(root, rows):
    if seeds.take(root, "legacy", 1):
        return "legacy", "旧数据导入的标杆种子还有待初核的,先用完"
    done = [r for r in rows if STAGE[r["skill"]] == "scan" and r["progress"]["outcome"] == "completed"
            and r["progress"]["source_kind"] in ROTATION]
    if not done:
        return ROTATION[0], "legacy 已用完,按固定轮换从 sibling 开始"
    last = done[-1]["progress"]["source_kind"]
    nxt = ROTATION[(ROTATION.index(last) + 1) % len(ROTATION)]
    return nxt, f"上次完成的发现来源是 {last},按固定轮换下一个是 {nxt}"


def _plan_quick(root, rows, run_id):
    latest = latest_runs(rows, "quick")
    active = {k: r for k, r in latest.items() if next_position(r)}
    require(run_id is None or run_id in latest, "指定的 run_id 不存在")
    conflict = run_id is None and len(active) > 1
    selected = latest.get(run_id) if run_id else (next(iter(active.values())) if len(active) == 1 else None)
    resume, action = None, "quick"
    if selected:
        if next_position(selected):
            resume = dict(selected["progress"], next_step="quick")
        else:
            action = "done"
    return {"lane": "quick", "action": None if conflict else action, "resume": resume, "conflict": conflict,
            "active_run_ids": sorted(active), "latest_log": selected["_path"] if selected else None,
            "semrush_calls_total": sum(r["semrush_calls"] for r in rows)}


def plan(root, run_id=None, lane="bench") -> dict:
    rows = records(root)
    if lane == "quick":
        return _plan_quick(root, rows, run_id)
    latest = latest_runs(rows, "bench")
    active = {k: r for k, r in latest.items() if next_position(r)}
    require(run_id is None or run_id in latest, "指定的 run_id 不存在")
    conflict = run_id is None and len(active) > 1
    selected = latest.get(run_id) if run_id else (next(iter(active.values())) if len(active) == 1 else None)
    found = sum(r["state"] == "found" for r in load_ledger(root)["directions"].values())
    source, reason = _next_source(root, rows)
    resume, action = None, "scan"
    if selected:
        cursor = next_position(selected)
        if cursor:
            resume = dict(selected["progress"], round=cursor["round"], next_step=cursor["stage"])
            action = cursor["stage"]
            if STAGE[selected["skill"]] == cursor["stage"]:
                source, reason = selected["progress"]["source_kind"], "恢复已开始的阶段,保持原来源与 seed_value"
        else:
            action = "done"
    return {"found_count": found, "action": None if conflict else action,
            "scan_outcome": "skipped" if action == "scan" and found >= FOUND_TARGET and not conflict else None,
            "resume": resume, "conflict": conflict, "active_run_ids": sorted(active),
            "next_source": source, "source_reason": reason,
            "latest_log": selected["_path"] if selected else None,
            "semrush_calls_total": sum(r["semrush_calls"] for r in rows)}


def finish(root, *, run_id, outcome="completed", sources_opened=(), directions_touched=(), semrush_calls=0,
           notes=()) -> Path:
    row = latest_runs(records(root)).get(run_id)
    require(row and row["progress"]["outcome"] in ("started", "blocked"),
            "finish 只针对 started/blocked 阶段;阶段已结束时不要重记调用数")
    require(outcome in ("completed", "blocked", "skipped"), "finish 的 outcome 须为 completed/blocked/skipped")
    p = dict(row["progress"], outcome=outcome)
    p["next_step"] = _expected_next(STAGE[row["skill"]], outcome, p["round"], p["max_rounds"])
    return record(root, skill=row["skill"], progress=p, sources_opened=sources_opened,
                  directions_touched=directions_touched, semrush_calls=semrush_calls, notes=notes)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--finish", action="store_true")
    ap.add_argument("--run-id")
    ap.add_argument("--lane", choices=("bench", "quick"), default="bench", help="--plan 看哪条道")
    ap.add_argument("--skill", choices=SKILLS)
    ap.add_argument("--round", type=int)
    ap.add_argument("--max-rounds", type=int)
    ap.add_argument("--source-kind", choices=SOURCE_KINDS)
    ap.add_argument("--seed-value")
    ap.add_argument("--outcome", choices=OUTCOMES)
    ap.add_argument("--next-step", choices=("scan", "assess", "quick", "done"))
    ap.add_argument("--source-opened", action="append", default=[])
    ap.add_argument("--direction-touched", action="append", default=[])
    ap.add_argument("--semrush-calls", type=int, default=0)
    ap.add_argument("--note", action="append", default=[])
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.plan:
            print(json.dumps(plan(root, a.run_id, a.lane), ensure_ascii=False, indent=2))
            return 0
        if a.finish:
            out = finish(root, run_id=a.run_id, outcome=a.outcome or "completed", sources_opened=a.source_opened,
                         directions_touched=a.direction_touched, semrush_calls=a.semrush_calls, notes=a.note)
        else:
            progress = {"run_id": a.run_id, "round": a.round, "max_rounds": a.max_rounds,
                        "source_kind": a.source_kind, "seed_value": a.seed_value,
                        "outcome": a.outcome, "next_step": a.next_step}
            require(all(v is not None for v in progress.values()) and a.skill,
                    "写清单须提供 --skill/--run-id/--round/--max-rounds/--source-kind/--seed-value/--outcome/--next-step")
            out = record(root, skill=a.skill, progress=progress, sources_opened=a.source_opened,
                         directions_touched=a.direction_touched, semrush_calls=a.semrush_calls, notes=a.note)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(f"已写 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
