"""进入优势预检与投入建议；研究四态、收入公式和执行授权保持独立。"""
import hashlib
import json
from urllib.parse import urlparse

import qualification as Q

LABELS = {'pilot': '值得小规模试做', 'needs_evidence': '需要补证据', 'defer': '暂不值得投入'}
ENTRY_FIELDS = ('user_gap', 'solution', 'advantage', 'delivery_basis', 'biggest_unknown')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate_entry(plan):
    Q.require(isinstance(plan, dict), 'entry plan 须对象')
    for key in ENTRY_FIELDS:
        Q.require(Q.nonempty(plan.get(key)), f'进入预检缺 {key}')
    Q.require(plan.get('status') in ('ready', 'unknown', 'infeasible'), '进入预检 status 无效')
    Q.require(isinstance(plan.get('evidence_refs'), list) and plan['evidence_refs']
              and len(set(plan['evidence_refs'])) == len(plan['evidence_refs']), '进入预检须不重复的观察引用')


def check_entry(root, rec, require_ready=False):
    entry = rec.get('entry_plan')
    Q.require(isinstance(entry, dict), '缺进入优势预检；先 set-entry-plan')
    validate_entry(entry['plan'])
    Q.require(entry['sha256'] == digest({k: v for k, v in entry.items() if k != 'sha256'}), '进入预检摘要不符')
    actual = [Q.read_observation(root, ref, rec['slug'])[1] for ref in entry['plan']['evidence_refs']]
    Q.require(actual == entry['bindings'], '进入预检证据摘要变化')
    if require_ready:
        Q.require(entry['plan']['status'] == 'ready', '进入优势或交付能力未明确，先补证据或 parked')
    return entry


def validate_monetization(value):
    Q.require(isinstance(value, dict), 'monetization 须对象')
    Q.require(value.get('status') in ('supported', 'unknown', 'unavailable'), '变现 status 无效')
    Q.require(value.get('channel') in ('ads', 'affiliate', 'both'), '变现 channel 须 ads/affiliate/both')
    for key in ('basis', 'key_assumption', 'validation_step'):
        Q.require(Q.nonempty(value.get(key)), f'monetization.{key} 必填')
    refs = value.get('source_urls')
    Q.require(isinstance(refs, list) and all(isinstance(u, str) and urlparse(u).scheme in ('http', 'https')
              and urlparse(u).netloc for u in refs), '变现来源须 HTTP(S) URL 数组')
    if value['status'] == 'supported':
        Q.require(refs and Q.nonempty(value.get('checked_at')), '变现已支持须来源和核对日期')
        from datetime import date
        Q.require(date.fromisoformat(value['checked_at']) <= date.today(), '变现核对日期不能在未来')


def recommendation(rec):
    """由冻结基线推导建议；不持久化为另一套状态，不宣称真实商业验证。"""
    import investment as I
    reasons, gaps = [], []
    if rec.get('state') == 'rejected':
        reasons.append('研究已否决，投入计划不能翻案')
    elif rec.get('state') != 'verified':
        gaps.append('研究尚未通过')
    entry = rec.get('entry_plan', {}).get('plan')
    if not entry or entry.get('status') == 'unknown':
        gaps.append('进入优势与交付能力未确认')
    elif entry.get('status') == 'infeasible':
        reasons.append('已有依据表明当前方案不可交付')
    b = rec.get('investment')
    sensitivity = None
    if not b:
        gaps.append('尚未登记投入基线，回本期未知')
    else:
        I.check_baseline(b)
        snap = b['research_snapshot']
        if any(snap.get(k) != rec.get(k) for k in ('state', 'revenue', 'qualification')):
            gaps.append('原投入基线对应旧研究裁决，须重新评估')
        p = b['plan']
        m = p.get('monetization')
        if m is None or m['status'] == 'unknown':
            gaps.append('变现渠道适用性未确认')
        elif m['status'] == 'unavailable':
            reasons.append('当前变现渠道不可用')
        else:
            forms = {g['revenue']['inputs']['form'] for g in (rec.get('revenue') or {}).get('inputs', {}).get('groups', [])}
            needed = set()
            if forms & {'commercial', 'mixed'}: needed.add('affiliate')
            if forms & {'info', 'lookup', 'tool', 'mixed'}: needed.add('ads')
            if not needed or (m['channel'] != 'both' and needed != {m['channel']}):
                gaps.append('变现依据未覆盖收入模型采用的全部渠道')
        base = b['estimate']['base']
        last = base['months'][-1]
        if any(base[k + '_status'] == 'unknown' for k in ('cash', 'economic')):
            gaps.append('成本、工时或收入爬坡仍有未知')
        elif any(last[k] <= 0 for k in ('cumulative_cash_usd', 'cumulative_economic_usd')):
            reasons.append('所选预测期末 base 扣现金或时间成本后无正结余')
        sensitivity = {s: dict(months=len(result['months']),
                              cash_break_even_month=result['cash_break_even_month'],
                              economic_break_even_month=result['economic_break_even_month'],
                              **result['months'][-1]) for s, result in b['estimate'].items()}
    status = 'defer' if reasons else ('needs_evidence' if gaps else 'pilot')
    return {'status': status, 'label': LABELS[status], 'reasons': reasons + gaps,
            'sensitivity': sensitivity,
            'scope': '原始投入建议，基于所选预测期及统一收入假设；不是盈利证明或执行授权。实际试验开始后用 review 决策，不据本建议重复启动。'}


def render(rec):
    decision = recommendation(rec)
    lines = ['## 原始投入建议', '', f"**{decision['label']}**", '']
    lines += [f'- {reason}' for reason in decision['reasons']]
    if not decision['reasons']:
        lines.append('研究通过、进入方案及变现渠道有依据，所选预测期末 base 扣现金和时间成本后为正；先验证最大未知。')
    lines += ['', decision['scope'], '']
    if rec.get('entry_plan'):
        p = rec['entry_plan']['plan']
        for key, label in zip(ENTRY_FIELDS, ('用户卡点', '最小解决方案', '具体优势', '交付依据', '最大未知')):
            lines.append(f'- {label}：{p[key]}')
    m = rec.get('investment', {}).get('plan', {}).get('monetization')
    if m:
        lines += ['', f"- 变现依据（{m['status']} / {m['channel']}）：{m['basis']}",
                  f"- 最依赖的假设：{m['key_assumption']}", f"- 下一步验证：{m['validation_step']}"]
        lines += [f'- 变现来源：{url}' for url in m['source_urls']]
    return '\n'.join(lines) + '\n'
