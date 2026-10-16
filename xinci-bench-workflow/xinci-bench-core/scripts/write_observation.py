#!/usr/bin/env python3
"""观察只追加:按 kind 校验必填读数,文件名带时间与随机后缀,永不覆盖旧文件。"""
import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import data_root
import quick_model as QM
from _common import EN_COUNTRIES, SLUG_RE, BenchError, is_date, load_json, require, stamp

QUICK_KINDS = ("quick_signal", "quick_screen", "quick_volume", "quick_brief", "quick_reference", "quick_forecast")
KINDS = ("scan", "benchmark", "demand", "serp", "differentiation", "delivery", "brief") + QUICK_KINDS
CHECKS = ("B1", "B2", "B3", "B4", "B5")
QUICK_CHECKS = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")
FORECAST_CHECKS = ("P1", "P2", "P3", "P4", "P5", "P6")        # 上线前预判的六条适用范围
QUICK_SOURCES = ("autocomplete", "trends_rising", "trends_rss", "steamcharts", "apple", "itunes",
                 "google_play", "producthunt", "github", "hackernews", "youtube", "wikipedia",
                 "policy", "reddit", "other")
# 初核数值门槛(选站契约 §3.2);标"通过"但数字不达标的观察直接拒收
LIMITS = {"max_age_months": 24, "max_authority_score": 30, "min_en_organic": 5000}
# 每个 kind 的 readings 必填键;值的类型在 _check_<kind> 里再细查
REQUIRED = {
    "scan": ("domains",),
    "benchmark": ("domain", "traffic_start", "us_organic_now", "us_organic_m12", "country_traffic",
                  "en_organic_now", "en_organic_m12", "curve", "referring_domains", "anchor_summary",
                  "link_driven", "algo_risk", "update_readings", "ads_txt", "pricing"),
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
    "quick_volume": ("window_days", "countries", "trend_geo", "estimate_7d", "estimate_30d", "series_30d"),
    "quick_brief": ("positioning", "pages", "data_sources", "license", "update_frequency", "build_days",
                    "data_available", "hosting", "risks"),
    "quick_reference": ("object", "category", "task", "task_term", "playable_at", "anchor_term", "anchor_volume",
                        "anchor_source", "object_window", "object_ratio", "task_window", "task_ratio",
                        "full_60_days", "object_volume_pre", "task_volume_post", "r"),
    "quick_forecast": ("object", "category", "playable_at", "date_source", "object_volume_pre", "object_volume_ref",
                       "skipped_geos", "tasks", "forecast_p25", "forecast_median", "suggestion", "checks", "serp"),
}
# quick_volume 里每个读得出的国家必须有的字段
COUNTRY_FIELDS = ("anchor_term", "anchor_volume", "anchor_source", "anchor_measured_at", "new_mean_7d",
                  "anchor_mean_7d", "new_mean_30d", "anchor_mean_30d", "ratio_7d", "estimate_7d", "estimate_30d")
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


def _en_factor(dist, label):
    """按国家分布 → 英文区 ÷ 美国 的倍数;美国为 0 时返回 None(不能按比例换算)。"""
    require(isinstance(dist, dict) and sorted(dist) == sorted(EN_COUNTRIES) and all(_num(v) for v in dist.values()),
            f"{label}: 按国家分布须恰好含英文区 6 国 {EN_COUNTRIES},值为非负数(没有的国家填 0)")
    return sum(dist.values()) / dist["US"] if dist["US"] else None


def _check_en(label, dist, us, en, en_key):
    """英文区读数 = 美区读数 × 6 国合计 ÷ 美国(允许取整误差 1);美国为 0 时按逐国实测填,只要求非负。"""
    factor = _en_factor(dist, label)
    if us is None:
        require(en is None, f"{label}: 美区读数为 null 时 {en_key} 也须为 null")
        return
    require(_num(en), f"{label}: {en_key} 须为非负数")
    if factor is not None:
        require(abs(en - us * factor) <= 1,
                f"{label}: {en_key} 须等于美区读数 × 6 国合计 ÷ 美国(应为约 {round(us * factor)})")


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
        require(_num(t), f"{name}: B3 判通过须有去品牌词与定位词后的美区自然流量 us_organic_now")
        _check_en(name, d.get("country_traffic"), t, d.get("en_organic_now"), "en_organic_now")
        require(d["en_organic_now"] >= LIMITS["min_en_organic"],
                f"{name}: 去品牌词与定位词后的英文区自然流量须 ≥ {LIMITS['min_en_organic']} 才能判 B3 通过")


