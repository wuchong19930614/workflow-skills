#!/usr/bin/env python3
"""快道决策书(go 时含"立即建站"与最小版本建站简报):账本 + 绑定观察 → 文档/<slug>.md,再生成 html。

只读绑定的观察;每节第一句是加粗的大白话结论,数字都从结构化字段派生。
开玩前按预判结算的方向(model.basis == "forecast")第一部分与"立即建站"另写一版,依据读绑定的 quick_forecast 观察。
"""
import argparse
import sys
from datetime import date
from pathlib import Path

import build_doc
import build_doc_html
import data_root
import quick_model as QM
import write_observation as W
from _common import BenchError, load_ledger, require

VERDICT_CN = {"go": "值得做（go）", "rejected": "否决", "parked": "搁置", "watching": "观察中"}
GATE_CN = {"scope": "范围排除", "not_new": "不是新的", "oneoff": "一次性或冲高回落", "occupied": "首页已有人做",
           "answered": "首屏已答完", "volume": "量不够"}
SCEN_CN = {"low": "保守", "base": "基准", "high": "乐观"}
_fmt, _money, _yn, _table = build_doc._fmt, build_doc._money, build_doc._yn, build_doc._table


def _latest(by_kind, kind):
    return by_kind[kind][-1][1]["readings"] if by_kind.get(kind) else None


def _go_block(rec, by_kind):
    m, fu, vol = rec["model"], rec["follow_up"], rec["volume"]
    base = m["scenarios"]["base"]
    brief = _latest(by_kind, "quick_brief")
    first_seen = min(t["first_seen"] for t in rec["terms"])
    lines = ["## 立即建站", "",
             f"**建议最晚 {fu['launch_by']} 上线：首页现在没人完整做这个任务，这个说法 {first_seen} 开始冒出来，"
             f"基准预计上线 90 天内单月约 {_fmt(base['visits'])} 次英文区访问（模型估算）。**", ""]
    lines += [f"- {SCEN_CN[k]}：约 {_fmt(v['visits'])} 次访问、{_money(v['revenue'])}/月" for k, v in m["scenarios"].items()]
    if m["single_site_100"]:
        lines.append("- 基准预计收入 ≥ $100/月：单站就能到 $100")
    lines.append(f"- 当前月搜索量约 {_fmt(vol['estimate_7d'])}（英文区各国 Trends 换算合计，其中美国约 "
                 f"{_fmt(vol['by_geo'].get('US', 0))}）")
    lines.append("- 最小版本要做的页面：" + "；".join(f"`{p['path']}` {p['target_query']}" for p in brief["pages"]))
    return lines + [""]


