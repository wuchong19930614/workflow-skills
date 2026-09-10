#!/usr/bin/env python3
"""候选账本:唯一写入口。4 态、合法转移表、证据必须存在、history 只追加、原子写。

通过资格委托 qualification.py 重算；规范看选词契约.md。
"""
import argparse
import json
import sys
import re
import uuid

import qualification as Q
from pathlib import Path

import revenue_model
from _common import atomic_save, ledger_path, load_ledger, now

STATES = ("found", "parked", "verified", "rejected")
TERMINAL = {"verified", "rejected"}
LEGAL = {
    ("found", "verified"), ("found", "rejected"), ("found", "parked"),
    ("parked", "verified"), ("parked", "rejected"),
}
FORMS = ("info", "lookup", "tool", "commercial", "mixed")
REVENUE_KEYS = ("downside", "base", "upside", "volume_needed_for_threshold", "threshold",
                "assumptions_version")


LedgerError = Q.QualificationError


def _require(cond, msg):
    if not cond:
        raise LedgerError(msg)


def _check_evidence(root, refs):
    _require(isinstance(refs, list) and refs, "至少 1 个证据文件")
    for ref in refs:
        _require((Path(root) / ref).is_file(), f"证据文件不存在: {ref}")


def load(root) -> dict:
    return load_ledger(root)


def save(root, ledger) -> None:
    atomic_save(ledger_path(root), ledger)


def register(root, *, slug, primary_keyword, cluster, seed, proxy, evidence, by, reason) -> dict:
    _require(isinstance(slug, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug), "slug 须小写连字符")
    _require(primary_keyword and primary_keyword.strip(), "primary_keyword 必填")
    _require(isinstance(cluster, dict) and type(cluster.get("total_volume")) is int, "cluster.total_volume 须为整数")
    _require(isinstance(cluster.get("keywords"), list), "cluster.keywords 须为数组")
    _require(isinstance(seed, dict) and seed.get("type") in ("root", "small_site", "forum"), "seed.type 须为 root|small_site|forum")
    _require(isinstance(proxy, dict) and Q.number(proxy.get("kd")) and 0 <= proxy["kd"] <= 100, "proxy.kd 必填")
    _require(by and reason and reason.strip(), "by 与 reason 必填")
    _check_evidence(root, evidence)
    for ref in evidence:
        obs, _ = Q.read_observation(root, ref, slug)
        _require(obs['stage'] == 'scan' and isinstance(obs.get('semrush_preview'), dict), '注册须含 scan 预览')
    _require(cluster['total_volume'] > 0, '簇量须为正数')
    terms = [Q.normalize(k['term']) for k in cluster['keywords']]
    _require(terms and len(set(terms)) == len(terms), '支撑词须非空且不重复')
    _require(all(type(k.get('volume')) is int and k['volume'] >= 0 for k in cluster['keywords']), '词量须为非负整数')
    _require(sum(k['volume'] for k in cluster['keywords']) <= cluster['total_volume'], '词表量超过原始总量')
    primary_volume = max((k['volume'] for k in cluster['keywords'] if Q.normalize(k['term']) == Q.normalize(primary_keyword)), default=0)
    _require(cluster['total_volume'] >= 50000 or primary_volume >= 5000, '未达发现准入量')
    ledger = load(root)
    _require(not any(Q.normalize(r['primary_keyword']) == Q.normalize(primary_keyword) for r in ledger['candidates'].values()), '主词已登记')
    _require(slug not in ledger["candidates"], f"slug 已存在: {slug}")
    rec = {
        "slug": slug, "primary_keyword": primary_keyword, "cluster": cluster, "seed": seed,
        "state": "found", "proxy": dict(proxy), "form": None, "revenue": None,
        "evidence_refs": list(evidence),
        "history": [{"at": now(), "from": None, "to": "found", "by": by, "reason": reason, "evidence_refs": list(evidence)}],
    }
    ledger["candidates"][slug] = rec
    save(root, ledger)
    return rec


def _qualify(root, rec, evidence, form, revenue):
    actual_form, actual_revenue, qualification = Q.assess(root, rec, evidence)
    _require(form == actual_form, 'form 与已核验任务组不一致')
    _require(revenue == actual_revenue, 'revenue 必须等于 qualification.py 的完整重算输出')
    _require(actual_revenue['base'] >= revenue_model.THRESHOLD, 'verified 重算收入不足门槛')
    scan_refs = rec['evidence_refs']
    for ref in scan_refs:
        obs, binding = Q.read_observation(root, ref, rec['slug'])
        if obs['stage'] == 'scan':
            qualification['bindings'].append(binding)
    _require(any(b['stage'] == 'scan' for b in qualification['bindings']), '缺 scan 证据')
    return qualification