def _check_benchmark(r):
    require(isinstance(r["domain"], str) and r["domain"], "benchmark.domain 缺失")
    require(r["traffic_start"] is None or _YM.fullmatch(str(r["traffic_start"])), "traffic_start 须为 YYYY-MM 或 null")
    require(_num(r["us_organic_now"]), "us_organic_now 须为非负数")
    require(r["us_organic_m12"] is None or _num(r["us_organic_m12"]), "us_organic_m12 须为非负数或 null")
    curve = r["curve"]
    require(isinstance(curve, dict) and set(curve) == {"3", "6", "12"}, "curve 须恰好含键 3/6/12")
    require(all(v is None or _num(v) for v in curve.values()), "curve 值须为非负数或 null")
    require(r["referring_domains"] is None or _num(r["referring_domains"]), "referring_domains 须为非负数或 null")
    _check_en(r["domain"], r["country_traffic"], r["us_organic_now"], r["en_organic_now"], "en_organic_now")
    _check_en(r["domain"], r["country_traffic"], r["us_organic_m12"], r["en_organic_m12"], "en_organic_m12")
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
        _check_en(c["id"], c.get("seed_country_volume"), c["volume"], c.get("en_volume"), "en_volume")
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
    """pass 为 true/false/null;null 表示"前项已不过、为省额度没查",快道 Q1 也可表示"查不到日期"。"""
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
        rising = it.get("rising")
        require(rising is None or rising == "breakout" or (_num(rising) and isinstance(rising, int)),
                "原料 rising 须为 Trends 飙升百分比(非负整数)、\"breakout\" 或不写")
        require(it.get("playable_at") is None or is_date(it["playable_at"]),
                "原料 playable_at 须为日历上存在的 YYYY-MM-DD(第一次让大量普通用户用上的日期,可在未来)")
        require(it.get("stage") is None or (isinstance(it["stage"], str) and it["stage"].strip()),
                "原料 stage 须为文字(如 closed beta、Early access)或不写")
        require(it.get("platform") is None or (isinstance(it["platform"], str) and it["platform"].strip()),
                "原料 platform 须为文字(如 roblox、steam、mobile)或不写")


def _check_quick_screen(r):
    require(isinstance(r["term"], str) and r["term"].strip(), "quick_screen.term 缺失")
    _check_null_rule(r["checks"], QUICK_CHECKS, r["term"])
    aio = r["ai_overview"]
    require(isinstance(aio, dict) and {"present", "completes_task", "cited_domains"} <= set(aio),
            "ai_overview 须含 present/completes_task/cited_domains")
    require(isinstance(r["top10"], list), "top10 须为列表")
    if r["checks"]["Q5"]["pass"] is False:
        require(isinstance(r["occupied_by"], str) and r["occupied_by"].strip(), "Q5 不过时 occupied_by 须写完整做了任务的页面域名")


def _check_country(c):
    geo = c.get("geo")
    require(isinstance(c.get("readable"), bool), f"{geo}: readable 须为布尔")
    require(isinstance(c.get("basis"), str) and c["basis"].strip(), f"{geo}: basis 须写怎么取的,或为什么读不出")
    if not c["readable"]:
        return
    missing = [k for k in COUNTRY_FIELDS if k not in c]
    require(not missing, f"{geo}: 读得出的国家缺字段 {missing}")
    require(isinstance(c["anchor_term"], str) and c["anchor_term"].strip(), f"{geo}: anchor_term 缺失")
    require(_num(c["anchor_volume"]) and c["anchor_volume"] > 0, f"{geo}: anchor_volume 须为正数")
    require(c["anchor_source"] in ("lexicon", "semrush"), f"{geo}: anchor_source 须为 lexicon/semrush")
    require(geo == "US" or c["anchor_source"] == "semrush", f"{geo}: 旧词库只有美国的量,美国以外的锚词月量须用 Semrush 查")
    require(is_date(c["anchor_measured_at"]), f"{geo}: anchor_measured_at 须为日历上存在的 YYYY-MM-DD")
    for k in ("new_mean_7d", "anchor_mean_7d", "new_mean_30d", "anchor_mean_30d", "estimate_7d", "estimate_30d"):
        require(_num(c[k]), f"{geo}: {k} 须为非负数")
    require(c["anchor_mean_7d"] > 0 and c["anchor_mean_30d"] > 0, f"{geo}: 锚词热度为 0,换一个锚词")
    ratio = c["new_mean_7d"] / c["anchor_mean_7d"]
    require(abs(ratio - c["ratio_7d"]) < 0.001, f"{geo}: ratio_7d 须等于 new_mean_7d ÷ anchor_mean_7d")
    require(QM.ratio_ok(ratio), f"{geo}: 锚词与新词热度比须在 0.2–5 之间,换一个量级更接近的锚词")
    require(abs(c["estimate_7d"] - c["anchor_volume"] * ratio) <= 1, f"{geo}: estimate_7d 须等于 anchor_volume × ratio_7d(取整)")


