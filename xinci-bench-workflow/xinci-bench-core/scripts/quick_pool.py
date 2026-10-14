#!/usr/bin/env python3
"""快道原料池与淘汰记录:登记原料(去重)、取待看原料、列出即将开玩的对象、标记已用或过期、记速判不过的词。"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import data_root
import quick_model as QM
import seeds
from _common import (LEDGER_REL, QUICK_POOL_REL, QUICK_REJECTS_REL, VERDICTS_REL, BenchError,
                     atomic_save, load_json, now, require, today)

STATUSES = ("pending", "used", "expired")
QUICK_GATES = ("scope", "not_new", "oneoff", "occupied", "answered", "volume")


def normalize_term(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    require(t, "原料词不能为空")
    return t


def _key(item) -> str:
    return normalize_term(item.get("term") or item["object"])


def _read_pool(root) -> list:
    p = Path(root) / QUICK_POOL_REL
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_pool(root, rows) -> None:
    p = Path(root) / QUICK_POOL_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(p)


def _rejects(root) -> dict:
    p = Path(root) / QUICK_REJECTS_REL
    return load_json(p) if p.is_file() else {"schema_version": 1, "terms": {}}


def _known_terms(root) -> dict:
    """已有快道方向的说法、旧裁决的主词 → 去重来源。"""
    known = {}
    ledger_p = Path(root) / LEDGER_REL
    if ledger_p.is_file():
        for slug, rec in load_json(ledger_p)["directions"].items():
            for t in rec.get("terms") or []:
                known[normalize_term(t["term"])] = f"已有方向 {slug}"
    ver_p = Path(root) / VERDICTS_REL
    if ver_p.is_file():
        for slug, v in load_json(ver_p)["candidates"].items():
            if v.get("primary_keyword"):
                known.setdefault(normalize_term(v["primary_keyword"]), f"旧裁决 {slug}({v.get('state')})")
    return known


def add_items(root, items, observation) -> dict:
    """登记一批原料;已在池里、被快道淘汰过、已有方向或旧裁决的跳过,返回新增与跳过原因。"""
    require(isinstance(observation, str) and observation.startswith("证据/_quick/"), "observation 须为 quick_signal 观察路径")
    rows, rejects, known = _read_pool(root), _rejects(root)["terms"], _known_terms(root)
    live = {_key(r) for r in rows if r["status"] != "expired"}
    pending_rows = {_key(r): r for r in rows if r["status"] == "pending"}
    expired = {_key(r): r for r in rows if r["status"] == "expired"}
    added, skipped = [], []
    for it in items:
        k = _key(it)
        reason = (f"快道淘汰过({rejects[k]['gate']})" if k in rejects else
                  "已在原料池" if k in live else known.get(k))
        if reason:
            row = pending_rows.get(k)
            if row is not None:            # 又被别的来源看到:记下来,排优先级时算"几个来源"
                row.setdefault("also_seen", []).append({"source": it["source"], "seen_at": it["seen_at"],
                                                        "observation": observation})
                row["rising"] = _max_rising(row.get("rising"), it.get("rising"))
                if it.get("playable_at"):  # 开玩日期以最新看到的为准(延期、改测试日期)
                    row.update(playable_at=it["playable_at"], stage=it.get("stage") or row.get("stage"))
            skipped.append({"term": k, "reason": reason})
            continue
        fresh = {"source": it["source"], "object": it["object"], "term": it.get("term"), "url": it["url"],
                 "seen_at": it["seen_at"], "rising": it.get("rising"), "status": "pending", "observation": observation}
        if it.get("playable_at"):
            fresh.update(playable_at=it["playable_at"], stage=it.get("stage"))
        row = expired.pop(k, None)
        if row is not None:           # 过期后又被来源取回:原行复活,保留 id
            row.update(fresh, revived_at=now())
        else:
            row = {"id": hashlib.sha1(k.encode("utf-8")).hexdigest()[:12], **fresh}
            rows.append(row)
        live.add(k)
        added.append(row)
    _write_pool(root, rows)
    return {"added": added, "skipped": skipped}


def _rising_value(r):
    return float("inf") if r == "breakout" else (r or 0)


def _max_rising(a, b):
    return a if _rising_value(a) >= _rising_value(b) else b


def priority(row) -> tuple:
    """排序键(越小越先看):有具体说法 > 被几个来源看到 > Trends 飙升幅度(breakout 最大) > 先看到的。"""
    sources = {row["source"]} | {a["source"] for a in row.get("also_seen") or []}
    return (row.get("term") is None, -len(sources), -_rising_value(row.get("rising")), row["seen_at"])


def _not_yet(row, on) -> bool:
    return bool(row.get("playable_at")) and row["playable_at"] > on


def pending(root, top=None, on=None) -> list:
    """待看原料按优先级排序;首屏速判每次取前 10 个。还没到开玩日的不列(在 upcoming 里)。"""
    on = on or today()
    rows = sorted((r for r in _read_pool(root) if r["status"] == "pending" and not _not_yet(r, on)), key=priority)
    return rows[:top] if top else rows


def upcoming(root, on=None, days=14) -> list:
    """即将开玩:待看原料里开玩日期在今天之后 days 天以内的,按日期排。"""
    on = on or today()
    until = (date.fromisoformat(on) + timedelta(days=days)).isoformat()
    rows = [r for r in _read_pool(root) if r["status"] == "pending" and _not_yet(r, on) and r["playable_at"] <= until]
    return sorted(rows, key=lambda r: (r["playable_at"], r["object"]))


def mark(root, ids, status) -> None:
    require(status in STATUSES, f"status 须为 {STATUSES}")
    rows = _read_pool(root)
    want = set(ids)
    found = {r["id"] for r in rows if r["id"] in want}
    require(found == want, f"原料池里没有: {sorted(want - found)}")
    for r in rows:
        if r["id"] in want:
            r["status"] = status
            r["updated_at"] = now()
    _write_pool(root, rows)


def consume(root, terms) -> list:
    """登记或否决之后,把这些说法对应的待看原料标 used,下次不再列出;返回标掉的 id。"""
    keys = {normalize_term(t) for t in terms}
    rows, used = _read_pool(root), []
    for r in rows:
        if r["status"] == "pending" and _key(r) in keys:
            r["status"] = "used"
            r["updated_at"] = now()
            used.append(r["id"])
    if used:
        _write_pool(root, rows)
    return used


def expire(root, on=None) -> list:
    """待看原料超过 7 天(拿不到"有人在搜"的证据)标 expired;带开玩日期的从开玩日起算。"""
    on = date.fromisoformat(on or today())
    rows, gone = _read_pool(root), []
    for r in rows:
        start = max(r["seen_at"], r.get("playable_at") or r["seen_at"])
        if r["status"] == "pending" and (on - date.fromisoformat(start)).days > QM.QUICK_ASSUMPTIONS["pool_days"]:
            r["status"] = "expired"
            gone.append(r["id"])
    if gone:
        _write_pool(root, rows)
    return gone


def reject_term(root, term, gate, observation, on=None, seed_domain=None) -> dict:
    """速判不过的词进快道淘汰记录,同词不再看;首页被小站做了(occupied)时顺带把它登记为标杆道种子。"""
    require(gate in QUICK_GATES, f"gate 须为 {QUICK_GATES}")
    require(isinstance(observation, str) and observation.startswith("证据/"), "observation 须为速判观察路径")
    require(seed_domain is None or gate == "occupied", "只有 occupied 才能顺带登记标杆种子")
    t = normalize_term(term)
    entry = {"gate": gate, "at": on or today(), "observation": observation}
    if seed_domain:
        entry["seed"] = seeds.normalize_domain(seed_domain)
        entry["seed_added"] = seeds.add(root, seed_domain, "serp", f"快道速判 {t} 首页({observation})")
    data = _rejects(root)
    data["terms"][t] = entry
    atomic_save(Path(root) / QUICK_REJECTS_REL, data)
    return dict(entry, consumed=consume(root, [t]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("add")
    a1.add_argument("--observation", required=True, help="quick_signal 观察路径,原料取自它的 items")
    pe = sub.add_parser("pending")
    pe.add_argument("--top", type=int, help="只列优先级最高的前 N 个(首屏速判取 10)")
    m = sub.add_parser("mark")
    m.add_argument("--id", action="append", required=True)
    m.add_argument("--status", required=True, choices=STATUSES)
    up = sub.add_parser("upcoming")
    up.add_argument("--days", type=int, default=14, help="列出今天之后多少天内开玩的对象")
    sub.add_parser("expire")
    r = sub.add_parser("reject")
    r.add_argument("--term", required=True)
    r.add_argument("--gate", required=True, choices=QUICK_GATES)
    r.add_argument("--observation", required=True)
    r.add_argument("--seed-domain", help="occupied 且占位的是小站时,登记为标杆道种子(来源 serp)")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "add":
            obs = load_json(Path(root) / a.observation)
            require(obs.get("kind") == "quick_signal", "--observation 须为 quick_signal 观察")
            out = add_items(root, obs["readings"]["items"], a.observation)
        elif a.cmd == "pending":
            out = pending(root, a.top)
        elif a.cmd == "upcoming":
            out = upcoming(root, days=a.days)
        elif a.cmd == "mark":
            mark(root, a.id, a.status)
            out = {"marked": a.id, "status": a.status}
        elif a.cmd == "expire":
            out = {"expired": expire(root)}
        else:
            out = reject_term(root, a.term, a.gate, a.observation, seed_domain=a.seed_domain)
    except (BenchError, OSError, ValueError, KeyError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
