#!/usr/bin/env python3
"""决策书(go 时含建站简报):账本 + 绑定观察 → 文档/<slug>.md,再生成同名 html。

只读绑定的观察;每节第一句是加粗的大白话结论,数字都从结构化字段派生。
"""
import argparse
import sys
from pathlib import Path

import bench_model
import build_doc_html
import data_root
import write_observation as W
from _common import BenchError, load_ledger, require

VERDICT_CN = {"go": "值得做（go）", "rejected": "否决", "parked": "搁置"}
GATE_CN = {"scope": "范围排除", "benchmark": "标杆不成立", "answered": "首屏已答完", "revenue": "收入不足"}
NET_CN = {"adsense": "AdSense", "mediavine_journey": "Mediavine Journey"}
SCEN_CN = {"low": "保守", "base": "基准", "high": "乐观"}
SEO_RULES = ["网址按任务分层,一个页面只服务一个主查询", "每页必须有独有数据或独有功能,不按模板批量复制,避开规模化内容滥用与 doorway 页",
             "页面之间按簇做内链,首页链到每个簇的入口页", "提交 sitemap,按页面类型加结构化数据"]
GEO_RULES = ["每页开头先给答案或工具入口,再展开说明(可被 AI 引用的段落)", "结构化数据与页面可见内容一致",
             "根目录放 llms.txt,列出站点用途与主要页面", "robots.txt 放行主要 AI 爬虫",
             "上线后每月抽查目标查询的 AI 概览是否引用本站"]


def _fmt(n):
    return "—" if n is None else (f"{n:,.0f}" if isinstance(n, (int, float)) else str(n))


def _money(x):
    return f"${x:,.2f}"


def _yn(v):
    return {True: "是", False: "否", None: "未查"}[v]


def _table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows]
    return out


def _observations(root, rec):
    refs = [f["ref"] for f in (rec.get("bindings") or {}).get("files", [])] or rec["evidence_refs"]
    by_kind = {}
    for ref in refs:
        obs = W.read(root, ref)
        by_kind.setdefault(obs["kind"], []).append((ref, obs))
    return refs, by_kind


def _section_benchmarks(rec, by_kind):
    bs = rec["benchmarks"]
    clean = [b for b in bs if b.get("clean") is True]
    lines = ["### 1. 标杆证据", ""]
    lines.append(f"**{len(bs)} 个标杆，其中 {len(clean)} 个干净（初核全过且不靠垃圾外链）。**流量是 Semrush 估算的自然流量；"
                 "英文区 = 美区读数按 Domain Overview 的国家分布换算到美、英、加、澳、新、爱 6 国合计。")
    lines.append("")
    lines += _table(["域名", "注册日", "起量月", "当前英文区", "当前美区", "第 12 个月英文区", "AS", "外链驱动", "算法风险",
                     "变现", "干净"],
                    [[b["domain"], b.get("registered_at") or "—", b.get("traffic_start") or "—",
                      _fmt(b.get("en_organic_now")), _fmt(b.get("us_organic_now")), _fmt(b.get("en_organic_m12")),
                      _fmt(b.get("authority_score")),
                      _yn(b.get("link_driven")), _yn(b.get("algo_risk")),
                      "、".join(b.get("monetization") or []) or "—", _yn(b.get("clean"))] for b in bs])
    for _, o in by_kind.get("benchmark", []):
        r = o["readings"]
        lines += ["", f"- **{r['domain']}**：引荐域名 {_fmt(r['referring_domains'])}；锚文本 {r['anchor_summary']}；"
                      f"垃圾更新前后 {r['update_readings']}；ads.txt {r['ads_txt']}；定价页 {r['pricing'] or '无'}"]
    return lines + [""]


