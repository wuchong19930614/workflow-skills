#!/usr/bin/env python3
"""标杆份额法:第 12 个月访问与收入三档。纯函数 + CLI,假设表只由用户改(改时升版本)。

我们第 12 个月访问 = min(系数 × 标杆份额率 × 我们覆盖的需求, 上限 × 我们覆盖的需求),全部按英文区 6 国算。
广告收入按国家分:美国访问按美国每千访问收入,其他英文国家按一半;访问按我们覆盖需求里美国的占比分。
"""
import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import data_root
from _common import BenchError, load_json, load_ledger, require

ASSUMPTIONS = {
    "version": "2026-10-14.2",
    "coef": {"low": 0.25, "base": 0.5, "high": 1.0},
    "crowded_base_coef": 0.33,
    "crowded_at": 3,
    "share_cap": 0.15,
    "near_me_factor": 0.2,
    "journey_min_visits": 10000,
    "rpm": {"adsense": 4.0, "mediavine_journey": 16.0},                 # 美国
    "rpm_other_en": {"adsense": 2.0, "mediavine_journey": 8.0},         # 美国以外的英文国家,按美国的一半
    "paid_conversion": {"low": 0.001, "base": 0.002, "high": 0.005},
    "threshold": 100.0,
}
UNCONFIRMED_RPM_TYPES = ("content", "game", "mixed")
SCENARIOS = ("low", "base", "high")


class ModelError(BenchError):
    pass


def _bench_traffic(b):
    """标杆的英文区流量:起量后第 12 个月,不满 12 个月用当前值。"""
    return b["en_organic_m12"] if b.get("en_organic_m12") is not None else b["en_organic_now"]


def _bench_us_traffic(b):
    """标杆的美区流量;流量曲线是美区读数,里程碑比例要和它比。"""
    return b["us_organic_m12"] if b.get("us_organic_m12") is not None else b["us_organic_now"]


def covered_demand(clusters, a=ASSUMPTIONS, key="en_volume") -> float:
    """计入且未被首屏答完的簇量合计(默认英文区,key="volume" 为美区);near me 簇 ×0.2。"""
    return sum(c[key] * (a["near_me_factor"] if c.get("near_me") else 1)
               for c in clusters if c.get("counted") and not c.get("answered"))


def _network(visits, a):
    return "mediavine_journey" if visits >= a["journey_min_visits"] else "adsense"


def _paid_per_visit(paid, scenario, a):
    if not (paid or {}).get("applicable"):
        return 0.0
    return a["paid_conversion"][scenario] * paid["price_month"]


def _blended_rpm(net, us_share, a):
    return us_share * a["rpm"][net] + (1 - us_share) * a["rpm_other_en"][net]


def visits_needed_for_threshold(paid, us_share=1.0, a=ASSUMPTIONS) -> int:
    """基准付费转化率下,达到门槛所需的最少第 12 个月英文区访问(网络分档会跳变;美国占比越低,要的访问越多)。"""
    extra = _paid_per_visit(paid, "base", a)
    per_adsense = _blended_rpm("adsense", us_share, a) / 1000 + extra
    v = math.ceil(a["threshold"] / per_adsense)
    if v < a["journey_min_visits"]:
        return v
    per_journey = _blended_rpm("mediavine_journey", us_share, a) / 1000 + extra
    return max(math.ceil(a["threshold"] / per_journey), a["journey_min_visits"])