def requalify(root, slug, *, evidence, by, reason, form, revenue, change_basis=None) -> dict:
    """判据变更后对 rejected 候选的受控翻案:rejected → verified。

    普通 transition 不开这条边(rejected 是终态)。本入口只在门槛、假设表或范围排除
    经用户拍板变更后使用,要求 reason 写明变更依据,并按新门槛重校 base。
    """
    ledger = load(root)
    _require(slug in ledger["candidates"], f"候选不存在: {slug}")
    rec = ledger["candidates"][slug]
    _require(rec["state"] == "rejected", f"requalify 只对 rejected 开放,当前 {rec['state']}")
    _require(by and reason and reason.strip(), "by 与 reason 必填")
    _require(form in FORMS, f"requalify 要求 form ∈ {FORMS}")
    _require(isinstance(revenue, dict) and all(k in revenue for k in REVENUE_KEYS),
             f"requalify 要求 revenue 含 {REVENUE_KEYS}")
    _check_evidence(root, evidence)
    gate = rec['history'][-1].get('gate')
    if gate is None and rec['history'][-1]['reason'].startswith('收入不足'):
        gate = 'revenue'
    _require(gate in ('revenue', 'revenue_prescreen', 'scope'), '竞争门或未知拒绝原因不能因门槛变更翻案')
    _require(Q.nonempty(change_basis), 'requalify 须 --change-basis 写明用户批准的判据变更')
    rec['qualification'] = _qualify(root, rec, evidence, form, revenue)
    rec["form"] = form
    rec["revenue"] = revenue
    rec["state"] = "verified"
    for ref in evidence:
        if ref not in rec["evidence_refs"]:
            rec["evidence_refs"].append(ref)
    rec["history"].append({"at": now(), "from": "rejected", "to": "verified", "by": by,
                           "reason": reason, "change_basis": change_basis, "evidence_refs": list(evidence)})
    save(root, ledger)
    return rec


def transition(root, slug, *, to, evidence, by, reason, form=None, revenue=None, gate=None) -> dict:
    ledger = load(root)
    _require(slug in ledger["candidates"], f"候选不存在: {slug}")
    rec = ledger["candidates"][slug]
    frm = rec["state"]
    _require(to in STATES, f"未知状态: {to}")
    _require((frm, to) in LEGAL, f"非法转移: {frm}→{to}")
    _require(by and reason and reason.strip(), "by 与 reason 必填")
    _check_evidence(root, evidence)
    _require(to != 'rejected' or gate in ('G1', 'G2', 'G3', 'scope', 'revenue', 'revenue_prescreen'), 'rejected 必填 --gate')
    for ref in evidence:
        obs, _ = Q.read_observation(root, ref, slug)
        _require(obs['stage'] == 'verify', '状态转移须 verify 观察')
    if to == 'rejected':
        Q.check_rejection(root, rec, evidence, gate)
    if to == "verified":
        _require(form in FORMS, f"verified 要求 form ∈ {FORMS}")
        _require(isinstance(revenue, dict) and all(k in revenue for k in REVENUE_KEYS),
                 f"verified 要求 revenue 含 {REVENUE_KEYS}")
        rec["qualification"] = _qualify(root, rec, evidence, form, revenue)
    if form is not None:
        _require(form in FORMS, f"form ∈ {FORMS}")
        rec["form"] = form
    if revenue is not None:
        rec["revenue"] = revenue
    rec["state"] = to
    for ref in evidence:
        if ref not in rec["evidence_refs"]:
            rec["evidence_refs"].append(ref)
    rec["history"].append({"at": now(), "from": frm, "to": to, "by": by, "reason": reason, "gate": gate, "evidence_refs": list(evidence)})
    save(root, ledger)
    return rec


