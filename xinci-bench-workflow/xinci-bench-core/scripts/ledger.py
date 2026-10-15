#!/usr/bin/env python3
"""方向账本:两条道(标杆道 bench、新词快道 quick)的登记、补数、排序、转移前的最小证据复核。

账本只由本脚本写;状态只经 settle.py 转移。快道比标杆道多一个 watching(观察中)状态。
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import bench_model
import data_root
import quick_model as QM
import quick_pool
import write_observation as W
from _common import (SLUG_RE, BenchError, is_date, load_json, load_ledger, now, require, save_ledger, sha256_file,
                     today)

STATES = ("found", "go", "rejected", "parked", "watching")
LANES = ("bench", "quick")
LEGAL_BY_LANE = {
    "bench": {"found": {"go", "rejected", "parked"}, "parked": {"go", "rejected"}},
    "quick": {"found": {"go", "rejected", "parked", "watching"}, "watching": {"go", "rejected"},
              "parked": {"go", "rejected"}},
}
LEGAL = LEGAL_BY_LANE["bench"]
GATES = ("scope", "benchmark", "answered", "revenue")
QUICK_GATES = quick_pool.QUICK_GATES
GATES_BY_LANE = {"bench": GATES, "quick": QUICK_GATES}
OBJECT_TYPES = ("game", "other")                       # 快道对象类型:游戏 14 天、其他 90 天
# 快道否决门 → 速判观察里必须不过的那一条
QUICK_GATE_CHECK = {"not_new": "Q1", "oneoff": "Q3", "scope": "Q4", "occupied": "Q5", "answered": "Q6"}
QUICK_PATCHABLE = ("title", "site_type", "terms", "object")   # object 只许更正 date_source
FOLLOW_UP_STATUSES = ("pending", "started", "launched", "abandoned")
SITE_TYPES = ("tool", "content", "game", "mixed")
SCOPE_ITEMS = ("ymyl", "brand_nav", "news", "adult_gambling", "infringement")
BENCH_KEYS = ("domain", "registered_at", "aged_domain", "traffic_start", "authority_score",
              "us_organic_now", "us_organic_m12", "en_organic_now", "en_organic_m12", "covered_demand",
              "link_driven", "algo_risk", "monetization", "clean")
CLUSTER_KEYS = ("id", "seed_term", "volume", "en_volume", "measured_at", "coverage", "near_me", "answered",
                "counted")
PATCHABLE = ("title", "site_type", "benchmarks", "clusters", "crowding", "paid")
FRESH_DAYS = 90
# 账本里决定收入的字段必须等于绑定观察的读数(结算时核对)
BENCH_OBS_FIELDS = ("traffic_start", "us_organic_now", "us_organic_m12", "en_organic_now", "en_organic_m12",
                    "link_driven", "algo_risk")
CLUSTER_OBS_FIELDS = ("seed_term", "volume", "en_volume", "measured_at", "coverage", "near_me")


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
        "slug": slug, "title": title.strip(), "site_type": site_type, "lane": "bench", "state": "found",
        "benchmarks": [{"domain": domain, "registered_at": item.get("registered_at"),
                        "aged_domain": bool(item.get("aged_domain", False)), "traffic_start": None,
                        "authority_score": item.get("authority_score"),
                        "us_organic_now": item.get("us_organic_now"), "us_organic_m12": None,
                        "en_organic_now": item.get("en_organic_now"), "en_organic_m12": None,
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
    """补数:标杆道只对 found/parked,改了输入就清掉旧模型结果;快道只能补标题、站型、说法、对象的日期来源与引用。"""
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    lane = rec.get("lane", "bench")
    open_states = ("found", "parked") if lane == "bench" else ("found", "parked", "watching")
    require(rec["state"] in open_states, f"{slug} 已是 {rec['state']},不能补数")
    allowed = PATCHABLE if lane == "bench" else QUICK_PATCHABLE
    bad = [k for k in patch if k not in allowed]
    require(not bad, f"不可补的字段: {bad}(可补: {allowed})")
    new_refs, screens = list(rec["evidence_refs"]), []
    for ref in refs:
        obs = W.read(root, ref)
        require(obs["slug"] in (None, slug), f"{ref} 属于别的方向")
        if obs["kind"] == "quick_screen":
            screens.append(obs)
        if ref not in new_refs:
            new_refs.append(ref)
    if "site_type" in patch:
        require(patch["site_type"] in SITE_TYPES, f"site_type 须为 {SITE_TYPES}")
    if lane == "quick" and "object" in patch:
        o = patch["object"]
        require(isinstance(o, dict) and set(o) == {"date_source"} and isinstance(o["date_source"], str)
                and o["date_source"].strip(), "快道对象只能更正 date_source(非空文字);名称、类型、首次公开日登记后不改")
        patch = dict(patch, object=dict(rec["object"], date_source=o["date_source"].strip()))
    if "terms" in patch:
        _check_terms(patch["terms"])
        _check_term_clash(ledger, slug, patch["terms"])
    for s in screens:
        _check_screen_term(patch.get("terms", rec.get("terms")), s)
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
    if lane == "bench":
        rec["model"] = None
    save_ledger(root, ledger)
    return rec


def _months_since(ym, on):
    y, m = map(int, ym.split("-")[:2])
    d = date.fromisoformat(on)
    return max((d.year - y) * 12 + d.month - m, 1)


def rank(root, on=None) -> list:
    """found 排序:起量速度(英文区流量 ÷ 起量月数)降序,同分 AS 低的在前。只排序不否决。"""
    on = on or today()
    rows = []
    for slug, rec in load_ledger(root)["directions"].items():
        if rec["state"] != "found" or rec.get("lane", "bench") != "bench":
            continue
        best = None
        for b in rec["benchmarks"]:
            if b.get("link_driven") is True or b.get("en_organic_now") is None:
                continue
            start = b.get("traffic_start") or (b.get("registered_at") or "")[:7] or None
            months = _months_since(start, on) if start else 24
            speed = b["en_organic_now"] / months
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


def _latest(obs, kind, key=None, value=None):
    rows = [o for _, o in obs if o["kind"] == kind and (key is None or o["readings"].get(key) == value)]
    return rows[-1] if rows else None


def _check_against_observations(rec, obs):
    """账本里的标杆读数、簇量、拥挤度必须等于最新的对应观察;覆盖需求不能小于"标杆已做"的簇量合计。"""
    floor = sum(c["en_volume"] for c in rec["clusters"] if c["coverage"] == "benchmark")
    for b in rec["benchmarks"]:
        if b.get("clean") is not True:
            continue
        o = _latest(obs, "benchmark", "domain", b["domain"])
        require(o, f"干净标杆 {b['domain']} 没有 benchmark 观察")
        diff = [k for k in BENCH_OBS_FIELDS if b.get(k) != o["readings"][k]]
        require(not diff, f"标杆 {b['domain']} 的 {diff} 与最新 benchmark 观察不一致")
        require(isinstance(b.get("covered_demand"), (int, float)) and b["covered_demand"] >= floor,
                f"标杆 {b['domain']} 的 covered_demand 小于\"标杆已做\"的簇量合计 {floor}(分母偏小会抬高份额率)")
    d = _latest(obs, "demand")
    require(d, "缺 demand 观察")
    by_id = {c["id"]: c for c in d["readings"]["clusters"]}
    for c in rec["clusters"]:
        oc = by_id.get(c["id"])
        require(oc, f"簇 {c['id']} 不在最新 demand 观察里")
        diff = [k for k in CLUSTER_OBS_FIELDS if c[k] != oc[k]]
        require(not diff, f"簇 {c['id']} 的 {diff} 与最新 demand 观察不一致")
    require(rec.get("crowding") == d["readings"]["crowding"], "crowding 与最新 demand 观察不一致")


def precheck(root, rec, to, gate, on, scope_hit=None):
    """不依赖结算产物的证据复核;settle 在写任何东西之前先跑它,转移时再跑一遍。按道分派。"""
    if rec.get("lane", "bench") == "quick":
        return _precheck_quick(root, rec, to, gate, on, scope_hit)
    return _precheck_bench(root, rec, to, gate, on, scope_hit)


def _precheck_bench(root, rec, to, gate, on, scope_hit=None):
    obs = _observations(root, rec["evidence_refs"])
    kinds = {o["kind"] for _, o in obs}
    if to == "parked":
        return
    if to == "go":
        need = {"benchmark", "demand", "serp", "differentiation", "delivery", "brief"}
        require(need <= kinds, f"go 缺观察: {sorted(need - kinds)}")
        require(_latest(obs, "delivery")["readings"]["feasible"] is True,
                "交付依据不成立(最新 delivery.feasible=false)")
        stale = [c["id"] for c in rec["clusters"] if c["counted"]
                 and (date.fromisoformat(on) - date.fromisoformat(c["measured_at"])).days > FRESH_DAYS]
        require(not stale, f"计入需求的簇测量超过 {FRESH_DAYS} 天: {stale}")
        serps = [o["readings"] for _, o in obs if o["kind"] == "serp"]
        for c in rec["clusters"]:
            if not c["counted"] or c["answered"]:
                continue
            mine = [s for s in serps if s["cluster_id"] == c["id"]]
            require(mine, f"计入需求的簇 {c['id']} 没有 serp 观察")
            require(not any(s["answered"] for s in mine), f"簇 {c['id']} 在 serp 观察里已被首屏答完,不能计入需求")
    if to == "go" or gate == "revenue":
        _check_against_observations(rec, obs)
        require(bench_model.compute(rec)["passes"] is (to == "go"), "模型结论与转移方向不符")
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
        require(scope_hit in SCOPE_ITEMS, f"scope 否决须写命中项 {SCOPE_ITEMS}")


def _require_evidence(root, rec, to, gate, on):
    dec = rec.get("decision") or {}
    require(dec.get("verdict") == to and dec.get("gate") == gate,
            "账本里的 decision 与本次转移不一致;请用 settle.py 结算")
    require(docs_consistent(root, rec["slug"]), "决策书 md/html 缺失或不一致;请用 settle.py 结算")
    precheck(root, rec, to, gate, on, dec.get("scope_hit"))
    if rec.get("lane", "bench") == "quick":
        if to in ("go", "watching") or gate == "volume":
            derived = derive_quick(root, rec)
            require(rec.get("volume") == derived["volume"] and rec.get("serp") == derived["serp"],
                    "账本里的量级与首屏读数须等于最新观察")
            require(rec.get("model") == QM.compute(rec), "账本里的模型结果与现场重算不一致")
        if to == "go":
            require((rec.get("follow_up") or {}).get("status") == "pending", "快道 go 须初始化建站跟进")
    elif to == "go" or gate == "revenue":
        require(rec.get("model") == bench_model.compute(rec), "账本里的模型结果与现场重算不一致")
    if to == "go":
        require(rec.get("bindings"), "go 须有绑定")


# ---------------------------------------------------------------- 新词快道

def _check_terms(terms):
    require(isinstance(terms, list) and terms, "terms 须为非空列表")
    for t in terms:
        require(isinstance(t.get("term"), str) and t["term"].strip(), "terms[].term 缺失")
        require(t.get("source") in W.QUICK_SOURCES, f"terms[].source 须为 {W.QUICK_SOURCES}")
        require(is_date(t.get("first_seen")), "terms[].first_seen 须为日历上存在的 YYYY-MM-DD")


def _term_set(terms) -> set:
    return {quick_pool.normalize_term(t["term"]) for t in terms or []}


def _check_term_clash(ledger, slug, terms):
    """同一说法(大小写与空格不计)不能属于两个方向。"""
    mine = _term_set(terms)
    for other, r in ledger["directions"].items():
        clash = mine & _term_set(r.get("terms")) if other != slug else set()
        require(not clash, f"说法 {sorted(clash)} 已属于方向 {other}")


def _check_screen_term(terms, screen):
    """速判观察只能为本方向登记的说法背书。"""
    require(quick_pool.normalize_term(screen["readings"]["term"]) in _term_set(terms),
            f"速判的词 {screen['readings']['term']!r} 不在登记的说法里")


def _screen_all_pass(obs):
    return all(obs["readings"]["checks"][k]["pass"] is True for k in W.QUICK_CHECKS)


def register_quick(root, slug, title, site_type, obj, terms, screen_ref, reason, by="xinci-bench-quick") -> dict:
    """登记快道方向:须有本方向 Q1–Q6 全过的速判观察;对象首次公开须在窗口内(游戏 14 天、其他 90 天)。"""
    require(isinstance(slug, str) and SLUG_RE.fullmatch(slug), "slug 须为小写字母数字连字符")
    require(isinstance(title, str) and title.strip(), "title 须写方向一句话")
    require(site_type in SITE_TYPES, f"site_type 须为 {SITE_TYPES}")
    require(isinstance(reason, str) and reason.strip(), "reason 不能为空")
    require(isinstance(obj, dict) and isinstance(obj.get("name"), str) and obj["name"].strip()
            and is_date(obj.get("first_public"))
            and isinstance(obj.get("date_source"), str) and obj["date_source"].strip(),
            "object 须含 name、first_public(YYYY-MM-DD)、date_source")
    require(obj.get("type") in OBJECT_TYPES, f"object.type 须为 {OBJECT_TYPES}(游戏 14 天、其他 90 天)")
    _check_terms(terms)
    screen = W.read(root, screen_ref)
    require(screen["kind"] == "quick_screen" and screen["slug"] == slug, f"{screen_ref} 不是本方向的速判观察")
    _check_screen_term(terms, screen)
    require(_screen_all_pass(screen), "速判六条没有全过,不登记,应进快道淘汰记录")
    age = (date.fromisoformat(screen["observed_at"][:10]) - date.fromisoformat(obj["first_public"])).days
    limit = QM.QUICK_ASSUMPTIONS["new_days_game" if obj["type"] == "game" else "new_days"]
    require(0 <= age <= limit,
            f"对象首次公开距速判 {age} 天,超出{'游戏类' if obj['type'] == 'game' else ''} {limit} 天(或日期在未来)")
    ledger = load_ledger(root)
    require(slug not in ledger["directions"], f"方向已存在: {slug}")
    _check_term_clash(ledger, slug, terms)
    rec = {
        "slug": slug, "title": title.strip(), "site_type": site_type, "lane": "quick", "state": "found",
        "object": {k: obj[k] for k in ("name", "type", "first_public", "date_source")}, "terms": terms,
        "volume": None, "serp": None, "watch": None, "follow_up": None,
        "model": None, "decision": None, "evidence_refs": [screen_ref], "bindings": None,
        "history": [{"at": now(), "from": None, "to": "found", "by": by, "reason": reason.strip()}],
    }
    ledger["directions"][slug] = rec
    save_ledger(root, ledger)
    quick_pool.consume(root, [t["term"] for t in terms])
    return rec


def derive_quick(root, rec) -> dict:
    """从最新的量级观察与速判观察推导 volume、serp;结算时写进账本。"""
    obs = _observations(root, rec["evidence_refs"])
    v, s = _latest(obs, "quick_volume"), _latest(obs, "quick_screen")
    volume = None
    if v:
        r = v["readings"]
        readable = [c for c in r["countries"] if c["readable"]]
        volume = {"estimate_7d": r["estimate_7d"], "estimate_30d": r["estimate_30d"],
                  "by_geo": {c["geo"]: c["estimate_7d"] for c in readable},
                  "anchors": {c["geo"]: {"term": c["anchor_term"], "volume": c["anchor_volume"],
                                         "source": c["anchor_source"], "measured_at": c["anchor_measured_at"],
                                         "ratio_7d": c["ratio_7d"]} for c in readable},
                  "anchor_measured_at": _oldest_anchor(r), "trend_geo": r["trend_geo"],
                  "trend": QM.trend(r["series_30d"])}
    serp = None
    if s:
        r = s["readings"]
        serp = {"aio_present": bool(r["ai_overview"]["present"]),
                "aio_completes": bool(r["ai_overview"]["completes_task"]), "occupied_by": r["occupied_by"]}
    return {"volume": volume, "serp": serp}


def _oldest_anchor(readings) -> str:
    """各国锚词里最早的测量日;新鲜度按最旧的那个算。"""
    return min(c["anchor_measured_at"] for c in readings["countries"] if c["readable"])


def _quick_model(root, rec):
    return QM.compute(dict(rec, **derive_quick(root, rec)))


def _precheck_quick(root, rec, to, gate, on, scope_hit=None):
    obs = _observations(root, rec["evidence_refs"])
    if to == "parked":
        return
    screen = _latest(obs, "quick_screen")
    require(screen, "缺速判观察 quick_screen")
    _check_screen_term(rec["terms"], screen)
    checks = screen["readings"]["checks"]
    vol = _latest(obs, "quick_volume")
    if to in ("go", "watching"):
        require(_screen_all_pass(screen), "最新速判观察六条须全过")
        require(vol, "缺量级观察 quick_volume")
        fresh = (date.fromisoformat(on) - date.fromisoformat(_oldest_anchor(vol["readings"]))).days
        require(fresh <= QM.QUICK_ASSUMPTIONS["anchor_fresh_days"], f"锚词测量已过 {fresh} 天,须在 90 天内")
        model = _quick_model(root, rec)
        trend = QM.trend(vol["readings"]["series_30d"])
        require(not trend["spike_decay"], "曲线冲高回落,应按 oneoff 否决")
        if to == "go":
            brief = _latest(obs, "quick_brief")
            require(brief, "go 缺最小简报素材 quick_brief")
            require(brief["readings"]["data_available"] is True and brief["readings"]["build_days"] <= 3,
                    "最小版本须 3 天内能做出、数据拿得到")
            require(model["passes"], "基准预计不到 1 万访问,不能判 go")
        else:
            require(not model["passes"], "基准已过 1 万,应判 go")
            require(trend["non_declining"], "趋势在降,不能进观察中(应按 volume 否决)")
    elif to == "rejected" and gate not in QUICK_GATES:
        require(False, f"快道否决门须为 {QUICK_GATES}")
    elif gate in QUICK_GATE_CHECK:
        q = QUICK_GATE_CHECK[gate]
        spike = gate == "oneoff" and vol and QM.trend(vol["readings"]["series_30d"])["spike_decay"]
        require(checks[q]["pass"] is False or spike, f"{gate} 否决须有 {q} 不过的速判观察")
        if gate == "scope":
            require(scope_hit in SCOPE_ITEMS, f"scope 否决须写命中项 {SCOPE_ITEMS}")
    elif gate == "volume":
        require(vol, "volume 否决须有量级观察")
        model = _quick_model(root, rec)
        require(not model["passes"], "基准已过 1 万,不能按 volume 否决")
        watch = rec.get("watch") or {}
        expired = bool(watch) and on >= watch["expires_at"]
        declining = not QM.trend(vol["readings"]["series_30d"])["non_declining"]
        require(expired or declining, "volume 否决须观察到期,或趋势在降")


def watch_check(root, slug, refs=(), on=None) -> dict:
    """复查观察中的方向:加入新观察,算一次,记一条复查;只给建议,转移仍走 settle.py。"""
    on = on or today()
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec and rec.get("lane") == "quick" and rec["state"] == "watching", f"{slug} 不是观察中的快道方向")
    for ref in refs:
        obs = W.read(root, ref)
        require(obs["slug"] == slug, f"{ref} 属于别的方向")
        if obs["kind"] == "quick_screen":
            _check_screen_term(rec["terms"], obs)
        if ref not in rec["evidence_refs"]:
            rec["evidence_refs"].append(ref)
    obs = _observations(root, rec["evidence_refs"])
    screen, vol = _latest(obs, "quick_screen"), _latest(obs, "quick_volume")
    checks = screen["readings"]["checks"]
    # 先看最新速判:第一条不过的项就是否决门;AI 概览已答完同 answered,此时不再测算
    failed = next((g for g, q in QUICK_GATE_CHECK.items() if checks[q]["pass"] is False), None)
    if failed is None and screen["readings"]["ai_overview"]["completes_task"]:
        failed = "answered"
    trend = QM.trend(vol["readings"]["series_30d"])
    model = None if failed else _quick_model(root, rec)
    if failed:
        suggestion = f"rejected:{failed}"
    elif trend["spike_decay"]:
        suggestion = "rejected:oneoff"
    elif model["passes"]:
        suggestion = "go"
    elif on >= rec["watch"]["expires_at"] or not trend["non_declining"]:
        suggestion = "rejected:volume"
    else:
        suggestion = "watching"
    check = {"at": on, "estimate_7d": vol["readings"]["estimate_7d"],
             "base_visits": model["scenarios"]["base"]["visits"] if model else None,
             "non_declining": trend["non_declining"], "suggestion": suggestion}
    rec["watch"]["checks"].append(check)
    save_ledger(root, ledger)
    return {"slug": slug, "expires_at": rec["watch"]["expires_at"], **check}


def follow_up(root, slug, status, domain=None, on=None, reason=None) -> dict:
    """建站跟进:pending → started → launched 只能前进,任何时候可 abandoned;不改 state。"""
    require(status in FOLLOW_UP_STATUSES[1:], "status 须为 started/launched/abandoned")
    on = on or today()
    require(is_date(on), f"日期须为日历上存在的 YYYY-MM-DD(收到 {on!r})")
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec and rec.get("lane") == "quick" and rec["state"] == "go" and rec.get("follow_up"),
            f"{slug} 不是快道 go,没有建站跟进")
    fu = rec["follow_up"]
    order = {"pending": 0, "started": 1, "launched": 2}
    require(fu["status"] != "abandoned", "已放弃的方向不能再改跟进")
    if status == "abandoned":
        require(isinstance(reason, str) and reason.strip(), "放弃须写理由")
        fu.update(status="abandoned", reason=reason.strip())
    else:
        require(order[status] == order[fu["status"]] + 1, f"跟进只能按 pending → started → launched 前进(当前 {fu['status']})")
        if status == "started":
            require(isinstance(domain, str) and domain.strip(), "已开建须写域名")
            require(on >= fu["go_at"], f"开建日期 {on} 早于判 go 日期 {fu['go_at']}")
            fu.update(status="started", domain=domain.strip(), started_at=on)
        else:
            require(on >= fu["started_at"], f"上线日期 {on} 早于开建日期 {fu['started_at']}")
            fu.update(status="launched", launched_at=on)
    fu["updated_at"] = now()
    save_ledger(root, ledger)
    return fu


def transition(root, slug, to, gate=None, reason="", by="xinci-bench-assess", on=None) -> dict:
    on = on or today()
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    frm, lane = rec["state"], rec.get("lane", "bench")
    require(to in LEGAL_BY_LANE[lane].get(frm, set()), f"非法转移 {frm} → {to}({lane})")
    gates = GATES_BY_LANE[lane]
    require((gate in gates) if to == "rejected" else gate is None,
            f"rejected 须带 gate {gates};go/parked/watching 不带 gate")
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
    rq = sub.add_parser("register-quick")
    rq.add_argument("--input", required=True, help="JSON:slug、title、site_type、object、terms、screen、reason")
    pv = sub.add_parser("quick-preview")
    pv.add_argument("--slug", required=True)
    wc = sub.add_parser("watch-check")
    wc.add_argument("--slug", required=True)
    wc.add_argument("--ref", action="append", default=[])
    fu = sub.add_parser("follow-up")
    fu.add_argument("--slug", required=True)
    fu.add_argument("--status", required=True, choices=FOLLOW_UP_STATUSES[1:])
    fu.add_argument("--domain")
    fu.add_argument("--date")
    fu.add_argument("--reason")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "register":
            out = register(root, a.slug, a.title, a.site_type, a.domain, a.scan, a.reason, a.by, a.confirm_distinct)
        elif a.cmd == "update":
            out = update(root, a.slug, load_json(Path(a.patch)), a.ref)
        elif a.cmd == "rank":
            out = rank(root)
        elif a.cmd == "register-quick":
            d = load_json(Path(a.input))
            out = register_quick(root, d["slug"], d["title"], d["site_type"], d["object"], d["terms"],
                                 d["screen"], d["reason"], d.get("by", "xinci-bench-quick"))
        elif a.cmd == "quick-preview":
            rec = load_ledger(root)["directions"].get(a.slug)
            require(rec and rec.get("lane") == "quick", f"没有快道方向 {a.slug}")
            out = {**derive_quick(root, rec), "model": _quick_model(root, rec)}
        elif a.cmd == "watch-check":
            out = watch_check(root, a.slug, a.ref)
        elif a.cmd == "follow-up":
            out = follow_up(root, a.slug, a.status, a.domain, a.date, a.reason)
        else:
            out = load_ledger(root)["directions"].get(a.slug)
            require(out, f"没有方向 {a.slug}")
    except (BenchError, OSError, ValueError, KeyError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
