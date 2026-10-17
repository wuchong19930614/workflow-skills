#!/usr/bin/env python3
"""方向账本:两条道(标杆道 bench、新词快道 quick)的登记、补数、排序、转移前的最小证据复核。

账本只由本脚本写;状态只经 settle.py 转移。快道比标杆道多一个 watching(观察中)状态。
"""
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import bench_model
import data_root
import quick_model as QM
import quick_pool
import quick_reference as QR
import trends_volume as TV
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
QUICK_PATCHABLE = ("title", "site_type", "terms", "object")   # 现行方向的 object 只许更正 date_source
FORECAST_SLIPPABLE = ("found", "watching", "go")          # 预判方向在这三个状态下可改开玩日(object.first_public)
FORECAST_REGISTERABLE = ("go", "watching")                # 预判建议为这两种才登记;skip、measure_rest 不登记
FORECAST_KEYS = ("ref", "playable_at", "object_volume_pre", "tasks", "forecast_p25", "forecast_median", "review_at",
                 "review", "slipped_days")                # 预判方向开玩前结算后账本里 forecast 块的键
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


def _patched_object(rec, o, on) -> dict:
    """快道对象的补数 → 补后的 object。现行方向只许更正 date_source;预判方向(开玩前、观察中、go)还可连同新的开玩日
    first_public 一起给,新开玩日须在 on 之后;名称、类型登记后不改。"""
    movable = rec.get("basis") == "forecast" and rec["state"] in FORECAST_SLIPPABLE
    keys = {"date_source", "first_public"} if movable else {"date_source"}
    require(isinstance(o, dict) and "date_source" in o and set(o) <= keys
            and isinstance(o["date_source"], str) and o["date_source"].strip(),
            "预判方向的对象只能更正 date_source(非空文字),或连同新的开玩日 first_public 一起给;名称、类型登记后不改" if movable
            else "快道对象只能更正 date_source(非空文字);名称、类型、首次公开日登记后不改")
    new = dict(rec["object"], date_source=o["date_source"].strip())
    if "first_public" in o:
        require(is_date(o["first_public"]), f"first_public 须为日历上存在的 YYYY-MM-DD(收到 {o['first_public']!r})")
        require(o["first_public"] > on, f"新开玩日 {o['first_public']} 须在 {on} 之后:开玩日是今天或更早，说明已经开玩，按现行路径看首页")
        new["first_public"] = o["first_public"]
    return new


def _slip_forecast(rec, days):
    """预判方向开玩日变了 days 天:forecast 块的开玩日、复核日、累计推迟天数跟着变;观察中的到期日顺延到新复核日,
    还没开建的 go 的建议最晚上线日顺延到新开玩日前 1 天。开玩前(found)还没有 forecast 块,旧预判观察的开玩日对不上,由结算拦下。"""
    f = rec.get("forecast")
    if not f:
        return
    require(f["review"] is None and not (rec.get("watch") or {}).get("checks"),
            "开玩后已经复核或复查过,开玩日不能再改")
    dates = QM.forecast_dates(rec["object"]["first_public"])
    f.update(playable_at=rec["object"]["first_public"], review_at=dates["review_at"],
             slipped_days=f["slipped_days"] + days)
    if rec["state"] == "watching":
        rec["watch"]["expires_at"] = dates["review_at"]
    if rec["state"] == "go" and (rec.get("follow_up") or {}).get("status") == "pending":
        rec["follow_up"]["launch_by"] = dates["launch_by"]


