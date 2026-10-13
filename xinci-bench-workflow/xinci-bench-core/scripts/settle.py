#!/usr/bin/env python3
"""结算一个方向:重算模型 → 固定绑定 → 生成决策书 → 转移状态 → 校验。

中断后用同一条命令重跑即可恢复:已转移的只补文档与校验,不重复写 history。
"""
import argparse
import shutil
import sys
from pathlib import Path

import bench_model
import build_doc
import data_root
import ledger as L
import validate_ledger
import write_observation as W
from _common import BenchError, load_ledger, now, require, save_ledger, sha256_file


def _archive_docs(root, slug):
    md, html = L.doc_paths(root, slug)
    if not md.is_file():
        return
    tag = sha256_file(md)[:12]
    dest = Path(root) / "文档" / "历史"
    dest.mkdir(parents=True, exist_ok=True)
    for p in (md, html):
        if p.is_file():
            shutil.move(str(p), str(dest / f"{slug}-{tag}{p.suffix}"))


def settle(root, slug, verdict, gate=None, reason="", biggest_unknown="", by="xinci-bench-assess",
           scope_hit=None, on=None) -> dict:
    require(verdict in ("go", "rejected", "parked"), "verdict 须为 go/rejected/parked")
    require(isinstance(biggest_unknown, str) and biggest_unknown.strip(), "biggest_unknown 须写最可能让结论翻转的一项")
    ledger = load_ledger(root)
    rec = ledger["directions"].get(slug)
    require(rec, f"没有方向 {slug}")
    if rec["state"] == verdict:            # 恢复:已转移,只补文档与校验
        dec = rec.get("decision") or {}
        require(dec.get("verdict") == verdict and dec.get("gate") == gate, "已结算的结论与本次参数不一致,不能覆盖")
        if not L.docs_consistent(root, slug):
            build_doc.build(root, slug)
    else:
        require(rec["state"] in L.LEGAL and verdict in L.LEGAL[rec["state"]], f"非法结算 {rec['state']} → {verdict}")
        for ref in rec["evidence_refs"]:      # 先确认引用的观察都在且合规,再算绑定
            W.read(root, ref)
        try:
            rec["model"] = bench_model.compute(rec)
        except BenchError:
            require(verdict != "go" and gate != "revenue", "go 与收入否决必须能完成测算")
            rec["model"] = None
        rec["decision"] = {"verdict": verdict, "gate": gate, "reason": reason.strip(),
                           "biggest_unknown": biggest_unknown.strip(), "scope_hit": scope_hit,
                           "decided_at": now()}
        rec["bindings"] = {"bound_at": now(), "files": [
            {"ref": ref, "sha256": sha256_file(Path(root) / ref)} for ref in rec["evidence_refs"]]}
        save_ledger(root, ledger)
        if rec["state"] == "parked":
            _archive_docs(root, slug)
        build_doc.build(root, slug)
        L.transition(root, slug, verdict, gate, reason, by, on)
    rec = load_ledger(root)["directions"][slug]
    errs = validate_ledger.check_direction(root, slug, rec)
    require(not errs, "结算后校验失败: " + "; ".join(errs))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--verdict", required=True, choices=("go", "rejected", "parked"))
    ap.add_argument("--gate", choices=L.GATES)
    ap.add_argument("--scope-hit", choices=L.SCOPE_ITEMS)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--biggest-unknown", required=True)
    ap.add_argument("--by", default="xinci-bench-assess")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        rec = settle(root, a.slug, a.verdict, a.gate, a.reason, a.biggest_unknown, a.by, a.scope_hit)
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    md, html = L.doc_paths(root, a.slug)
    print(f"{a.slug}: {rec['state']}\n决策书: {md}\n        {html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
