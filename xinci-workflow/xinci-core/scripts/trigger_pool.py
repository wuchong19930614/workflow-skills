#!/usr/bin/env python3
"""原始变化触发池：把官方标题与可注册搜索候选分开。

官方公告只能先 add；approve 必须给出用户会搜索的 task query、独立搜索语言证据和
商业预检。批准仍不等于候选通过闸门，只表示允许进入 xinci-scan 的正式候选入口。
"""
import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import data_root
from run_controller import RunControllerError, require_active_round


FILE_NAME = "触发池.jsonl"
EVENTS = {"add", "approve", "discard"}
ACTORS = {"user", "xinci-scan", "xinci-run"}


class TriggerPoolError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _url(value):
    try:
        p = urlparse(value)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except (TypeError, ValueError):
        return False


def _day(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _id(title, source_url):
    raw = f"{title.strip().lower()}\n{source_url.strip()}".encode()
    return "trigger-" + hashlib.sha256(raw).hexdigest()[:16]


def _validate(row, line=None):
    where = f"第 {line} 行" if line else "事件"
    if not isinstance(row, dict) or row.get("event") not in EVENTS:
        raise TriggerPoolError(f"触发池{where} event 非法")
    required = {"trigger_id", "event", "at", "actor"}
    if (not required <= set(row) or not row.get("trigger_id", "").startswith("trigger-")
            or row.get("actor") not in ACTORS
            or (row.get("actor") == "xinci-run" and not row.get("run_id"))):
        raise TriggerPoolError(f"触发池{where}缺公共字段")
    try:
        at = datetime.fromisoformat(row["at"])
        if at.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError):
        raise TriggerPoolError(f"触发池{where} at 必须是带时区 ISO 时间")
    if row["event"] == "add":
        needed = {"observed_date", "title", "source_url", "source_family", "task_hypothesis"}
        if (not needed <= set(row) or not _day(row.get("observed_date"))
                or not row.get("title") or not _url(row.get("source_url"))
                or not row.get("source_family") or not row.get("task_hypothesis")):
            raise TriggerPoolError(f"触发池{where} add 字段非法")
        if row["trigger_id"] != _id(row["title"], row["source_url"]):
            raise TriggerPoolError(f"触发池{where} trigger_id 与标题/来源不一致")
    elif row["event"] == "approve":
        needed = {"query", "search_evidence_urls", "payer", "repeat_unit",
                  "self_serve_path", "base_case_source", "reason"}
        if (not needed <= set(row) or len((row.get("query") or "").split()) < 2
                or not isinstance(row.get("search_evidence_urls"), list)
                or not row["search_evidence_urls"]
                or not all(_url(x) for x in row["search_evidence_urls"])
                or not all(row.get(x) for x in
                           ("payer", "repeat_unit", "self_serve_path", "base_case_source", "reason"))
                or not _url(row["base_case_source"])):
            raise TriggerPoolError(f"触发池{where} approve 缺搜索语言证据或商业预检")
    elif not row.get("reason"):
        raise TriggerPoolError(f"触发池{where} discard 要求 reason")
    return row


def load(root):
    path = Path(root) / FILE_NAME
    if not path.is_file():
        return []
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise TriggerPoolError(f"触发池第 {i} 行不是合法 JSON: {e}")
        out.append(_validate(row, i))
    return out


def current(root):
    states = {}
    for row in load(root):
        tid = row["trigger_id"]
        if row["event"] == "add":
            if tid in states:
                raise TriggerPoolError(f"重复 add: {tid}")
            states[tid] = {**row, "status": "pending"}
        else:
            if tid not in states:
                raise TriggerPoolError(f"{row['event']} 指向不存在的 trigger: {tid}")
            status = states[tid]["status"]
            # approved 保留唯一一条 discard 出边:批准只表示可进 G0,方向随后被闸门否决
            # (典型是 G1 实测 veto)时要能作废,否则死方向永远挂在 approved 上被反复提取。
            if status == "discarded" or (status == "approved" and row["event"] != "discard"):
                raise TriggerPoolError(f"trigger 已终结，不可追加 {row['event']}: {tid}")
            states[tid].update(row)
            states[tid]["status"] = "approved" if row["event"] == "approve" else "discarded"
    return states