def _check_quick_volume(r):
    require(r["window_days"] == 7, "window_days 固定为 7(同时报 30 天对照)")
    geos = QM.QUICK_ASSUMPTIONS["countries"]
    cs = r["countries"]
    require(isinstance(cs, list) and all(isinstance(c, dict) for c in cs)
            and sorted(str(c.get("geo")) for c in cs) == sorted(geos),
            f"countries 须恰好是英文区 {len(geos)} 国 {geos} 各一行(读不出的写 readable=false)")
    for c in cs:
        _check_country(c)
    readable = [c for c in cs if c["readable"]]
    require(readable, "至少要有一个国家读得出;全读不出说明 Trends 还没有量,原料留到下次")
    require(r["estimate_7d"] == sum(c["estimate_7d"] for c in readable),
            "estimate_7d 须等于各国 estimate_7d 合计(读不出的国家记 0)")
    require(r["estimate_30d"] == sum(c["estimate_30d"] for c in readable), "estimate_30d 须等于各国 estimate_30d 合计")
    best = max(c["estimate_7d"] for c in readable)
    tops = sorted(c["geo"] for c in readable if c["estimate_7d"] == best)
    require(r["trend_geo"] in tops, f"trend_geo 须是换算量最大的国家 {tops},series_30d 取它的逐日曲线")
    s = r["series_30d"]
    require(isinstance(s, list) and len(s) >= 14 and all(_num(v) for v in s),
            "series_30d 须为至少 14 个非负数(Trends 显示 \"<1\" 的点记 0)")
    require("term" not in r or (isinstance(r["term"], str) and r["term"].strip()),
            "term 须为非空文字(测的是哪个词:对象名还是任务词),不测别的词就不写")


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


def _check_quick_reference(r, observed_at):
    """参照:一款已开玩的游戏,开玩前对象名的量与开玩后任务词的量之比 r(预判的倍数从这些参照里取)。"""
    a = QM.QUICK_ASSUMPTIONS
    for k in ("object", "task_term", "anchor_term"):
        require(isinstance(r[k], str) and r[k].strip(), f"quick_reference.{k} 须为非空文字")
    require(r["category"] in QM.GAME_CATEGORIES, f"category 须为 {QM.GAME_CATEGORIES}")
    require(isinstance(r["task"], str) and QM.TASK_TYPE_RE.fullmatch(r["task"]),
            "task 须为小写英文任务类型(字母开头,可含数字与下划线,如 map、tier_list)")
    require(is_date(r["playable_at"]), "playable_at 须为日历上存在的 YYYY-MM-DD")
    require(_num(r["anchor_volume"]) and r["anchor_volume"] > 0, "anchor_volume 须为正数")
    require(r["anchor_source"] in ("lexicon", "semrush"), "anchor_source 须为 lexicon/semrush")
    require(r["object_window"] == QM.reference_object_window(r["playable_at"]),
            f"object_window 须为开玩日前第 {a['reference_object_window'][0]} 天到第 {a['reference_object_window'][1]} 天"
            f"(应为 {QM.reference_object_window(r['playable_at'])})")
    tw = r["task_window"]
    require(isinstance(tw, list) and len(tw) == 2 and all(is_date(d) for d in tw), "task_window 须为 [起, 止] 两个日期")
    start, end, play = date.fromisoformat(tw[0]), date.fromisoformat(tw[1]), date.fromisoformat(r["playable_at"])
    days, span = a["reference_task_days"], a["reference_task_span"]
    require((end - start).days == days - 1, f"task_window 须恰好 {days} 天(起止相差 {days - 1} 天)")
    require(start >= play, "task_window 的起点不能早于开玩日")
    require(end <= play + timedelta(days=span - 1), f"task_window 的终点须在开玩后 {span} 天内")
    require(end < date.fromisoformat(observed_at[:10]), "task_window 的终点须早于观察日(窗口里的曲线要已经走完)")
    require(_num(r["object_ratio"]) and r["object_ratio"] > 0, "object_ratio 须为正数(对象名开玩前读不出就不能做参照)")
    require(_num(r["task_ratio"]), "task_ratio 须为非负数")
    for vol, ratio in (("object_volume_pre", "object_ratio"), ("task_volume_post", "task_ratio")):
        require(_num(r[vol]), f"{vol} 须为非负数")
        want = r["anchor_volume"] * r[ratio]
        require(abs(r[vol] - want) <= 1, f"{vol} 须等于 anchor_volume × {ratio}(取整,应为约 {round(want)})")
    require(r["object_volume_pre"] > 0, "object_volume_pre 须为正数(r 要拿它做分母)")
    expect = round(r["task_volume_post"] / r["object_volume_pre"], 4)
    require(_num(r["r"]) and abs(r["r"] - expect) < 1e-9, f"r 须等于 task_volume_post ÷ object_volume_pre(4 位小数,应为 {expect})")
    require(isinstance(r["full_60_days"], bool), "full_60_days 须为布尔")
    if r["full_60_days"]:
        require(date.fromisoformat(observed_at[:10]) >= play + timedelta(days=span),
                f"full_60_days 为 true 须观察日 ≥ 开玩日 + {span} 天(不到就写 false)")