def update(root, slug, patch: dict, refs=(), on=None) -> dict:
    """补数:标杆道只对 found/parked,改了输入就清掉旧模型结果;快道只能补标题、站型、说法、对象的日期来源与引用。
    预判方向(found、观察中、go)还可改开玩日 object.first_public(须同时给 date_source,新日期在 on 之后,on 缺省今天),
    forecast 块、观察到期日、建议最晚上线日跟着顺延;go 只许改 object。"""
    on = on or today()
    require(is_date(on), f"日期须为日历上存在的 YYYY-MM-DD(收到 {on!r})")
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    lane = rec.get("lane", "bench")
    forecast_dir = lane == "quick" and rec.get("basis") == "forecast"
    open_states = ("found", "parked") if lane == "bench" else ("found", "parked", "watching")
    if forecast_dir:
        open_states += ("go",)
    require(rec["state"] in open_states, f"{slug} 已是 {rec['state']},不能补数")
    allowed = PATCHABLE if lane == "bench" else QUICK_PATCHABLE
    if forecast_dir and rec["state"] == "go":
        allowed = ("object",)
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
    slip = 0
    if lane == "quick" and "object" in patch:
        new_object = _patched_object(rec, patch["object"], on)
        slip = (date.fromisoformat(new_object["first_public"]) - date.fromisoformat(rec["object"]["first_public"])).days
        patch = dict(patch, object=new_object)
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
    if slip:
        _slip_forecast(rec, slip)
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
        if is_pregame(rec):
            if to in ("go", "watching"):
                model = forecast_model(root, rec)
                require(rec.get("volume") is None and rec.get("serp") is None, "预判方向开玩前结算,volume、serp 须为空")
                require(rec.get("model") == model, "账本里的模型结果与现场重算不一致")
                require(rec.get("forecast") == forecast_block(root, rec, model), "账本里的预判块与最新预判观察不一致")
        elif to in ("go", "watching") or gate == "volume":
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


def _check_forecast_terms(terms, forecast):
    """预判观察只能为它任务里的说法背书:登记的每个说法(大小写与空格不计)都得在某项任务的 terms 里。"""
    covered = {quick_pool.normalize_term(x) for t in forecast["readings"]["tasks"] for x in t["terms"]}
    stray = sorted(_term_set(terms) - covered)
    require(not stray, f"说法 {stray} 不在预判观察的任务说法里(预判只为任务里的说法背书)")


def _screen_all_pass(obs):
    return all(obs["readings"]["checks"][k]["pass"] is True for k in W.QUICK_CHECKS)


def _screen_basis(root, slug, obj, terms, screen_ref) -> list:
    """现行登记的依据:本方向 Q1–Q6 全过的速判观察;对象首次公开须在窗口内(游戏 14 天、其他 90 天)。返回 evidence_refs。"""
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
    return [screen_ref]


def _forecast_basis(root, slug, obj, terms, forecast_ref) -> list:
    """预判登记的依据:本方向 P1–P6 全过、建议 go 或 watching 的预判观察;游戏、对象名与开玩日一致且在 3–21 天内,
    说法都在某项任务里,对象名量级观察是本方向的 quick_volume。返回 evidence_refs:[预判观察, 对象名量级观察]。"""
    require(obj.get("type") == "game", "预判登记只收游戏(object.type 须为 game):开玩日是预判的前提")
    _check_terms(terms)
    forecast = W.read(root, forecast_ref)
    require(forecast["kind"] == "quick_forecast" and forecast["slug"] == slug, f"{forecast_ref} 不是本方向的预判观察")
    r = forecast["readings"]
    failed = [k for k in W.FORECAST_CHECKS if r["checks"][k]["pass"] is not True]
    require(not failed, f"预判六条没有全过({'、'.join(failed)}),不登记")
    require(r["suggestion"] in FORECAST_REGISTERABLE,
            f"预判建议(suggestion)为 {r['suggestion']},只有 {'、'.join(FORECAST_REGISTERABLE)} 才登记")
    require(quick_pool.normalize_term(obj["name"]) == quick_pool.normalize_term(r["object"]),
            f"object.name {obj['name']!r} 与预判观察的对象 {r['object']!r} 不一致(大小写与空格不计)")
    require(obj["first_public"] == r["playable_at"],
            f"object.first_public {obj['first_public']} 与预判观察的开玩日 {r['playable_at']} 不一致")
    lo, hi = QM.QUICK_ASSUMPTIONS["forecast_days"]
    lead = (date.fromisoformat(r["playable_at"]) - date.fromisoformat(forecast["observed_at"][:10])).days
    require(lo <= lead <= hi, f"开玩日在预判之后 {lead} 天,须在 {lo}–{hi} 天内")
    _check_forecast_terms(terms, forecast)
    volume_ref = r["object_volume_ref"]
    volume = W.read(root, volume_ref)
    require(volume["kind"] == "quick_volume" and volume["slug"] == slug,
            f"预判的 object_volume_ref {volume_ref} 不是本方向的对象名量级观察 quick_volume")
    return [forecast_ref, volume_ref]