def _append(root, row):
    _validate(row)
    path = Path(root) / FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _check_actor(root, actor, run_id):
    if actor not in ACTORS:
        raise TriggerPoolError(f"actor 必须属于 {sorted(ACTORS)}")
    if actor == "xinci-run":
        if not run_id:
            raise TriggerPoolError("actor=xinci-run 要求 run_id")
        try:
            return require_active_round(root, run_id)["current_round"]
        except RunControllerError as e:
            raise TriggerPoolError(str(e))
    elif run_id:
        raise TriggerPoolError("非 xinci-run 事件不得携带 run_id")
    return None


def source_rotation_status(root, run_id, current_round=None):
    """返回本次运行必须暂停使用的来源家族。

    两条独立约束都在这里计算，供策略提示与 add 写入口共同使用：
    1) 一个来源家族占本 run 新 trigger 超过 40%（至少已有 5 条）；
    2) 同一来源家族已经连续主导两个已完成轮次，下一轮必须轮换。
    """
    adds = [row for row in load(root)
            if row.get("event") == "add" and row.get("run_id") == run_id]
    family_counts = {}
    for row in adds:
        family = row.get("source_family", "(unknown)")
        family_counts[family] = family_counts.get(family, 0) + 1

    blocked = set()
    dominant_family = max(family_counts, key=family_counts.get) if family_counts else None
    dominant_share = ((family_counts[dominant_family] / len(adds)) if dominant_family else 0)
    if len(adds) >= 5:
        blocked.update(family for family, count in family_counts.items()
                       if count / len(adds) > 0.40)

    by_round = {}
    for row in adds:
        number = row.get("round")
        if not isinstance(number, int) or (current_round is not None and number >= current_round):
            continue
        counts = by_round.setdefault(number, {})
        family = row.get("source_family", "(unknown)")
        counts[family] = counts.get(family, 0) + 1
    round_dominants = []
    for number in sorted(by_round):
        counts = by_round[number]
        highest = max(counts.values())
        leaders = sorted(family for family, count in counts.items() if count == highest)
        round_dominants.append((number, leaders[0] if len(leaders) == 1 else None))
    consecutive_family = None
    if len(round_dominants) >= 2:
        previous, latest = round_dominants[-2:]
        if (previous[0] + 1 == latest[0] and previous[1]
                and previous[1] == latest[1]):
            consecutive_family = latest[1]
            blocked.add(consecutive_family)

    return {
        "family_counts": family_counts,
        "dominant_family": dominant_family,
        "dominant_share": dominant_share,
        "consecutive_family": consecutive_family,
        "blocked_source_families": sorted(blocked),
    }


def add(root, *, observed_date, title, source_url, source_family, task_hypothesis,
        actor="user", run_id=None):
    round_number = _check_actor(root, actor, run_id)
    if actor == "xinci-run":
        rotation = source_rotation_status(root, run_id, round_number)
        if source_family in rotation["blocked_source_families"]:
            raise TriggerPoolError(
                f"source family {source_family!r} 已命中轮换约束；本轮必须改用其他来源")
    tid = _id(title, source_url)
    if tid in current(root):
        raise TriggerPoolError(f"触发已存在: {tid}")
    row = {"trigger_id": tid, "event": "add", "at": _now(), "actor": actor,
           "observed_date": observed_date, "title": title, "source_url": source_url,
           "source_family": source_family, "task_hypothesis": task_hypothesis}
    if run_id:
        row["run_id"] = run_id; row["round"] = round_number
    return _append(root, row)


def approve(root, trigger_id, *, query, search_evidence_urls, payer, repeat_unit,
            self_serve_path, base_case_source, reason, actor="user", run_id=None):
    round_number = _check_actor(root, actor, run_id)
    state = current(root).get(trigger_id)
    if not state or state["status"] != "pending":
        raise TriggerPoolError("approve 要求存在且 pending 的 trigger_id")
    row = {"trigger_id": trigger_id, "event": "approve", "at": _now(), "actor": actor,
           "query": query, "search_evidence_urls": list(search_evidence_urls), "payer": payer,
           "repeat_unit": repeat_unit, "self_serve_path": self_serve_path,
           "base_case_source": base_case_source, "reason": reason}
    if run_id:
        row["run_id"] = run_id; row["round"] = round_number
    return _append(root, row)


