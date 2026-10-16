#!/usr/bin/env python3
"""快道参照库:已开玩的游戏里,"开玩前对象名的量"与"开玩后任务词的量"之比 r,上线前预判的倍数就从这些参照里取。

口径写死,不由执行者现挑:参照只测美国;对象名和任务词分别和同一个锚词在同一次 Trends 查询里比;
对象名取开玩日前第 9 到第 3 天,任务词取开玩后 60 天内均值最高的连续 14 天(并列取最早);
体积 = 锚词月量 × 窗口均值比,r = 任务词体积 ÷ 对象名体积。数值只读 QUICK_ASSUMPTIONS。

取数日期范围用 time-range 算(交给 xinciTrends 的 time,不改 trends_fetch.js);build 把两次查询的原样输出
(对象名 + 锚词、任务词 + 锚词)算成 quick_reference 观察并写入 证据/_quick/,经 write_observation 校验;
summary 看参照库每个任务类型 × 类别有几条、倍数多大。
"""
import argparse
import json
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import data_root
import quick_model as QM
import quick_pool
import write_observation as W
from _common import BenchError, is_date, load_json, now, require, today

LIBRARY_GLOB = "证据/_quick/*-quick_reference.json"
SCOPES = ("category", "task_type")
PAYLOAD_KEYS = ("object", "category", "task", "task_term", "playable_at", "anchor_term", "anchor_volume",
                "anchor_source", "object_series", "task_series")


def _mean(xs):
    return sum(xs) / len(xs)


def time_range(playable_at: str, on: str, a=QM.QUICK_ASSUMPTIONS) -> str:
    """取数日期范围:开玩日前 9 天到 min(开玩日 + 59 天, 取数日前一天);当天的点还没走完,不要。"""
    require(is_date(playable_at) and is_date(on), "playable_at、on 须为日历上存在的 YYYY-MM-DD")
    start = QM.reference_object_window(playable_at, a)[0]
    end = min(QM.add_days(playable_at, a["reference_task_span"] - 1), QM.add_days(on, -1))
    require(end >= start, f"取数日 {on} 太早:开玩日 {playable_at} 前后的曲线还没走出来")
    return f"{start} {end}"


def _by_day(dates, values) -> dict:
    """曲线逐日取成 {日期: [词值, 锚词值]},顺便核对形状。"""
    require(isinstance(dates, list) and isinstance(values, list) and dates and len(dates) == len(values),
            "曲线的 dates 与 values 须非空且等长")
    rows = {}
    for d, v in zip(dates, values):
        require(is_date(d), f"曲线日期无效: {d}")
        require(isinstance(v, list) and len(v) == 2
                and all(isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 for x in v),
                f"{d}: 每点须为 [词值, 锚词值] 两个非负数")
        rows[d] = v
    require(len(rows) == len(dates), "曲线日期有重复")
    return rows


def window_ratio(dates, values, start: str, end: str) -> float:
    """窗口内第一列均值 ÷ 第二列均值(四位小数);窗口里缺日期、锚词均值为 0 都拒收。"""
    require(is_date(start) and is_date(end) and start <= end, f"窗口须为 [起, 止] 两个日期: {start} {end}")
    rows = _by_day(dates, values)
    n = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    days = [QM.add_days(start, i) for i in range(n)]
    missing = [d for d in days if d not in rows]
    if missing:
        raise BenchError(f"窗口 {start}~{end} 里缺 {len(missing)} 天(如 {missing[0]}):曲线须逐日并覆盖整个窗口")
    anchor = _mean([rows[d][1] for d in days])
    require(anchor > 0, f"窗口 {start}~{end} 里锚词热度为 0,换锚词")
    return round(_mean([rows[d][0] for d in days]) / anchor, 4)


def best_task_window(dates, values, playable_at: str, a=QM.QUICK_ASSUMPTIONS) -> dict:
    """开玩日起 60 天内,第一列均值最高的连续 14 天(并列取最早)→ {"window", "ratio", "full_60_days"}。"""
    require(is_date(playable_at), f"playable_at 须为日历上存在的 YYYY-MM-DD: {playable_at}")
    rows = _by_day(dates, values)
    days = sorted(rows)
    require(all(QM.add_days(p, 1) == c for p, c in zip(days, days[1:])),
            "曲线不是逐日的(日期范围太长 Trends 会按周返回),缩短 time")
    require(days[0] <= playable_at, f"曲线须从开玩日 {playable_at} 或更早开始(现从 {days[0]} 开始),否则会漏掉开玩头几天")
    length, span = a["reference_task_days"], a["reference_task_span"]
    last = QM.add_days(playable_at, span - 1)
    post = [d for d in days if playable_at <= d <= last]
    require(len(post) >= length, f"开玩后只有 {len(post)} 天曲线,不足 {length} 天,不能做参照")
    best, best_sum = 0, None
    for i in range(len(post) - length + 1):
        s = sum(rows[d][0] for d in post[i:i + length])
        if best_sum is None or s > best_sum:                 # 严格大于:并列留最早
            best, best_sum = i, s
    start, end = post[best], post[best + length - 1]
    return {"window": [start, end], "ratio": window_ratio(dates, values, start, end), "full_60_days": days[-1] >= last}


