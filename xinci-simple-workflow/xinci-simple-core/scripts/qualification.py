"""通过资格的共享计算：观察、任务组、G3、收入与裁决证据绑定。只读。"""
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import revenue_model as M

VERSION = 2
SCOPE = ('ymyl', 'firsthand', 'brand_nav', 'news')


class QualificationError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise QualificationError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def normalize(term):
    return ' '.join(term.lower().split())


def read_observation(root, ref, slug):
    root = Path(root).resolve()
    path = (root / ref).resolve()
    require(not Path(ref).is_absolute() and path.is_relative_to(root / '证据' / slug),
            f'证据必须在 证据/{slug}/ 内: {ref}')
    try:
        raw = path.read_bytes()
        obs = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise QualificationError(f'证据不可读: {ref}: {exc}') from exc
    require(isinstance(obs, dict) and obs.get('slug') == slug, f'{ref}: slug 不匹配')
    require(obs.get('stage') in ('scan', 'verify'), f'{ref}: stage 无效')
    try:
        stamp = datetime.fromisoformat(obs['observed_at'])
        require(stamp.utcoffset() is not None, f'{ref}: observed_at 必须带时区')
    except (KeyError, TypeError, ValueError) as exc:
        raise QualificationError(f'{ref}: observed_at 无效') from exc
    require(isinstance(obs.get('source_urls'), list) and obs['source_urls']
            and all(nonempty(u) for u in obs['source_urls']), f'{ref}: 缺 source_urls')
    require(isinstance(obs.get('points'), list), f'{ref}: 缺 points')
    return obs, {'ref': ref, 'sha256': hashlib.sha256(raw).hexdigest(), 'stage': obs['stage']}


def strong_results(obs):
    """返回确定强对手及无法排除为强对手的结果；未知不能计作零。"""
    strong, unknown = [], []
    for row in obs.get('serp_top10', []):
        if row.get('completes_task') is not True:
            continue
        if row.get('fresh') is False or row.get('format_match') is False:
            continue
        dr = row.get('dr')
        if number(dr) and 0 <= dr < 50:
            continue
        if (number(dr) and 50 <= dr <= 100 and row.get('fresh') is True
                and row.get('format_match') is True):
            strong.append(row)
        else:
            unknown.append(row)
    return strong, unknown


def check_environment(obs):
    require(isinstance(obs.get('browser_preflight'), dict), '缺浏览器预检')
    pre = obs.get('browser_preflight') or {}
    require(all(pre.get(k) is True for k in ('controllable', 'desktop', 'logged_out'))
            and pre.get('region') == 'us' and nonempty(pre.get('evidence')), '浏览器预检不完整或不合规')
    url = urlparse(obs.get('query_url', ''))
    query = parse_qs(url.query)
    require(url.scheme == 'https' and url.hostname == 'www.google.com' and url.path == '/search'
            and all(query.get(k) == [v] for k, v in {'gl':'us', 'hl':'en', 'pws':'0'}.items()),
            'Google 查询 URL 必须含美区三参')


def check_top(obs):
    top = obs.get('serp_top10')
    require(isinstance(top, list) and 1 <= len(top) <= 10, '首页自然结果须为 1–10 条')
    require(len(top) == 10 or (obs.get('natural_results_exhausted') is True
            and nonempty(obs.get('exhaustion_evidence'))), '不足 10 条须记录读尽自然结果的依据')
    require(all(isinstance(r, dict) for r in top), '自然结果必须为对象')
    require([r.get('pos') for r in top] == list(range(1, len(top) + 1)), '自然结果位置必须连续且不重复')
    for row in top:
        require(nonempty(row.get('domain')) and nonempty(row.get('url'))
                and row.get('type') in ('tool','article','forum','video','official','brand','other')
                and type(row.get('completes_task')) is bool, '自然结果缺 URL/域名/类型/任务判断')
        require(row.get('dr') is None or (number(row['dr']) and 0 <= row['dr'] <= 100), 'AS 须为 0–100 或 null')