def discard(root, trigger_id, *, reason, actor="user", run_id=None):
    """废弃一个 trigger。pending 与 approved 都可以走这条边:后者用于批准之后
    方向才被闸门否决的情形,reason 应写明失败的闸门与现场结论。"""
    round_number = _check_actor(root, actor, run_id)
    state = current(root).get(trigger_id)
    if not state or state["status"] not in {"pending", "approved"}:
        raise TriggerPoolError("discard 要求存在且未废弃的 trigger_id")
    row = {"trigger_id": trigger_id, "event": "discard", "at": _now(), "actor": actor,
           "reason": reason}
    if run_id:
        row["run_id"] = run_id; row["round"] = round_number
    return _append(root, row)


def round_funnel(root, run_id, round_number):
    """按本轮 add 的 trigger 计算互斥终点；存量维护不冒充本轮 harvest。"""
    events = load(root)
    added = [row["trigger_id"] for row in events
             if row.get("run_id") == run_id and row.get("round") == round_number
             and row.get("event") == "add"]
    result = {"harvested": len(added), "discarded_preapproval": 0,
              "discarded_postapproval": 0, "pending": 0, "approved": 0}
    for trigger_id in added:
        rows = [row for row in events if row["trigger_id"] == trigger_id]
        approved = any(row["event"] == "approve" for row in rows)
        discarded = any(row["event"] == "discard" for row in rows)
        if discarded:
            result["discarded_postapproval" if approved else "discarded_preapproval"] += 1
        elif approved:
            result["approved"] += 1
        else:
            result["pending"] += 1
    return result


def round_states(root, run_id, round_number):
    """返回本轮 harvest 的 trigger 及其轮末真实状态，供检查点交叉核验。"""
    events = load(root)
    added = {row["trigger_id"] for row in events
             if row.get("run_id") == run_id and row.get("round") == round_number
             and row.get("event") == "add"}
    states = current(root)
    return {trigger_id: states[trigger_id]["status"] for trigger_id in added}


def stats(root):
    states = current(root).values()
    result = {"total": 0, "pending": 0, "approved": 0, "discarded": 0,
              "pending_by_source_family": {}}
    for row in states:
        result["total"] += 1; result[row["status"]] += 1
        if row["status"] == "pending":
            family = row.get("source_family", "(unknown)")
            result["pending_by_source_family"][family] = result["pending_by_source_family"].get(family, 0) + 1
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="xinci 原始变化触发池")
    ap.add_argument("--data-root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    for name in ("date", "title", "source-url", "source-family", "task-hypothesis"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--by", default="xinci-run"); p.add_argument("--run-id")
    p = sub.add_parser("approve"); p.add_argument("--trigger-id", required=True)
    for name in ("query", "payer", "repeat-unit", "self-serve-path", "base-case-source", "reason"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--search-evidence-url", action="append", required=True)
    p.add_argument("--by", default="xinci-run"); p.add_argument("--run-id")
    p = sub.add_parser("discard"); p.add_argument("--trigger-id", required=True)
    p.add_argument("--reason", required=True); p.add_argument("--by", default="xinci-run"); p.add_argument("--run-id")
    sub.add_parser("stats"); sub.add_parser("list")
    a = ap.parse_args(argv); root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "add":
            obj = add(root, observed_date=a.date, title=a.title, source_url=a.source_url,
                      source_family=a.source_family, task_hypothesis=a.task_hypothesis,
                      actor=a.by, run_id=a.run_id)
        elif a.cmd == "approve":
            obj = approve(root, a.trigger_id, query=a.query,
                          search_evidence_urls=a.search_evidence_url, payer=a.payer,
                          repeat_unit=a.repeat_unit, self_serve_path=a.self_serve_path,
                          base_case_source=a.base_case_source, reason=a.reason,
                          actor=a.by, run_id=a.run_id)
        elif a.cmd == "discard":
            obj = discard(root, a.trigger_id, reason=a.reason, actor=a.by, run_id=a.run_id)
        elif a.cmd == "stats": obj = stats(root)
        else: obj = list(current(root).values())
    except TriggerPoolError as e:
        print(f"trigger_pool 拒绝: {e}", file=sys.stderr); return 2
    print(json.dumps(obj, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    sys.exit(main())
