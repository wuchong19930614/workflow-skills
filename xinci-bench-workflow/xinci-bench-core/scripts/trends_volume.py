#!/usr/bin/env python3
"""快道锚词换算:把 trends_fetch.js 取回的各国曲线与锚词月量换算成 quick_volume 观察,不再手算。

先只带曲线跑一次:读不出的国家自动记 0,输出里列出"读得出、要去 Semrush 查锚词月量"的国家;
补齐 anchors 再跑一次就写入观察(经 write_observation 校验)。比值不在 0.2–5 或锚词热度为 0 时拒收,换锚词重查。
"""
import argparse
import json
import sys
from pathlib import Path

import data_root
import quick_model as QM
import write_observation as W
from _common import EN_COUNTRIES, BenchError, load_json, now, require

STATUS_CN = {"ok": "可换算", "unreadable": "读不出(新词最近 7 天全为 0)", "anchor_zero": "锚词热度为 0,换锚词",
             "ratio_out_of_range": "比值不在 0.2–5,换锚词", "needs_anchor_volume": "读得出,要查锚词在该国的月量",
             "empty_curve": "读不出(Trends 返回空曲线,量太小)"}
READABLE_OR_ZERO = ("ok", "unreadable", "empty_curve")


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _check_series(s):
    geo = s.get("geo")
    require(geo in EN_COUNTRIES, f"series 的 geo 须为英文区国家 {EN_COUNTRIES}")
    require(isinstance(s.get("terms"), list) and len(s["terms"]) == 2, f"{geo}: terms 须为 [新词, 锚词]")
    vals = s.get("values")
    if vals == []:
        return                         # Trends 对量太小的词返回空曲线:按读不出处理
    require(isinstance(vals, list) and len(vals) >= 14
            and all(isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and x >= 0 for x in v)
                    for v in vals),
            f"{geo}: values 须为至少 14 个 [新词值, 锚词值]")
    require(isinstance(s.get("url"), str) and s["url"], f"{geo}: 缺 url")


def analyze(payload) -> dict:
    """逐国算均值与比值,给出状态;不写任何东西。"""
    series, skipped = payload.get("series") or [], payload.get("skipped") or {}
    anchors = payload.get("anchors") or {}
    for s in series:
        _check_series(s)
    geos = [s["geo"] for s in series] + list(skipped)
    require(sorted(geos) == sorted(EN_COUNTRIES),
            f"英文区 6 国 {EN_COUNTRIES} 每国须恰好出现一次:查了的放 series,没查的放 skipped 并写原因")
    require(len({s["terms"][0].strip().lower() for s in series}) <= 1, "各国 series 的新词(terms[0])须是同一个词")
    countries, needs = {}, []
    for s in series:
        if not s["values"]:
            countries[s["geo"]] = {"status": "empty_curve"}
            continue
        new, anc = [v[0] for v in s["values"]], [v[1] for v in s["values"]]
        n7, a7 = round(_mean(new[-7:]), 4), round(_mean(anc[-7:]), 4)
        n30, a30 = round(_mean(new[-30:]), 4), round(_mean(anc[-30:]), 4)
        c = {"new_mean_7d": n7, "anchor_mean_7d": a7, "new_mean_30d": n30, "anchor_mean_30d": a30}
        if n7 == 0:
            c["status"] = "unreadable"
        elif a7 == 0:
            c["status"] = "anchor_zero"
        elif not QM.ratio_ok(n7 / a7):
            c.update(status="ratio_out_of_range", ratio_7d=round(n7 / a7, 4))
        elif s["geo"] not in anchors:
            c.update(status="needs_anchor_volume", ratio_7d=round(n7 / a7, 4))
            needs.append(s["geo"])
        else:
            c.update(status="ok", ratio_7d=round(n7 / a7, 4))
        countries[s["geo"]] = c
    return {"countries": countries, "needs_anchor_volume": [g for g in EN_COUNTRIES if g in needs],
            "skipped": dict(skipped)}