def check_gate(obs, gate):
    """只验证该拒因所需证据，不要求继续采集后续无关门。"""
    if gate == 'scope':
        require(any((obs.get('scope_recheck') or {}).get(k) is True for k in SCOPE)
                and nonempty(obs.get('scope_evidence')), 'scope: 没有明确范围命中及依据')
        return
    check_environment(obs)
    if gate == 'G1':
        aio, direct = obs.get('ai_overview') or {}, obs.get('direct_answer') or {}
        require((aio.get('present') is True and aio.get('completes_task') is True and nonempty(aio.get('excerpt')))
                or (any(direct.get(k) is True for k in ('featured_snippet_completes_task','native_widget_completes_task'))
                    and nonempty(direct.get('evidence'))), 'G1: 观察没有首屏完成任务的证据')
    elif gate == 'G2':
        check_top(obs)
        structure = obs.get('serp_structure') or {}
        require(structure.get('blocked') is True and nonempty(structure.get('evidence'))
                and nonempty(obs.get('page2_note')), 'G2: 结构否决或读满证据不足')
    elif gate == 'G3':
        check_top(obs)
        strong, _ = strong_results(obs)
        require(len(strong) >= 3 and nonempty(obs.get('page2_note')), 'G3: 未证实至少三个强对手')
    else:
        raise QualificationError('未知拒因')


def validate_task_plan(plan, rec):
    require(isinstance(plan, dict) and nonempty(plan.get('core_reason')), '任务清单须说明核心任务')
    groups = plan.get('groups')
    require(isinstance(groups, list) and groups, '任务清单不能为空')
    ids, terms = set(), set()
    known = {normalize(r['term']) for r in rec['cluster']['keywords']}
    core_terms = set()
    for g in groups:
        require(isinstance(g, dict) and nonempty(g.get('id')) and g['id'] not in ids, '任务组 id 缺失或重复')
        require(g.get('role') in ('core','support'), '任务组 role 必须为 core/support')
        words = g.get('keywords')
        require(isinstance(words, list) and words and all(nonempty(t) for t in words), '任务组须有关键词')
        words = [normalize(t) for t in words]
        require(len(set(words)) == len(words) and not terms.intersection(words), '计划关键词重复')
        require(set(words) <= known, '计划词必须在 cluster.keywords 中')
        ids.add(g['id']); terms.update(words)
        if g['role'] == 'core':
            core_terms.update(words)
    require(core_terms, '至少一个核心组')
    primary = normalize(rec['primary_keyword'])
    require(primary not in known or primary in core_terms, '主词必须归入核心组')
    return {g['id']: g for g in groups}


def check_rejection(root, rec, refs, gate):
    require(isinstance(refs, list) and refs, '拒绝须有观察')
    if gate == 'revenue':
        _, revenue, _ = assess(root, rec, refs)
        require(revenue['base'] < M.THRESHOLD, 'revenue: 完整核验重算收入未低于门槛')
        return
    for ref in refs:
        obs, _ = read_observation(root, ref, rec['slug'])
        require(obs['stage'] == 'verify', '拒绝须 verify 观察')
        if gate == 'revenue_prescreen':
            pre = obs.get('prescreen') or {}
            require(nonempty(pre.get('basis')), '收入预筛缺形态/垂类依据')
            result = pre.get('result') or {}
            actual = M.upper_bound(rec['cluster']['total_volume'], result.get('possible_forms'), result.get('possible_niches'))
            require(actual == result and actual['can_reject'], '收入预筛重算不支持拒绝')
        else:
            check_gate(obs, gate)
            if rec.get('task_plan') and gate in ('G1','G2','G3'):
                planned = validate_task_plan(rec['task_plan'], rec)
                group = obs.get('task_group') or {}
                require(group.get('id') in planned and planned[group['id']]['role'] == 'core',
                        '支撑组失败不能直接拒绝整个候选，须结算全部组')