def _part_one(rec, by_kind):
    obj, vol, serp, m = rec["object"], rec.get("volume"), rec.get("serp"), rec.get("model")
    screen = _latest(by_kind, "quick_screen")
    lines = ["## 第一部分 决策", "", "### 1. 新对象与新说法", "",
             f"**{obj['name']} 首次公开于 {obj['first_public']}，冒出 {len(rec['terms'])} 个任务说法。**"
             f"日期来源：{obj['date_source']}", ""]
    lines += _table(["说法", "来源", "首次看到"], [[t["term"], t["source"], t["first_seen"]] for t in rec["terms"]])
    lines += ["", "### 2. 有人在搜", ""]
    if vol:
        geos = QM.QUICK_ASSUMPTIONS["countries"]
        lines.append(f"**当前月搜索量约 {_fmt(vol['estimate_7d'])}（英文区 {len(geos)} 国各自按 Trends 锚词换算后相加，"
                     f"其中美国约 {_fmt(vol['by_geo'].get('US', 0))}）。**")
        lines.append("")
        rows = []
        for g in geos:
            an = vol["anchors"].get(g)
            rows.append([g, an["term"], _fmt(an["volume"]), an["ratio_7d"], _fmt(vol["by_geo"][g])] if an
                        else [g, "读不出", "—", "—", "0"])
        lines += _table(["国家", "锚词", "锚词月量", "比值", "换算月搜索量"], rows)
        lines += ["", f"- 按 30 天算约 {_fmt(vol['estimate_30d'])}/月；最早的锚词测于 {vol['anchor_measured_at']}；"
                      f"趋势按 {vol['trend_geo']} 的逐日曲线判断"]
    else:
        lines += ["**本方向没有做到量级换算这一步。**", ""]
    if screen:
        lines.append(f"- Q2 依据：{screen['checks']['Q2']['basis']}")
    lines += ["", "### 3. 不是一次性", ""]
    if vol:
        tr = vol["trend"]
        lines.append(f"**最近 7 天均值 {tr['last7']}、前 7 天 {tr['prev7']}、近 30 天峰值 {tr['peak30']}："
                     f"{'趋势不降' if tr['non_declining'] else '趋势在降'}，{'是' if tr['spike_decay'] else '不是'}冲高回落。**")
    else:
        lines.append("**本方向没有曲线读数。**")
    if screen:
        lines += ["", f"- Q3 依据：{screen['checks']['Q3']['basis']}"]
    lines += ["", "### 4. 首页现场与 GEO", ""]
    if screen:
        aio = screen["ai_overview"]
        aio_cn = "不在" if not aio["present"] else ("已答完" if aio["completes_task"] else "在场但没答完")
        occ = screen["occupied_by"]
        lines.append(f"**首页前 10 条{'有页面完整做了这个任务（' + occ + '）' if occ else '没有页面完整做了这个任务'}；AI 概览{aio_cn}。**")
        lines.append("")
        lines += _table(["位置", "域名", "类型", "完整做了任务"],
                        [[r.get("pos", "—"), r.get("domain", "—"), r.get("type", "—"), _yn(r.get("completes_task"))]
                         for r in screen["top10"]])
        if aio.get("cited_domains"):
            lines.append("")
            lines.append("- AI 概览引用：" + "、".join(aio["cited_domains"]))
    else:
        lines.append("**本方向没有首屏读数。**")
    lines += ["", "### 5. 预计访问与收入", ""]
    if m:
        base = m["scenarios"]["base"]
        lines.append(f"**基准情景上线 90 天内单月约 {_fmt(base['visits'])} 次英文区访问、{_money(base['revenue'])}/月（模型估算），"
                     f"{'过' if m['passes'] else '不过'} {_fmt(m['threshold_visits'])} 访问门槛。**")
        lines.append("")
        lines += _table(["情景", "首发份额", "预计月访问", "预计月收入（AdSense）"],
                        [[SCEN_CN[k], f"{v['share']:.0%}", _fmt(v["visits"]), _money(v["revenue"])] for k, v in m["scenarios"].items()])
        a = QM.QUICK_ASSUMPTIONS
        lines += ["", f"- 其中美国访问约 {_fmt(base['us_visits'])}；收入按 AdSense 美国 ${a['rpm_adsense']:.0f}、"
                      f"其他英文国家 ${a['rpm_other_en']:.0f}/千访问估算",
                  f"- AI 概览系数 {m['aio_factor']}；基准过线需要英文区月搜索量约 {_fmt(m['searches_needed'])}",
                  f"- 假设表版本 {m['assumptions_version']}；按当前量估算，不外推增长"]
    else:
        lines.append("**本方向没有完成测算。**")
    if rec.get("watch"):
        w = rec["watch"]
        lines += ["", f"- 观察中：{w['since']} 起，{w['expires_at']} 到期；已复查 {len(w['checks'])} 次"]
    lines += ["", "### 6. 风险与最大未知", "", f"**最大的未知：{rec['decision']['biggest_unknown']}。**", ""]
    risks = list((_latest(by_kind, "quick_brief") or {}).get("risks") or [])
    risks.append("首发份额是起点假设（10/20/30%），新域名多久能排上去未确认")
    lines += [f"- {x}" for x in risks]
    return lines + [""]


def _is_forecast_doc(rec) -> bool:
    """开玩前按预判结算(go、观察中)的方向:模型是预判模型且有 forecast 块;搁置没有 forecast 块,照现行版式出。"""
    return (rec.get("model") or {}).get("basis") == "forecast" and bool(rec.get("forecast"))


def _forecast_readings(rec, by_kind) -> dict:
    """绑定的观察里 forecast.ref 指向的那份预判观察的读数(绑了几份就认账本记的那份)。"""
    ref = rec["forecast"]["ref"]
    rows = [o for r, o in by_kind.get("quick_forecast", []) if r == ref]
    require(rows, f"绑定的观察里没有账本 forecast.ref 指向的预判观察 {ref}")
    return rows[0]["readings"]


def _days(start, end) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _scope_cn(t, category) -> str:
    if t["scope"] == "category":
        return f"同类别 `{category}`"
    return f"同类别不足 {QM.QUICK_ASSUMPTIONS['min_references']} 条，取全部类别"


