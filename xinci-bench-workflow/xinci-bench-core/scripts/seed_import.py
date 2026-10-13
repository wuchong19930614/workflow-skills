#!/usr/bin/env python3
"""从 xinci-simple 数据区只读导入:标杆种子、同类站种子、旧词库、旧裁决。幂等。

旧数据区路径必须显式传入;导入前后对读过的旧文件逐个算 SHA-256,不一致就报错。
"""
import argparse
import json
import re
import sys
from pathlib import Path

import data_root
from _common import (LEXICON_REL, MANUAL_SEEDS_REL, SEEDS_REL, VERDICTS_REL, BenchError,
                     atomic_save, load_json, now, require, sha256_file)
from seeds import ROLES, normalize_domain

AS_LIMIT = 30
EXCLUDED_TYPES = {"official", "brand", "forum", "video"}
PLATFORMS = {"pinterest.com", "play.google.com", "scribd.com", "reddit.com", "facebook.com",
             "youtube.com", "quora.com", "amazon.com"}
_GOV = re.compile(r"(^|\.)[a-z0-9-]*gov(\.|$)|\.(edu|mil)$")
_HOST = re.compile(r"^(?:https?://)?([^/\s?#]+)")
_DOMAIN_IN_TEXT = re.compile(r"\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b")


def _legacy_files(legacy_root: Path) -> list:
    files = [legacy_root / "账本" / "候选账本.json"]
    require(files[0].is_file(), f"旧账本不存在: {files[0]}")
    files += sorted((legacy_root / "证据").glob("*/*.json"))
    return files


def _host(row) -> str:
    m = _HOST.match(row.get("url") or row.get("domain") or "")
    if not m:
        return ""
    try:
        return normalize_domain(m.group(1))
    except BenchError:
        return ""


def benchmark_candidates(legacy_root: Path) -> dict:
    """旧证据 serp_top10 → {域名: {source_ref, as_recorded}};规则见设计稿 §5.4。"""
    seen = {}
    for f in sorted((legacy_root / "证据").glob("*/*.json")):
        try:
            obs = load_json(f)
        except ValueError:
            continue
        for row in obs.get("serp_top10") or []:
            h = _host(row)
            if not h:
                continue
            info = seen.setdefault(h, {"types": set(), "as": [], "ref": f"{f.parent.name}/{f.name}"})
            info["types"].add(row.get("type"))
            if row.get("dr") is not None:
                info["as"].append(row["dr"])
    out = {}
    for h, info in seen.items():
        if not info["as"] or _GOV.search(h) or h in PLATFORMS or info["types"] & EXCLUDED_TYPES:
            continue
        known = [v for v in info["as"] if v != 0]          # 0 视为未测
        if known and min(known) >= AS_LIMIT:
            continue
        out[h] = {"source_ref": "xinci-simple:证据/" + info["ref"],
                  "as_recorded": min(known) if known else None}
    return out


def sibling_candidates(ledger: dict) -> dict:
    out = {}
    for slug, c in ledger["candidates"].items():
        seed = c.get("seed") or {}
        if seed.get("type") != "small_site":
            continue
        for m in _DOMAIN_IN_TEXT.findall(str(seed.get("value", "")).lower()):
            try:
                out.setdefault(normalize_domain(m), {"source_ref": f"xinci-simple:账本/{slug}.seed"})
            except BenchError:
                pass
    return out


def lexicon(ledger: dict) -> dict:
    """旧账本全部逐词量,按小写词去重;重复时保留测量更晚的那条。"""
    words = {}
    for slug, c in ledger["candidates"].items():
        measured = str((c.get("seed") or {}).get("queried_at", ""))[:10] or None
        for k in (c.get("cluster") or {}).get("keywords") or []:
            term = str(k.get("term", "")).strip().lower()
            if not term:
                continue
            row = {"volume": k.get("volume"), "kd": k.get("kd"), "slug": slug, "measured_at": measured}
            old = words.get(term)
            if old is None or (measured or "") > (old["measured_at"] or ""):
                words[term] = row
    return words


def verdicts(ledger: dict) -> dict:
    out = {}
    for slug, c in ledger["candidates"].items():
        final = [h for h in c.get("history") or [] if h.get("to") == c["state"]]
        last = final[-1] if final else {}
        gated = [h for h in final if h.get("gate")]
        out[slug] = {"primary_keyword": c.get("primary_keyword"), "state": c["state"],
                     "gate": gated[-1]["gate"] if gated else None, "reason": last.get("reason")}
    return out


def import_legacy(root, legacy_root) -> dict:
    root, legacy_root = Path(root), Path(legacy_root)
    files = _legacy_files(legacy_root)
    before = {str(f): sha256_file(f) for f in files}
    ledger = load_json(files[0])
    bench, sib = benchmark_candidates(legacy_root), sibling_candidates(ledger)
    manual = load_json(root / MANUAL_SEEDS_REL)["seeds"]
    pool = load_json(root / SEEDS_REL)
    added = {"benchmark": 0, "sibling": 0, "manual": 0}

    def put(domain, role, ref, key, extra=None):
        if domain in pool["seeds"]:
            return
        pool["seeds"][domain] = {"source": "legacy", "source_ref": ref, "role": role,
                                 "added_at": now(), "status": "pending", **(extra or {})}
        added[key] += 1

    for item in manual:
        role = item.get("role", "benchmark")     # 不满足 B2、只用来查同类站的写 sibling
        require(role in ROLES, f"手工种子 {item.get('domain')} 的 role 须为 {ROLES}")
        put(normalize_domain(item["domain"]), role, MANUAL_SEEDS_REL, "manual", {"note": item.get("note")})
    for d, info in bench.items():
        put(d, "benchmark", info["source_ref"], "benchmark", {"as_recorded": info["as_recorded"]})
    for d, info in sib.items():
        put(d, "sibling", info["source_ref"], "sibling")
    words, ver = lexicon(ledger), verdicts(ledger)
    after = {str(f): sha256_file(f) for f in files}
    require(before == after, "旧数据区在导入期间被改动,已停止;请检查是否有其他进程在写 xinci-simple 数据区")
    digest = sha256_file(files[0])
    atomic_save(root / SEEDS_REL, pool)
    atomic_save(root / LEXICON_REL, {"schema_version": 1, "imported_from": str(legacy_root),
                                     "ledger_sha256": digest, "words": words})
    atomic_save(root / VERDICTS_REL, {"schema_version": 1, "imported_from": str(legacy_root),
                                      "ledger_sha256": digest, "candidates": ver})
    return {"seeds_added": added, "seeds_total": len(pool["seeds"]),
            "benchmark_candidates": len(bench), "sibling_candidates": len(sib),
            "lexicon_words": len(words), "verdicts": len(ver), "legacy_files_checked": len(files)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--legacy-root", required=True, help="xinci-simple 数据区路径,只读")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        print(json.dumps(import_legacy(root, a.legacy_root), ensure_ascii=False, indent=2))
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
