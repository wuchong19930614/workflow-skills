#!/usr/bin/env python3
"""投入预测与累计反馈。预测冻结；反馈不改变研究状态、不执行试验。金额 USD。"""
import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import qualification as Q
from _common import atomic_save, now

COSTS = ('initial_cash_usd', 'build_hours', 'data_hours', 'content_hours',
         'monthly_cash_usd', 'monthly_hours', 'hourly_rate_usd')
TEXT = ('minimum_product', 'entry_advantage', 'delivery_basis', 'biggest_unknown',
        'cost_basis', 'ramp_basis')
METRICS = {'feasibility': 'passed_cases/test_cases', 'usability': 'completions/attempts',
           'seo': 'organic_clicks/impressions', 'monetization': 'transactions/qualified_visits'}
ACTUALS = ('cash_spent_usd', 'hours_spent', 'revenue_usd', 'sample', 'successes')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def validate_plan(p):
    Q.require(isinstance(p, dict), 'plan 须对象')
    for key in TEXT:
        Q.require(Q.nonempty(p.get(key)), f'{key} 须写依据或明确未知')
    unknowns = p.get('unknowns', {})
    Q.require(isinstance(unknowns, dict), 'unknowns 须对象')
    for key in COSTS:
        Q.require(key in p, f'缺 {key}；未知填 null 并说明原因')
        value = p[key]
        Q.require((value is None and Q.nonempty(unknowns.get(key))) or
                  (Q.number(value) and value >= 0), f'{key} 须非负有限数，或 null + unknowns 原因')
    ramp = p.get('monthly_revenue_fraction')
    Q.require(isinstance(ramp, list) and 1 <= len(ramp) <= 60, '收入爬坡须 1–60 个月数组')
    for value in ramp:
        Q.require((value is None and Q.nonempty(unknowns.get('monthly_revenue_fraction'))) or
                  (Q.number(value) and 0 <= value <= 1), '爬坡须 0–1，未知 null 须原因；不是成功概率')
    e = p.get('experiment')
    Q.require(isinstance(e, dict) and e.get('type') in METRICS, 'experiment.type 无效')
    Q.require(e.get('metric') == METRICS[e['type']], 'metric 须匹配试验类型')
    for key in ('hypothesis', 'sample_definition', 'success_rule', 'stop_rule', 'extend_rule'):
        Q.require(Q.nonempty(e.get(key)), f'experiment.{key} 必填')
    for key in ('window_days', 'min_sample', 'min_successes'):
        Q.require(type(e.get(key)) is int and e[key] > 0, f'{key} 须正整数')
    Q.require(e['min_successes'] <= e['min_sample'], 'min_successes 不得大于 min_sample')
    for key in ('max_cash_usd', 'max_hours'):
        Q.require(Q.number(e.get(key)) and e[key] >= 0, f'{key} 须明确预算；不能用未知预算启动试验')
    Q.require(Q.number(e.get('min_success_rate')) and 0 <= e['min_success_rate'] <= 1,
              'min_success_rate 须 0–1')


def estimate(p, revenue):
    validate_plan(p)
    result = {}
    for scenario in ('downside', 'base', 'upside'):
        income = revenue.get(scenario) if isinstance(revenue, dict) else None
        cash = None if p['initial_cash_usd'] is None else -p['initial_cash_usd']
        initial_hours = [p[k] for k in ('build_hours', 'data_hours', 'content_hours')]
        hours = sum(initial_hours) if all(v is not None for v in initial_hours) else None
        rate = p['hourly_rate_usd']
        economic = cash - hours * rate if cash is not None and hours is not None and rate is not None else None
        cash_month = economic_month = None
        rows = []
        for month, fraction in enumerate(p['monthly_revenue_fraction'], 1):
            gross = income * fraction if income is not None and fraction is not None else None
            net = gross - p['monthly_cash_usd'] if gross is not None and p['monthly_cash_usd'] is not None else None
            cash = cash + net if cash is not None and net is not None else None
            effort = p['monthly_hours']
            economic = economic + net - effort * rate if all(v is not None for v in (economic, net, effort, rate)) else None
            Q.require(all(v is None or Q.number(v) for v in (gross, net, cash, economic)), '投入计算溢出，检查输入单位和数值')
            if cash_month is None and cash is not None and cash >= 0:
                cash_month = month
            if economic_month is None and economic is not None and economic >= 0:
                economic_month = month
            rows.append({'month': month, 'revenue_usd': gross, 'cumulative_cash_usd': cash,
                         'cumulative_economic_usd': economic})
        result[scenario] = {'cash_break_even_month': cash_month, 'economic_break_even_month': economic_month,
                            'cash_status': 'unknown' if cash is None else ('reached' if cash_month else 'not_within_horizon'),
                            'economic_status': 'unknown' if economic is None else ('reached' if economic_month else 'not_within_horizon'),
                            'months': rows}
    return result