def _section_demand(rec, by_kind):
    cs = rec["clusters"]
    counted = [c for c in cs if c["counted"] and not c["answered"]]
    covered = bench_model.covered_demand(cs)
    covered_us = bench_model.covered_demand(cs, key="volume")
    lines = ["### 2. 方向需求与对手", ""]
    if not cs:
        return lines + ["**本方向没有做到需求测算这一步。**", ""]
    lines.append(f"**计入需求约 {_fmt(covered)}/月（英文区，其中美国约 {_fmt(covered_us)}；{len(counted)} 个簇计入，"
                 f"{sum(c['answered'] for c in cs)} 个簇被首屏答完不计）；同方向 {_fmt(rec.get('crowding'))} 个新站在抢（含标杆）。**")
    lines.append("")
    lines += _table(["簇", "种子词", "英文区月量", "美区月量", "测量日", "覆盖", "near me", "首屏答完", "计入"],
                    [[c["id"], c["seed_term"], _fmt(c["en_volume"]), _fmt(c["volume"]), c["measured_at"],
                      "标杆已做" if c["coverage"] == "benchmark" else "我们额外做",
                      _yn(c["near_me"]), _yn(c["answered"]), _yn(c["counted"])] for c in cs])
    lines.append("")
    for _, o in by_kind.get("demand", []):
        for t in o["readings"]["competitor_traffic"]:
            lines.append(f"- 对手 {t['domain']}：约 {_fmt(t['traffic'])}/月（{t['basis']}）")
        if o["readings"]["new_sites"]:
            lines.append("- 同方向新站：" + "、".join(o["readings"]["new_sites"]))
    return lines + [""]


def _section_serp(by_kind):
    serps = [o["readings"] for _, o in by_kind.get("serp", [])]
    lines = ["### 3. 现场与 GEO", ""]
    if not serps:
        return lines + ["**本方向没有做到现场抽检这一步。**", ""]
    aio = [s for s in serps if s["ai_overview"]["present"]]
    rec_tools = [s for s in aio if s["ai_overview"]["recommends_tools"]]
    pos = [s["benchmark_position"] for s in serps if s["benchmark_position"]]
    lines.append(f"**抽检 {len(serps)} 个查询：{sum(s['answered'] for s in serps)} 个被首屏答完；AI 概览出现 {len(aio)} 次，"
                 f"其中 {len(rec_tools)} 次点名推荐工具站；标杆最好排第 {min(pos) if pos else '—'} 位。**")
    lines.append("")
    lines += _table(["查询", "簇", "首屏答完", "AI 概览", "AI 引用", "推荐工具", "标杆排名"],
                    [[s["query"], s["cluster_id"], _yn(s["answered"]), _yn(s["ai_overview"]["present"]),
                      "、".join(s["ai_overview"]["cited_domains"]) or "—", _yn(s["ai_overview"]["recommends_tools"]),
                      _fmt(s["benchmark_position"])] for s in serps])
    return lines + [""]


def _section_model(model):
    lines = ["### 4. 12 个月流量与收入", ""]
    if not model:
        return lines + ["**本方向没有完成测算。**", ""]
    base = model["scenarios"]["base"]
    lines.append(f"**基准情景第 12 个月约 {_fmt(base['visits_m12'])} 次英文区访问、{_money(base['total'])}/月（模型估算），"
                 f"{'过' if model['passes'] else '不过'} ${model['threshold']:.0f} 门槛。**")
    lines.append("")
    lines += _table(["情景", "后来者系数", "第 12 个月访问", "其中美国", "广告网络", "广告", "付费", "合计"],
                    [[SCEN_CN[k], v["coef"], _fmt(v["visits_m12"]), _fmt(v["us_visits"]), NET_CN[v["network"]],
                      _money(v["ads"]), _money(v["paid"]), _money(v["total"])] for k, v in model["scenarios"].items()])
    lines += ["", f"- 标杆份额率 {model['share_rate']:.4f}；我们覆盖的英文区需求约 {_fmt(model['covered_demand'])}/月；拥挤度 {model['crowding']}",
              f"- 美国访问占 {model['us_share']:.0%}（按覆盖需求里美国的占比）；美国以外按美国一半的每千访问收入算",
              f"- 达到 ${model['threshold']:.0f} 需要第 12 个月约 {_fmt(model['visits_needed_for_threshold'])} 次访问，"
              f"相当于标杆流量的 {model['benchmark_fraction_needed']} 倍",
              f"- 假设表版本 {model['assumptions_version']}" + ("；标杆还不满 12 个月，用的是当前值，偏保守" if model["ramping"] else "")]
    if model["unconfirmed_assumptions"]:
        lines.append("- 用到的未确认假设：" + "；".join(model["unconfirmed_assumptions"]))
    return lines + [""]