def register_quick(root, slug, title, site_type, obj, terms, screen_ref, reason, by="xinci-bench-quick",
                   forecast_ref=None) -> dict:
    """登记快道方向。依据二选一:screen_ref 给本方向 Q1–Q6 全过的速判观察(现行,对象首次公开须在窗口内);
    forecast_ref 给本方向的预判观察(上线前预判,记 basis=forecast,开玩日在 3–21 天内)。"""
    require((screen_ref is None) != (forecast_ref is None),
            "screen_ref 与 forecast_ref 恰好给一个(速判登记给 screen,上线前预判登记给 forecast)")
    require(isinstance(slug, str) and SLUG_RE.fullmatch(slug), "slug 须为小写字母数字连字符")
    require(isinstance(title, str) and title.strip(), "title 须写方向一句话")
    require(site_type in SITE_TYPES, f"site_type 须为 {SITE_TYPES}")
    require(isinstance(reason, str) and reason.strip(), "reason 不能为空")
    require(isinstance(obj, dict) and isinstance(obj.get("name"), str) and obj["name"].strip()
            and is_date(obj.get("first_public"))
            and isinstance(obj.get("date_source"), str) and obj["date_source"].strip(),
            "object 须含 name、first_public(YYYY-MM-DD)、date_source")
    refs = (_screen_basis(root, slug, obj, terms, screen_ref) if forecast_ref is None
            else _forecast_basis(root, slug, obj, terms, forecast_ref))
    ledger = load_ledger(root)
    require(slug not in ledger["directions"], f"方向已存在: {slug}")
    _check_term_clash(ledger, slug, terms)
    rec = {
        "slug": slug, "title": title.strip(), "site_type": site_type, "lane": "quick", "state": "found",
        "object": {k: obj[k] for k in ("name", "type", "first_public", "date_source")}, "terms": terms,
        "volume": None, "serp": None, "watch": None, "follow_up": None,
        "model": None, "decision": None, "evidence_refs": refs, "bindings": None,
        "history": [{"at": now(), "from": None, "to": "found", "by": by, "reason": reason.strip()}],
    }
    if forecast_ref is not None:
        rec["basis"] = "forecast"              # 现行方向不写 basis(不写即速判登记)
    ledger["directions"][slug] = rec
    save_ledger(root, ledger)
    used = [t["term"] for t in terms] + ([obj["name"]] if forecast_ref is not None else [])
    quick_pool.consume(root, used)             # 预判登记另消耗游戏本身:开玩日历原料没有说法,以对象名为键
    return rec


def _latest_term_volume(obs, terms):
    """最新一份本方向说法的量级观察:term 不写(现行方向),或规范化后属于本方向的说法;测对象名的不算。"""
    mine = _term_set(terms)
    rows = [o for _, o in obs if o["kind"] == "quick_volume"
            and (o["readings"].get("term") is None or quick_pool.normalize_term(o["readings"]["term"]) in mine)]
    return rows[-1] if rows else None


def derive_quick(root, rec) -> dict:
    """从最新的量级观察与速判观察推导 volume、serp;结算时写进账本。"""
    obs = _observations(root, rec["evidence_refs"])
    v, s = _latest_term_volume(obs, rec.get("terms")), _latest(obs, "quick_screen")
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


def is_pregame(rec) -> bool:
    """预判登记、还没结算过的方向:按开玩前的预判结算;结算之后(观察中、搁置)的复核按现行路径。"""
    return rec.get("basis") == "forecast" and rec["state"] == "found"


def _at(ts: str) -> datetime:
    t = datetime.fromisoformat(ts)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def latest_forecast(root, rec) -> tuple:
    """方向引用里最新的预判观察 → (路径, 观察);按观察时间比,同时刻取引用里靠后的;没有返回 (None, None)。"""
    rows = [(ref, o) for ref, o in _observations(root, rec["evidence_refs"]) if o["kind"] == "quick_forecast"]
    if not rows:
        return None, None
    return max(enumerate(rows), key=lambda x: (_at(x[1][1]["observed_at"]), x[0]))[1]