def _check_series(s, label, term, anchor):
    require(isinstance(s, dict), f"{label}须为 xinciTrends 的原样输出")
    require(s.get("geo") == "US", f"{label}: geo 须为 US(参照只测美国)")
    require(s.get("terms") == [term, anchor],
            f"{label}: terms 须为 {[term, anchor]}(两个词分别和同一个锚词比),实际是 {s.get('terms')}")
    require(isinstance(s.get("url"), str) and s["url"], f"{label}: 缺 url")


def build_observation(payload: dict, at: str | None = None) -> dict:
    """两次 Trends 查询的原样输出 → quick_reference 观察;对象名开玩前读不出、曲线不够长都拒收。"""
    require(isinstance(payload, dict), "payload 须为 JSON 对象")
    missing = [k for k in PAYLOAD_KEYS if k not in payload]
    require(not missing, f"payload 缺字段: {missing}")
    a = QM.QUICK_ASSUMPTIONS
    vol, play, obj_s, task_s = payload["anchor_volume"], payload["playable_at"], payload["object_series"], payload["task_series"]
    require(isinstance(vol, (int, float)) and not isinstance(vol, bool) and vol > 0, "anchor_volume 须为正数")
    require(is_date(play), "playable_at 须为日历上存在的 YYYY-MM-DD")
    _check_series(obj_s, "对象名曲线", payload["object"], payload["anchor_term"])
    _check_series(task_s, "任务词曲线", payload["task_term"], payload["anchor_term"])
    object_window = QM.reference_object_window(play, a)
    object_ratio = window_ratio(obj_s["dates"], obj_s["values"], *object_window)
    require(object_ratio > 0, "对象名开玩前读不出,不能做参照")
    best = best_task_window(task_s["dates"], task_s["values"], play, a)
    pre, post = round(vol * object_ratio), round(vol * best["ratio"])
    require(pre > 0, "对象名按锚词月量换算后为 0,不能做参照")
    r = round(post / pre, 4)
    w = best["window"]
    points = [f"对象名 {payload['object']} 开玩前 {object_window[0]}~{object_window[1]} 比值 {object_ratio},约 {pre:,}/月",
              f"任务词 {payload['task_term']} 开玩后最高连续 {a['reference_task_days']} 天 {w[0]}~{w[1]} 比值 {best['ratio']},约 {post:,}/月",
              f"倍数 r = {r}(任务词 ÷ 对象名)" + ("" if best["full_60_days"] else ",开玩后不满 60 天,之后补测")]
    obs = {"slug": None, "observed_at": at or now(), "stage": "quick", "kind": "quick_reference",
           "source_urls": [obj_s["url"], task_s["url"]], "semrush_calls": payload.get("semrush_calls", 0), "points": points,
           "readings": {"object": payload["object"], "category": payload["category"], "task": payload["task"],
                        "task_term": payload["task_term"], "playable_at": play, "anchor_term": payload["anchor_term"],
                        "anchor_volume": vol, "anchor_source": payload["anchor_source"], "object_window": object_window,
                        "object_ratio": object_ratio, "task_window": w, "task_ratio": best["ratio"],
                        "full_60_days": best["full_60_days"], "object_volume_pre": pre, "task_volume_post": post, "r": r}}
    W.validate(obs)
    return obs


def _at(ts: str) -> datetime:
    t = datetime.fromisoformat(ts)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def load_library(root) -> list:
    """证据/_quick/ 下全部参照观察(逐条重新校验);同一(规范化对象名, 任务类型)只留观察时间最新的一条。"""
    latest = {}
    for p in sorted(Path(root).glob(LIBRARY_GLOB)):
        ref = p.relative_to(root).as_posix()
        obs = W.read(root, ref)
        item = {"ref": ref, "observed_at": obs["observed_at"], **obs["readings"]}
        key = (quick_pool.normalize_term(item["object"]), item["task"])
        if key not in latest or _at(item["observed_at"]) >= _at(latest[key]["observed_at"]):
            latest[key] = item
    return list(latest.values())


