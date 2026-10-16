#!/usr/bin/env python3
"""新词快道测算:锚词换算、趋势判断、上线 90 天内单月访问三档。纯函数 + CLI。

当前月搜索量 = 英文区 6 国各自按 Trends 锚词换算后相加(读不出的国家记 0)。
预计月访问 = floor(当前月搜索量 × 首发份额 × AI 概览系数);按当前量,不外推增长。
收入按国家分:美国访问 × 美国每千访问收入 + 其他英文国家访问 × 其他每千访问收入。
假设表只由用户改(改时升版本)。

上线前预判(forecast):对象名开玩前月搜索量 × 参照库倍数(任务词 ÷ 对象名),按一款游戏一个站
把 1–4 项任务相加;下四分位倍数过线判 go,仅中位数过线进观察。预判一律按 AI 概览系数处理。
"""
import argparse
import json
import math
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import data_root
from _common import EN_COUNTRIES, BenchError, load_json, load_ledger, require

QUICK_ASSUMPTIONS = {
    "version": "2026-10-16.q4",
    "countries": EN_COUNTRIES,                            # 英文区:美、英、加、澳、新、爱
    "share": {"low": 0.10, "base": 0.20, "high": 0.30},
    "aio_factor": 0.6,
    "threshold_visits": 10000,                            # 英文区合计
    "single_site_revenue": 100.0,
    "rpm_adsense": 4.0,                                   # 美国
    "rpm_other_en": 2.0,                                  # 美国以外的英文国家
    "new_days": 90,
    "new_days_game": 14,                                  # 游戏类:开放游玩后 14 天内
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
    # 上线前预判(q4)
    "forecast_days": (3, 21),                             # 开玩日在今天之后 3–21 天才预判
    "forecast_per_run": 2,                                # 每轮最多预判 2 个对象
    "min_references": 3,                                  # 倍数至少要 3 条同类参照
    "forecast_launch_lead": 1,                            # 预判 go 的建议最晚上线日 = 开玩日前 1 天
    "review_days": 7,                                     # 复核日 = 开玩日 + 7 天
    "review_stop_ratio": 0.25,                            # 复核时实测 < 预测 × 25% 提示止损
    "us_only_cutoff": 0.5,                                # 美国单国中位数基准 < 门槛 × 50% 就不测其他 5 国
    "reference_object_window": (9, 3),                    # 参照里对象名窗口:开玩日前第 9 到第 3 天
    "reference_task_days": 14,                            # 参照里任务词窗口长 14 天
    "reference_task_span": 60,                            # 在开玩后 60 天内找最高的连续 14 天
    "forecast_slip_days": 7,                              # 开玩日累计推迟超过 7 天,看板提醒重新评估
}
TASK_WORDS = ("calculator", "codes", "tracker", "tier list", "map", "checker", "generator",
              "converter", "build", "value")
SCENARIOS = ("low", "base", "high")
GAME_CATEGORIES = ("open_world_survival", "mmo_gacha", "metroidvania_adventure", "sports_racing_party", "roblox")
TASK_TYPE_RE = re.compile(r"[a-z][a-z0-9_]*")             # 任务类型,如 map、tier_list


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


def _scenarios(total, us, factor, a, pool=None) -> tuple:
    """搜索量 total → 三档情景的访问、美国访问、收入。us 是 pool 里美国的量,访问按 us/pool 分(pool 缺省取 total)。
    返回 (scenarios, raw);raw 是四舍五入前的收入,用来判"单站 $100"。"""
    pool = total if pool is None else pool
    scenarios, raw = {}, {}
    for s in SCENARIOS:
        v = math.floor(total * a["share"][s] * factor)
        us_v = v * us // pool if pool else 0            # 访问按各国搜索量的比例分
        raw[s] = (us_v * a["rpm_adsense"] + (v - us_v) * a["rpm_other_en"]) / 1000
        scenarios[s] = {"share": a["share"][s], "visits": v, "us_visits": us_v, "revenue": round(raw[s], 2)}
    return scenarios, raw


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
    scenarios, raw = _scenarios(total, us, factor, a)
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


