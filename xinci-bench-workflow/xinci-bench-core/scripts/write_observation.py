#!/usr/bin/env python3
"""观察只追加:按 kind 校验必填读数,文件名带时间与随机后缀,永不覆盖旧文件。"""
import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

import data_root
import quick_model as QM
from _common import SLUG_RE, BenchError, is_date, load_json, require, stamp

QUICK_KINDS = ("quick_signal", "quick_screen", "quick_volume", "quick_brief")
KINDS = ("scan", "benchmark", "demand", "serp", "differentiation", "delivery", "brief") + QUICK_KINDS
CHECKS = ("B1", "B2", "B3", "B4", "B5")
QUICK_CHECKS = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")
QUICK_SOURCES = ("autocomplete", "trends_rising", "trends_rss", "steamcharts", "apple", "itunes",
                 "google_play", "producthunt", "github", "hackernews", "youtube", "wikipedia",
                 "policy", "reddit", "other")
# 初核数值门槛(选站契约 §3.2);标"通过"但数字不达标的观察直接拒收
LIMITS = {"max_age_months": 24, "max_authority_score": 30, "min_us_organic": 5000}
# 每个 kind 的 readings 必填键;值的类型在 _check_<kind> 里再细查
REQUIRED = {
    "scan": ("domains",),
    "benchmark": ("domain", "traffic_start", "us_organic_now", "us_organic_m12", "curve",
                  "referring_domains", "anchor_summary", "link_driven", "algo_risk",
                  "update_readings", "ads_txt", "pricing"),
    "demand": ("clusters", "competitor_traffic", "crowding", "new_sites"),
    "serp": ("query", "cluster_id", "answered", "answered_basis", "ai_overview",
             "benchmark_position", "top10"),
    "differentiation": ("copy_only", "gaps"),
    "delivery": ("data_sources", "license", "hours", "cash_first_year", "monthly_hours",
                 "feasible", "basis"),
    "brief": ("positioning", "pages", "tech_hosting", "monetization_plan", "seo_notes",
              "geo_notes", "risks"),
    "quick_signal": ("items",),
    "quick_screen": ("term", "checks", "ai_overview", "top10", "occupied_by"),
    "quick_volume": ("anchor_term", "anchor_volume", "anchor_source", "anchor_measured_at", "window_days",
                     "new_mean_7d", "anchor_mean_7d", "new_mean_30d", "anchor_mean_30d", "ratio_7d",
                     "estimate_7d", "estimate_30d", "series_30d"),
    "quick_brief": ("positioning", "pages", "data_sources", "license", "update_frequency", "build_days",
                    "data_available", "hosting", "risks"),
}
_YM = re.compile(r"\d{4}-\d{2}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso(ts):
    try:
        datetime.fromisoformat(ts)
        return True
    except (TypeError, ValueError):
        return False


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


def _check_scan(r, observed_at):
    require(isinstance(r["domains"], list) and r["domains"], "scan.domains 须为非空列表")
    for d in r["domains"]:
        require(isinstance(d.get("domain"), str) and d["domain"], "scan.domains[].domain 缺失")
        checks = d.get("checks") or {}
        require(set(checks) == set(CHECKS), f"{d['domain']}: checks 须恰好含 B1–B5")
        verdicts = []
        for k in CHECKS:
            c = checks[k]
            require(c.get("pass") in (True, False, None), f"{d['domain']}.{k}.pass 须为 true/false/null")
            require(isinstance(c.get("basis"), str) and c["basis"].strip(), f"{d['domain']}.{k}.basis 缺失")
            verdicts.append(c["pass"])
        # null 只表示"前面已不过、为省额度没查",全过时不允许有 null
        require(False in verdicts or None not in verdicts, f"{d['domain']}: 没有不过项时 B1–B5 不能留 null")
        _check_limits(d, observed_at)


def _months_between(earlier, later):
    a, b = date.fromisoformat(earlier[:10]), date.fromisoformat(later[:10])
    return (b.year - a.year) * 12 + b.month - a.month - (b.day < a.day)


def _check_limits(d, observed_at):
    c, name = d["checks"], d["domain"]
    if c["B1"]["pass"] is True and not d.get("aged_domain"):
        reg = d.get("registered_at")
        require(isinstance(reg, str) and _DATE.fullmatch(reg[:10]),
                f"{name}: B1 判通过须有 registered_at,或标 aged_domain=true 并在 basis 写 24 个月前流量≈0 的依据")
        require(_months_between(reg, observed_at) <= LIMITS["max_age_months"],
                f"{name}: 注册已超过 {LIMITS['max_age_months']} 个月,B1 不能判通过")
    if c["B2"]["pass"] is True:
        a = d.get("authority_score")
        require(_num(a) and a <= LIMITS["max_authority_score"], f"{name}: AS 须 ≤ {LIMITS['max_authority_score']} 才能判 B2 通过")
    if c["B3"]["pass"] is True:
        t = d.get("us_organic_now")
        require(_num(t) and t >= LIMITS["min_us_organic"],
                f"{name}: 去品牌词与定位词后的美区自然流量须 ≥ {LIMITS['min_us_organic']} 才能判 B3 通过")


def _check_benchmark(r):
    require(isinstance(r["domain"], str) and r["domain"], "benchmark.domain 缺失")
    require(r["traffic_start"] is None or _YM.fullmatch(str(r["traffic_start"])), "traffic_start 须为 YYYY-MM 或 null")
    require(_num(r["us_organic_now"]), "us_organic_now 须为非负数")
    require(r["us_organic_m12"] is None or _num(r["us_organic_m12"]), "us_organic_m12 须为非负数或 null")
    curve = r["curve"]
    require(isinstance(curve, dict) and set(curve) == {"3", "6", "12"}, "curve 须恰好含键 3/6/12")
    require(all(v is None or _num(v) for v in curve.values()), "curve 值须为非负数或 null")
    require(r["referring_domains"] is None or _num(r["referring_domains"]), "referring_domains 须为非负数或 null")
    for k in ("link_driven", "algo_risk"):
        require(isinstance(r[k], bool), f"{k} 须为布尔")
    for k in ("anchor_summary", "update_readings", "ads_txt"):
        require(isinstance(r[k], str) and r[k].strip(), f"{k} 须为非空文字")


def _check_demand(r):
    require(isinstance(r["clusters"], list) and r["clusters"], "demand.clusters 须为非空列表")
    for c in r["clusters"]:
        require(isinstance(c.get("id"), str) and SLUG_RE.fullmatch(c["id"]), "cluster.id 无效")
        require(isinstance(c.get("seed_term"), str) and c["seed_term"].strip(), f"{c['id']}: seed_term 缺失")
        require(_num(c.get("volume")), f"{c['id']}: volume 须为非负数")
        require(_DATE.fullmatch(str(c.get("measured_at"))), f"{c['id']}: measured_at 须为 YYYY-MM-DD")
        require(c.get("coverage") in ("benchmark", "ours"), f"{c['id']}: coverage 须为 benchmark/ours")
        require(isinstance(c.get("near_me"), bool), f"{c['id']}: near_me 须为布尔")
    require(isinstance(r["competitor_traffic"], list), "competitor_traffic 须为列表")
    for t in r["competitor_traffic"]:
        require(isinstance(t, dict) and isinstance(t.get("domain"), str) and _num(t.get("traffic"))
                and isinstance(t.get("basis"), str) and t["basis"].strip(),
                "competitor_traffic[] 须含 domain、traffic(非负数)、basis(按网址筛选的依据)")
    require(isinstance(r["crowding"], int) and r["crowding"] >= 1, "crowding 须为 ≥1 的整数(含标杆本身)")
    require(isinstance(r["new_sites"], list), "new_sites 须为列表")


def _check_serp(r):
    require(isinstance(r["query"], str) and r["query"].strip(), "serp.query 缺失")
    require(isinstance(r["cluster_id"], str) and r["cluster_id"], "serp.cluster_id 缺失")
    require(isinstance(r["answered"], bool), "serp.answered 须为布尔")
    require(isinstance(r["answered_basis"], str) and r["answered_basis"].strip(), "answered_basis 缺失")
    aio = r["ai_overview"]
    require(isinstance(aio, dict) and {"present", "completes_task", "cited_domains", "recommends_tools"} <= set(aio),
            "ai_overview 须含 present/completes_task/cited_domains/recommends_tools")
    require(r["benchmark_position"] is None or (isinstance(r["benchmark_position"], int) and r["benchmark_position"] >= 1),
            "benchmark_position 须为 ≥1 的整数或 null")
    require(isinstance(r["top10"], list), "top10 须为列表")


def _check_differentiation(r):
    require(isinstance(r["copy_only"], bool), "copy_only 须为布尔")
    require(isinstance(r["gaps"], list), "gaps 须为列表")
    if r["copy_only"]:
        return
    require(r["gaps"], "copy_only=false 时 gaps 不能为空")
    for g in r["gaps"]:
        for k in ("benchmark_now", "ours", "evidence"):
            require(isinstance(g.get(k), str) and g[k].strip(), f"gap.{k} 缺失")


def _check_delivery(r):
    require(isinstance(r["data_sources"], list), "data_sources 须为列表")
    require(isinstance(r["license"], str) and r["license"].strip(), "license 缺失")
    h = r["hours"]
    require(isinstance(h, dict) and set(h) == {"dev", "data", "content"} and all(_num(v) for v in h.values()),
            "hours 须恰好含 dev/data/content 三个非负数")
    require(_num(r["cash_first_year"]) and _num(r["monthly_hours"]), "cash_first_year/monthly_hours 须为非负数")
    require(isinstance(r["feasible"], bool), "feasible 须为布尔")
    require(isinstance(r["basis"], str) and r["basis"].strip(), "basis 缺失")


def _check_brief(r):
    require(isinstance(r["positioning"], str) and r["positioning"].strip(), "positioning 缺失")
    require(isinstance(r["pages"], list) and r["pages"], "pages 须为非空列表")
    for p in r["pages"]:
        for k in ("path", "target_query", "page_type", "deliverable"):
            require(isinstance(p.get(k), str) and p[k].strip(), f"page.{k} 缺失")
        require(_num(p.get("volume")), "page.volume 须为非负数")
    for k in ("tech_hosting", "monetization_plan"):
        require(isinstance(r[k], str) and r[k].strip(), f"{k} 缺失")
    for k in ("seo_notes", "geo_notes", "risks"):
        require(isinstance(r[k], list), f"{k} 须为列表")


def _check_null_rule(checks, keys, label):
    """pass 为 true/false/null;null 只表示"前项已不过、为省额度没查"。"""
    require(isinstance(checks, dict) and set(checks) == set(keys), f"{label}: checks 须恰好含 {keys}")
    verdicts = []
    for k in keys:
        c = checks[k]
        require(isinstance(c, dict) and c.get("pass") in (True, False, None), f"{label}.{k}.pass 须为 true/false/null")
        require(isinstance(c.get("basis"), str) and c["basis"].strip(), f"{label}.{k}.basis 缺失")
        verdicts.append(c["pass"])
    require(False in verdicts or None not in verdicts, f"{label}: 没有不过项时不能留 null")


def _check_quick_signal(r):
    require(isinstance(r["items"], list) and r["items"], "quick_signal.items 须为非空列表")
    for it in r["items"]:
        require(it.get("source") in QUICK_SOURCES, f"原料来源须为 {QUICK_SOURCES}")
        require(isinstance(it.get("object"), str) and it["object"].strip(), "原料 object 缺失")
        require(it.get("term") is None or (isinstance(it["term"], str) and it["term"].strip()), "原料 term 须为文字或 null")
        require(isinstance(it.get("url"), str) and it["url"].strip(), "原料 url 缺失(写实际取回的网址)")
        require(is_date(it.get("seen_at")), "原料 seen_at 须为日历上存在的 YYYY-MM-DD")


def _check_quick_screen(r):
    require(isinstance(r["term"], str) and r["term"].strip(), "quick_screen.term 缺失")
    _check_null_rule(r["checks"], QUICK_CHECKS, r["term"])
    aio = r["ai_overview"]
    require(isinstance(aio, dict) and {"present", "completes_task", "cited_domains"} <= set(aio),
            "ai_overview 须含 present/completes_task/cited_domains")
    require(isinstance(r["top10"], list), "top10 须为列表")
    if r["checks"]["Q5"]["pass"] is False:
        require(isinstance(r["occupied_by"], str) and r["occupied_by"].strip(), "Q5 不过时 occupied_by 须写完整做了任务的页面域名")


def _check_quick_volume(r):
    require(isinstance(r["anchor_term"], str) and r["anchor_term"].strip(), "anchor_term 缺失")
    require(_num(r["anchor_volume"]) and r["anchor_volume"] > 0, "anchor_volume 须为正数")
    require(r["anchor_source"] in ("lexicon", "semrush"), "anchor_source 须为 lexicon/semrush")
    require(is_date(r["anchor_measured_at"]), "anchor_measured_at 须为日历上存在的 YYYY-MM-DD")
    require(r["window_days"] == 7, "window_days 固定为 7(同时报 30 天对照)")
    for k in ("new_mean_7d", "anchor_mean_7d", "new_mean_30d", "anchor_mean_30d", "estimate_7d", "estimate_30d"):
        require(_num(r[k]), f"{k} 须为非负数")
    require(r["anchor_mean_7d"] > 0 and r["anchor_mean_30d"] > 0, "锚词热度为 0,换一个锚词")
    ratio = r["new_mean_7d"] / r["anchor_mean_7d"]
    require(abs(ratio - r["ratio_7d"]) < 0.001, "ratio_7d 须等于 new_mean_7d ÷ anchor_mean_7d")
    require(QM.ratio_ok(ratio), "锚词与新词热度比须在 0.2–5 之间,换一个量级更接近的锚词")
    require(abs(r["estimate_7d"] - r["anchor_volume"] * ratio) <= 1, "estimate_7d 须等于 anchor_volume × ratio_7d(取整)")
    s = r["series_30d"]
    require(isinstance(s, list) and len(s) >= 14 and all(_num(v) for v in s),
            "series_30d 须为至少 14 个非负数(Trends 显示 \"<1\" 的点记 0)")


def _check_quick_brief(r):
    require(isinstance(r["positioning"], str) and r["positioning"].strip(), "positioning 缺失")
    require(isinstance(r["pages"], list) and r["pages"], "pages 须为非空列表")
    for p in r["pages"]:
        for k in ("path", "target_query", "deliverable"):
            require(isinstance(p.get(k), str) and p[k].strip(), f"page.{k} 缺失")
    for k in ("license", "update_frequency", "hosting"):
        require(isinstance(r[k], str) and r[k].strip(), f"{k} 缺失")
    require(isinstance(r["data_sources"], list) and isinstance(r["risks"], list), "data_sources/risks 须为列表")
    require(_num(r["build_days"]), "build_days 须为非负数")
    require(isinstance(r["data_available"], bool), "data_available 须为布尔")


def _expected_stage(kind):
    return "scan" if kind == "scan" else ("quick" if kind in QUICK_KINDS else "assess")


def _preflight_ok(pf):
    pf = pf or {}
    return (all(pf.get(k) is True for k in ("controllable", "desktop", "logged_out")) and pf.get("region") == "us"
            and isinstance(pf.get("evidence"), str) and bool(pf["evidence"].strip()))


def validate(obs: dict) -> None:
    kind, stage = obs.get("kind"), obs.get("stage")
    require(kind in KINDS, f"kind 须为 {KINDS}")
    require(stage == _expected_stage(kind), "kind=scan 时 stage=scan;快道四类 stage=quick;其余 stage=assess")
    if kind in ("scan", "quick_signal"):
        require(obs.get("slug") is None, f"{kind} 批次观察 slug 须为 null")
    else:
        require(isinstance(obs.get("slug"), str) and SLUG_RE.fullmatch(obs["slug"]), "slug 无效")
    require(isinstance(obs.get("observed_at"), str) and _iso(obs["observed_at"]),
            "observed_at 须为 ISO 时间;写观察前先取系统时间,不要估")
    urls = obs.get("source_urls")
    require(isinstance(urls, list) and urls and all(isinstance(u, str) and u for u in urls), "source_urls 须为非空列表")
    require(isinstance(obs.get("semrush_calls"), int) and obs["semrush_calls"] >= 0, "semrush_calls 须为非负整数")
    require(isinstance(obs.get("points"), list), "points 须为列表")
    if kind == "serp":
        require(_preflight_ok(obs.get("browser_preflight")),
                "serp 观察须有通过的 browser_preflight(可控、桌面、美区、未登录、依据)")
    r = obs.get("readings")
    require(isinstance(r, dict), "readings 须为对象")
    missing = [k for k in REQUIRED[kind] if k not in r]
    require(not missing, f"{kind}.readings 缺字段: {missing}")
    if kind == "scan":
        _check_scan(r, obs["observed_at"])
    else:
        globals()[f"_check_{kind}"](r)
    if kind == "quick_screen" and (r["checks"]["Q5"]["pass"] is not None or r["checks"]["Q6"]["pass"] is not None):
        require(_preflight_ok(obs.get("browser_preflight")), "Q5/Q6 有结论时须有通过的 browser_preflight")


def write(root, obs: dict) -> str:
    validate(obs)
    folder = {"scan": "_scan", "quick_signal": "_quick"}.get(obs["kind"], obs["slug"])
    ref = f"证据/{folder}/{stamp()}-{uuid.uuid4().hex[:8]}-{obs['kind']}.json"
    path = Path(root) / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(obs, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return ref


def read(root, ref: str) -> dict:
    """读回并重新校验;路径必须在 证据/ 下。"""
    require(ref.startswith("证据/") and ".." not in ref, f"观察路径须在 证据/ 下: {ref}")
    p = Path(root) / ref
    require(p.is_file(), f"观察不存在: {ref}")
    obs = load_json(p)
    validate(obs)
    return obs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--input", required=True, help="观察 JSON 文件")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        print(write(root, json.loads(Path(a.input).read_text(encoding="utf-8"))))
    except (BenchError, OSError, ValueError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
