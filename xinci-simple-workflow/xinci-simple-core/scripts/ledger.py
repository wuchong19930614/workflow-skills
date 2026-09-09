#!/usr/bin/env python3
"""候选账本:唯一写入口。4 态、合法转移表、证据必须存在、history 只追加、原子写。

判据不在这里:这里只保证"状态机不被违反、证据可追溯"。判据看 选词契约.md。
"""
import argparse
import json
import sys
from pathlib import Path

from _common import atomic_save, ledger_path, load_ledger, now

STATES = ("found", "parked", "verified", "rejected")
TERMINAL = {"verified", "rejected"}
LEGAL = {
    ("found", "verified"), ("found", "rejected"), ("found", "parked"),
    ("parked", "verified"), ("parked", "rejected"),
}
FORMS = ("info", "lookup", "tool", "commercial", "mixed")
REVENUE_KEYS = ("downside", "base", "upside", "volume_needed_for_500", "assumptions_version")


class LedgerError(Exception):
    pass


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
    _require(slug and slug == slug.lower() and " " not in slug, "slug 须小写且无空格")
    _require(primary_keyword and primary_keyword.strip(), "primary_keyword 必填")
    _require(isinstance(cluster, dict) and isinstance(cluster.get("total_volume"), int), "cluster.total_volume 须为整数")
    _require(isinstance(cluster.get("keywords"), list), "cluster.keywords 须为数组")
    _require(isinstance(seed, dict) and seed.get("type") in ("root", "small_site", "forum"), "seed.type 须为 root|small_site|forum")
    _require(isinstance(proxy, dict) and isinstance(proxy.get("kd"), (int, float)), "proxy.kd 必填")
    _require(by and reason and reason.strip(), "by 与 reason 必填")
    _check_evidence(root, evidence)
    ledger = load(root)
    _require(slug not in ledger["candidates"], f"slug 已存在: {slug}")
    rec = {
        "slug": slug, "primary_keyword": primary_keyword, "cluster": cluster, "seed": seed,
        "state": "found", "proxy": dict(proxy), "form": None, "revenue": None,
        "evidence_refs": list(evidence),
        "history": [{"at": now(), "from": None, "to": "found", "by": by, "reason": reason}],
    }
    ledger["candidates"][slug] = rec
    save(root, ledger)
    return rec


def transition(root, slug, *, to, evidence, by, reason, form=None, revenue=None) -> dict:
    ledger = load(root)
    _require(slug in ledger["candidates"], f"候选不存在: {slug}")
    rec = ledger["candidates"][slug]
    frm = rec["state"]
    _require(to in STATES, f"未知状态: {to}")
    _require((frm, to) in LEGAL, f"非法转移: {frm}→{to}")
    _require(by and reason and reason.strip(), "by 与 reason 必填")
    _check_evidence(root, evidence)
    if to == "verified":
        _require(form in FORMS, f"verified 要求 form ∈ {FORMS}")
        _require(isinstance(revenue, dict) and all(k in revenue for k in REVENUE_KEYS),
                 f"verified 要求 revenue 含 {REVENUE_KEYS}")
        _require(isinstance(revenue["base"], (int, float)) and revenue["base"] >= 500,
                 "verified 要求 revenue.base ≥ 500;不达标应转 rejected")
    if form is not None:
        _require(form in FORMS, f"form ∈ {FORMS}")
        rec["form"] = form
    if revenue is not None:
        rec["revenue"] = revenue
    rec["state"] = to
    for ref in evidence:
        if ref not in rec["evidence_refs"]:
            rec["evidence_refs"].append(ref)
    rec["history"].append({"at": now(), "from": frm, "to": to, "by": by, "reason": reason})
    save(root, ledger)
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


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="xinci-simple 账本写入口")
    ap.add_argument("--data-root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    r.add_argument("--slug", required=True)
    r.add_argument("--primary-keyword", required=True)
    r.add_argument("--cluster-json", required=True)
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
    t.add_argument("--revenue-json", default=None)
    ls = sub.add_parser("list")
    ls.add_argument("--state", default=None, choices=STATES)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "register":
            rec = register(root, slug=a.slug, primary_keyword=a.primary_keyword,
                           cluster=_json_arg(a.cluster_json, "--cluster-json"),
                           seed=_json_arg(a.seed_json, "--seed-json"),
                           proxy=_json_arg(a.proxy_json, "--proxy-json"),
                           evidence=a.evidence, by=a.by, reason=a.reason)
            print(f"已登记 {rec['slug']} → found")
        elif a.cmd == "transition":
            rec = transition(root, a.slug, to=a.to, evidence=a.evidence, by=a.by, reason=a.reason,
                             form=a.form,
                             revenue=_json_arg(a.revenue_json, "--revenue-json") if a.revenue_json else None)
            print(f"{rec['slug']}:{rec['history'][-2]['to']} → {rec['state']}")
        else:
            for rec in list_candidates(root, a.state):
                score = (rec.get("proxy") or {}).get("rank_score")
                print(f"{rec['state']:9} {rec['slug']:40} 簇量 {rec['cluster']['total_volume']:>8} "
                      f"rank {score if score is not None else '-'}")
    except LedgerError as e:
        print(f"拒收: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