def _check_object_volume(root, rec, r, forecast_at):
    """预判观察的对象名月量须来自本方向引用里的对象名量级观察(测的词是对象名),数对得上,
    且在预判观察当天或之前 forecast_volume_max_lag_days 天内测。"""
    ref = r["object_volume_ref"]
    require(ref in rec["evidence_refs"], f"预判观察的对象名量级观察 {ref} 不在方向引用里(先用 update --ref 补进来)")
    vol = W.read(root, ref)
    require(vol["kind"] == "quick_volume" and vol["slug"] == rec["slug"], f"{ref} 不是本方向的对象名量级观察 quick_volume")
    term = vol["readings"].get("term")
    require(isinstance(term, str) and quick_pool.normalize_term(term) == quick_pool.normalize_term(r["object"]),
            f"{ref} 测的词是 {term!r},不是对象名 {r['object']!r}(任务词的量不能当对象名的量用)")
    QM.check_object_volume_lag(ref, vol["observed_at"], forecast_at)
    pre = {c["geo"]: c["estimate_7d"] for c in vol["readings"]["countries"] if c["readable"]}
    require(pre == r["object_volume_pre"], f"预判观察的对象名月量 {r['object_volume_pre']} 与量级观察 {ref} 的读数 {pre} 不一致")


def forecast_model(root, rec) -> dict:
    """预判方向的模型:从方向引用里最新的预判观察重算。预判观察的口径(params)与它引用的参照的口径都须是当前假设表的,
    否则拒收"口径已变,重做预判"(不按新口径悄悄重算);六条须全过、国家须测全、说法须在任务里;对象名量级须在引用里、
    对得上、在预判当天或之前 2 天内测;
    每项任务的倍数与条数都按引用的参照路径向参照库重算,不一致就拒收(观察里的倍数不能自己说了算)。"""
    ref, f = latest_forecast(root, rec)
    require(f, "缺预判观察 quick_forecast")
    r = f["readings"]
    require(r["params"] == QM.forecast_params(),
            f"口径已变,重做预判:最新预判观察 {ref} 写于假设表 {r['assumptions_version']},口径与现行的"
            f"({QM.QUICK_ASSUMPTIONS['version']})不同,不能按新口径悄悄重算")
    failed = [k for k in W.FORECAST_CHECKS if r["checks"][k]["pass"] is not True]
    require(not failed, f"最新预判观察 {ref} 的 {'、'.join(failed)} 没过,不能测算")
    require(not r["skipped_geos"], f"最新预判观察 {ref} 还有没测的国家 {r['skipped_geos']},补测其余国家后重新预判")
    _check_forecast_terms(rec["terms"], f)
    _check_object_volume(root, rec, r, f["observed_at"])
    for t in r["tasks"]:
        got = QR.check_refs(root, t["reference_refs"], t["task"], r["category"], t["scope"])
        same = (t["r_p25"], t["r_median"], t["references"]) == (got["r_p25"], got["r_median"], got["references"])
        require(same, f"{t['task']}: 参照倍数与参照库重算不一致(观察写 下四分位 {t['r_p25']}、中位数 {t['r_median']}、"
                      f"{t['references']} 条;按引用的参照重算为 {got['r_p25']}、{got['r_median']}、{got['references']} 条)")
    return QM.forecast(r["object_volume_pre"], r["tasks"], complete=True)


def forecast_block(root, rec, model) -> dict:
    """开玩前结算后账本里的 forecast 块:最新预判观察的预测与任务倍数、复核日;复核结果之后由复核写入。"""
    ref, f = latest_forecast(root, rec)
    r = f["readings"]
    return {"ref": ref, "playable_at": r["playable_at"], "object_volume_pre": dict(r["object_volume_pre"]),
            "tasks": [{"task": t["task"], "r_p25": t["r_p25"], "r_median": t["r_median"]} for t in r["tasks"]],
            "forecast_p25": model["forecast_p25"], "forecast_median": model["forecast_median"],
            "review_at": QM.forecast_dates(r["playable_at"])["review_at"], "review": None, "slipped_days": 0}


def _require_brief(obs):
    brief = _latest(obs, "quick_brief")
    require(brief, "go 缺最小简报素材 quick_brief")
    require(brief["readings"]["data_available"] is True and brief["readings"]["build_days"] <= 3,
            "最小版本须 3 天内能做出、数据拿得到")