def invalidate(root, slug, *, to, evidence, by, reason, gate):
    """审计纠错专用：撤销既有 verified；保留旧记录并归档原报告。"""
    data = load(root)
    _require(slug in data['candidates'], '候选不存在')
    rec = data['candidates'][slug]
    _require(rec['state'] == 'verified', 'invalidate 只用于既有 verified')
    _require(to in ('parked','rejected') and Q.nonempty(by) and Q.nonempty(reason), '纠错须目标状态、执行者与原因')
    _require((to, gate) in (('parked','evidence'), ('rejected','scope')), '证据不足应 parked；范围排除应 rejected')
    _check_evidence(root, evidence)
    for ref in evidence:
        obs, _ = Q.read_observation(root, ref, slug)
        _require(obs['stage'] == 'verify' and Q.nonempty(obs.get('audit_basis')), '纠错须 verify 审计观察与 audit_basis')
        if gate == 'scope':
            _require(any((obs.get('scope_recheck') or {}).get(k) is True for k in Q.SCOPE), '范围纠错须明确命中项')
    archived = []
    token = uuid.uuid4().hex[:12]
    try:
        for ext in ('md','html'):
            source = Path(root) / '报告' / f'{slug}.{ext}'
            if source.exists():
                target = Path(root) / '报告' / '历史' / f'{slug}-{token}.{ext}'
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
                archived.append((source, target))
        rec['state'] = to
        rec['evidence_refs'] = list(dict.fromkeys(rec['evidence_refs'] + evidence))
        rec['history'].append({'at': now(), 'from':'verified', 'to':to, 'by':by, 'reason':reason,
                               'action':'invalidate', 'gate':gate, 'evidence_refs':list(evidence),
                               'archived_reports':[str(dst.relative_to(root)) for _, dst in archived]})
        save(root, data)
    except Exception:
        for source, target in archived:
            target.rename(source)
        raise
    return rec


def set_task_plan(root, slug, *, plan, by, reason):
    data = load(root)
    _require(slug in data['candidates'], '候选不存在')
    rec = data['candidates'][slug]
    _require(rec['state'] in ('found','parked'), '任务计划只可用于 found/parked')
    _require(Q.nonempty(by) and Q.nonempty(reason), '计划须执行者与依据')
    Q.validate_task_plan(plan, rec)
    if rec.get('task_plan'):
        _require(rec['task_plan'] == plan, '任务清单已冻结；不能在看到核验结果后改核心组或删组')
        return rec
    rec['task_plan'] = plan
    rec['history'].append({'at':now(), 'from':rec['state'], 'to':rec['state'], 'by':by, 'reason':reason,
                           'action':'set_task_plan', 'task_plan':plan})
    save(root, data)
    return rec


def refresh_cluster(root, slug, *, cluster, evidence, by, reason):
    """补采词表只更新非终态；留存旧量级，旧观察不覆盖。"""
    data = load(root)
    _require(slug in data['candidates'], '候选不存在')
    rec = data['candidates'][slug]
    _require(rec['state'] in ('found','parked'), '仅可补采 found/parked')
    _require(Q.nonempty(by) and Q.nonempty(reason), '补采须执行者与原因')
    _check_evidence(root, evidence)
    for ref in evidence:
        obs, _ = Q.read_observation(root, ref, slug)
        _require(obs['stage'] == 'scan' and isinstance(obs.get('semrush_preview'), dict), '补采须 scan 预览/导出依据')
    _require(type(cluster.get('total_volume')) is int and cluster['total_volume'] > 0, '总量须正整数')
    rows = cluster.get('keywords')
    _require(isinstance(rows, list) and rows and all(Q.nonempty(r.get('term')) and type(r.get('volume')) is int and r['volume'] >= 0 for r in rows), '词表无效')
    _require(len({Q.normalize(r['term']) for r in rows}) == len(rows), '词表重复')
    _require(sum(r['volume'] for r in rows) <= cluster['total_volume'], '词表量超过原始总量')
    if rec.get('task_plan'):
        Q.validate_task_plan(rec['task_plan'], dict(rec, cluster=cluster))
    previous = rec['cluster']
    rec['cluster'] = cluster
    rec['evidence_refs'] = list(dict.fromkeys(rec['evidence_refs'] + evidence))
    rec['history'].append({'at':now(), 'from':rec['state'], 'to':rec['state'], 'by':by, 'reason':reason,
                           'action':'refresh_cluster', 'previous_cluster':previous, 'evidence_refs':list(evidence)})
    save(root, data)
    return rec


def list_candidates(root, state=None) -> list:
    recs = list(load(root)["candidates"].values())
    if state:
        recs = [r for r in recs if r["state"] == state]
    return sorted(recs, key=lambda r: r["slug"])


def _json_arg(text, name):
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LedgerError(f"{name} 不是合法 JSON: {e}")