def _check_forecast_task(t):
    """预判里一项任务的倍数:参照条数够数、引用的路径与条数对得上、下四分位不超过中位数。"""
    a = QM.QUICK_ASSUMPTIONS
    name = t["task"]
    n, refs = t.get("references"), t.get("reference_refs")
    require(isinstance(n, int) and not isinstance(n, bool) and n >= a["min_references"],
            f"{name}: references 须为整数且 ≥ {a['min_references']}(参照不足不能预判)")
    require(isinstance(refs, list) and len(refs) == n and all(isinstance(x, str) and x.startswith("证据/") for x in refs),
            f"{name}: reference_refs 须为 {n} 个 证据/ 下的参照观察路径,与 references 条数一致")
    require(len(set(refs)) == len(refs), f"{name}: reference_refs 有重复的路径,同一条参照不能算两次")
    require(_num(t.get("r_p25")) and _num(t.get("r_median")) and t["r_p25"] <= t["r_median"],
            f"{name}: r_p25、r_median 须为非负数且 r_p25 ≤ r_median")
    require(t.get("scope") in ("category", "task_type"), f"{name}: scope 须为 category(同类别)或 task_type(退到全部类别)")


def _check_forecast_numbers(r):
    """六条都过时的数:对象名量、跳过的国家、每项任务的倍数、合计与建议都要对得上。"""
    pre, tasks = r["object_volume_pre"], r["tasks"]
    require(isinstance(pre, dict) and pre and set(pre) <= set(EN_COUNTRIES) and all(_num(v) for v in pre.values()),
            f"object_volume_pre 须为英文区 {EN_COUNTRIES} 里读得出的国家 → 开玩前月搜索量(非负数)")
    require(pre.get("US", 0) > 0, "object_volume_pre 里美国须 > 0(参照的倍数按美国测,美国读不出就不能预判)")
    require(isinstance(r["object_volume_ref"], str) and r["object_volume_ref"].startswith("证据/"),
            "六条都过时 object_volume_ref 须为对象名量级观察 quick_volume 的路径(证据/ 下)")
    skipped = r["skipped_geos"]
    require(isinstance(skipped, list) and len(set(skipped)) == len(skipped) and set(skipped) <= set(EN_COUNTRIES)
            and "US" not in skipped and not set(skipped) & set(pre),
            "skipped_geos 须为英文区里没查的国家:不含美国、不重复、不与 object_volume_pre 的国家重叠")
    for t in tasks:
        _check_forecast_task(t)
    p25, median = QM.forecast_totals(pre, tasks)
    require((r["forecast_p25"], r["forecast_median"]) == (p25, median),
            f"forecast_p25、forecast_median 须等于对象名量 × 各任务倍数之和(取整,应为 {p25}、{median})")
    want = QM.forecast_suggestion(p25, median, complete=not skipped)
    require(r["suggestion"] == want, f"suggestion 须为 {want}(按下四分位 {p25}、中位数 {median}、"
                                     f"{'已测全部国家' if not skipped else '只测了部分国家'}算出)")