def _stop_line(rec) -> str:
    """复核日止损线:预测下四分位月搜索量 × 止损比例。"""
    return _fmt(rec["forecast"]["forecast_p25"] * QM.QUICK_ASSUMPTIONS["review_stop_ratio"])


def _scenario_rows(scenarios):
    return [[SCEN_CN[k], f"{v['share']:.0%}", _fmt(v["visits"]), _money(v["revenue"])] for k, v in scenarios.items()]


def _go_block_forecast(rec, by_kind):
    m, fu = rec["model"], rec["follow_up"]
    base, med = m["scenarios"]["base"], m["median_scenarios"]["base"]
    brief = _latest(by_kind, "quick_brief")
    playable = rec["object"]["first_public"]
    lead = _days(fu["launch_by"], playable)
    lines = ["## 立即建站", "",
             f"**建议最晚 {fu['launch_by']}（开玩日 {playable} 前 {lead} 天）上线：{rec['object']['name']} 开玩前首页还没人专做，"
             f"按参照库下四分位倍数预测，基准开玩后单月约 {_fmt(base['visits'])} 次英文区访问（开玩前预判，模型估算）。**", ""]
    lines += [f"- {SCEN_CN[k]}：约 {_fmt(v['visits'])} 次访问、{_money(v['revenue'])}/月" for k, v in m["scenarios"].items()]
    if m["single_site_100"]:
        lines.append("- 基准预计收入 ≥ $100/月：单站就能到 $100")
    lines.append(f"- 以上按下四分位倍数（偏保守）算；中位数倍数下基准约 {_fmt(med['visits'])} 次访问、{_money(med['revenue'])}/月")
    lines.append("- 最小版本要做的页面：" + "；".join(f"`{p['path']}` {p['target_query']}" for p in brief["pages"]))
    return lines + [""]


