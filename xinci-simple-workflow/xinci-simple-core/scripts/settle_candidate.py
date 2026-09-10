"""候选结算：重算/转移/报告/校验；重复调用只恢复已提交结果，不重复历史。"""
import argparse
import json
from pathlib import Path

import build_report as B
import data_root
import ledger as L
import qualification as Q
import validate_ledger as V


def settle(root, slug, *, evidence, by, reason, gate=None, park=False):
    rec = L.load(root)['candidates'][slug]
    if gate and park:
        raise Q.QualificationError('不能同时拒绝与 parked')
    if rec['state'] == 'verified':
        refs = {b['ref'] for b in rec.get('qualification', {}).get('bindings', []) if b['stage'] == 'verify'}
        Q.require(not gate and not park and set(evidence) == refs, '已通过候选只能恢复同一裁决报告；新结论须审计')
    elif rec['state'] in ('rejected','parked') and rec['history'][-1].get('evidence_refs') == evidence:
        last = rec['history'][-1]
        Q.require((park and rec['state'] == 'parked') or (rec['state'] == 'rejected' and (gate or 'revenue') == last.get('gate')),
                  '相同观察不能变更既有结论')
        if rec['state'] == 'rejected':
            Q.check_rejection(root, rec, evidence, last['gate'])
        return {'slug':slug, 'state':rec['state'], 'recovered':True}
    else:
        if park:
            rec = L.transition(root, slug, to='parked', evidence=evidence, by=by, reason=reason)
        elif gate:
            rec = L.transition(root, slug, to='rejected', gate=gate, evidence=evidence, by=by, reason=reason)
        else:
            form, revenue, _ = Q.assess(root, rec, evidence)
            to = 'verified' if revenue['base'] >= revenue['threshold'] else 'rejected'
            rec = L.transition(root, slug, to=to, gate='revenue' if to == 'rejected' else None,
                               evidence=evidence, by=by, reason=reason, form=form, revenue=revenue)
    if rec['state'] == 'verified':
        try:
            B.build(root, slug)
        except Exception as exc:
            raise Q.QualificationError(f'状态已提交，报告未完成；用相同结算命令恢复，不要重建运行：{exc}') from exc
    errors, _ = V.validate(root)
    errors = [e for e in errors if e.startswith(slug + ':')]
    Q.require(not errors, '结算完整性错误：' + '；'.join(errors))
    return {'slug':slug, 'state':rec['state'], 'report':f'报告/{slug}.md' if rec['state'] == 'verified' else None}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root')
    ap.add_argument('--slug', required=True)
    ap.add_argument('--evidence', action='append', required=True)
    ap.add_argument('--by', required=True)
    ap.add_argument('--reason', required=True)
    choice = ap.add_mutually_exclusive_group()
    choice.add_argument('--gate', choices=('G1','G2','G3','scope','revenue','revenue_prescreen'))
    choice.add_argument('--park', action='store_true')
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        result = settle(root, a.slug, evidence=a.evidence, by=a.by, reason=a.reason, gate=a.gate, park=a.park)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (Q.QualificationError, B.ReportError, KeyError, OSError, ValueError) as exc:
        print(f'结算未完成: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