def check_serp(obs):
    for key in ('browser_preflight','ai_overview','direct_answer','serp_structure','trends','scope_recheck'):
        require(isinstance(obs.get(key), dict), f'{key}: 缺少对象字段')
    check_environment(obs)
    aio = obs.get('ai_overview') or {}
    require(type(aio.get('present')) is bool and aio.get('completes_task') is False
            and nonempty(aio.get('excerpt')), 'G1: AIO 未采全或已完成任务')
    direct = obs.get('direct_answer') or {}
    require(direct.get('featured_snippet_completes_task') is False
            and direct.get('native_widget_completes_task') is False
            and nonempty(direct.get('evidence')), 'G1: 摘要/组件未核验或已完成任务')
    structure = obs.get('serp_structure') or {}
    require(structure.get('blocked') is False and nonempty(structure.get('evidence')),
            'G2: 首页结构未通过或缺依据')
    check_top(obs)
    strong, unknown = strong_results(obs)
    require(not unknown, 'G3: 可能的强对手缺 AS、新鲜度或格式证据')
    require(len(strong) < 3, f'G3: 强占位 {len(strong)} 个')
    require(nonempty(obs.get('page2_note')), 'G2/G3: 缺第二页观察')
    trends = obs.get('trends') or {}
    require(trends.get('status') == 'nonseasonal' and nonempty(trends.get('evidence'))
            and nonempty(trends.get('source_url')), '季节性未证实通过，应 parked')
    scope = obs.get('scope_recheck') or {}
    require(all(scope.get(k) is False for k in SCOPE) and nonempty(obs.get('scope_evidence')),
            '范围排除命中或未完成复核')
    return len(strong), aio['present']


def assess(root, rec, refs):
    """每份 verify 对应一个任务组，组内词去重后计量；组间收入求和。"""
    require(isinstance(refs, list) and refs and len(set(refs)) == len(refs), '至少一份且不重复的 verify 观察')
    keywords = {}
    for row in rec['cluster']['keywords']:
        term = normalize(row['term'])
        require(term not in keywords, '候选支撑词重复')
        require(type(row.get('volume')) is int and row['volume'] >= 0, '支撑词量须为非负整数')
        keywords[term] = row['volume']
    planned = validate_task_plan(rec.get('task_plan'), rec)
    groups, bindings, seen, ids, excluded = [], [], set(), set(), []
    for ref in refs:
        obs, binding = read_observation(root, ref, rec['slug'])
        require(obs['stage'] == 'verify', '通过裁决只接受 verify 观察')
        require(obs.get('schema_version') == VERSION, '通过须使用 schema_version=2 的观察')
        require(isinstance(obs.get('task_group'), dict), 'task_group 必须为对象')
        group = obs['task_group']
        require(nonempty(group.get('id')) and group['id'] not in ids, '任务组 id 缺失或重复')
        ids.add(group['id'])
        require(group['id'] in planned, '观察任务组未在计划中')
        terms = group.get('keywords')
        require(isinstance(terms, list) and terms and all(nonempty(t) for t in terms), '任务组缺 keywords')
        terms = [normalize(t) for t in terms]
        require(len(set(terms)) == len(terms) and not seen.intersection(terms), '任务组内/组间关键词重复计量')
        require(all(t in keywords for t in terms), '任务组词必须来自已登记的 cluster.keywords')
        require(set(terms) == {normalize(t) for t in planned[group['id']]['keywords']}, '观察任务组词与预登记计划不一致')
        representative = normalize(group.get('representative_keyword', ''))
        require(representative in terms and parse_qs(urlparse(obs['query_url']).query).get('q')
                and normalize(parse_qs(urlparse(obs['query_url']).query)['q'][0]) == representative,
                '现场查询必须对应任务组 representative_keyword')
        require(nonempty(group.get('coverage_reason')), '须解释代表查询为何覆盖该任务组')
        seen.update(terms)
        if group.get('exclusion_reason') is not None:
            require(planned[group['id']]['role'] == 'support' and nonempty(group['exclusion_reason']),
                    '核心组不能剔除；支撑组剔除须有理由')
            excluded.append({'id':group['id'], 'keywords':terms, 'reason':group['exclusion_reason'], 'evidence_ref':ref})
            bindings.append(binding)
            continue
        k, aio = check_serp(obs)
        volume = sum(keywords[t] for t in terms)
        try:
            rev = M.model(group.get('form'), volume, group.get('niche'), aio, k)
        except ValueError as exc:
            raise QualificationError(str(exc)) from exc
        groups.append({'id': group['id'], 'keywords': terms, 'evidence_ref': ref, 'revenue': rev})
        bindings.append(binding)
    require(ids == set(planned), '任务组观察不完整；不得省略核心或失败组')
    require(groups, '没有计入收入的任务组')
    volume = sum(g['revenue']['inputs']['cluster_volume'] for g in groups)
    require(volume <= rec['cluster']['total_volume'], '已核验词量不能超过原始 phrase-match 总量')
    forms = {g['revenue']['inputs']['form'] for g in groups}
    form = next(iter(forms)) if len(forms) == 1 else 'mixed'
    rev = {key: round(sum(g['revenue'][key] for g in groups), 2) for key in ('downside', 'base', 'upside')}
    rev.update(threshold=M.THRESHOLD, assumptions_version=M.VERSION,
               volume_needed_for_threshold=math.ceil(M.THRESHOLD * volume / rev['base']) if rev['base'] else None,
               inputs={'form': form, 'cluster_volume': volume, 'raw_cluster_volume': rec['cluster']['total_volume'],
                       'groups': groups})
    return form, rev, {'version': VERSION, 'bindings': bindings, 'qualified_volume': volume, 'task_plan': rec['task_plan'], 'excluded_groups': excluded}