def _precheck_forecast(root, rec, to, on):
    """开玩前结算预判方向:搁置直接放行,不能否决;go、观察中要求开玩日对得上、结算日在开玩前 3–21 天、
    重算的预判建议与结论一致(go 只认 go,观察中只认 watching),go 另要最小简报素材。"""
    if to == "parked":
        return
    require(to != "rejected", "预判方向开玩前只能结算 go、观察中或搁置;否决等开玩后复核按现行路径")
    _, f = latest_forecast(root, rec)
    require(f, "缺预判观察 quick_forecast")
    playable_at = f["readings"]["playable_at"]
    require(playable_at == rec["object"]["first_public"],
            f"最新预判观察的开玩日 {playable_at} 与方向的 object.first_public {rec['object']['first_public']} 不一致"
            "(开玩日变过的话:按新开玩日重做预判写新的 quick_forecast 观察,用 update --ref 引用后再结算)")
    lo, hi = QM.QUICK_ASSUMPTIONS["forecast_days"]
    lead = (date.fromisoformat(playable_at) - date.fromisoformat(on)).days
    require(lo <= lead <= hi, f"开玩日在结算日之后 {lead} 天,须在 {lo}–{hi} 天内才能按预判结算")
    suggestion = forecast_model(root, rec)["suggestion"]
    require(suggestion == to, f"重算的预判建议是 {suggestion},与结论 {to} 不符(go 只认 go,观察中只认 watching)")
    if to == "go":
        _require_brief(_observations(root, rec["evidence_refs"]))


def _require_after_launch(rec, screen, vol, on):
    """预判观察中的方向开玩后结算(go 与读量级的否决门):复核日到了、复查过(watch-check),
    最新速判与任务说法的量级(有的话)都是开玩日或之后看的;到期日在第一次复查前只是复核日,不能拿它当观察到期。"""
    f, review_at = rec["forecast"], rec["forecast"]["review_at"]
    require(on >= review_at, f"复核日 {review_at} 未到:预判观察中的方向要开玩后 {QM.QUICK_ASSUMPTIONS['review_days']} 天"
                             f"复查过才能结算(现在 {on})")
    require(rec["watch"]["checks"], "预判观察中的方向还没复查过:到了复核日，先跑 watch-check(开玩后的速判与任务说法的量),再按建议结算")
    for name, o in (("速判", screen), ("量级", vol)):
        if o is not None:
            require(o["observed_at"][:10] >= f["playable_at"],
                    f"最新{name}观察是 {o['observed_at'][:10]} 看的,在开玩日 {f['playable_at']} 之前;开玩后重新观察、跑 watch-check 再结算")


def _require_parked_after_launch(rec, screen, vol):
    """预判登记后开玩前搁置的方向开玩后判 go:开玩日取 object.first_public(搁置的方向没有 forecast 块,也没有复核日与复查);
    最新速判须在开玩日当天到开玩后 new_days_game 天内(相当于开玩后重新判一次 Q1),任务说法的量级(有的话)须在开玩日或之后看。
    只管 go;否决是保守方向,不受这条限制。"""
    playable_at = rec["object"]["first_public"]
    limit = QM.QUICK_ASSUMPTIONS["new_days_game"]
    seen = screen["observed_at"][:10]
    age = (date.fromisoformat(seen) - date.fromisoformat(playable_at)).days
    require(0 <= age <= limit,
            f"预判后搁置的方向开玩后判 go:最新速判是 {seen} 看的,须在开玩日 {playable_at} 当天到开玩后 {limit} 天内"
            "(开玩前的看不算;过了窗口的重新在开玩后观察)")
    if vol is not None:
        require(vol["observed_at"][:10] >= playable_at,
                f"预判后搁置的方向开玩后判 go:最新量级观察是 {vol['observed_at'][:10]} 看的,在开玩日 {playable_at} 之前;"
                "开玩后重新测任务说法的量再判 go")


