#!/usr/bin/env python3
"""从已登记观察生成只读导航；不推断有效证据、不合并门结论、不回写摘要。"""
import argparse
import hashlib
import json
from pathlib import Path

import data_root
from _common import ledger_path, parse_aware_timestamp
from _constants import SLUG_RE


def build(root, slug):
    root = Path(root).resolve()
    if not SLUG_RE.fullmatch(slug):
        raise ValueError("候选 slug 非法")
    raw = ledger_path(root).read_bytes()
    rec = json.loads(raw)["candidates"].get(slug)
    if not isinstance(rec, dict):
        raise ValueError(f"账本中没有候选 {slug}")
    rows, errors, latest, seen, observed = [], [], {}, set(), []
    for ref in rec.get("evidence_refs", []):
        if isinstance(ref, str) and ref in seen:
            continue
        try:
            if not isinstance(ref, str):
                raise ValueError("引用必须是字符串")
            rel = Path(ref)
            if (rel.is_absolute() or ".." in rel.parts or len(rel.parts) < 3
                    or rel.parts[:2] != ("证据", slug) or rel.suffix != ".json"):
                raise ValueError("引用不是本候选的相对观察路径")
            path = (root / rel).resolve()
            if not path.is_relative_to((root / "证据" / slug).resolve()) or not path.is_relative_to(root):
                raise ValueError("观察路径越界")
            seen.add(ref)
            obs = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(obs, dict) or obs.get("slug") != slug:
                raise ValueError("观察候选不匹配")
            stage = obs.get("stage")
            if stage not in {"scan", "track", "qualify", "decide"}:
                raise ValueError("观察阶段非法")
            when = parse_aware_timestamp(obs.get("observed_at"), "观察时间", ValueError)
            observed.append((when, ref, obs))
            rows.append({"ref": ref, "stage": stage, "observed_at": obs["observed_at"],
                         "schema_version": obs.get("schema_version", 1)})
            if stage not in latest or when > latest[stage][0]:
                latest[stage] = (when, [ref])
            elif when == latest[stage][0]:
                latest[stage][1].append(ref)
        except (OSError, ValueError, TypeError) as exc:
            errors.append({"ref": ref, "reason": str(exc)})
    start = [ref for stage in sorted(latest) for ref in latest[stage][1]]
    # 最近登记的不一定是最新观察；补录旧日证据也必须可见。
    if rows and rows[-1]["ref"] not in start:
        start.append(rows[-1]["ref"])
    review_gates, unknown_lines, review_times = {}, {}, {}
    for when, ref, obs in sorted(observed, key=lambda row: (row[0], row[1])):
        if obs["stage"] in {"scan", "track"} and "g6_tentative_lines" in obs:
            unknown_lines = {k: ref for k, v in obs["g6_tentative_lines"].items()
                             if v == "tentative_inconclusive"}
            if unknown_lines and "G3" not in obs.get("gates", {}):
                review_gates["G3"] = ref
                review_times["G3"] = when
        if obs["stage"] == "qualify" and "g6_lines" in obs:
            unknown_lines = {k: ref for k, v in obs["g6_lines"].items() if v == "inconclusive"}
        for gate in obs.get("gates", {}):
            if gate in review_times and when > review_times[gate]:
                review_gates.pop(gate, None)
    return {"slug": slug, "lane": rec.get("lane", "new"), "state": rec.get("state"),
            "review_required_gates": review_gates, "unknown_income_lines": unknown_lines,
            "ledger_sha256": hashlib.sha256(raw).hexdigest(), "gates": rec.get("gates", {}),
            "qualify_pending": rec.get("qualify_pending"),
            "latest_history": rec.get("history", [])[-1:] or [],
            "start_refs": start, "observations": rows, "errors": errors,
            "boundary": "start_refs 仅为阅读起点。打开这些观察及其 coverage/income/risk 引用；"
                        "按缺口、任务改写、替代关系或冲突展开旧证据。时间较新不自动覆盖旧结论，"
                        "无编号旧观察按文件和要点引用。未登记文件不在本索引内；来源引用不代表本次打开。"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    parser.add_argument("--data-root")
    args = parser.parse_args(argv)
    root = data_root.resolve_or_exit(args.data_root)
    try:
        result = build(root, args.slug)
    except (OSError, ValueError, KeyError) as exc:
        print(f"证据索引失败: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
