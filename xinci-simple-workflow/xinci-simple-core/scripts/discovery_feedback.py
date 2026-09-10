"""只读发现反馈：来源与词根收益、拒因、去重提示和准入规则回放。"""
import argparse
from collections import Counter
import json

from _common import load_ledger
import qualification as Q

SOURCES = ('root', 'small_site', 'forum')


def summarize(root, rows=None):
    import run_log
    import validate_ledger
    rows = run_log.records(root) if rows is None else rows
    candidates = load_ledger(root)['candidates']
    errors, _ = validate_ledger.validate(root)
    invalid = {slug for slug in candidates if any(e.startswith(slug + ':') for e in errors)}
    completed = {(r['progress']['run_id'], r['progress']['round']) for r in rows
                 if r.get('skill') == 'xinci-simple-scan' and (r.get('progress') or {}).get('outcome') == 'completed'}
    attributed = {(r['progress']['source_kind'], slug) for r in rows
                  if r.get('skill') == 'xinci-simple-scan' and r.get('progress')
                  and (r['progress']['run_id'], r['progress']['round']) in completed
                  for slug in r.get('candidates_touched', [])}
    stats = {source: {'registered': 0, 'verified': 0, 'rejected': 0, 'pending': 0,
                      'integrity_excluded': 0, 'cohort_verified': 0, 'cohort_rejected': 0, 'completed_scans': 0, 'scan_calls': 0,
                      'gates': Counter()} for source in SOURCES}
    directions, duplicates = {}, []
    for slug, rec in candidates.items():
        seed = rec.get('seed') or {}
        source = seed.get('type')
        if source not in stats: continue
        key = (source, Q.normalize(seed.get('value', 'unknown')))
        direction = directions.setdefault(key, {'source': source, 'seed': key[1], 'registered': 0,
                                                'verified': 0, 'rejected': 0, 'pending': 0,
                                                'integrity_excluded': 0, 'cohort_verified': 0, 'cohort_rejected': 0, 'gates': Counter()})
        state = rec.get('state')
        bucket = 'integrity_excluded' if slug in invalid else (state if state in ('verified', 'rejected') else 'pending')
        history = rec.get('history', [])
        verdicts = [h for h in history if h.get('to') == state and h.get('action') not in ('set_task_plan', 'set_entry_plan', 'refresh_cluster')]
        gate = verdicts[-1].get('gate') if verdicts else None
        trusted_rejection = False
        if bucket == 'rejected' and gate:
            try:
                Q.check_rejection(root, rec, verdicts[-1].get('evidence_refs', []), gate)
                trusted_rejection = True
            except (Q.QualificationError, KeyError, TypeError):
                pass
        for target in (stats[source], direction):
            target['registered'] += 1
            target[bucket] += 1
            if (source, slug) in attributed:
                if bucket == 'verified': target['cohort_verified'] += 1
                elif trusted_rejection: target['cohort_rejected'] += 1
            if bucket == 'rejected': target['gates'][gate or 'historical_unknown'] += 1
        duplicates.append({'slug': slug, 'primary_keyword': rec['primary_keyword'], 'state': state,
                           'gate': gate, 'reason': verdicts[-1].get('reason') if verdicts else None,
                           'terms': [k['term'] for k in rec['cluster']['keywords']]})
    scans, last_seen = [], {source: -1 for source in SOURCES}
    for row in rows:
        p = row.get('progress') or {}
        if row.get('skill') != 'xinci-simple-scan' or p.get('source_kind') not in stats: continue
        source = p['source_kind']
        stats[source]['scan_calls'] += row.get('billable_calls', 0)
        if p.get('outcome') == 'completed':
            last_seen[source] = len(scans)
            scans.append(row)
            stats[source]['completed_scans'] += 1
    for stat in stats.values():
        resolved = stat['cohort_verified'] + stat['cohort_rejected']
        stat['resolved'] = resolved
        stat['verified_rate'] = stat['cohort_verified'] / resolved if resolved else None
        stat['scan_calls_per_verified'] = stat['scan_calls'] / stat['cohort_verified'] if stat['cohort_verified'] else None
    rotation = SOURCES[(SOURCES.index(scans[-1]['progress']['source_kind']) + 1) % 3] if scans else 'root'
    eligible = [s for s in SOURCES if stats[s]['resolved'] >= 3 and stats[s]['completed_scans'] >= 2]
    # 样本不足保持轮换；每四次实际发现留一次给最久未扫描的来源，避免永久饿死。
    if len(eligible) < 2:
        selected, reason = rotation, '样本不足：沿用来源轮换'
    elif (len(scans) + 1) % 4 == 0:
        selected = min(SOURCES, key=lambda s: (last_seen[s], SOURCES.index(s)))
        reason = '探索轮：选择最久未完成扫描的来源'
    else:
        def score(s):
            stat = stats[s]
            return ((stat['cohort_verified'] + 1) / (stat['resolved'] + 2) /
                    (1 + stat['scan_calls'] / stat['completed_scans']))
        selected = max(eligible, key=lambda s: (score(s), -last_seen[s]))
        reason = '按平滑通过率与每次发现调用成本优先；不改变核验门槛'
    for d in directions.values():
        d['lower_priority'] = d['cohort_rejected'] >= 3 and d['cohort_verified'] == 0
    return {'sources': stats, 'directions': list(directions.values()), 'duplicate_index': duplicates,
            'next_source': selected, 'selection_reason': reason,
            'legacy_logs_excluded': sum(not r.get('progress') for r in rows),
            'unattributed_verify_calls': sum(r.get('billable_calls', 0) for r in rows if r.get('skill') == 'xinci-simple-verify'),
            'cost_scope': '学习样本仅含已完成结构化 scan 引用且当前裁决可校验的候选，按 slug 去重。来源成本仅含结构化 scan 新增调用；verify 可能混合来源，不摊分、不声称全流程获客成本。'}


def replay(root):
    """只回放已登记样本的两种准入口径；不能推断未登记的小量机会。"""
    candidates = load_ledger(root)['candidates']
    rows = []
    for rec in candidates.values():
        cluster = rec['cluster']
        primary = max((k['volume'] for k in cluster['keywords']
                       if Q.normalize(k['term']) == Q.normalize(rec['primary_keyword'])), default=0)
        rows.append({'slug': rec['slug'], 'state': rec['state'], 'raw_volume': cluster['total_volume'],
                     'measured_keywords_volume': sum(k['volume'] for k in cluster['keywords']),
                     'current_admission': cluster['total_volume'] >= 50000 or primary >= 5000,
                     'volume_priority_only_admission': cluster['total_volume'] > 0,
                     'revenue': rec.get('revenue'), 'investment_present': bool(rec.get('investment'))})
    return {'sample_count': len(rows), 'candidates': rows,
            'newly_admitted_in_observed_sample': [r['slug'] for r in rows if not r['current_admission'] and r['volume_priority_only_admission']],
            'decision': 'retain_current_thresholds',
            'limitations': ['账本只含既有准入后的候选，无法估计此前被过滤的小量机会；不把零新增当成无漏选。',
                            '没有真实同口径流量/收入反馈时，不据模型自身输出校准 CTR、RPM、佣金。',
                            '需另收集低量任务样本及真实反馈，再决定准入与收入假设变更。']}


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root')
    ap.add_argument('--replay', action='store_true')
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    print(json.dumps(replay(root) if a.replay else summarize(root), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