def quantiles(rs: list) -> tuple:
    """(下四分位, 中位数),四位小数;下四分位用 inclusive 法。"""
    require(rs, "没有参照,算不出分位")
    p25 = rs[0] if len(rs) == 1 else statistics.quantiles(rs, n=4, method="inclusive")[0]
    return round(p25, 4), round(statistics.median(rs), 4)


def _rates_of(rows, scope) -> dict:
    p25, median = quantiles([x["r"] for x in rows])
    return {"r_p25": p25, "r_median": median, "references": len(rows),
            "reference_refs": sorted(x["ref"] for x in rows), "scope": scope}


def rates(library: list, task: str, category: str, a=QM.QUICK_ASSUMPTIONS):
    """某任务的倍数:同任务同类别够 min_references 条用 category;不够退到同任务全部类别(task_type);再不够返回 None。"""
    same = [x for x in library if x["task"] == task]
    for scope, rows in (("category", [x for x in same if x["category"] == category]), ("task_type", same)):
        if len(rows) >= a["min_references"]:
            return _rates_of(rows, scope)
    return None


def check_refs(root, refs: list, task: str, category: str, scope: str, a=QM.QUICK_ASSUMPTIONS) -> dict:
    """用观察里引用的参照路径重算倍数,与 rates() 同结构;任何一条不合规矩都拒收。"""
    require(scope in SCOPES, f"scope 须为 {SCOPES}")
    require(isinstance(refs, list) and refs, "参照路径须为非空列表")
    rows, seen = [], set()
    for ref in refs:
        require(isinstance(ref, str), f"参照路径须为文字: {ref!r}")
        obs = W.read(root, ref)
        require(obs["kind"] == "quick_reference", f"{ref} 不是参照观察(kind={obs['kind']})")
        r = obs["readings"]
        require(r["task"] == task, f"{ref} 的任务类型是 {r['task']},要的是 {task}")
        if scope == "category":
            require(r["category"] == category, f"{ref} 的类别是 {r['category']},要的是 {category}")
        key = quick_pool.normalize_term(r["object"])
        require(key not in seen, f"参照里对象 {r['object']} 重复(同一款游戏只算一条)")
        seen.add(key)
        rows.append({"ref": ref, **r})
    require(len(rows) >= a["min_references"], f"参照只有 {len(rows)} 条,至少要 {a['min_references']} 条")
    return _rates_of(rows, scope)


def summary(library: list, task=None, category=None) -> list:
    """每个任务类型 × 类别一行:条数、下四分位、中位数。"""
    groups = {}
    for x in library:
        if (task is None or x["task"] == task) and (category is None or x["category"] == category):
            groups.setdefault((x["task"], x["category"]), []).append(x["r"])
    rows = []
    for (t, c), rs in sorted(groups.items()):
        p25, median = quantiles(rs)
        rows.append({"任务类型": t, "类别": c, "条数": len(rs), "下四分位": p25, "中位数": median})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("time-range", help="算 xinciTrends 的 time 参数(对象名与任务词两次查询都用它)")
    t.add_argument("--playable-at", required=True, help="开玩日 YYYY-MM-DD")
    t.add_argument("--on", help="取数日,默认今天(UTC)")
    b = sub.add_parser("build", help="两次 Trends 输出 → quick_reference 观察并写入")
    b.add_argument("--input", required=True, help="JSON:对象、类别、任务、开玩日、锚词与月量、两条 series(xinciTrends 原样输出)")
    b.add_argument("--dry-run", action="store_true", help="只打印观察,不写入")
    s = sub.add_parser("summary", help="参照库每个任务类型 × 类别的条数与倍数")
    s.add_argument("--task")
    s.add_argument("--category")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "time-range":
            print(time_range(a.playable_at, a.on or today()))
            return 0
        root = data_root.resolve_or_exit(a.data_root)
        if a.cmd == "summary":
            out = summary(load_library(root), a.task, a.category)
        else:
            obs = build_observation(load_json(Path(a.input)))
            if a.dry_run:
                out = obs
            else:
                r = obs["readings"]
                out = {"写入": W.write(root, obs), "r": r["r"], "任务词窗口": r["task_window"], "满 60 天": r["full_60_days"]}
    except (BenchError, OSError, ValueError, KeyError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