def compute(record: dict, a=ASSUMPTIONS) -> dict:
    clean = [b for b in record.get("benchmarks") or [] if b.get("clean") is True]
    require(clean, "没有干净标杆,不能测算")
    for b in clean:
        if not b.get("covered_demand"):
            raise ModelError(f"标杆 {b['domain']} 缺 covered_demand")
    clusters = record.get("clusters") or []
    require(clusters, "没有簇,不能测算")
    paid = record.get("paid") or {"applicable": False}
    if paid.get("applicable"):
        require(isinstance(paid.get("price_month"), (int, float)) and paid["price_month"] > 0,
                "付费适用时 price_month 须为正数")
    rates = [_bench_traffic(b) / b["covered_demand"] for b in clean]
    share = statistics.median(rates)
    covered = covered_demand(clusters, a)
    covered_us = covered_demand(clusters, a, key="volume")
    us_share = min(covered_us / covered, 1.0) if covered else 1.0
    crowding = record.get("crowding") or 1
    coefs = dict(a["coef"])
    if crowding >= a["crowded_at"]:
        coefs["base"] = a["crowded_base_coef"]
    scenarios = {}
    for s in SCENARIOS:
        visits = math.floor(min(coefs[s] * share * covered, a["share_cap"] * covered))
        net = _network(visits, a)                       # 分档按英文区合计访问
        us_visits = math.floor(visits * us_share)
        ads = round((us_visits * a["rpm"][net] + (visits - us_visits) * a["rpm_other_en"][net]) / 1000, 2)
        paid_rev = round(visits * _paid_per_visit(paid, s, a), 2)
        scenarios[s] = {"coef": coefs[s], "visits_m12": visits, "us_visits": us_visits, "network": net,
                        "ads": ads, "paid": paid_rev, "total": round(ads + paid_rev, 2)}
    unconfirmed = []
    if record.get("site_type") in UNCONFIRMED_RPM_TYPES:
        unconfirmed.append("内容类/游戏类每千访问收入(暂按工具类 $4)")
    if any(v["network"] == "mediavine_journey" for v in scenarios.values()):
        unconfirmed.append("Mediavine Journey 每千访问 $16")
    if paid.get("applicable"):
        unconfirmed.append("付费转化率 0.1%/0.2%/0.5%")
    if us_share < 1:
        unconfirmed.append("美国以外英文国家每千访问按美国的一半(AdSense $2、Journey $8)")
    needed = visits_needed_for_threshold(paid, us_share, a)
    bench_median = statistics.median(_bench_traffic(b) for b in clean)
    return {
        "assumptions_version": a["version"], "threshold": a["threshold"],
        "share_rate": round(share, 6), "covered_demand": round(covered, 2), "us_share": round(us_share, 4),
        "crowding": crowding, "ramping": any(b.get("en_organic_m12") is None for b in clean),
        "scenarios": scenarios, "passes": scenarios["base"]["total"] >= a["threshold"],
        "visits_needed_for_threshold": needed,
        "benchmark_fraction_needed": round(needed / bench_median, 2) if bench_median else None,
        "unconfirmed_assumptions": unconfirmed,
    }


def milestones(record: dict, model: dict, curve: dict) -> dict:
    """第 3/6/12 个月预期点击与止损线;标杆曲线缺的月份按线性补。"""
    clean = [b for b in record["benchmarks"] if b.get("clean") is True]
    ref = statistics.median(_bench_us_traffic(b) for b in clean)     # 曲线是美区读数,比例也按美区算
    base = model["scenarios"]["base"]["visits_m12"]
    out = {}
    for k in ("3", "6"):
        v = (curve or {}).get(k)
        frac = min(v / ref, 1.0) if (v is not None and ref) else int(k) / 12
        out[k] = {"expected_clicks": math.floor(base * frac),
                  "basis": "标杆曲线" if v is not None and ref else "线性补"}
    out["12"] = {"expected_clicks": base, "basis": "第 12 个月即基准情景"}
    out["stop_line_m6"] = math.floor(out["6"]["expected_clicks"] * 0.25)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--direction", help="读账本里该方向的记录")
    g.add_argument("--input", help="读一个方向记录 JSON 文件")
    a = ap.parse_args(argv)
    try:
        if a.direction:
            rec = load_ledger(data_root.resolve_or_exit(a.data_root))["directions"].get(a.direction)
            require(rec, f"账本里没有方向 {a.direction}")
        else:
            rec = load_json(Path(a.input))
        print(json.dumps(compute(rec), ensure_ascii=False, indent=2))
    except (BenchError, OSError, ValueError, KeyError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
