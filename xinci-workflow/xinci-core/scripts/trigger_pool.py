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
            require_active_round(root, run_id)
        except RunControllerError as e:
            raise TriggerPoolError(str(e))
    elif run_id:
        raise TriggerPoolError("非 xinci-run 事件不得携带 run_id")


def add(root, *, observed_date, title, source_url, source_family, task_hypothesis,
        actor="user", run_id=None):
    _check_actor(root, actor, run_id)
    tid = _id(title, source_url)
    if tid in current(root):
        raise TriggerPoolError(f"触发已存在: {tid}")
    row = {"trigger_id": tid, "event": "add", "at": _now(), "actor": actor,
           "observed_date": observed_date, "title": title, "source_url": source_url,
           "source_family": source_family, "task_hypothesis": task_hypothesis}
    if run_id:
        row["run_id"] = run_id
    return _append(root, row)


def approve(root, trigger_id, *, query, search_evidence_urls, payer, repeat_unit,
            self_serve_path, base_case_source, reason, actor="user", run_id=None):
    _check_actor(root, actor, run_id)
    state = current(root).get(trigger_id)
    if not state or state["status"] != "pending":
        raise TriggerPoolError("approve 要求存在且 pending 的 trigger_id")
    row = {"trigger_id": trigger_id, "event": "approve", "at": _now(), "actor": actor,
           "query": query, "search_evidence_urls": list(search_evidence_urls), "payer": payer,
           "repeat_unit": repeat_unit, "self_serve_path": self_serve_path,
           "base_case_source": base_case_source, "reason": reason}
    if run_id:
        row["run_id"] = run_id
    return _append(root, row)


def discard(root, trigger_id, *, reason, actor="user", run_id=None):
    """废弃一个 trigger。pending 与 approved 都可以走这条边:后者用于批准之后
    方向才被闸门否决的情形,reason 应写明失败的闸门与现场结论。"""
    _check_actor(root, actor, run_id)
    state = current(root).get(trigger_id)
    if not state or state["status"] not in {"pending", "approved"}:
        raise TriggerPoolError("discard 要求存在且未废弃的 trigger_id")
    row = {"trigger_id": trigger_id, "event": "discard", "at": _now(), "actor": actor,
           "reason": reason}
    if run_id:
        row["run_id"] = run_id
    return _append(root, row)


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