def check_bound(root, rec):
    q = rec.get('qualification') or {}
    require(q.get('version') == VERSION and q.get('bindings'), '历史 verified 未绑定 v2 完整核验，须重新核验')
    refs = []
    for old in q['bindings']:
        obs, current = read_observation(root, old['ref'], rec['slug'])
        require(current == old, f"裁决证据 SHA 不一致: {old['ref']}")
        if obs['stage'] == 'verify':
            refs.append(old['ref'])
    require(q.get("task_plan") == rec.get("task_plan") and q.get("task_plan"), "缺绑定任务计划，须补核")
    form, rev, expected = assess(root, rec, refs)
    require(form == rec.get('form') and rev == rec.get('revenue'), '收入/形态与绑定观察重算不一致')
    require(rev['base'] >= M.THRESHOLD, '重算收入不足当前门槛')
    require(any(b['stage'] == 'scan' for b in q['bindings']), '缺绑定 scan 证据')
    require(q.get('excluded_groups') == expected['excluded_groups'], '剔除任务组与绑定观察不一致')
    return [g['evidence_ref'] for g in rev['inputs']['groups']]


def main(argv=None):
    import argparse
    import data_root
    from _common import load_ledger
    ap = argparse.ArgumentParser(description='按任务组核验观察重算收入，不写账本')
    ap.add_argument('--data-root')
    ap.add_argument('--slug', required=True)
    ap.add_argument('--evidence', action='append', required=True)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        rec = load_ledger(root)['candidates'][a.slug]
        form, revenue, _ = assess(root, rec, a.evidence)
        print(json.dumps({'form': form, 'revenue': revenue, 'passes': revenue['base'] >= M.THRESHOLD}, ensure_ascii=False, indent=2))
    except (QualificationError, KeyError, TypeError, OSError) as exc:
        print(f'拒收: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