def _revenue_arg(args):
    if args.revenue_file:
        obj = _json_arg(Path(args.revenue_file).read_text(encoding='utf-8'), '--revenue-file')
        return obj.get('revenue', obj)
    return _json_arg(args.revenue_json, '--revenue-json') if args.revenue_json else None


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="xinci-simple 账本写入口")
    ap.add_argument("--data-root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    r.add_argument("--slug", required=True)
    r.add_argument("--primary-keyword", required=True)
    cg = r.add_mutually_exclusive_group(required=True)
    cg.add_argument("--cluster-json")
    cg.add_argument("--cluster-file")
    r.add_argument("--seed-json", required=True)
    r.add_argument("--proxy-json", required=True)
    r.add_argument("--evidence", action="append", required=True)
    r.add_argument("--by", required=True)
    r.add_argument("--reason", required=True)
    t = sub.add_parser("transition")
    t.add_argument("--slug", required=True)
    t.add_argument("--to", required=True, choices=STATES)
    t.add_argument("--evidence", action="append", required=True)
    t.add_argument("--by", required=True)
    t.add_argument("--reason", required=True)
    t.add_argument("--form", default=None, choices=FORMS)
    tg = t.add_mutually_exclusive_group()
    tg.add_argument("--revenue-json")
    tg.add_argument("--revenue-file")
    t.add_argument("--gate", choices=("G1", "G2", "G3", "scope", "revenue", "revenue_prescreen"))
    rq = sub.add_parser("requalify", help="判据变更后的受控翻案:rejected → verified")
    rq.add_argument("--slug", required=True)
    rq.add_argument("--evidence", action="append", required=True)
    rq.add_argument("--by", required=True)
    rq.add_argument("--reason", required=True)
    rq.add_argument("--form", required=True, choices=FORMS)
    rg = rq.add_mutually_exclusive_group(required=True)
    rg.add_argument("--revenue-json")
    rg.add_argument("--revenue-file")
    rq.add_argument("--change-basis", required=True)
    tp = sub.add_parser('set-task-plan', help='核验前登记并冻结核心/支撑任务组')
    tp.add_argument('--slug', required=True)
    tp.add_argument('--plan-file', required=True)
    tp.add_argument('--by', required=True)
    tp.add_argument('--reason', required=True)
    inv = sub.add_parser('invalidate', help='审计撤销既有 verified，并归档原报告')
    inv.add_argument('--slug', required=True)
    inv.add_argument('--to', required=True, choices=('parked','rejected'))
    inv.add_argument('--gate', required=True, choices=('evidence','scope'))
    refresh = sub.add_parser('refresh-cluster', help='补采 found/parked 的词表')
    refresh.add_argument('--slug', required=True)
    fg = refresh.add_mutually_exclusive_group(required=True)
    fg.add_argument('--cluster-json')
    fg.add_argument('--cluster-file')
    for parser in (inv, refresh):
        parser.add_argument('--evidence', action='append', required=True)
        parser.add_argument('--by', required=True)
        parser.add_argument('--reason', required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--state", default=None, choices=STATES)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "register":
            rec = register(root, slug=a.slug, primary_keyword=a.primary_keyword,
                           cluster=_json_arg(Path(a.cluster_file).read_text() if a.cluster_file else a.cluster_json, "cluster"),
                           seed=_json_arg(a.seed_json, "--seed-json"),
                           proxy=_json_arg(a.proxy_json, "--proxy-json"),
                           evidence=a.evidence, by=a.by, reason=a.reason)
            print(f"已登记 {rec['slug']} → found")
        elif a.cmd == "transition":
            rec = transition(root, a.slug, to=a.to, evidence=a.evidence, by=a.by, reason=a.reason,
                             form=a.form,
                             revenue=_revenue_arg(a), gate=a.gate)
            print(f"{rec['slug']}:{rec['history'][-2]['to']} → {rec['state']}")
        elif a.cmd == "requalify":
            rec = requalify(root, a.slug, evidence=a.evidence, by=a.by, reason=a.reason,
                            form=a.form, revenue=_revenue_arg(a), change_basis=a.change_basis)
            print(f"{rec['slug']}:rejected → {rec['state']}(判据变更重审)")
        elif a.cmd == 'set-task-plan':
            set_task_plan(root, a.slug, plan=_json_arg(Path(a.plan_file).read_text(encoding='utf-8'), 'task plan'), by=a.by, reason=a.reason)
            print(f'{a.slug}: 任务清单已登记')
        elif a.cmd == 'invalidate':
            rec = invalidate(root, a.slug, to=a.to, gate=a.gate, evidence=a.evidence, by=a.by, reason=a.reason)
            print(f"{a.slug}:verified → {rec['state']}（审计纠错）")
        elif a.cmd == 'refresh-cluster':
            refresh_cluster(root, a.slug, cluster=_json_arg(Path(a.cluster_file).read_text() if a.cluster_file else a.cluster_json, 'cluster'), evidence=a.evidence, by=a.by, reason=a.reason)
            print(f'{a.slug}: 已追加量级补采')
        else:
            for rec in list_candidates(root, a.state):
                score = (rec.get("proxy") or {}).get("rank_score")
                print(f"{rec['state']:9} {rec['slug']:40} 簇量 {rec['cluster']['total_volume']:>8} "
                      f"rank {score if score is not None else '-'}")
    except (Q.QualificationError, KeyError, TypeError, OSError) as e:
        print(f"拒收: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
