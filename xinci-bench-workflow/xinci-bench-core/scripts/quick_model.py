#!/usr/bin/env python3
"""新词快道测算:锚词换算、趋势判断、上线 90 天内单月访问三档。纯函数 + CLI。

当前月搜索量 = 英文区 6 国各自按 Trends 锚词换算后相加(读不出的国家记 0)。
预计月访问 = floor(当前月搜索量 × 首发份额 × AI 概览系数);按当前量,不外推增长。
收入按国家分:美国访问 × 美国每千访问收入 + 其他英文国家访问 × 其他每千访问收入。
假设表只由用户改(改时升版本)。
"""
import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import data_root
from _common import BenchError, load_json, load_ledger, require

QUICK_ASSUMPTIONS = {
    "version": "2026-10-14.q2",
    "countries": ("US", "GB", "CA", "AU", "NZ", "IE"),     # 英文区:美、英、加、澳、新、爱
    "share": {"low": 0.10, "base": 0.20, "high": 0.30},
    "aio_factor": 0.6,
    "threshold_visits": 10000,                            # 英文区合计
    "single_site_revenue": 100.0,
    "rpm_adsense": 4.0,                                   # 美国
    "rpm_other_en": 2.0,                                  # 美国以外的英文国家
    "new_days": 90,
    "watch_days": 30,
    "oneoff_ratio": 0.3,
    "trend_floor": 0.8,
    "anchor_ratio": (0.2, 5.0),
    "anchor_fresh_days": 90,
    "pool_days": 7,
    "max_serp_per_run": 10,
    "launch_days": 7,
    "milestones": (14, 30, 90),
    "stop_ratio": 0.25,
}
TASK_WORDS = ("calculator", "codes", "tracker", "tier list", "map", "checker", "generator",
              "converter", "build", "value")
SCENARIOS = ("low", "base", "high")


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def ratio_ok(ratio, a=QUICK_ASSUMPTIONS) -> bool:
    lo, hi = a["anchor_ratio"]
    return lo <= ratio <= hi


def anchor_estimate(anchor_volume, new_series, anchor_series, window=7) -> dict:
    """同一次 Trends 查询里的两条曲线 → 新词当前月搜索量。窗口取序列末尾 window 个点。"""
    require(anchor_volume > 0, "锚词月搜索量须为正数")
    require(len(new_series) == len(anchor_series) and len(new_series) >= window,
            "两条曲线须等长且不短于窗口")
    new_mean, anchor_mean = _mean(new_series[-window:]), _mean(anchor_series[-window:])
    require(anchor_mean > 0, "锚词在窗口内热度为 0,换一个锚词")
    ratio = new_mean / anchor_mean
    return {"new_mean": round(new_mean, 4), "anchor_mean": round(anchor_mean, 4),
            "ratio": round(ratio, 4), "estimate": round(anchor_volume * ratio),
            "ratio_ok": ratio_ok(ratio)}


def trend(series, a=QUICK_ASSUMPTIONS) -> dict:
    """最近 7 天 vs 前 7 天看趋势;最近 7 天 vs 近 30 天峰值看冲高回落。"""
    require(len(series) >= 14, "曲线至少要 14 个点")
    last7, prev7, peak = _mean(series[-7:]), _mean(series[-14:-7]), max(series)
    non_declining = last7 > 0 and (prev7 == 0 or last7 >= a["trend_floor"] * prev7)
    spike_decay = peak > 0 and last7 < a["oneoff_ratio"] * peak
    return {"last7": round(last7, 2), "prev7": round(prev7, 2), "peak30": peak,
            "non_declining": non_declining, "spike_decay": spike_decay}


def aio_factor(serp, a=QUICK_ASSUMPTIONS) -> float:
    return a["aio_factor"] if serp.get("aio_present") and not serp.get("aio_completes") else 1.0


def searches_needed(factor, a=QUICK_ASSUMPTIONS) -> int:
    return math.ceil(a["threshold_visits"] / (a["share"]["base"] * factor))


def compute(record: dict, a=QUICK_ASSUMPTIONS) -> dict:
    """record 须有 volume(estimate_7d、by_geo、trend)与 serp(aio_present、aio_completes)。"""
    vol, serp = record.get("volume") or {}, record.get("serp") or {}
    require(isinstance(vol.get("estimate_7d"), (int, float)) and vol["estimate_7d"] >= 0, "缺当前月搜索量 estimate_7d")
    by_geo = vol.get("by_geo")
    require(isinstance(by_geo, dict) and by_geo and set(by_geo) <= set(a["countries"])
            and all(isinstance(x, (int, float)) and x >= 0 for x in by_geo.values())
            and sum(by_geo.values()) == vol["estimate_7d"],
            f"by_geo 须只含英文区 {a['countries']} 且合计等于 estimate_7d")
    require("aio_present" in serp, "缺首屏读数 serp.aio_present")
    require(not serp.get("aio_completes"), "AI 概览已答完,不能测算(应按 answered 否决)")
    factor = aio_factor(serp, a)
    total, us = vol["estimate_7d"], by_geo.get("US", 0)
    scenarios, raw = {}, {}
    for s in SCENARIOS:
        v = math.floor(total * a["share"][s] * factor)
        us_v = v * us // total if total else 0          # 访问按各国搜索量的比例分
        raw[s] = (us_v * a["rpm_adsense"] + (v - us_v) * a["rpm_other_en"]) / 1000
        scenarios[s] = {"share": a["share"][s], "visits": v, "us_visits": us_v, "revenue": round(raw[s], 2)}
    base = scenarios["base"]["visits"]
    tr = vol.get("trend") or {}
    passes = base >= a["threshold_visits"]
    if tr.get("spike_decay"):
        suggestion = "rejected:oneoff"
    elif passes:
        suggestion = "go"
    elif tr.get("non_declining"):
        suggestion = "watching"
    else:
        suggestion = "rejected:volume"
    return {"assumptions_version": a["version"], "searches": total, "us_share": round(us / total, 4) if total else 0.0,
            "aio_factor": factor, "scenarios": scenarios, "passes": passes,
            "single_site_100": raw["base"] >= a["single_site_revenue"],     # 用四舍五入前的收入判
            "threshold_visits": a["threshold_visits"], "searches_needed": searches_needed(factor, a),
            "suggestion": suggestion}


def add_days(day: str, n: int) -> str:
    return (date.fromisoformat(day[:10]) + timedelta(days=n)).isoformat()


def milestones(launched_at: str, a=QUICK_ASSUMPTIONS) -> list:
    return [{"day": d, "date": add_days(launched_at, d)} for d in a["milestones"]]


def stop_line(model: dict, a=QUICK_ASSUMPTIONS) -> int:
    return math.floor(model["scenarios"]["base"]["visits"] * a["stop_ratio"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--direction", help="读账本里该快道方向")
    g.add_argument("--input", help="读一个方向记录 JSON 文件")
    a = ap.parse_args(argv)
    try:
        if a.direction:
            rec = load_ledger(data_root.resolve_or_exit(a.data_root))["directions"].get(a.direction)
            require(rec and rec.get("lane") == "quick", f"账本里没有快道方向 {a.direction}")
        else:
            rec = load_json(Path(a.input))
        print(json.dumps(compute(rec), ensure_ascii=False, indent=2))
    except (BenchError, OSError, ValueError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