def _precheck_quick(root, rec, to, gate, on, scope_hit=None):
    if is_pregame(rec):
        return _precheck_forecast(root, rec, to, on)
    obs = _observations(root, rec["evidence_refs"])
    if to == "parked":
        return
    screen = _latest(obs, "quick_screen")
    require(screen, "缺速判观察 quick_screen")
    _check_screen_term(rec["terms"], screen)
    checks = screen["readings"]["checks"]
    forecast_dir = rec.get("basis") == "forecast"
    vol = _latest_term_volume(obs, rec["terms"]) if forecast_dir else _latest(obs, "quick_volume")   # 预判方向别取成对象名的量
    if forecast_dir and rec["state"] == "watching" and (to == "go" or gate in ("volume", "oneoff")):
        _require_after_launch(rec, screen, vol, on)
    if forecast_dir and rec["state"] == "parked" and to == "go":
        _require_parked_after_launch(rec, screen, vol)
    if to in ("go", "watching"):
        require(_screen_all_pass(screen), "最新速判观察六条须全过")
        require(vol, "缺量级观察 quick_volume")
        fresh = (date.fromisoformat(on) - date.fromisoformat(_oldest_anchor(vol["readings"]))).days
        require(fresh <= QM.QUICK_ASSUMPTIONS["anchor_fresh_days"], f"锚词测量已过 {fresh} 天,须在 90 天内")
        model = _quick_model(root, rec)
        trend = QM.trend(vol["readings"]["series_30d"])
        require(not trend["spike_decay"], "曲线冲高回落,应按 oneoff 否决")
        if to == "go":
            _require_brief(obs)
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
    """复查观察中的方向:加入新观察,算一次,记一条复查;只给建议,转移仍走 settle.py。
    预判方向另有三条:复核日前拒收;最新速判与量级(取任务说法的量,对象名的不算)须在开玩日或之后;
    第一次复查先把到期日改为复查日 + 观察天数(预判结算时的到期日只是复核日)。"""
    on = on or today()
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec and rec.get("lane") == "quick" and rec["state"] == "watching", f"{slug} 不是观察中的快道方向")
    pregame = rec.get("basis") == "forecast"           # 预判方向:开玩后才复查,速判与量级都按开玩后的读数
    if pregame:
        review_at = rec["forecast"]["review_at"]
        require(on >= review_at, f"复核日 {review_at} 未到:预判方向要开玩后 {QM.QUICK_ASSUMPTIONS['review_days']} 天才复查(现在 {on})")
    for ref in refs:
        obs = W.read(root, ref)
        require(obs["slug"] == slug, f"{ref} 属于别的方向")
        if obs["kind"] == "quick_screen":
            _check_screen_term(rec["terms"], obs)
        if ref not in rec["evidence_refs"]:
            rec["evidence_refs"].append(ref)
    obs = _observations(root, rec["evidence_refs"])
    screen = _latest(obs, "quick_screen")
    require(screen, "缺速判观察 quick_screen")
    vol = _latest_term_volume(obs, rec["terms"]) if pregame else _latest(obs, "quick_volume")    # 预判方向别取成对象名的量
    require(vol, "缺量级观察 quick_volume(预判方向须有开玩后测任务说法的量,对象名的量不算)" if pregame else "缺量级观察 quick_volume")
    if pregame:
        playable_at = rec["forecast"]["playable_at"]
        for name, o in (("速判", screen), ("量级", vol)):
            require(o["observed_at"][:10] >= playable_at,
                    f"最新{name}观察是 {o['observed_at'][:10]} 看的,在开玩日 {playable_at} 之前;开玩后重新观察再复查")
        if not rec["watch"]["checks"]:             # 第一次复查:到期日改为复查日 + 观察天数,在此之前的建议才有"还能观察"可言
            rec["watch"]["expires_at"] = QM.add_days(on, QM.QUICK_ASSUMPTIONS["watch_days"])
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