def _risks(rec, by_kind, model):
    out = [f"标杆 {b['domain']} 靠垃圾外链起量" for b in rec["benchmarks"] if b.get("link_driven")]
    out += [f"标杆 {b['domain']} 在 2026 年垃圾内容更新后掉过一半以上" for b in rec["benchmarks"] if b.get("algo_risk")]
    for _, o in by_kind.get("delivery", [])[-1:]:
        out.append(f"数据授权：{o['readings']['license']}")
    if model and model["unconfirmed_assumptions"]:
        out.append("收入依赖未确认假设：" + "；".join(model["unconfirmed_assumptions"]))
    return out


def _section_risk(rec, by_kind, model):
    dec = rec["decision"]
    lines = ["### 5. 风险与最大未知", "", f"**最大的未知：{dec['biggest_unknown']}。**", ""]
    lines += [f"- {x}" for x in _risks(rec, by_kind, model)] or ["- 未发现额外风险"]
    return lines + [""]


def _lead_curve(rec, by_kind):
    """里程碑用流量最高的干净标杆的曲线;没有对应观察时返回空(全部按线性补)。"""
    clean = sorted((b for b in rec["benchmarks"] if b.get("clean") is True),
                   key=lambda b: -(b.get("us_organic_m12") or b.get("us_organic_now") or 0))
    curves = {o["readings"]["domain"]: o["readings"]["curve"] for _, o in by_kind.get("benchmark", [])}
    return curves.get(clean[0]["domain"], {}) if clean else {}


def _brief(rec, by_kind, model):
    b = by_kind["brief"][-1][1]["readings"]
    dif = by_kind["differentiation"][-1][1]["readings"]
    dl = by_kind["delivery"][-1][1]["readings"]
    curve = _lead_curve(rec, by_kind)
    ms = bench_model.milestones(rec, model, curve)
    base = model["scenarios"]["base"]
    hours = sum(dl["hours"].values())
    total_hours = hours + 12 * dl["monthly_hours"]
    # 线性爬坡:第 k 个月收入 = 第 12 个月收入 × k/12,第 12 个月后持平
    monthly = [base["total"] * min(k, 12) / 12 for k in range(1, 37)]
    cum12 = sum(monthly[:12])
    payback = next((k for k in range(1, 37) if sum(monthly[:k]) >= dl["cash_first_year"]), None)
    lines = ["## 第二部分 建站简报", "", "### 1. 定位", "", f"**{b['positioning']}**", "",
             f"- 站型：{rec['site_type']}", "",
             "### 2. 首版页面清单", "",
             f"**首版 {len(b['pages'])} 个页面，目标查询合计约 {_fmt(sum(p['volume'] for p in b['pages']))}/月。**", ""]
    lines += _table(["路径", "目标查询", "月量", "页面类型", "要交付的内容或功能"],
                    [[p["path"], p["target_query"], _fmt(p["volume"]), p["page_type"], p["deliverable"]] for p in b["pages"]])
    lines += ["", "### 3. 差异点", ""]
    if dif["copy_only"]:
        lines.append("**没有差异点，照搬标杆；后来者系数照常适用。**")
    else:
        lines.append(f"**{len(dif['gaps'])} 条差异点，每条都对照了标杆现状并有现场证据。**")
        lines.append("")
        lines += _table(["标杆现状", "我们做什么", "证据"], [[g["benchmark_now"], g["ours"], g["evidence"]] for g in dif["gaps"]])
    lines += ["", "### 4. 数据", "", f"**数据来自 {len(dl['data_sources'])} 个来源；授权：{dl['license']}。**", ""]
    lines += [f"- {s}" for s in dl["data_sources"]]
    lines += ["", "### 5. 技术与托管", "", "**展示广告须先按托管方条款确认允许商业用途（如 Vercel Hobby 禁止含广告的商业用途）。**", "",
              b["tech_hosting"], "",
              "### 6. SEO 规范", "", "**按下面几条做，重点是每页都有独有内容。**", ""]
    lines += [f"- {x}" for x in SEO_RULES + b["seo_notes"]]
    lines += ["", "### 7. GEO 规范", "", "**让 AI 能直接引用本站的答案，并每月抽查是否被引用。**", ""]
    lines += [f"- {x}" for x in GEO_RULES + b["geo_notes"]]
    lines += ["", "### 8. 变现计划", "",
              f"**基准情景第 12 个月走 {NET_CN[base['network']]}"
              + ("，并计入付费功能。**" if rec["paid"]["applicable"] else "，不计付费功能。**"), "",
              b["monetization_plan"], "",
              "### 9. 投入", "",
              f"**首版约 {_fmt(hours)} 小时、首年现金约 {_money(dl['cash_first_year'])}、每月维护 {_fmt(dl['monthly_hours'])} 小时；"
              f"基准情景 12 个月累计收入约 {_money(cum12)}，折合约 {_money(cum12 / total_hours if total_hours else 0)}/小时（按线性爬坡估算）。**", ""]
    lines += _table(["开发", "数据", "内容", "首年现金", "每月维护", "现金回本"],
                    [[_fmt(dl["hours"]["dev"]), _fmt(dl["hours"]["data"]), _fmt(dl["hours"]["content"]),
                      _money(dl["cash_first_year"]), _fmt(dl["monthly_hours"]),
                      f"第 {payback} 个月" if payback else "36 个月内回不了本"]])
    lines += ["", "### 10. 里程碑与止损", "",
              f"**第 6 个月 Search Console 点击低于 {_fmt(ms['stop_line_m6'])} 就停（基准曲线的 25%）。**", ""]
    lines += _table(["上线后月份", "预期月点击（基准）", "依据"],
                    [[k, _fmt(ms[k]["expected_clicks"]), ms[k]["basis"]] for k in ("3", "6", "12")])
    lines += ["", "### 11. 风险清单", "", "**上线前把下面几条逐一确认。**", ""]
    lines += [f"- {x}" for x in b["risks"] + _risks(rec, by_kind, model)] or ["- 未发现额外风险"]
    return lines + [""]


