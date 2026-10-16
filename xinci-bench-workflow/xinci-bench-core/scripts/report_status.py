#!/usr/bin/env python3
"""只读看板:置顶待开建的快道 go;各状态数、待深核排序、观察中剩余天数、搁置天数、go 的文档、
到期的验收节点、即将开玩的对象与建议跑快道的日期、上线前预判的五类提醒(可预判的原料、复核到期、预判失准、
开玩日推迟、补参照)、参照库里不可用的参照、种子池与原料池余量、待复查淘汰、累计 Semrush 调用。"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import data_root
import ledger as L
import quick_model as QM
import quick_pool
import quick_reference as QR
import run_log
import seeds
import write_observation as W
from _common import BenchError, load_ledger, today

FORECAST_GLOB = "证据/*/*-quick_forecast.json"
PARKED_WARN_DAYS = 90
RUN_AFTER_PLAYABLE_DAYS = 3                       # 建议在开玩当天到第 3 天之间跑一次快道


def _last_forecasts(root) -> dict:
    """各方向文件夹里的预判观察 → {规范化对象名: {"observed_at": 日期, "suggestion": 建议}},同一对象取观察时间最新的
    (同时刻取路径靠后的);读不出、校验不过的跳过(看板不因它拒收)。"""
    latest = {}
    for p in sorted(Path(root).glob(FORECAST_GLOB)):
        try:
            obs = W.read(root, p.relative_to(root).as_posix())
            r, at = obs["readings"], L._at(obs["observed_at"])
            key = quick_pool.normalize_term(r["object"])
        except (BenchError, ValueError, KeyError, TypeError, AttributeError, OSError):
            continue
        if obs["kind"] == "quick_forecast" and (key not in latest or at >= latest[key][0]):
            latest[key] = (at, {"observed_at": obs["observed_at"][:10], "suggestion": r["suggestion"]})
    return {k: v for k, (_, v) in latest.items()}


def _forecast_window(root, on) -> list:
    """可预判的待看原料:开玩日在今天之后 forecast_days 这个范围(含两端)内的。每行带 last_forecast(上次预判的日期与建议,
    没预判过为 None):预判 skip、measure_rest 不登记也不消耗原料,不标出来每轮都会重做最近的那几个;没预判过的排前面,再按开玩日。"""
    near, far = QM.QUICK_ASSUMPTIONS["forecast_days"]
    last = _last_forecasts(root)
    rows = [{"object": r["object"], "stage": r.get("stage"), "playable_at": r["playable_at"],
             "days_ahead": (date.fromisoformat(r["playable_at"]) - date.fromisoformat(on)).days,
             "last_forecast": last.get(quick_pool.normalize_term(r["object"]))}
            for r in quick_pool.upcoming(root, on=on, days=far)]
    return sorted([w for w in rows if w["days_ahead"] >= near], key=lambda w: (w["last_forecast"] is not None, w["playable_at"]))


def _forecast_reminders(dirs, on) -> dict:
    """预判方向的三类提醒:复核到期、预判失准、开玩日推迟(都只读账本里的 forecast 块、复核与复查记录)。
    复核到期:预判 go(模型是开玩前预判,不含观察中开玩后按现行路径才判 go 的)没复核过,或预判观察中还没复查过,且到了复核日。"""
    due, warnings, slipped = [], [], []
    for s, r in dirs.items():
        f = r.get("forecast")                      # 只有预判登记的方向才有 forecast 块(开玩前结算时写入)
        if not f:
            continue
        if r["state"] == "go" and (r.get("model") or {}).get("basis") == "forecast" and f["review"] is None \
                and on >= f["review_at"]:
            due.append({"slug": s, "state": "go", "review_at": f["review_at"]})
        if r["state"] == "watching" and not r["watch"]["checks"] and on >= f["review_at"]:
            due.append({"slug": s, "state": "watching", "review_at": f["review_at"]})
        if f["review"] and f["review"]["stop"] and (r.get("follow_up") or {}).get("status") != "abandoned":
            warnings.append({"slug": s, "actual": f["review"]["actual"], "forecast_p25": f["review"]["forecast_p25"]})
        if r["state"] in ("go", "watching") and f["slipped_days"] > QM.QUICK_ASSUMPTIONS["forecast_slip_days"]:
            slipped.append({"slug": s, "first_public": r["object"]["first_public"], "slipped_days": f["slipped_days"]})
    return {"forecast_reviews_due": due, "forecast_warnings": warnings, "forecast_slipped": slipped}


def _references_due(library, dirs, on) -> list:
    """补参照提醒:有 forecast 块的方向(任何状态),开玩满 reference_task_days 天、参照库里还没有该对象该任务的,每项任务一行 add;
    参照库里 full_60_days 为假的,开玩满 reference_task_span 天后一行 update。due 是提醒到期的那天。"""
    a = QM.QUICK_ASSUMPTIONS
    have = {(quick_pool.normalize_term(x["object"]), x["task"]) for x in library}
    rows = []
    for r in dirs.values():
        f = r.get("forecast")
        if not f:
            continue
        due = QM.add_days(f["playable_at"], a["reference_task_days"])
        name = r["object"]["name"]
        for t in f["tasks"]:
            key = (quick_pool.normalize_term(name), t["task"])
            if on >= due and key not in have:
                rows.append({"object": name, "task": t["task"], "action": "add", "due": due})
    for x in library:
        due = QM.add_days(x["playable_at"], a["reference_task_span"])
        if not x["full_60_days"] and on >= due:
            rows.append({"object": x["object"], "task": x["task"], "action": "update", "due": due})
    return sorted(rows, key=lambda x: (x["due"], x["object"], x["task"]))


def _quick_status(root, dirs, on) -> dict:
    pending, launched_due, watching = [], [], []
    for s, r in dirs.items():
        if r.get("lane") != "quick":
            continue
        if r["state"] == "watching":
            left = (date.fromisoformat(r["watch"]["expires_at"]) - date.fromisoformat(on)).days
            watching.append({"slug": s, "days_left": left, "expires_at": r["watch"]["expires_at"],
                             "checks": len(r["watch"]["checks"])})
        if r["state"] != "go":
            continue
        fu, base = r["follow_up"], r["model"]["scenarios"]["base"]
        if fu["status"] == "pending":
            pending.append({"slug": s, "title": r["title"], "base_visits": base["visits"],
                            "base_revenue": base["revenue"], "launch_by": fu["launch_by"],
                            "overdue": on > fu["launch_by"], "doc": str(L.doc_paths(root, s)[0]),
                            "forecast": r["model"].get("basis") == "forecast"})
        elif fu["status"] == "launched":
            for m in QM.milestones(fu["launched_at"]):
                if m["date"] <= on:
                    launched_due.append({"slug": s, "day": m["day"], "date": m["date"]})
    unusable = []                                 # 参照库里读不出、校验不过的参照:跳过并列出,不让一条坏参照拖垮看板
    library = QR.load_library(root, unusable)
    upcoming = [{"object": r["object"], "stage": r.get("stage"), "playable_at": r["playable_at"],
                 "run_from": r["playable_at"],
                 "run_to": (date.fromisoformat(r["playable_at"]) + timedelta(days=RUN_AFTER_PLAYABLE_DAYS)).isoformat()}
                for r in quick_pool.upcoming(root, on=on)]
    return {"pending_go": pending, "watching": sorted(watching, key=lambda w: w["days_left"]),
            "milestones_due": launched_due, "pool_pending": len(quick_pool.pending(root, on=on)), "upcoming": upcoming,
            "forecast_window": _forecast_window(root, on), **_forecast_reminders(dirs, on),
            "references_due": _references_due(library, dirs, on), "references_unusable": unusable}


def status(root, on=None) -> dict:
    on = on or today()
    dirs = load_ledger(root)["directions"]
    counts = {s: sum(r["state"] == s for r in dirs.values()) for s in L.STATES}
    parked = []
    for slug, r in dirs.items():
        if r["state"] == "parked":
            days = (date.fromisoformat(on) - date.fromisoformat(r["history"][-1]["at"][:10])).days
            parked.append({"slug": slug, "days": days, "overdue": days > PARKED_WARN_DAYS,
                           "reason": r["history"][-1]["reason"]})
    go = [{"slug": s, "title": r["title"], "base_total": r["model"]["scenarios"]["base"]["total"],
           "doc": str(L.doc_paths(root, s)[0])} for s, r in dirs.items()
          if r["state"] == "go" and r.get("lane", "bench") == "bench"]
    quick = _quick_status(root, dirs, on)
    rejected = {}
    for r in dirs.values():
        if r["state"] == "rejected":
            g = r["decision"]["gate"]
            rejected[g] = rejected.get(g, 0) + 1
    rows = run_log.records(root)
    return {"data_root": str(root), "counts": counts, "quick": quick, "found_ranked": L.rank(root, on),
            "parked": parked, "go": go, "rejected_by_gate": rejected, "seeds": seeds.stats(root, on),
            "semrush_calls_total": sum(r["semrush_calls"] for r in rows), "semrush": run_log.semrush_budget(rows)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        st = status(root)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    c, q = st["counts"], st["quick"]
    for g in q["pending_go"]:
        tag = "(开玩前预判)" if g["forecast"] else ""
        print(f"【立即建站】{g['slug']}{tag}:基准约 {g['base_visits']:,} 次访问、${g['base_revenue']:.2f}/月,"
              f"建议最晚 {g['launch_by']} 上线" + ("(已超期)" if g["overdue"] else "") + f" → {g['doc']}")
    for m in q["milestones_due"]:
        print(f"  验收节点到了:{m['slug']} 上线第 {m['day']} 天({m['date']}),去看 Search Console")
    for d in q["forecast_reviews_due"]:
        print(f"  复核到期 {d['slug']}:{d['review_at']},测任务词的量后跑 ledger.py review-forecast(观察中的跑 watch-check)")
    for w in q["forecast_warnings"]:
        print(f"  预判失准 {w['slug']}:实测 {w['actual']} / 预测 {w['forecast_p25']},建议停止追加投入")
    for w in q["forecast_slipped"]:
        print(f"  开玩日推迟 {w['slug']}:累计 {w['slipped_days']} 天,现为 {w['first_public']},请重新评估")
    for x in q["references_due"]:
        print(f"  {'补参照' if x['action'] == 'add' else '更新参照'} {x['object']} {x['task']}")
    for x in q["references_unusable"]:
        print(f"  参照不可用 {x['ref']}: {x['reason']}")
    print(f"数据区:{st['data_root']}")
    print(f"方向:found {c['found']} · go {c['go']} · rejected {c['rejected']} · parked {c['parked']} · 观察中 {c['watching']}")
    for w in q["watching"]:
        print(f"  观察中 {w['slug']}:还剩 {w['days_left']} 天({w['expires_at']} 到期),已复查 {w['checks']} 次")
    for row in st["found_ranked"]:
        print(f"  待深核 {row['slug']}:起量速度 {row['speed']}/月,AS {row['authority_score']}")
    for g in st["go"]:
        print(f"  go {g['slug']}:基准 ${g['base_total']}/月 → {g['doc']}")
    for p in st["parked"]:
        print(f"  搁置 {p['slug']}:{p['days']} 天" + (" (超过 90 天,请复核)" if p["overdue"] else ""))
    if st["rejected_by_gate"]:
        print("  否决按门:" + "、".join(f"{k} {v}" for k, v in st["rejected_by_gate"].items()))
    s = st["seeds"]
    print(f"种子池待初核:{s['pending'] or '无'};已初核 {s['checked']};淘汰 {s['rejected']}(到期可复查 {s['recheck_due']})")
    print(f"快道原料池待看:{q['pool_pending']}")
    for u in q["upcoming"]:
        print(f"  即将开玩 {u['object']}" + (f"({u['stage']})" if u["stage"] else "")
              + f":{u['playable_at']},建议 {u['run_from']}~{u['run_to']} 跑一次快道")
    for w in q["forecast_window"]:
        lf = w["last_forecast"]
        print(f"  可预判 {w['object']}:{w['playable_at']},还有 {w['days_ahead']} 天"
              + (f",上次预判 {lf['observed_at']}:{lf['suggestion']}" if lf else "")
              + f"(每轮最多预判 {QM.QUICK_ASSUMPTIONS['forecast_per_run']} 个)")
    b = st["semrush"]
    print(f"今天 Semrush 已用 {b['semrush_calls_today']}/{b['semrush_daily_limit']} 次"
          + ("(到了停止线,今天别再跑 Semrush)" if b["semrush_stop"] else "") + f";累计 {st['semrush_calls_total']} 次")
    return 0


if __name__ == "__main__":
    sys.exit(main())