def _part_one_forecast(rec, by_kind):
    obj, m, f, dec = rec["object"], rec["model"], rec["forecast"], rec["decision"]
    r = _forecast_readings(rec, by_kind)
    a, checks, tasks = QM.QUICK_ASSUMPTIONS, r["checks"], r["tasks"]
    playable = obj["first_public"]
    settled = (rec.get("follow_up") or {}).get("go_at") or (rec.get("watch") or {}).get("since") or dec["decided_at"][:10]
    base, med = m["scenarios"]["base"], m["median_scenarios"]["base"]
    lines = ["## 第一部分 决策", "", "### 1. 即将开玩的游戏", "",
             f"**{obj['name']} 计划 {playable} 开玩，离结算日 {settled} 还有 {_days(settled, playable)} 天。**"
             f"日期来源：{obj['date_source']}", "",
             f"- P1 依据：{checks['P1']['basis']}", "", "### 2. 有人在等", ""]
    pre = f["object_volume_pre"]
    lines += [f"**{obj['name']} 开玩前月搜索量约 {_fmt(m['object_volume'])}（英文区 {len(a['countries'])} 国各自按 Trends "
              f"锚词换算后相加，其中美国约 {_fmt(pre.get('US', 0))}）。**", ""]
    lines += _table(["国家", "开玩前月搜索量"], [[g, _fmt(pre[g]) if g in pre else "读不出，记 0"] for g in a["countries"]])
    lines += ["", f"- P2 依据：{checks['P2']['basis']}", "", "### 3. 任务与参照倍数", "",
              f"**最小版本做 {len(tasks)} 项任务（{'、'.join(t['task'] for t in tasks)}），倍数取自已开玩游戏的参照："
              f"下四分位是保守档，中位数是对照档。**", ""]
    lines += _table(["任务", "说法", "参照条数", "下四分位倍数", "中位数倍数", "取自"],
                    [[t["task"], "、".join(t["terms"]), f"{t['references']} 条参照", f"{t['r_p25']:g}", f"{t['r_median']:g}",
                      _scope_cn(t, r["category"])] for t in tasks])
    lines += ["", "### 4. 首页现场", ""]
    done = sum(1 for s in r["serp"] for row in s["top10"] if row.get("completes_task") is True)
    lines += [f"**两次首页查询的前 10 条里，完整做了这个任务的有 {done} 条；AI 概览开玩前未知，按 {m['aio_factor']} 取系数。**", ""]
    lines += _table(["查询", "前 10 条域名", "完整做了任务"],
                    [[s["query"], "、".join(str(row.get("domain") or "—") for row in s["top10"]),
                      sum(1 for row in s["top10"] if row.get("completes_task") is True)] for s in r["serp"]])
    lines += ["", f"- P5 依据：{checks['P5']['basis']}", f"- P6 依据：{checks['P6']['basis']}", "",
              "### 5. 预测访问与收入", "",
              f"**下四分位倍数下基准单月约 {_fmt(base['visits'])} 次英文区访问、{_money(base['revenue'])}/月（模型估算），"
              f"{'过' if m['passes'] else '不过'} {_fmt(m['threshold_visits'])} 访问门槛；中位数倍数下基准约 {_fmt(med['visits'])} 次、"
              f"{_money(med['revenue'])}/月，{'过' if m['passes_median'] else '不过'}。**", ""]
    head = ["情景", "首发份额", "预计月访问", "预计月收入（AdSense）"]
    lines += [f"下四分位倍数（判 go 看这一档）：站点预测月搜索量约 {_fmt(m['forecast_p25'])}", ""]
    lines += _table(head, _scenario_rows(m["scenarios"]))
    lines += ["", f"中位数倍数（对照）：站点预测月搜索量约 {_fmt(m['forecast_median'])}", ""]
    lines += _table(head, _scenario_rows(m["median_scenarios"]))
    lines += ["", f"- 站点预测月搜索量 = 对象名开玩前月搜索量 {_fmt(m['object_volume'])} × 各任务倍数，按任务相加；"
                  f"基准访问 = 预测月搜索量 × 首发份额 × AI 概览系数 {m['aio_factor']}",
              f"- 其中美国访问约 {_fmt(base['us_visits'])}（基准，下四分位）；收入按 AdSense 美国 ${a['rpm_adsense']:.0f}、"
              f"其他英文国家 ${a['rpm_other_en']:.0f}/千访问估算",
              f"- 基准过线需要站点预测月搜索量约 {_fmt(m['searches_needed'])}；假设表版本 {m['assumptions_version']}",
              "", "### 6. 预判依据与风险", "", f"**最大的未知：{dec['biggest_unknown']}。**", ""]
    lines += ["- 倍数来自参照库：" + "；".join(
        f"{t['task']} {t['references']} 条参照（{_scope_cn(t, r['category'])}），下四分位 {t['r_p25']:g}、中位数 {t['r_median']:g}"
        for t in tasks) + "；参照条数越少倍数越不稳",
        f"- 两档结果：下四分位基准约 {_fmt(base['visits'])} 次访问（{'过' if m['passes'] else '不过'}线）、中位数基准约 "
        f"{_fmt(med['visits'])} 次（{'过' if m['passes_median'] else '不过'}线）；判 go 只认下四分位，中位数过线只进观察",
        f"- 参照窗口写死、不挑：对象名取开玩日前第 {a['reference_object_window'][0]} 到第 {a['reference_object_window'][1]} 天，"
        f"任务词取开玩后 {a['reference_task_span']} 天内最高的连续 {a['reference_task_days']} 天"]
    review = f"- {f['review_at']} 复核（开玩日后第 {_days(playable, f['review_at'])} 天）：按现行锚词换算实测各任务词的量，和预测比"
    if dec["verdict"] == "go":
        lines.append(review + f"；实测月搜索量低于 {_stop_line(rec)}（预测下四分位 {_fmt(f['forecast_p25'])} × "
                              f"{a['review_stop_ratio']:.0%}）提示止损，不再追加投入")
    else:
        lines.append(review + "，并按现行路径复判（过线判 go、继续观察或否决）")
    lines.append(f"- 开玩日累计推迟超过 {a['forecast_slip_days']} 天，这个预判要重新评估")
    if rec.get("watch"):
        w = rec["watch"]
        lines.append(f"- 观察中：{w['since']} 起，{w['expires_at']} 到期；已复查 {len(w['checks'])} 次")
    risks = list((_latest(by_kind, "quick_brief") or {}).get("risks") or [])
    risks.append(f"首发份额是起点假设（{'/'.join(f'{v:.0%}' for v in a['share'].values())}），新域名多久能排上去未确认")
    lines += [f"- {x}" for x in risks]
    return lines + [""]


