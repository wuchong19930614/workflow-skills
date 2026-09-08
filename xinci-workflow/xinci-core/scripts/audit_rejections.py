#!/usr/bin/env python3
"""只读筛选历史结论的复核样本；不声称现场重审或正式误杀率。"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import data_root
from _common import load_ledger, ledger_path
import screen_index


def build(root, per_group=2):
    root = Path(root)
    ledger = load_ledger(root)
    candidates = ledger.get("candidates", {})
    groups = defaultdict(list)
    versions, sources, missing = Counter(), Counter(), []
    for slug, rec in sorted(candidates.items()):
        if rec.get("state") not in {"rejected", "disqualified"}:
            continue
        observations = []
        refs = rec.get("evidence_refs", [])
        for ref in refs:
            rel = Path(ref)
            if rel.is_absolute() or ".." in rel.parts or rel.suffix != ".json":
                continue
            try:
                obs = json.loads((root / rel).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                missing.append(ref)
                continue
            observations.append(obs)
        versions.update(str(o.get("schema_version", 1)) for o in observations)
        source_hosts = sorted({urlsplit(u).netloc for o in observations for u in o.get("source_urls", [])})
        sources.update(source_hosts)
        text = "\n".join(str(p) for o in observations for p in o.get("points", []))
        text += "\n" + "\n".join(str(h.get("reason", "")) for h in rec.get("history", []))
        tags = []
        if rec.get("state") == "disqualified":
            tags.append("评分认定")
        if any(k in text for k in ("无官方计数", "计数口径", "受约束主体无")):
            tags.append("计数前提")
        if any(k in text for k in ("签字", "持牌机构", "无法律效力")):
            tags.append("法律效力逐线边界")
        if any(k in text for k in ("免费", "官方工具", "受理方", "计算器")):
            tags.append("已有供给")
        if any(k in text for k in ("未登录", "未实测", "维护中", "小站无数据", "not fully available")):
            tags.append("证据访问或覆盖")
        if rec.get("gates", {}).get("G2") == "veto":
            tags.append("G2意图与身份")
        if any(set(o.get("g6_lines", {})) == {"subscription", "advertising"}
               or set(o.get("g6_tentative_lines", {})) == {"subscription", "advertising"}
               for o in observations):
            tags.append("历史双线")
        for tag in tags or ["其他否决"]:
            groups[tag].append({"slug": slug, "state": rec["state"], "score": rec.get("score"),
                "first_observed_at": rec.get("first_observed_at"), "source_hosts": source_hosts,
                "evidence_refs": refs, "review_status": "needs_review"})
    index = screen_index.load(root, strict=True)
    path = ledger_path(root)
    return {"scope": "offline_review_candidates_only", "ledger_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "gate_version": screen_index.GATE_VERSION,
            "candidate_count": len(candidates), "states": dict(Counter(c.get("state") for c in candidates.values())),
            "observation_versions": dict(versions), "source_hosts": dict(sources.most_common(12)),
            "index_count": len(index), "index_versions": dict(Counter(r.get("gate_version", "unknown") for r in index)),
            "groups": {k: {"count": len(v), "samples": v[:per_group]} for k, v in sorted(groups.items())},
            "missing_evidence": sorted(set(missing)),
            "limitations": "标签可重叠；样本是按 slug 稳定选取的诊断样本，不是随机估计；未现场重审，不计算误杀率，不改写历史。"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root")
    parser.add_argument("--per-group", type=int, default=2)
    args = parser.parse_args(argv)
    if args.per_group < 1:
        parser.error("--per-group 必须 ≥1")
    root = data_root.resolve_or_exit(args.data_root)
    print(json.dumps(build(root, args.per_group), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
