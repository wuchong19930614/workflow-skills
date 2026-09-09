#!/usr/bin/env python3
"""机会报告:从账本记录 + 最新 verify 观察生成 报告/<slug>.md。9 节固定,不手写。"""
import argparse
import sys
from pathlib import Path

import ledger as L
from _common import load_json

PLAY_SINGLE_MAX = 150000
FORM_LABELS = {"info": "信息", "lookup": "查表", "tool": "工具", "commercial": "商业/联盟", "mixed": "混合"}
SCOPE_LABELS = {"ymyl": "YMYL（健康/金融/法律/安全）", "firsthand": "需亲身体验/一手数据",
                "brand_nav": "纯品牌/导航词", "news": "新闻热点"}


class ReportError(Exception):
    pass


def _latest_obs(root, slug, stage):
    d = Path(root) / "证据" / slug
    files = sorted(d.glob(f"*-{stage}.json")) if d.is_dir() else []
    if not files:
        raise ReportError(f"{slug}: 缺 {stage} 观察文件")
    return load_json(files[-1])


def _fmt(n):
    return f"{n:,}" if isinstance(n, int) else str(n)


def render(rec, scan_obs, verify_obs) -> str:
    slug = rec["slug"]
    cluster = rec["cluster"]
    rev = rec["revenue"]
    aio = verify_obs.get("ai_overview") or {}
    top10 = verify_obs.get("serp_top10") or []
    scope = verify_obs.get("scope_recheck") or {}
    preview = scan_obs.get("semrush_preview") or {}
    strong = [r for r in top10 if r.get("completes_task") and (r.get("dr") or 0) >= 50]
    play = "single_domain" if cluster["total_volume"] < PLAY_SINGLE_MAX else "cluster_expansion"
    lines = [f"# 机会报告：{rec['primary_keyword']}", "",
             f"- slug：`{slug}`", f"- 状态：{rec['state']}", f"- 生成依据：{verify_obs.get('observed_at')} 的 verify 观察", ""]
    lines += ["## 1. 主关键词与簇", "",
              f"- 主关键词：**{rec['primary_keyword']}**",
              f"- 簇量（phrase-match 合计月量）：**{_fmt(cluster['total_volume'])}**",
              f"- 来源：{rec['seed']['type']} — {rec['seed']['value']}（查询于 {rec['seed'].get('queried_at')}）", "",
              "| 支撑词 | 月量 | KD |", "| --- | ---: | ---: |"]
    for kw in cluster.get("keywords", [])[:20]:
        lines.append(f"| {kw['term']} | {_fmt(kw.get('volume'))} | {kw.get('kd')} |")
    lines += ["", "## 2. 形态与意图", "",
              f"- 形态：**{FORM_LABELS.get(rec['form'], rec['form'])}**（`{rec['form']}`）",
              f"- 判断依据：首页 {len(top10)} 条中 {sum(1 for r in top10 if r.get('type') == 'tool')} 条工具、"
              f"{sum(1 for r in top10 if r.get('type') == 'forum')} 条论坛、"
              f"{sum(1 for r in top10 if r.get('type') == 'article')} 条文章", ""]
    lines += ["## 3. 量级证据", "",
              f"- Semrush 预览：{preview.get('note', '见 scan 观察')}",
              f"- 查询日期：{preview.get('queried_at', rec['seed'].get('queried_at'))}",
              f"- 过滤条件：{preview.get('filters', 'US, KD ≤ 49, 排除 Navigational')}",
              f"- 主词 KD：{rec['proxy'].get('kd')}；代理排序分：{rec['proxy'].get('rank_score')}", ""]
    lines += ["## 4. 竞争现场", "", f"查询：`{verify_obs.get('query_url')}`", "",
              "| # | 域名 | DR | 类型 | 完成任务 | 日期 |", "| ---: | --- | ---: | --- | --- | --- |"]
    for r in top10:
        lines.append(f"| {r.get('pos')} | {r.get('domain')} | {r.get('dr')} | {r.get('type')} | "
                     f"{'是' if r.get('completes_task') else '否'} | {r.get('dated') or '-'} |")
    lines += ["", f"- 完整完成任务且 DR ≥ 50 的结果：**{len(strong)}** 个（{', '.join(r['domain'] for r in strong) or '无'}）",
              f"- 第二页：{verify_obs.get('page2_note', '-')}", ""]
    lines += ["## 5. AI Overview 状态", "",
              ("- 无 AI Overview" if not aio.get("present") else
               f"- 有，**未完成任务**；要点：{aio.get('excerpt', '-')}"), ""]
    lines += ["## 6. 季节性", "", f"- Trends 12 个月：{verify_obs.get('trends_12m', '-')}", ""]
    inp = rev.get("inputs", {})
    lines += ["## 7. 收入三情景", "",
              f"- 假设表版本：`{rev['assumptions_version']}`",
              f"- 输入：形态 `{inp.get('form', rec['form'])}`，簇量 {_fmt(inp.get('cluster_volume', cluster['total_volume']))}，"
              f"垂类 `{inp.get('niche', '-')}`，AIO 折减 {'是' if inp.get('aio_present') else '否'}，"
              f"强完整结果 {inp.get('strong_complete_count', len(strong))} 个", "",
              "| 情景 | 月收入 |", "| --- | ---: |",
              f"| downside | ${_fmt(rev['downside'])} |", f"| **base** | **${_fmt(rev['base'])}** |",
              f"| upside | ${_fmt(rev['upside'])} |", "",
              f"- 在当前假设下 base 到 $500 需要簇量：{_fmt(rev['volume_needed_for_500'])}", ""]
    lines += ["## 8. 范围排除复核", ""]
    for k, label in SCOPE_LABELS.items():
        lines.append(f"- [{'x' if not scope.get(k) else ' '}] {label}：{'未命中' if not scope.get(k) else '**命中**'}")
    lines += ["", "## 9. 建议 play 与风险", "",
              f"- play：**{play}**（簇量 {'<' if play == 'single_domain' else '≥'} {_fmt(PLAY_SINGLE_MAX)}）",
              "- 风险：",
              f"  1. AI Overview：{'存在，可能继续扩展覆盖' if aio.get('present') else '暂无，可能出现'}",
              f"  2. 强占位：{len(strong)} 个 DR ≥ 50 的完整答案",
              f"  3. 季节性：{verify_obs.get('trends_12m', '-')}",
              "- 下一步是人的动作：决定建站方式后再做页面地图；本报告不含域名与内容大纲。", ""]
    if verify_obs.get("points"):
        lines += ["## 附：现场要点", ""] + [f"- {p}" for p in verify_obs["points"]] + [""]
    return "\n".join(lines)


def build(root, slug) -> Path:
    root = Path(root)
    ledger = L.load(root)
    if slug not in ledger["candidates"]:
        raise ReportError(f"候选不存在: {slug}")
    rec = ledger["candidates"][slug]
    if rec["state"] != "verified":
        raise ReportError(f"{slug}: 只为 verified 出报告,当前 {rec['state']}")
    if not rec.get("revenue") or not rec.get("form"):
        raise ReportError(f"{slug}: 缺 form/revenue")
    scan_obs = _latest_obs(root, slug, "scan")
    verify_obs = _latest_obs(root, slug, "verify")
    out = root / "报告" / f"{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rec, scan_obs, verify_obs), encoding="utf-8")
    return out


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="生成机会报告")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--slug", required=True)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        print(f"已写 {build(root, a.slug)}")
    except ReportError as e:
        print(f"拒绝: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