def review_forecast(root, slug, refs=(), on=None) -> dict:
    """开玩后 7 天复核预判 go:任务与说法按结算时那份预判观察(forecast.ref);每项任务取复核日及之后测的最新量级
    (6 国都测过,没有"未查:"的国家),合计与预测下四分位比,实测低于 25% 提示止损。
    只对开玩前预判就判 go 的方向(模型是预判模型);观察中、开玩后按现行路径才判 go 的不复核。
    只写 forecast.review,不改状态;每个方向只复核一次。"""
    on = on or today()
    require(is_date(on), f"日期须为日历上存在的 YYYY-MM-DD(收到 {on!r})")
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec and rec.get("lane") == "quick" and rec.get("basis") == "forecast" and rec["state"] == "go"
            and isinstance(rec.get("forecast"), dict), f"{slug} 不是预判的 go 方向,没有预测可复核")
    require((rec.get("model") or {}).get("basis") == "forecast",
            f"{slug} 的 go 是观察中、开玩后按现行路径判的(模型不是开玩前预判),预判下四分位当初没过线,没有预判止损可复核")
    f = rec["forecast"]
    require(f["review"] is None, f"{slug} 已复核过: {f['review']}")
    require(on >= f["review_at"], f"复核日 {f['review_at']} 未到(开玩后 {QM.QUICK_ASSUMPTIONS['review_days']} 天才复核,现在 {on})")
    for ref in refs:
        obs = W.read(root, ref)
        require(obs["slug"] == slug, f"{ref} 属于别的方向")
        if ref not in rec["evidence_refs"]:
            rec["evidence_refs"].append(ref)
    obs = _observations(root, rec["evidence_refs"])
    forecast = W.read(root, f["ref"])                 # 按结算时那份预判观察的任务与说法,go 之后再挂的预判观察不算
    require(forecast["kind"] == "quick_forecast", f"forecast.ref {f['ref']} 不是预判观察 quick_forecast")
    by_task, missing = [], []
    for t in forecast["readings"]["tasks"]:
        terms = {quick_pool.normalize_term(x) for x in t["terms"]}
        rows = [(i, ref, o) for i, (ref, o) in enumerate(obs)
                if o["kind"] == "quick_volume" and o["readings"].get("term") is not None
                and quick_pool.normalize_term(o["readings"]["term"]) in terms
                and o["observed_at"][:10] >= f["review_at"]]          # 复核日起测的:7 天窗口整段落在开玩后
        if not rows:
            missing.append(f"{t['task']}(测的词须是 {t['terms']})")
            continue
        _, ref, o = max(rows, key=lambda x: (_at(x[2]["observed_at"]), x[0]))
        skipped = [c["geo"] for c in o["readings"]["countries"]
                   if not c["readable"] and c["basis"].startswith(TV.SKIPPED_PREFIX)]
        require(not skipped, f"{t['task']} 用的量级观察 {ref} 有没测的国家 {skipped}(basis 以\"{TV.SKIPPED_PREFIX}\"开头):"
                             "预测是英文区 6 国合计,复核也要 6 国都测过,补测后再复核")
        by_task.append({"task": t["task"], "ref": ref, "estimate_7d": o["readings"]["estimate_7d"]})
    require(not missing, f"缺复核日 {f['review_at']} 或之后测的量级观察 quick_volume:{';'.join(missing)}")
    actual = sum(t["estimate_7d"] for t in by_task)
    stop = actual < f["forecast_p25"] * QM.QUICK_ASSUMPTIONS["review_stop_ratio"]
    ratio = round(actual / f["forecast_p25"], 4)
    f["review"] = {"at": on, "actual": actual, "forecast_p25": f["forecast_p25"], "ratio": ratio, "stop": stop,
                   "by_task": by_task}
    save_ledger(root, ledger)
    message = ("预判失准,建议停止追加投入" if stop
               else f"实测达到预测下四分位的 {ratio:.0%},没低到 {QM.QUICK_ASSUMPTIONS['review_stop_ratio']:.0%},不提示止损")
    return {"slug": slug, **f["review"], "message": message}


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
    rq.add_argument("--input", required=True,
                    help="JSON:slug、title、site_type、object、terms、reason,另有 screen(速判观察)或 forecast(预判观察)二选一")
    pv = sub.add_parser("quick-preview")
    pv.add_argument("--slug", required=True)
    wc = sub.add_parser("watch-check")
    wc.add_argument("--slug", required=True)
    wc.add_argument("--ref", action="append", default=[])
    rf = sub.add_parser("review-forecast")
    rf.add_argument("--slug", required=True)
    rf.add_argument("--ref", action="append", default=[], help="开玩后测任务说法的量级观察路径(每项任务一份)")
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
                                 d.get("screen"), d["reason"], d.get("by", "xinci-bench-quick"), d.get("forecast"))
        elif a.cmd == "quick-preview":
            rec = load_ledger(root)["directions"].get(a.slug)
            require(rec and rec.get("lane") == "quick", f"没有快道方向 {a.slug}")
            out = {**derive_quick(root, rec), "model": _quick_model(root, rec)}
        elif a.cmd == "watch-check":
            out = watch_check(root, a.slug, a.ref)
        elif a.cmd == "review-forecast":
            out = review_forecast(root, a.slug, a.ref)
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