def reference_object_window(playable_at: str, a=QUICK_ASSUMPTIONS) -> list:
    """参照里对象名的窗口:开玩日前第 9 天到第 3 天(预判最晚也在这之前取到对象名的量)。"""
    far, near = a["reference_object_window"]
    return [add_days(playable_at, -far), add_days(playable_at, -near)]


def forecast_dates(playable_at: str, a=QUICK_ASSUMPTIONS) -> dict:
    return {"launch_by": add_days(playable_at, -a["forecast_launch_lead"]),
            "review_at": add_days(playable_at, a["review_days"])}


def forecast_totals(by_geo: dict, tasks: list) -> tuple:
    """站点预测月搜索量:对象名量 O 按任务逐项乘倍数再相加,各取整 → (下四分位, 中位数)。"""
    o = sum(by_geo.values())
    return (round(sum(o * t["r_p25"] for t in tasks)), round(sum(o * t["r_median"] for t in tasks)))


def forecast_suggestion(forecast_p25: int, forecast_median: int, complete: bool, a=QUICK_ASSUMPTIONS) -> str:
    """complete=False 表示只测了美国:中位数基准不到门槛 × 50% 就不再测其他 5 国。"""
    def base(f):
        return math.floor(f * a["share"]["base"] * a["aio_factor"])
    if not complete:
        return "skip" if base(forecast_median) < a["threshold_visits"] * a["us_only_cutoff"] else "measure_rest"
    if base(forecast_p25) >= a["threshold_visits"]:
        return "go"
    return "watching" if base(forecast_median) >= a["threshold_visits"] else "skip"


def forecast(by_geo: dict, tasks: list, a=QUICK_ASSUMPTIONS, complete=True) -> dict:
    """上线前预判。by_geo 是对象名开玩前月搜索量(英文区各国);tasks 是最小版本要做的 1–4 项任务,
    每项带 r_p25、r_median(参照库倍数)。访问、收入、过线都从取整后的合计算,和观察校验同一口径。"""
    require(isinstance(by_geo, dict) and by_geo and set(by_geo) <= set(a["countries"])
            and all(isinstance(x, (int, float)) and x >= 0 for x in by_geo.values()),
            f"对象名月量 by_geo 须只含英文区 {a['countries']},且不为负")
    require(isinstance(tasks, list) and 1 <= len(tasks) <= 4, "预判任务须 1–4 项")
    for t in tasks:
        require(isinstance(t, dict) and all(isinstance(t.get(k), (int, float)) and t[k] >= 0 for k in ("r_p25", "r_median"))
                and t["r_p25"] <= t["r_median"], "每项任务的倍数须非负,且 r_p25 ≤ r_median")
    f25, f50 = forecast_totals(by_geo, tasks)
    factor, o, us = a["aio_factor"], sum(by_geo.values()), by_geo.get("US", 0)
    scenarios, raw = _scenarios(f25, us, factor, a, pool=o)       # 收入按 by_geo 里美国的比例分
    median_scenarios, _ = _scenarios(f50, us, factor, a, pool=o)
    return {"basis": "forecast", "assumptions_version": a["version"], "object_volume": o,
            "us_share": round(us / o, 4) if o else 0.0, "aio_factor": factor,
            "forecast_p25": f25, "forecast_median": f50,
            "scenarios": scenarios, "median_scenarios": median_scenarios,
            "passes": scenarios["base"]["visits"] >= a["threshold_visits"],
            "passes_median": median_scenarios["base"]["visits"] >= a["threshold_visits"],
            "single_site_100": raw["base"] >= a["single_site_revenue"],     # 用四舍五入前的收入判
            "threshold_visits": a["threshold_visits"], "searches_needed": searches_needed(factor, a),
            "complete": complete, "suggestion": forecast_suggestion(f25, f50, complete, a)}


def recompute(rec: dict, a=QUICK_ASSUMPTIONS) -> dict:
    """按记录里模型的口径重算:预判方向走 forecast,现行方向(不写 basis)走 compute。"""
    if (rec.get("model") or {}).get("basis") == "forecast":
        f = rec["forecast"]
        return forecast(f["object_volume_pre"], f["tasks"], a, complete=True)
    return compute(rec, a)


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
