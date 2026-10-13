#!/usr/bin/env python3
"""方向账本:四态合法转移、登记、补数、排序、转移前的最小证据复核。账本只由本脚本写。"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import bench_model
import data_root
import write_observation as W
from _common import SLUG_RE, BenchError, load_json, load_ledger, now, require, save_ledger, sha256_file, today

STATES = ("found", "go", "rejected", "parked")
LEGAL = {"found": {"go", "rejected", "parked"}, "parked": {"go", "rejected"}}
GATES = ("scope", "benchmark", "answered", "revenue")
SITE_TYPES = ("tool", "content", "game", "mixed")
SCOPE_ITEMS = ("ymyl", "brand_nav", "news", "adult_gambling", "infringement")
BENCH_KEYS = ("domain", "registered_at", "aged_domain", "traffic_start", "authority_score",
              "us_organic_now", "us_organic_m12", "covered_demand", "link_driven", "algo_risk",
              "monetization", "clean")
CLUSTER_KEYS = ("id", "seed_term", "volume", "measured_at", "coverage", "near_me", "answered", "counted")
PATCHABLE = ("title", "site_type", "benchmarks", "clusters", "crowding", "paid")
FRESH_DAYS = 90


def _observations(root, refs):
    return [(ref, W.read(root, ref)) for ref in refs]


def _scan_domain(root, refs, domain):
    """在引用的 scan 观察里找该域名的初核记录;找不到返回 None。"""
    for _, obs in _observations(root, [r for r in refs if r.startswith("证据/_scan/")]):
        for d in obs["readings"]["domains"]:
            if d["domain"] == domain:
                return d
    return None


def _all_pass(item):
    return item is not None and all(item["checks"][k]["pass"] is True for k in W.CHECKS)


def register(root, slug, title, site_type, domain, scan_ref, reason, by="xinci-bench-scan",
             confirm_distinct=None) -> dict:
    require(isinstance(slug, str) and SLUG_RE.fullmatch(slug), "slug 须为小写字母数字连字符")
    require(isinstance(title, str) and title.strip(), "title 须写方向一句话")
    require(site_type in SITE_TYPES, f"site_type 须为 {SITE_TYPES}")
    require(isinstance(reason, str) and reason.strip(), "reason 不能为空")
    ledger = load_ledger(root)
    require(slug not in ledger["directions"], f"方向已存在: {slug}")
    W.read(root, scan_ref)
    item = _scan_domain(root, [scan_ref], domain)
    require(_all_pass(item), f"{domain} 在 {scan_ref} 里没有 B1–B5 全过的记录,不能登记")
    same = [s for s, r in ledger["directions"].items() if any(b["domain"] == domain for b in r["benchmarks"])]
    require(not same or (confirm_distinct or "").strip(),
            f"标杆 {domain} 已用于方向 {same};确属不同方向请用 --confirm-distinct 写理由")
    rec = {
        "slug": slug, "title": title.strip(), "site_type": site_type, "state": "found",
        "benchmarks": [{"domain": domain, "registered_at": item.get("registered_at"),
                        "aged_domain": bool(item.get("aged_domain", False)), "traffic_start": None,
                        "authority_score": item.get("authority_score"),
                        "us_organic_now": item.get("us_organic_now"), "us_organic_m12": None,
                        "covered_demand": None, "link_driven": None, "algo_risk": None,
                        "monetization": [], "clean": None}],
        "clusters": [], "crowding": None,
        "paid": {"applicable": False, "price_month": None, "evidence": None},
        "model": None, "decision": None, "evidence_refs": [scan_ref], "bindings": None,
        "history": [{"at": now(), "from": None, "to": "found", "by": by, "reason": reason.strip(),
                     **({"confirm_distinct": confirm_distinct.strip()} if same else {})}],
    }
    ledger["directions"][slug] = rec
    save_ledger(root, ledger)
    return rec


def _check_benchmarks(root, refs, benchmarks):
    require(isinstance(benchmarks, list) and benchmarks, "benchmarks 须为非空列表")
    for b in benchmarks:
        missing = [k for k in BENCH_KEYS if k not in b]
        require(not missing, f"标杆 {b.get('domain')} 缺字段 {missing}")
        require(b["clean"] in (True, False, None), "clean 须为 true/false/null")
        if b["clean"] is True:
            require(b["link_driven"] is False, f"{b['domain']}: 外链驱动的标杆不能标 clean")
            require(_all_pass(_scan_domain(root, refs, b["domain"])),
                    f"{b['domain']}: 引用的 scan 观察里没有 B1–B5 全过的记录,不能标 clean")


def _check_clusters(clusters):
    require(isinstance(clusters, list), "clusters 须为列表")
    ids = [c.get("id") for c in clusters]
    require(len(ids) == len(set(ids)), "簇 id 重复")
    for c in clusters:
        missing = [k for k in CLUSTER_KEYS if k not in c]
        require(not missing, f"簇 {c.get('id')} 缺字段 {missing}")
        require(c["coverage"] in ("benchmark", "ours"), f"簇 {c['id']}: coverage 须为 benchmark/ours")
        for k in ("near_me", "answered", "counted"):
            require(isinstance(c[k], bool), f"簇 {c['id']}: {k} 须为布尔")


def update(root, slug, patch: dict, refs=()) -> dict:
    """补数:只对 found/parked;改了输入就清掉旧模型结果(避免陈旧数字)。"""
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    require(rec["state"] in ("found", "parked"), f"{slug} 已是 {rec['state']},不能补数")
    bad = [k for k in patch if k not in PATCHABLE]
    require(not bad, f"不可补的字段: {bad}(可补: {PATCHABLE})")
    new_refs = list(rec["evidence_refs"])
    for ref in refs:
        obs = W.read(root, ref)
        require(obs["slug"] in (None, slug), f"{ref} 属于别的方向")
        if ref not in new_refs:
            new_refs.append(ref)
    if "site_type" in patch:
        require(patch["site_type"] in SITE_TYPES, f"site_type 须为 {SITE_TYPES}")
    if "benchmarks" in patch:
        _check_benchmarks(root, new_refs, patch["benchmarks"])
    if "clusters" in patch:
        _check_clusters(patch["clusters"])
    if "crowding" in patch:
        require(isinstance(patch["crowding"], int) and patch["crowding"] >= 1, "crowding 须为 ≥1 的整数")
    if "paid" in patch:
        p = patch["paid"]
        require(isinstance(p, dict) and isinstance(p.get("applicable"), bool), "paid.applicable 须为布尔")
        if p["applicable"]:
            require(isinstance(p.get("price_month"), (int, float)) and p["price_month"] > 0
                    and isinstance(p.get("evidence"), str) and p["evidence"].strip(),
                    "付费适用时须有正数 price_month 与有用户的 evidence")
    rec.update(patch)
    rec["evidence_refs"] = new_refs
    rec["model"] = None
    save_ledger(root, ledger)
    return rec


def _months_since(ym, on):
    y, m = map(int, ym.split("-")[:2])
    d = date.fromisoformat(on)
    return max((d.year - y) * 12 + d.month - m, 1)


def rank(root, on=None) -> list:
    """found 排序:起量速度(流量 ÷ 起量月数)降序,同分 AS 低的在前。只排序不否决。"""
    on = on or today()
    rows = []
    for slug, rec in load_ledger(root)["directions"].items():
        if rec["state"] != "found":
            continue
        best = None
        for b in rec["benchmarks"]:
            if b.get("link_driven") is True or b.get("us_organic_now") is None:
                continue
            start = b.get("traffic_start") or (b.get("registered_at") or "")[:7] or None
            months = _months_since(start, on) if start else 24
            speed = b["us_organic_now"] / months
            if best is None or speed > best[0]:
                best = (speed, b.get("authority_score") if b.get("authority_score") is not None else 99)
        if best:
            rows.append({"slug": slug, "speed": round(best[0], 1), "authority_score": best[1]})
    return sorted(rows, key=lambda r: (-r["speed"], r["authority_score"], r["slug"]))


def doc_paths(root, slug):
    base = Path(root) / "文档"
    return base / f"{slug}.md", base / f"{slug}.html"


def docs_consistent(root, slug) -> bool:
    md, html = doc_paths(root, slug)
    if not (md.is_file() and html.is_file()):
        return False
    return f'content="{sha256_file(md)}"' in html.read_text(encoding="utf-8")


def _require_evidence(root, rec, to, gate, on):
    obs = _observations(root, rec["evidence_refs"])
    kinds = {o["kind"] for _, o in obs}
    dec = rec.get("decision") or {}
    require(dec.get("verdict") == to and dec.get("gate") == gate,
            "账本里的 decision 与本次转移不一致;请用 settle.py 结算")
    require(docs_consistent(root, rec["slug"]), "决策书 md/html 缺失或不一致;请用 settle.py 结算")
    if to == "parked":
        return
    if to == "go" or gate == "revenue":
        model = bench_model.compute(rec)
        require(rec.get("model") == model, "账本里的模型结果与现场重算不一致")
        require(model["passes"] is (to == "go"), "模型结论与转移方向不符")
    if to == "go":
        need = {"benchmark", "demand", "serp", "differentiation", "delivery", "brief"}
        require(need <= kinds, f"go 缺观察: {sorted(need - kinds)}")
        delivery = [o for _, o in obs if o["kind"] == "delivery"][-1]
        require(delivery["readings"]["feasible"] is True, "交付依据不成立(最新 delivery.feasible=false)")
        stale = [c["id"] for c in rec["clusters"] if c["counted"]
                 and (date.fromisoformat(on) - date.fromisoformat(c["measured_at"])).days > FRESH_DAYS]
        require(not stale, f"计入需求的簇测量超过 {FRESH_DAYS} 天: {stale}")
        require(rec.get("bindings"), "go 须有绑定")
    elif gate == "benchmark":
        require("benchmark" in kinds, "benchmark 否决须有起量手段观察")
    elif gate == "answered":
        require(rec["clusters"] and all(c["answered"] for c in rec["clusters"]),
                "answered 否决要求所有簇都被首屏答完")
        answered_ids = {o["readings"]["cluster_id"] for _, o in obs
                        if o["kind"] == "serp" and o["readings"]["answered"]}
        missing = [c["id"] for c in rec["clusters"] if c["id"] not in answered_ids]
        require(not missing, f"这些簇没有首屏答完的 serp 观察: {missing}")
    elif gate == "scope":
        require(dec.get("scope_hit") in SCOPE_ITEMS, f"scope 否决须写命中项 {SCOPE_ITEMS}")


def transition(root, slug, to, gate=None, reason="", by="xinci-bench-assess", on=None) -> dict:
    on = on or today()
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    frm = rec["state"]
    require(to in LEGAL.get(frm, set()), f"非法转移 {frm} → {to}")
    require((gate in GATES) if to == "rejected" else gate is None,
            f"rejected 须带 gate {GATES};go/parked 不带 gate")
    require(isinstance(reason, str) and reason.strip(), "reason 不能为空")
    _require_evidence(root, rec, to, gate, on)
    rec["state"] = to
    rec["history"].append({"at": now(), "from": frm, "to": to, "by": by, "reason": reason.strip(),
                           **({"gate": gate} if gate else {})})
    save_ledger(root, ledger)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    r.add_argument("--slug", required=True)
    r.add_argument("--title", required=True)
    r.add_argument("--site-type", required=True, choices=SITE_TYPES)
    r.add_argument("--domain", required=True)
    r.add_argument("--scan", required=True, help="scan 观察路径")
    r.add_argument("--reason", required=True)
    r.add_argument("--by", default="xinci-bench-scan")
    r.add_argument("--confirm-distinct")
    u = sub.add_parser("update")
    u.add_argument("--slug", required=True)
    u.add_argument("--patch", required=True, help="补数 JSON 文件")
    u.add_argument("--ref", action="append", default=[], help="新增引用的观察路径")
    sub.add_parser("rank")
    s = sub.add_parser("show")
    s.add_argument("--slug", required=True)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "register":
            out = register(root, a.slug, a.title, a.site_type, a.domain, a.scan, a.reason, a.by, a.confirm_distinct)
        elif a.cmd == "update":
            out = update(root, a.slug, load_json(Path(a.patch)), a.ref)
        elif a.cmd == "rank":
            out = rank(root)
        else:
            out = load_ledger(root)["directions"].get(a.slug)
            require(out, f"没有方向 {a.slug}")
    except (BenchError, OSError, ValueError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
