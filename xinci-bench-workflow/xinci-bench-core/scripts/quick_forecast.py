#!/usr/bin/env python3
"""快道上线前预判:把"对象名开玩前的量"和"参照库倍数"算成 quick_forecast 观察,不再手算。

预测 = 对象名开玩前月搜索量 O × 各项任务的参照倍数,一款游戏一个站,1–4 项任务相加;下四分位倍数判 go,
仅中位数过线进观察(见 quick_model.forecast)。倍数由本脚本从参照库(证据/_quick/ 下的 quick_reference)里取,
r_p25、r_median、references、reference_refs、scope 原样来自 quick_reference.rates,不手填、不挑选。

输入 JSON(--input):
  slug、object、category、playable_at、date_source:提议的方向名、对象名、游戏类别、开玩日及其出处;
  object_volume_ref:对象名量级观察(quick_volume,须是本方向的、term 就是对象名,在预判当天或之前 2 天内测)的路径,
    前面有不过项没测时填 null;
  tasks:[{task, terms}],最小版本要做的 1–4 项任务与归到它的说法;
  checks:P1、P2、P4、P5、P6 的 {pass, basis}(P3 由本脚本按参照库算;自己写了 P3 不过则照记,写通过不算数);
  serp:P5 看的两次美国首页 [{query, top10}],其中一次是"<游戏名> wiki";source_urls;
  可选 browser_preflight(P5 有结论时必填)、semrush_calls。

六条没有全过时,数值字段(对象名量、合计、各任务倍数)置 null,suggestion 记 skip,只留观察。
参照库里有读不出、校验不过的参照时跳过它照常算,跳过了哪些写进观察的 points 与输出的"参照不可用"。
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import data_root
import quick_model as QM
import quick_pool
import quick_reference as QR
import trends_volume as TV
import write_observation as W
from _common import EN_COUNTRIES, SLUG_RE, BenchError, load_json, now, require

PAYLOAD_KEYS = ("slug", "object", "category", "playable_at", "date_source", "object_volume_ref", "tasks", "checks",
                "serp", "source_urls")
INPUT_CHECKS = ("P1", "P2", "P4", "P5", "P6")                 # 执行者判;P3 由脚本按参照库算
RATE_KEYS = ("r_p25", "r_median", "references", "reference_refs", "scope")


def _object_volume(root, ref, slug, obj, at) -> tuple:
    """读对象名量级观察 → (读得出的国家 → 开玩前月搜索量, 没查的国家)。须是本方向的 quick_volume,term 就是对象名,
    且在预判观察时间 at 当天或之前 forecast_volume_max_lag_days 天内测。"""
    vol = W.read(root, ref)
    require(vol["kind"] == "quick_volume", f"{ref} 不是量级观察(kind={vol['kind']}),须是 quick_volume")
    require(vol["slug"] == slug, f"{ref} 属于方向 {vol['slug']},不是 {slug}(量级观察的 slug 须和预判一致)")
    term = vol["readings"].get("term")
    require(isinstance(term, str) and term.strip(),
            f"{ref} 没记 term:对象名的量须用 trends_volume.py --term 记下测的是哪个词")
    require(quick_pool.normalize_term(term) == quick_pool.normalize_term(obj),
            f"{ref} 的 term 是 {term!r},不是对象名 {obj!r}(任务词的量不能当对象名的量用)")
    QM.check_object_volume_lag(ref, vol["observed_at"], at)
    rows = vol["readings"]["countries"]
    pre = {c["geo"]: c["estimate_7d"] for c in rows if c["readable"]}
    cut = {c["geo"] for c in rows if not c["readable"] and c["basis"].startswith(TV.SKIPPED_PREFIX)}
    return pre, [g for g in EN_COUNTRIES if g in cut]


def _task_rates(root, category, tasks, unusable) -> list:
    """逐项任务从参照库取倍数(QR.rates,原样用);参照不足的任务记 None。参照库里校验不过的跳过,记进 unusable。"""
    library = QR.load_library(root, unusable)
    return [QR.rates(library, t["task"], category) for t in tasks]


def _p3(category, tasks, rates) -> dict:
    a = QM.QUICK_ASSUMPTIONS
    short = [t["task"] for t, got in zip(tasks, rates) if got is None]
    if short:
        return {"pass": False, "basis": f"参照不足:{'、'.join(short)} 同类型参照不到 {a['min_references']} 条"}
    scope_cn = {"category": f"同类别 {category}", "task_type": "同类别不足,取全部类别"}
    return {"pass": True, "basis": ";".join(
        f"{t['task']} 参照 {got['references']} 条({scope_cn[got['scope']]}),下四分位 {got['r_p25']}、中位数 {got['r_median']}"
        for t, got in zip(tasks, rates))}


def _points(readings) -> list:
    r, pre, skipped = readings, readings["object_volume_pre"], readings["skipped_geos"]
    if pre is None:
        fails = [f"{k} 不过:{c.get('basis')}" for k, c in r["checks"].items() if isinstance(c, dict) and c.get("pass") is False]
        return [f"对象名 {r['object']}:六条没有全过,只记观察,不预判"] + fails
    lines = [f"对象名 {r['object']} 开玩前月搜索量 {sum(pre.values()):,}(" + "、".join(f"{g} {v:,}" for g, v in pre.items()) + ")"]
    if skipped:
        lines.append(f"{'、'.join(skipped)} 没查,只按已测的国家预判")
    lines += [f"任务 {t['task']}:倍数下四分位 {t['r_p25']}、中位数 {t['r_median']}(参照 {t['references']} 条,{t['scope']})"
              for t in r["tasks"]]
    lines.append(f"站点预测月搜索量 下四分位 {r['forecast_p25']:,}、中位数 {r['forecast_median']:,};建议 {r['suggestion']}")
    return lines


def build_observation(root, payload: dict, at: str | None = None, unusable: list | None = None) -> dict:
    """预判输入 → quick_forecast 观察;量级观察不是本方向对象名的、任务不合规、数不对都拒收。
    参照库里读不出、校验不过的参照跳过不用,写进观察的 points;给了 unusable 列表时也记进去({"ref", "reason"})。"""
    unusable = [] if unusable is None else unusable
    require(isinstance(payload, dict), "payload 须为 JSON 对象")
    missing = [k for k in PAYLOAD_KEYS if k not in payload]
    require(not missing, f"payload 缺字段: {missing}(object_volume_ref 可以是 null,但键要写)")
    slug, obj, category, ref = payload["slug"], payload["object"], payload["category"], payload["object_volume_ref"]
    require(isinstance(slug, str) and SLUG_RE.fullmatch(slug), "slug 无效")
    require(isinstance(obj, str) and obj.strip(), "object 须为非空文字")
    tasks = payload["tasks"]
    require(isinstance(tasks, list) and tasks and all(isinstance(t, dict) and isinstance(t.get("task"), str) for t in tasks),
            "tasks 须为非空列表,每项 {task, terms}")
    checks_in = payload["checks"]
    require(isinstance(checks_in, dict) and set(INPUT_CHECKS) <= set(checks_in) <= set(W.FORECAST_CHECKS),
            f"checks 须含 {INPUT_CHECKS}(P3 由脚本按参照库算,可以不写)")
    require(ref is None or isinstance(ref, str), "object_volume_ref 须为路径或 null")
    at = at or now()
    pre, skipped = _object_volume(root, ref, slug, obj, at) if ref is not None else (None, [])
    rates = _task_rates(root, category, tasks, unusable)
    given = checks_in.get("P3")
    p3 = given if isinstance(given, dict) and given.get("pass") is False else _p3(category, tasks, rates)
    checks = {k: (p3 if k == "P3" else checks_in[k]) for k in W.FORECAST_CHECKS}
    all_pass = all(isinstance(c, dict) and c.get("pass") is True for c in checks.values())
    if all_pass:
        require(pre is not None, "六条都过时须给 object_volume_ref(对象名开玩前的量级观察 quick_volume)")
        out_tasks = [{"task": t["task"], "terms": t.get("terms"), **{k: got[k] for k in RATE_KEYS}}
                     for t, got in zip(tasks, rates)]
        f25, f50 = QM.forecast_totals(pre, out_tasks)
        suggestion = QM.forecast_suggestion(f25, f50, complete=not skipped)
    else:
        out_tasks = [{"task": t["task"], "terms": t.get("terms"), "r_p25": None, "r_median": None, "references": None,
                      "reference_refs": [], "scope": None} for t in tasks]
        pre, f25, f50, suggestion = None, None, None, "skip"
    readings = {"object": obj, "category": category, "playable_at": payload["playable_at"],
                "date_source": payload["date_source"], "object_volume_pre": pre, "object_volume_ref": ref,
                "skipped_geos": skipped, "tasks": out_tasks, "forecast_p25": f25, "forecast_median": f50,
                "suggestion": suggestion, "checks": checks, "serp": payload["serp"],
                "assumptions_version": QM.QUICK_ASSUMPTIONS["version"], "params": QM.forecast_params()}
    obs = {"slug": slug, "observed_at": at, "stage": "quick", "kind": "quick_forecast",
           "source_urls": payload["source_urls"], "semrush_calls": payload.get("semrush_calls", 0),
           "points": _points(readings) + [f"参照不可用,已跳过 {x['ref']}:{x['reason']}" for x in unusable],
           "readings": readings}
    if payload.get("browser_preflight") is not None:
        obs["browser_preflight"] = payload["browser_preflight"]
    W.validate(obs)
    return obs


def base_visits(readings: dict):
    """下四分位倍数下的基准预测月访问(英文区合计);没预测出来(有不过项)时 None。"""
    if readings["forecast_p25"] is None:
        return None
    return QM.forecast(readings["object_volume_pre"], readings["tasks"], complete=not readings["skipped_geos"])[
        "scenarios"]["base"]["visits"]


PERMANENT_FAILS = {"P4": "不在范围内", "P5": "首页已被占位", "P6": "AI 概览已答完"}      # 这几条不过,开玩前不会变好


def _days_between(later: str, earlier: str) -> int:
    return (date.fromisoformat(later[:10]) - date.fromisoformat(earlier[:10])).days


def reforecast_status(history: list, playable_at: str, on: str, library: list, a=QM.QUICK_ASSUMPTIONS) -> dict:
    """看板"可预判"每行的重做状态:这款游戏预判过之后,什么时候值得再预判一次(设计稿 14.1)。纯函数,不读数据区。

    history:这款游戏(按规范化后的游戏名)的预判历史,按观察时间升序,最后一条是"上次";每条
      {"observed_at": 日期, "playable_at", "suggestion", "failed": 第一个不过的检查 P1–P6 或 None, "tasks": [任务类型], "category"}。
    playable_at:原料里现在的开玩日;on:今天;library:参照库(quick_reference.load_library 的结果)。
    返回 {"reforecast": "new" 没预判过 | "due" 可以重做 | "wait" 还不到时候 | "no" 不再预判, "reason": 大白话原因}。

    判法(先到先得):没预判过 → new;已预判满 forecast_max_per_object 次(建议为 measure_rest 的不算),或上次是 go、
    watching(应已登记;还出现在这里说明没登记,原因写"先查原因")→ no;上次 P4、P5、P6 不过 → no;P1 不过 → 开玩日改了才 due;P3 不过 → 每项任务的倍数都取得到才 due,
    否则 wait;P2 不过、或六条都过但建议 skip(量不够)→ 看对象名窗口(开玩前第 9 到第 3 天):上次已在窗口里做过 no,
    今天在窗口里 due,还没到窗口 wait,窗口已过 no;上次是 measure_rest → due(补测其余国家)。
    """
    far, near = a["reference_object_window"]
    window, most = f"开玩前 {far}–{near} 天", a["forecast_max_per_object"]

    def out(state, reason):
        return {"reforecast": state, "reason": reason}

    if not history:
        return out("new", "没预判过")
    last = history[-1]
    done = sum(1 for x in history if x["suggestion"] != "measure_rest")           # measure_rest 只测了美国,不算一次完整预判
    if done >= most:
        return out("no", f"已预判 {done} 次(每款游戏最多 {most} 次),不再预判")
    if last["suggestion"] in ("go", "watching"):            # 登记会把这款游戏的原料标已用,正常不会再出现在可预判里
        return out("no", f"上次建议 {last['suggestion']},应已登记;还在可预判里说明没登记,先查原因")
    failed = last["failed"]
    if failed in PERMANENT_FAILS:
        return out("no", f"上次 {failed} 不过({PERMANENT_FAILS[failed]}),开玩后按现行路径看,不再预判")
    if failed == "P1":
        if last["playable_at"] != playable_at:
            return out("due", f"上次 P1 不过,开玩日改了(上次 {last['playable_at']},现在 {playable_at}),可以重做")
        return out("no", f"上次 P1 不过,开玩日没改(仍是 {playable_at}),不再预判")
    if failed == "P3":
        short = [t for t in last["tasks"] if QR.rates(library, t, last["category"], a) is None]
        if short:
            return out("wait", f"上次 P3 不过(参照不足),参照库里 {'、'.join(short)} 还没有够 {a['min_references']} 条的参照,补参照后再做")
        return out("due", "上次 P3 不过(参照不足),现在每项任务的参照都够了,可以重做")
    if last["suggestion"] == "measure_rest":
        return out("due", f"上次只测了美国,补测其余 {len(a['countries']) - 1} 国后重做")
    why = "美国读不出" if failed == "P2" else "量不够"                                  # 剩下的:P2 不过,或六条过了建议 skip
    ahead = _days_between(playable_at, on)
    if near <= _days_between(playable_at, last["observed_at"]) <= far:
        return out("no", f"上次{why},但已在{window}里做过({last['observed_at'][:10]}),不再预判")
    if ahead > far:
        return out("wait", f"上次{why},还没到{window},到时再做一次")
    if ahead >= near:
        return out("due", f"上次{why},现在到了{window},可以再做一次")
    return out("no", f"上次{why},现在已过{window},不再预判")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root")
    ap.add_argument("--input", required=True, help="预判输入 JSON(见上)")
    ap.add_argument("--dry-run", action="store_true", help="只打印观察,不写入")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        unusable = []
        obs = build_observation(root, load_json(Path(a.input)), unusable=unusable)
        if a.dry_run:
            out = obs                                   # 跳过的参照写在观察的 points 里
        else:
            r = obs["readings"]
            out = {"写入": W.write(root, obs), "suggestion": r["suggestion"], "forecast_p25": r["forecast_p25"],
                   "forecast_median": r["forecast_median"], "下四分位基准访问": base_visits(r), "参照不可用": unusable}
    except (BenchError, OSError, ValueError, KeyError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
