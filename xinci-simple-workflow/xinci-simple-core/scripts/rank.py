#!/usr/bin/env python3
"""代理排序:决定谁先进现场核验。只排序,不否决。

五项:kd(反向)、cluster.total_volume、low_dr_count、ugc_count、content_age_median_days。
每项在当前 found 池内 min-max 归一化到 0–1,缺失取 0.5,等权平均。
池内只有一个候选或某项全相等时该项取 0.5。排序口径见选词契约 §4。
"""
import argparse
import sys

import ledger as L

DIMS = (  # (取值函数, 是否反向)
    (lambda r: r["proxy"].get("kd"), True),
    (lambda r: r["cluster"].get("total_volume"), False),
    (lambda r: r["proxy"].get("low_dr_count"), False),
    (lambda r: r["proxy"].get("ugc_count"), False),
    (lambda r: r["proxy"].get("content_age_median_days"), False),
)


def _normalize(values):
    present = [v for v in values if isinstance(v, (int, float))]
    if len(present) < 2 or max(present) == min(present):
        return [0.5 for _ in values]
    lo, hi = min(present), max(present)
    return [((v - lo) / (hi - lo)) if isinstance(v, (int, float)) else 0.5 for v in values]


def rank_all(root, write=False) -> dict:
    recs = L.list_candidates(root, state="found")
    if not recs:
        return {}
    cols = []
    for getter, reverse in DIMS:
        norm = _normalize([getter(r) for r in recs])
        cols.append([1 - x if reverse else x for x in norm])
    scores = {r["slug"]: round(sum(col[i] for col in cols) / len(DIMS), 4) for i, r in enumerate(recs)}
    if write:
        ledger = L.load(root)
        for slug, s in scores.items():
            ledger["candidates"][slug]["proxy"]["rank_score"] = s
        L.save(root, ledger)
    return scores


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="对 found 候选算代理排序分并回写账本")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--top", type=int, default=0, help="只打印前 N")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    scores = rank_all(root, write=not a.no_write)
    rows = sorted(scores.items(), key=lambda kv: -kv[1])
    if a.top:
        rows = rows[:a.top]
    for slug, s in rows:
        print(f"{s:.4f}  {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