def baseline(rec, plan, by):
    Q.require(Q.nonempty(by), 'by 必填')
    validate_plan(plan)
    snapshot = {'state': rec['state'], 'revenue': rec.get('revenue'),
                'qualification': rec.get('qualification'), 'history': rec['history']}
    body = {'version': 1, 'created_at': now(), 'by': by, 'plan': plan,
            'research_snapshot': snapshot, 'estimate': estimate(plan, snapshot['revenue'])}
    return dict(body, sha256=digest(body))


def check_baseline(b):
    Q.require(isinstance(b, dict) and b.get('version') == 1, '投入基线版本无效')
    Q.require(b.get('sha256') == digest({k: v for k, v in b.items() if k != 'sha256'}), '投入基线摘要不符')
    Q.require(b['estimate'] == estimate(b['plan'], b['research_snapshot']['revenue']), '投入预测重算不符')


def feedback_path(root, slug):
    return Path(root) / '反馈' / f'{slug}.json'


def validate_feedback(root, rec, data):
    b = rec['investment']
    check_baseline(b)
    Q.require(data.get('baseline_sha256') == b['sha256'] and data.get('slug') == rec['slug'], '反馈基线不符')
    Q.require(isinstance(data.get('snapshots'), list), '反馈 snapshots 须数组')
    previous = None
    seen = set()
    for index, row in enumerate(data['snapshots']):
        for key in ('id', 'by', 'channel', 'learning', 'realized_risks', 'next_action', 'calibration_proposal'):
            Q.require(Q.nonempty(row.get(key)), f'反馈 {key} 必填；没有校准建议写 none')
        Q.require(row['id'] not in seen, '反馈 id 重复')
        seen.add(row['id'])
        start = date.fromisoformat(row['started_on'])
        end = date.fromisoformat(row['as_of'])
        Q.require(end >= start, '反馈日期倒序')
        Q.require(end <= datetime.now(timezone.utc).date(), '实际反馈不能填未来日期')
        Q.require(start >= date.fromisoformat(b['created_at'][:10]), '实际试验须在基线登记后开始；不能事后冒充预先预测')
        if previous:
            Q.require(row['started_on'] == previous['started_on'] and row['as_of'] > previous['as_of'], '累计快照须同一起点且日期递增')
        unknowns = row.get('unknowns', {})
        Q.require(isinstance(unknowns, dict), '反馈 unknowns 须对象')
        for key in ACTUALS:
            Q.require(key in row, f'反馈缺 {key}')
            v = row[key]
            Q.require((v is None and Q.nonempty(unknowns.get(key))) or (Q.number(v) and v >= 0), f'反馈 {key} 未知须原因')
            if key in ('sample', 'successes') and v is not None:
                Q.require(type(v) is int, '样本与成功数须整数')
            known_before = [r[key] for r in data['snapshots'][:index] if r[key] is not None]
            if known_before and v is not None:
                Q.require(v >= max(known_before), '累计反馈不可倒退；修正须另存原始证据并人工审计')
        if row['sample'] is not None and row['successes'] is not None:
            Q.require(row['successes'] <= row['sample'], '成功数超过样本')
        bindings = row.get('evidence', [])
        Q.require(isinstance(bindings, list) and bindings, '实际反馈须本地原始证据')
        for binding in bindings:
            path = (Path(root) / binding['ref']).resolve()
            Q.require(path.is_relative_to((Path(root) / '证据' / rec['slug']).resolve()) and path.is_file(), '反馈证据须位于候选证据目录')
            Q.require(hashlib.sha256(path.read_bytes()).hexdigest() == binding['sha256'], '反馈证据摘要变化')
        previous = row