def build_observation(payload, slug, semrush_calls=0, at=None) -> dict:
    """全部国家都是"可换算"或"读不出"时,拼出 quick_volume 观察;否则拒收并说明要做什么。"""
    res = analyze(payload)
    bad = {g: c["status"] for g, c in res["countries"].items() if c["status"] not in READABLE_OR_ZERO}
    require(not res["needs_anchor_volume"], f"这些国家读得出,先用 Semrush 查锚词在该国的锚词月量再填 anchors: {res['needs_anchor_volume']}")
    require(not bad, "换锚词重查,或把该国放进 skipped 写明原因(比值须在 0.2–5): "
                     + "、".join(f"{g} {STATUS_CN[s]}" for g, s in bad.items()))
    by_geo = {s["geo"]: s for s in payload["series"]}
    rows, points = [], []
    for g in EN_COUNTRIES:
        if g in res["skipped"]:
            rows.append({"geo": g, "readable": False, "basis": f"未查:{res['skipped'][g]}"})
            points.append(f"{g} 未查:{res['skipped'][g]}")
            continue
        c, s = res["countries"][g], by_geo[g]
        if c["status"] == "empty_curve":
            rows.append({"geo": g, "readable": False, "basis": f"Trends {s['time']},geo={g},返回空曲线(新词与锚词量都太小)"})
            points.append(f"{g} 返回空曲线,记 0")
            continue
        if c["status"] == "unreadable":
            rows.append({"geo": g, "readable": False, "basis": f"Trends {s['time']},geo={g},新词最近 7 天全为 0"})
            points.append(f"{g} 读不出,记 0")
            continue
        an = payload["anchors"][g]
        ratio = c["new_mean_7d"] / c["anchor_mean_7d"]                  # 用落盘的均值算,校验时逐位对得上
        est7 = round(an["volume"] * ratio)
        est30 = round(an["volume"] * c["new_mean_30d"] / c["anchor_mean_30d"])
        rows.append({"geo": g, "readable": True, "basis": f"Trends {s['time']},geo={g},新词与锚词同一次查询",
                     "anchor_term": s["terms"][1], "anchor_volume": an["volume"], "anchor_source": an["source"],
                     "anchor_measured_at": an["measured_at"], "new_mean_7d": c["new_mean_7d"],
                     "anchor_mean_7d": c["anchor_mean_7d"], "new_mean_30d": c["new_mean_30d"],
                     "anchor_mean_30d": c["anchor_mean_30d"], "ratio_7d": round(ratio, 4),
                     "estimate_7d": est7, "estimate_30d": est30})
        points.append(f"{g} 比值 {round(ratio, 4)},换算约 {est7:,}/月")
    readable = [r for r in rows if r["readable"]]
    require(readable, "6 国都读不出:Trends 还没有量,原料留到下次")
    top = max(readable, key=lambda r: r["estimate_7d"])["geo"]
    readings = {"window_days": 7, "countries": rows, "trend_geo": top,
                "estimate_7d": sum(r["estimate_7d"] for r in readable),
                "estimate_30d": sum(r["estimate_30d"] for r in readable),
                "series_30d": [v[0] for v in by_geo[top]["values"]][-30:]}
    return {"slug": slug, "observed_at": at or now(), "stage": "quick", "kind": "quick_volume",
            "source_urls": [s["url"] for s in payload["series"]], "semrush_calls": semrush_calls,
            "points": points, "readings": readings}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--input", required=True, help="JSON:series(各国 trends_fetch.js 输出)、anchors、skipped")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--semrush-calls", type=int, default=0, help="这份观察新花的 Semrush 调用数(查锚词月量)")
    ap.add_argument("--dry-run", action="store_true", help="只打印观察,不写入")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        payload = load_json(Path(a.input))
        res = analyze(payload)
        summary = {g: STATUS_CN[c["status"]] for g, c in res["countries"].items()}
        summary.update({g: f"未查:{why}" for g, why in res["skipped"].items()})
        if res["needs_anchor_volume"] or any(c["status"] not in READABLE_OR_ZERO for c in res["countries"].values()):
            print(json.dumps({"写入": False, "各国": summary, "要查锚词月量的国家": res["needs_anchor_volume"]},
                             ensure_ascii=False, indent=2))
            return 2
        obs = build_observation(payload, a.slug, a.semrush_calls)
        if a.dry_run:
            print(json.dumps(obs, ensure_ascii=False, indent=2))
            return 0
        ref = W.write(root, obs)
    except (BenchError, OSError, ValueError, KeyError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"写入": ref, "各国": summary, "英文区月搜索量": obs["readings"]["estimate_7d"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
