#!/usr/bin/env python3
"""种子池与淘汰索引:取一批待初核域名、登记新发现、记初核不过、到期回池。"""
import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import data_root
from _common import REJECTS_REL, SEEDS_REL, BenchError, atomic_save, load_json, now, require, today

SOURCES = ("legacy", "sibling", "serp", "geo", "community")
ROLES = ("benchmark", "sibling")
RECHECK_DAYS = 90
_DOMAIN = re.compile(r"[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*\.[a-z]{2,}")


def normalize_domain(text: str) -> str:
    """https://www.Example.com/a?b → example.com;不是域名就拒收。"""
    d = (text or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d).split("/")[0].split("?")[0].split(":")[0]
    d = d.rstrip(".").removeprefix("www.")
    require(_DOMAIN.fullmatch(d), f"不是有效域名: {text!r}")
    return d


def _load(root):
    return load_json(Path(root) / SEEDS_REL), load_json(Path(root) / REJECTS_REL)


def add(root, domain, source, source_ref, role="benchmark") -> bool:
    """登记新种子;已在池里或在淘汰索引里的不重复登记,返回是否新增。"""
    require(source in SOURCES, f"source 须为 {SOURCES}")
    require(role in ROLES, f"role 须为 {ROLES}")
    require(isinstance(source_ref, str) and source_ref.strip(), "source_ref 须写明从哪发现的")
    d = normalize_domain(domain)
    pool, rejects = _load(root)
    if d in pool["seeds"] or d in rejects["domains"]:
        return False
    pool["seeds"][d] = {"source": source, "source_ref": source_ref, "role": role,
                        "added_at": now(), "status": "pending"}
    atomic_save(Path(root) / SEEDS_REL, pool)
    return True


def take(root, source, n=16, role="benchmark") -> list:
    """按登记顺序取 n 个待初核种子,只读不标记。"""
    require(source in SOURCES and role in ROLES, "source 或 role 无效")
    pool, _ = _load(root)
    picked = [{"domain": d, **s} for d, s in pool["seeds"].items()
              if s["source"] == source and s["role"] == role and s["status"] == "pending"]
    return picked[:n]


def mark_checked(root, domains) -> None:
    pool, _ = _load(root)
    for raw in domains:
        d = normalize_domain(raw)
        require(d in pool["seeds"], f"种子池里没有 {d}")
        pool["seeds"][d]["status"] = "checked"
        pool["seeds"][d]["checked_at"] = now()
    atomic_save(Path(root) / SEEDS_REL, pool)


def reject(root, domain, failed, readings, observation, on=None) -> dict:
    """记初核不过;只有 B3 不过的才设 90 天复查(新站还会长)。"""
    require(failed and set(failed) <= {"B1", "B2", "B3", "B4", "B5"}, "failed 须为 B1–B5 的非空子集")
    require(isinstance(readings, str) and readings.strip(), "readings 须写读数摘要")
    require(isinstance(observation, str) and observation.startswith("证据/_scan/"), "observation 须为 scan 观察路径")
    d = normalize_domain(domain)
    on = on or today()
    pool, rejects = _load(root)
    entry = {"failed": sorted(set(failed)), "readings": readings, "at": on,
             "recheck_after": (date.fromisoformat(on) + timedelta(days=RECHECK_DAYS)).isoformat()
             if set(failed) == {"B3"} else None,
             "observation": observation}
    rejects["domains"][d] = entry
    atomic_save(Path(root) / REJECTS_REL, rejects)
    if d in pool["seeds"]:
        pool["seeds"][d]["status"] = "checked"
        pool["seeds"][d]["checked_at"] = now()
        atomic_save(Path(root) / SEEDS_REL, pool)
    return entry


def requeue(root, on=None) -> list:
    """把复查日已到的 B3 淘汰域名放回种子池(状态 pending),并移出淘汰索引。"""
    on = on or today()
    pool, rejects = _load(root)
    due = [d for d, e in rejects["domains"].items() if e["recheck_after"] and e["recheck_after"] <= on]
    for d in due:
        e = rejects["domains"].pop(d)
        seed = pool["seeds"].get(d) or {"source": "legacy", "source_ref": e["observation"],
                                         "role": "benchmark", "added_at": now()}
        seed.update(status="pending", requeued_at=now(), requeued_from=e)
        pool["seeds"][d] = seed
    if due:
        atomic_save(Path(root) / SEEDS_REL, pool)
        atomic_save(Path(root) / REJECTS_REL, rejects)
    return due


def stats(root, on=None) -> dict:
    on = on or today()
    pool, rejects = _load(root)
    pending = {}
    for s in pool["seeds"].values():
        if s["status"] == "pending":
            key = f"{s['source']}/{s['role']}"
            pending[key] = pending.get(key, 0) + 1
    due = sum(1 for e in rejects["domains"].values() if e["recheck_after"] and e["recheck_after"] <= on)
    return {"pending": pending, "checked": sum(s["status"] == "checked" for s in pool["seeds"].values()),
            "rejected": len(rejects["domains"]), "recheck_due": due}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("take")
    t.add_argument("--source", required=True, choices=SOURCES)
    t.add_argument("--role", default="benchmark", choices=ROLES)
    t.add_argument("--n", type=int, default=16)
    ad = sub.add_parser("add")
    ad.add_argument("--domain", required=True)
    ad.add_argument("--source", required=True, choices=SOURCES)
    ad.add_argument("--source-ref", required=True)
    ad.add_argument("--role", default="benchmark", choices=ROLES)
    m = sub.add_parser("checked")
    m.add_argument("--domain", action="append", required=True)
    r = sub.add_parser("reject")
    r.add_argument("--domain", required=True)
    r.add_argument("--failed", action="append", required=True)
    r.add_argument("--readings", required=True)
    r.add_argument("--observation", required=True)
    sub.add_parser("requeue")
    sub.add_parser("stats")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "take":
            out = take(root, a.source, a.n, a.role)
        elif a.cmd == "add":
            out = {"added": add(root, a.domain, a.source, a.source_ref, a.role)}
        elif a.cmd == "checked":
            mark_checked(root, a.domain)
            out = {"checked": a.domain}
        elif a.cmd == "reject":
            out = reject(root, a.domain, a.failed, a.readings, a.observation)
        elif a.cmd == "requeue":
            out = {"requeued": requeue(root)}
        else:
            out = stats(root)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