def review(b, row):
    e = b['plan']['experiment']
    elapsed = (date.fromisoformat(row['as_of']) - date.fromisoformat(row['started_on'])).days
    complete = row['sample'] is not None and row['successes'] is not None
    sufficient = complete and row['sample'] >= e['min_sample']
    met = sufficient and row['successes'] >= e['min_successes'] and row['successes'] / row['sample'] >= e['min_success_rate']
    caps = [key for key, cap in (('cash_spent_usd', 'max_cash_usd'), ('hours_spent', 'max_hours'))
            if row[key] is not None and row[key] >= e[cap]]
    actual_cash = row['revenue_usd'] - row['cash_spent_usd'] if all(row[k] is not None for k in ('revenue_usd', 'cash_spent_usd')) else None
    rate = b['plan']['hourly_rate_usd']
    actual_economic = actual_cash - row['hours_spent'] * rate if all(v is not None for v in (actual_cash, row['hours_spent'], rate)) else None
    # 只比较完成的整段规划月份，不把少量天数的收入外推成稳定月收入。
    months = elapsed // 30
    forecast = {s: values['months'][months - 1] for s, values in b['estimate'].items()} if 0 < months <= len(b['plan']['monthly_revenue_fraction']) else None
    return {'signal': 'criterion_met' if met else ('criterion_not_met' if sufficient else 'insufficient_evidence'),
            'metric': e['metric'], 'window_elapsed': elapsed >= e['window_days'], 'budget_caps_reached': caps,
            'budget_unknown': any(row[k] is None for k in ('cash_spent_usd', 'hours_spent')),
            'actual_cash_balance_usd': actual_cash, 'actual_economic_balance_usd': actual_economic,
            'forecast_at_completed_30_day_month': forecast,
            'comparison_note': f'实际覆盖 {elapsed} 天；预测展示已完成的 {months} 个 30 天规划月，不直接计算不等长期间偏差。',
            'scope': '仅描述该试验指标；不能据此宣布建站成功或自动扩张。到期或达预算须复核后决定。'}


def record_feedback(root, rec, row):
    Q.require('investment' in rec, '先登记投入基线')
    path = feedback_path(root, rec['slug'])
    data = json.loads(path.read_text()) if path.exists() else {'slug': rec['slug'], 'baseline_sha256': rec['investment']['sha256'], 'snapshots': []}
    validate_feedback(root, rec, data)
    existing = next((r for r in data['snapshots'] if r['id'] == row.get('id')), None)
    if existing:
        Q.require(existing == row, '反馈 id 已存在且内容不同；不可覆盖')
        return review(rec['investment'], existing)
    data['snapshots'].append(row)
    validate_feedback(root, rec, data)
    atomic_save(path, data)
    return review(rec['investment'], row)