def render_md(root, rec) -> str:
    dec = rec.get("decision")
    require(dec, f"{rec['slug']} 还没有 decision;用 settle.py 结算")
    refs, by_kind = _observations(root, rec)
    model = rec.get("model")
    verdict = VERDICT_CN[dec["verdict"]] + (f"（{GATE_CN[dec['gate']]}）" if dec.get("gate") else "")
    lines = [f"# {rec['title']}：方向决策书", "",
             f"- 方向 `{rec['slug']}` · 站型 {rec['site_type']} · 结论 {verdict} · 决定于 {dec['decided_at']}", "",
             "## 结论", "", f"一句话：**{verdict}**。{dec['reason']}", ""]
    if model:
        base = model["scenarios"]["base"]
        lines += [f"- 基准情景第 12 个月约 {_fmt(base['visits_m12'])} 次英文区访问、{_money(base['total'])}/月（模型估算）",
                  f"- 达标需要约 {_fmt(model['visits_needed_for_threshold'])} 次访问（标杆的 {model['benchmark_fraction_needed']} 倍）"]
    lines += [f"- 最大的未知：{dec['biggest_unknown']}", "", "## 第一部分 决策", ""]
    lines += _section_benchmarks(rec, by_kind) + _section_demand(rec, by_kind) + _section_serp(by_kind)
    lines += _section_model(model) + _section_risk(rec, by_kind, model)
    if dec["verdict"] == "go":
        lines += _brief(rec, by_kind, model)
    files = (rec.get("bindings") or {}).get("files") or [{"ref": r, "sha256": ""} for r in refs]
    lines += ["## 附：证据清单", ""]
    lines += _table(["观察文件", "SHA-256 前 12 位"], [[f"`{f['ref']}`", f["sha256"][:12] or "未绑定"] for f in files])
    return "\n".join(lines) + "\n"


def build(root, slug):
    rec = load_ledger(root)["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
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