def _check_quick_forecast(r, observed_at):
    """上线前预判:对象名开玩前的量 × 参照库倍数,一款游戏一个站,按 1–4 项任务合计;六条没有全过时只记观察、建议 skip。"""
    a = QM.QUICK_ASSUMPTIONS
    require(isinstance(r["object"], str) and r["object"].strip(), "quick_forecast.object 须为非空文字")
    _check_null_rule(r["checks"], FORECAST_CHECKS, r["object"])
    require(r["category"] in QM.GAME_CATEGORIES, f"category 须为 {QM.GAME_CATEGORIES}")
    require(is_date(r["playable_at"]), "playable_at 须为日历上存在的 YYYY-MM-DD")
    require(isinstance(r["date_source"], str) and r["date_source"].strip(), "date_source 须为非空文字(开玩日从哪读的)")
    verdicts = {k: r["checks"][k]["pass"] for k in FORECAST_CHECKS}
    if verdicts["P1"] is True:
        lo, hi = a["forecast_days"]
        lead = (date.fromisoformat(r["playable_at"]) - datetime.fromisoformat(observed_at).date()).days
        require(lo <= lead <= hi, f"P1 判通过须开玩日在观察日之后 {lo}–{hi} 天(现为 {lead} 天)")
    tasks = r["tasks"]
    require(isinstance(tasks, list) and 1 <= len(tasks) <= 4, "tasks 须为 1–4 项(一款游戏一个站,最小版本要做的任务)")
    for t in tasks:
        require(isinstance(t, dict) and isinstance(t.get("task"), str) and QM.TASK_TYPE_RE.fullmatch(t["task"]),
                "tasks[].task 须为小写英文任务类型(字母开头,可含数字与下划线,如 map、tier_list)")
        require(isinstance(t.get("terms"), list) and t["terms"] and all(isinstance(x, str) and x.strip() for x in t["terms"]),
                f"{t['task']}: terms 须为非空的文字列表(归到这项任务的说法)")
    names = [t["task"] for t in tasks]
    require(len(set(names)) == len(names), "tasks 里任务类型不能重复")
    serp = r["serp"]
    require(isinstance(serp, list) and all(isinstance(s, dict) and isinstance(s.get("query"), str) and s["query"].strip()
                                           and isinstance(s.get("top10"), list) for s in serp),
            "serp 须为列表,每项含 query 与 top10 列表(两次首页的前 10)")
    if verdicts["P5"] is not None:
        require(len(serp) >= 2 and any(s["query"].strip().lower().endswith(" wiki") for s in serp),
                "P5 有结论时 serp 至少两条(<游戏名> <任务词> 与 <游戏名> wiki),其中一条查询以 \" wiki\" 结尾")
    require(r["suggestion"] in ("go", "watching", "skip", "measure_rest"), "suggestion 须为 go/watching/skip/measure_rest")
    if all(v is True for v in verdicts.values()):
        _check_forecast_numbers(r)
    else:
        require(r["suggestion"] == "skip", "六条里有不过项时 suggestion 须为 skip(只记观察,不预判)")


def _expected_stage(kind):
    return "scan" if kind == "scan" else ("quick" if kind in QUICK_KINDS else "assess")


def _preflight_ok(pf):
    pf = pf or {}
    return (all(pf.get(k) is True for k in ("controllable", "desktop", "logged_out")) and pf.get("region") == "us"
            and isinstance(pf.get("evidence"), str) and bool(pf["evidence"].strip()))


def validate(obs: dict) -> None:
    kind, stage = obs.get("kind"), obs.get("stage")
    require(kind in KINDS, f"kind 须为 {KINDS}")
    require(stage == _expected_stage(kind), "kind=scan 时 stage=scan;快道各类 stage=quick;其余 stage=assess")
    if kind in ("scan", "quick_signal", "quick_reference"):
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
    if kind in ("scan", "quick_reference", "quick_forecast"):
        globals()[f"_check_{kind}"](r, obs["observed_at"])
    else:
        globals()[f"_check_{kind}"](r)
    if kind == "quick_screen" and (r["checks"]["Q5"]["pass"] is not None or r["checks"]["Q6"]["pass"] is not None):
        require(_preflight_ok(obs.get("browser_preflight")), "Q5/Q6 有结论时须有通过的 browser_preflight")
    if kind == "quick_forecast" and r["checks"]["P5"]["pass"] is not None:
        require(_preflight_ok(obs.get("browser_preflight")), "P5 有结论时须有通过的 browser_preflight")


def write(root, obs: dict) -> str:
    validate(obs)
    folder = {"scan": "_scan", "quick_signal": "_quick", "quick_reference": "_quick"}.get(obs["kind"], obs["slug"])
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