def render(rec):
    b = rec.get('investment')
    if not b:
        return '## 投入与最小验证\n\n尚未登记投入基线，回本期未知。研究通过不等于已批准投入；先补成本、收入爬坡和有预算的最小验证方案。\n'
    check_baseline(b)
    p, e = b['plan'], b['plan']['experiment']
    lines = ['## 投入与最小验证', '', f"原始预测：`{b['sha256']}`（{b['created_at']}）；不随实际反馈改写。", '']
    for key, label in zip(TEXT, ('最小产品', '进入优势及证据', '交付与数据维护依据', '最大未知', '成本估算依据', '收入爬坡依据')):
        lines.append(f'- {label}：{p[key]}')
    lines += ['', '金额 USD；时间独立保留，时薪仅为可调整的规划参数。基线冻结后不同参数可用 estimate 命令比较，不覆盖原预测。', '']
    for key, label in zip(COSTS, ('初始现金 USD', '开发小时', '数据整理小时', '内容小时', '每月现金 USD', '每月持续小时', '内部时薪 USD')):
        lines.append(f"- {label}：{p[key] if p[key] is not None else '未知：' + p['unknowns'][key]}")
    lines += [f"- 各月收入 / 稳态情景收入：{p['monthly_revenue_fraction']}；不是成功概率。",
              f"- 爬坡未知依据：{p.get('unknowns', {}).get('monthly_revenue_fraction', '无')}", '',
              '| 情景 | 首次现金回本月 | 首次含时间成本回本月 | 期末现金结余 / 含时间结余 USD |', '| --- | --- | --- | --- |']
    for scenario, result in b['estimate'].items():
        def display(kind):
            return result[kind + '_break_even_month'] or ('未知' if result[kind + '_status'] == 'unknown' else '预测期内未回本')
        last = result['months'][-1]
        lines.append(f"| {scenario} | {display('cash')} | {display('economic')} | {last['cumulative_cash_usd']} / {last['cumulative_economic_usd']} |")
    lines += ['', '月 1 起扣持续成本；累计收入先扣初始现金，再扣持续现金；经济结余另扣初始及持续小时 × 时薪。首次回本不保证后续持续盈利。', '',
              '### 最小验证方案（执行需单独授权）', '']
    labels = {'type': '试验类型', 'metric': '指标（成功数/样本数）', 'hypothesis': '待验证假设',
              'sample_definition': '样本口径', 'success_rule': '成功定义', 'min_sample': '最少样本',
              'min_successes': '最少成功数', 'min_success_rate': '最低成功比例', 'window_days': '观察天数',
              'max_cash_usd': '现金上限 USD', 'max_hours': '小时上限', 'stop_rule': '停止条件', 'extend_rule': '延期条件'}
    for key in labels:
        lines.append(f'- {labels[key]}：{e[key]}')
    lines += ['', f"实际结果另存 `反馈/{rec['slug']}.json`，用 investment.py review 对照冻结基线。",
              '无流量只说明获客证据不足；任务完成不证明 SEO，SEO 点击不证明变现。校准建议须有人复核，不能自动降低闸门。', '']
    return '\n'.join(lines)


def main(argv=None):
    import data_root
    import ledger as L
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=('plan', 'estimate', 'feedback', 'review'))
    ap.add_argument('--data-root')
    ap.add_argument('--slug', required=True)
    ap.add_argument('--file', help='plan/estimate 输入计划；feedback 输入累计快照')
    ap.add_argument('--by')
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        rec = L.load(root)['candidates'][a.slug]
        if a.action in ('plan', 'estimate', 'feedback'):
            Q.require(a.file, '此操作须 --file')
            payload = json.loads(Path(a.file).read_text())
        if a.action == 'plan':
            result = L.set_investment(root, a.slug, plan=payload, by=a.by)
            if result['state'] == 'verified':
                import build_report
                try:
                    build_report.build(root, a.slug)
                except (build_report.ReportError, OSError) as exc:
                    raise Q.QualificationError(f'基线已保存，报告未完成；相同 plan 命令恢复：{exc}') from exc
            result = result['investment']
        elif a.action == 'estimate':
            result = estimate(payload, rec.get('revenue'))
        elif a.action == 'feedback':
            result = record_feedback(root, rec, payload)
        else:
            Q.require('investment' in rec, '尚无投入基线')
            data = json.loads(feedback_path(root, a.slug).read_text())
            validate_feedback(root, rec, data)
            result = {'baseline': rec['investment'], 'snapshots': data['snapshots'],
                      'review': review(rec['investment'], data['snapshots'][-1]) if data['snapshots'] else None}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (Q.QualificationError, KeyError, TypeError, ValueError, OSError) as exc:
        print(f'拒绝: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