def _brief(rec, by_kind):
    b, m = _latest(by_kind, "quick_brief"), rec["model"]
    base = m["scenarios"]["base"]
    lines = ["## 第二部分 最小版本建站简报", "", "### 1. 做什么", "", f"**{b['positioning']}**", "",
             "- 1 个主页面完成核心任务，最多 2–3 个配套页覆盖同一对象的其他任务词", "",
             "### 2. 页面清单", "", f"**首版 {len(b['pages'])} 个页面，预计 {_fmt(b['build_days'])} 天做完。**", ""]
    lines += _table(["路径", "目标查询", "要交付的内容或功能"], [[p["path"], p["target_query"], p["deliverable"]] for p in b["pages"]])
    lines += ["", "### 3. 数据", "", f"**数据来自 {len(b['data_sources'])} 个来源，{b['update_frequency']}更新；授权：{b['license']}。**", ""]
    lines += [f"- {s}" for s in b["data_sources"]]
    lines += ["", "### 4. 上线清单", "", "**免费托管上线，当天提交 Search Console 和 sitemap。**", "", f"- 托管：{b['hosting']}"]
    lines += [f"- {x}" for x in build_doc.SEO_RULES + build_doc.GEO_RULES]
    lines += ["", "### 5. 预计访问与收入", "",
              f"**基准约 {_fmt(base['visits'])} 次英文区访问、{_money(base['revenue'])}/月，按 AdSense 美国 "
              f"${QM.QUICK_ASSUMPTIONS['rpm_adsense']:.0f}、其他英文国家 ${QM.QUICK_ASSUMPTIONS['rpm_other_en']:.0f}/千访问估算。**", ""]
    lines += ["### 6. 验收与止损", "",
              f"**上线第 30 天月点击低于 {_fmt(QM.stop_line(m))} 就止损（基准预计的 25%）：不再加工时，站留着。**", ""]
    lines += _table(["上线后", "看什么", "结论"],
                    [["第 14 天", "主页面是否收录、有展现", "没有就先查收录"],
                     ["第 30 天", f"月点击是否低于 {_fmt(QM.stop_line(m))}", "低于即止损"],
                     ["第 90 天", f"单月是否 ≥ {_fmt(m['threshold_visits'])} 访问", "达到算成功"]])
    return lines + [""]


def render_md(root, rec) -> str:
    dec = rec.get("decision")
    require(dec, f"{rec['slug']} 还没有 decision;用 settle.py 结算")
    refs, by_kind = build_doc._observations(root, rec)
    verdict = VERDICT_CN[dec["verdict"]] + (f"（{GATE_CN[dec['gate']]}）" if dec.get("gate") else "")
    lines = [f"# {rec['title']}：快道决策书", "",
             f"- 方向 `{rec['slug']}` · 新词快道 · 站型 {rec['site_type']} · 结论 {verdict} · 决定于 {dec['decided_at']}", ""]
    forecast_doc = _is_forecast_doc(rec)
    if dec["verdict"] == "go":
        lines += (_go_block_forecast if forecast_doc else _go_block)(rec, by_kind)
    lines += ["## 结论", "", f"一句话：**{verdict}**。{dec['reason']}", ""]
    if rec.get("model"):
        base = rec["model"]["scenarios"]["base"]
        lines.append(f"- {'按参照库下四分位倍数预判，' if forecast_doc else ''}"
                     f"基准情景上线 90 天内单月约 {_fmt(base['visits'])} 次访问、{_money(base['revenue'])}/月（模型估算）")
    lines += [f"- 最大的未知：{dec['biggest_unknown']}", ""]
    lines += (_part_one_forecast if forecast_doc else _part_one)(rec, by_kind)
    if dec["verdict"] == "go":
        lines += _brief(rec, by_kind)
    files = (rec.get("bindings") or {}).get("files") or [{"ref": r, "sha256": ""} for r in refs]
    lines += ["## 附：证据清单", ""]
    lines += _table(["观察文件", "SHA-256 前 12 位"], [[f"`{f['ref']}`", f["sha256"][:12] or "未绑定"] for f in files])
    return "\n".join(lines) + "\n"


def build(root, slug):
    rec = load_ledger(root)["directions"].get(slug)
    require(rec and rec.get("lane") == "quick", f"没有快道方向 {slug}")
    md = Path(root) / "文档" / f"{slug}.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_md(root, rec), encoding="utf-8")
    return md, build_doc_html.build(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--slug", required=True)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        md, html = build(root, a.slug)
    except (BenchError, KeyError, IndexError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(f"已生成: {md}\n已生成: {html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
