#!/usr/bin/env python3
"""机会报告:从账本记录 + 当次绑定的 verify 观察生成 报告/<slug>.md。9 节固定,不手写。"""
import argparse
import sys
from pathlib import Path

import build_report_html
import ledger as L
import narrative
import qualification as Q
import investment
import opportunity

PLAY_SINGLE_MAX = 150000


class ReportError(Exception):
    pass



def render_groups(rec, observations):
    rev = rec['revenue']
    volume = rev['inputs']['cluster_volume']
    play = 'single_domain' if volume < PLAY_SINGLE_MAX else 'cluster_expansion'
    lines = [f"# 机会报告：{rec['primary_keyword']}", '', f"- slug：`{rec['slug']}`", '',
             narrative.build_groups(rec, observations), opportunity.render(rec), investment.render(rec), "---", "",
             '## 1. 主关键词与簇', '',
             f"- 原始 phrase-match 月量：{rec['cluster']['total_volume']:,}",
             f"- 已核验去重月量：{volume:,}", '',
             '| 支撑词 | 月量 | KD |', '| --- | ---: | ---: |']
    for kw in rec['cluster']['keywords']:
        lines.append(f"| {kw['term']} | {kw['volume']:,} | {kw.get('kd')} |")
    lines += ['', '## 2. 形态与意图', '', '| 任务组 | 形态 | 月量 | 代表查询 |', '| --- | --- | ---: | --- |']
    for o, g in zip(observations, rev['inputs']['groups']):
        inp = g['revenue']['inputs']
        lines.append(f"| {g['id']} | {inp['form']} | {inp['cluster_volume']:,} | {o['task_group']['representative_keyword']} |")
        lines += ['', o['task_group']['coverage_reason'], '']
    for group in rec['qualification'].get('excluded_groups', []):
        lines += [f"- 未计入的支撑组 {group['id']}：{group['reason']}（观察 `{group['evidence_ref']}`）", '']
    lines += ['## 3. 量级证据', '', '裁决固定引用以下观察；新增观察不会改变本报告依据。', '']
    for b in rec['qualification']['bindings']:
        lines.append(f"- `{b['ref']}` SHA-256 `{b['sha256']}`")
    lines += ['', '## 4. 竞争现场', '']
    for o in observations:
        strong, _ = Q.strong_results(o)
        lines += [f"### {o['task_group']['id']}", '', f"查询：{o['query_url']}", '',
                  '| # | 域名 | AS | 完成任务 | 新鲜 | 格式对 |', '| ---: | --- | ---: | --- | --- | --- |']
        for row in o['serp_top10']:
            lines.append(f"| {row['pos']} | {row['domain']} | {row.get('dr')} | {row['completes_task']} | {row.get('fresh')} | {row.get('format_match')} |")
        lines += ['', f"- G3 强对手：{len(strong)}", f"- 首页结构：{o['serp_structure']['evidence']}", f"- 第二页：{o['page2_note']}", '']
    lines += ['## 5. AI Overview 状态', '']
    for o in observations:
        lines += [f"- {o['task_group']['id']}：{o['ai_overview']['excerpt']}；摘要/组件：{o['direct_answer']['evidence']}"]
    lines += ['', '## 6. 季节性', '']
    for o in observations:
        lines += [f"- {o['task_group']['id']}：{o['trends']['evidence']}（{o['trends']['source_url']}）"]
    lines += ['', '## 7. 收入三情景', '', f"- 假设版本：`{rev['assumptions_version']}`；门槛 ${rev['threshold']}/月", '',
              '| 任务组 | downside | base | upside |', '| --- | ---: | ---: | ---: |']
    for g in rev['inputs']['groups']:
        r = g['revenue']
        lines.append(f"| {g['id']} | ${r['downside']:,.2f} | ${r['base']:,.2f} | ${r['upside']:,.2f} |")
    lines += [f"| 合计 | ${rev['downside']:,.2f} | ${rev['base']:,.2f} | ${rev['upside']:,.2f} |", '',
              f"- 维持当前任务组比例及假设时，门槛所需词量：{rev['volume_needed_for_threshold']:,}", '',
              '## 8. 范围排除复核', '']
    for o in observations:
        lines.append(f"- {o['task_group']['id']}：四项均未命中；{o['scope_evidence']}")
    lines += ['', '## 9. 建议 play 与风险', '', f'- play：`{play}`（按已核验词量）',
              '- 未核验任务组不进入收益；代表词覆盖范围、RPM、佣金与实际排名需在建站决策时复核。',
              '- 本报告不包含域名、页面地图或内容大纲。', '', '## 附：现场要点', '']
    for o in observations:
        lines += [f"- {o['task_group']['id']}：{point}" for point in o['points']]
    return '\n'.join(lines) + '\n'


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
    try:
        refs = Q.check_bound(root, rec)
        observations = [Q.read_observation(root, ref, slug)[0] for ref in refs]
    except Q.QualificationError as exc:
        raise ReportError(str(exc)) from exc
    out = root / "报告" / f"{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_groups(rec, observations), encoding="utf-8")
    # 同一调用顺序产出；中途失败由 validator 报缺失，恢复时重建。
    build_report_html.build(out)
    return out


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="生成机会报告")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--slug", required=True)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        md = build(root, a.slug)
        print(f"已写 {md}")
        print(f"已写 {md.with_suffix('.html')}")
    except ReportError as e:
        print(f"拒绝: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
