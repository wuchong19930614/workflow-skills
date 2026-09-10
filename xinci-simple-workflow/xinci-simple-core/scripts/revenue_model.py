#!/usr/bin/env python3
"""三情景收入模型。纯函数 + CLI。假设表版本化,改假设先改 VERSION。

base 公式(选词契约 §收入模型):
  info/lookup: 任务组量 × CTR 0.07 / 1000 × RPM[niche]
  tool:        任务组量 × CTR 0.10 / 1000 × RPM[niche]
  commercial:  任务组量 × CTR 0.07 × 0.15 × 0.03 × 30
  mixed:       组内 min(info, commercial);多组聚合由 qualification.py 完成。
折减(乘在 CTR 上):AIO 存在未完成 ×0.6;强完整结果 1–2 个 ×0.7。
downside = CTR ×0.5;upside = CTR ×1.5。
门槛 THRESHOLD 由用户决定,变更须同时更新 VERSION(见 选词契约.md §6)。
"""
import argparse
import json
import math
import sys

VERSION = "2026-09-09.2"
THRESHOLD = 200
FORMS = ("info", "lookup", "tool", "commercial", "mixed")
RPM = {"tech": 10, "home": 18, "hobby": 12}
CTR = {"info": 0.07, "lookup": 0.07, "tool": 0.10, "commercial": 0.07}
AFFILIATE = {"outbound_ctr": 0.15, "conversion": 0.03, "commission": 30}
HAIRCUT_AIO = 0.6
HAIRCUT_STRONG = 0.7


def _ctr_multiplier(aio_present, strong_complete_count):
    m = 1.0
    if aio_present:
        m *= HAIRCUT_AIO
    if strong_complete_count in (1, 2):
        m *= HAIRCUT_STRONG
    return m


def _monthly(form, volume, niche, ctr_scale):
    """单一形态在给定 CTR 缩放下的月收入。"""
    if form == "commercial":
        clicks = volume * CTR["commercial"] * ctr_scale
        return clicks * AFFILIATE["outbound_ctr"] * AFFILIATE["conversion"] * AFFILIATE["commission"]
    sessions = volume * CTR[form] * ctr_scale
    return sessions / 1000 * RPM[niche]


def _base_fn(form, niche, mult):
    def f(volume, scale=1.0):
        s = mult * scale
        if form == "mixed":
            return min(_monthly("info", volume, niche, s), _monthly("commercial", volume, niche, s))
        return _monthly(form, volume, niche, s)
    return f


def model(form, cluster_volume, niche="tech", aio_present=False, strong_complete_count=0) -> dict:
    if form not in FORMS:
        raise ValueError(f"form 须为 {FORMS}")
    if type(cluster_volume) not in (int, float) or not math.isfinite(cluster_volume) or cluster_volume <= 0:
        raise ValueError("cluster_volume 须为正数")
    if niche not in RPM:
        raise ValueError(f"niche 须为 {tuple(RPM)}")
    if type(aio_present) is not bool:
        raise ValueError("aio_present 必须为布尔值")
    if type(strong_complete_count) is not int or strong_complete_count not in (0, 1, 2):
        raise ValueError("strong_complete_count 只能是 0/1/2;≥3 由 G3 否决,不进收入模型")
    f = _base_fn(form, niche, _ctr_multiplier(aio_present, strong_complete_count))
    base = f(cluster_volume)
    per_unit = base / cluster_volume  # 所有公式对簇量线性
    return {
        "downside": round(f(cluster_volume, 0.5), 2),
        "base": round(base, 2),
        "upside": round(f(cluster_volume, 1.5), 2),
        "volume_needed_for_threshold": math.ceil(THRESHOLD / per_unit),
        "threshold": THRESHOLD,
        "assumptions_version": VERSION,
        "inputs": {"form": form, "cluster_volume": cluster_volume, "niche": niche,
                   "aio_present": bool(aio_present), "strong_complete_count": strong_complete_count},
    }


def upper_bound(cluster_volume, possible_forms=None, possible_niches=None):
    """当前假设表内的无折减上限；形态/垂类未知则覆盖所有允许选项。"""
    forms = list(FORMS) if possible_forms is None else possible_forms
    niches = list(RPM) if possible_niches is None else possible_niches
    if not forms or not niches:
        raise ValueError('可能形态/垂类不能为空')
    rows = [model(form, cluster_volume, niche) for form in forms for niche in niches]
    best = max(rows, key=lambda r: r['base'])
    return {'upper_bound': best['base'], 'can_reject': best['base'] < THRESHOLD,
            'threshold': THRESHOLD, 'assumptions_version': VERSION,
            'cluster_volume': cluster_volume, 'possible_forms': forms, 'possible_niches': niches,
            'best_inputs': best['inputs']}


def passes(revenue) -> bool:
    return isinstance(revenue.get("base"), (int, float)) and revenue["base"] >= THRESHOLD


def main(argv=None):
    ap = argparse.ArgumentParser(description="三情景收入模型;输出 JSON")
    ap.add_argument("--form", choices=FORMS)
    ap.add_argument("--upper-bound", action="store_true")
    ap.add_argument("--possible-form", action="append", choices=FORMS)
    ap.add_argument("--possible-niche", action="append", choices=tuple(RPM))
    ap.add_argument("--cluster-volume", type=int, required=True)
    ap.add_argument("--niche", default="tech", choices=tuple(RPM))
    ap.add_argument("--aio-present", action="store_true")
    ap.add_argument("--strong-complete-count", type=int, default=0)
    a = ap.parse_args(argv)
    try:
        if a.upper_bound:
            print(json.dumps(upper_bound(a.cluster_volume, a.possible_form, a.possible_niche), ensure_ascii=False, indent=2))
            return 0
        r = model(a.form, a.cluster_volume, a.niche, a.aio_present, a.strong_complete_count)
    except ValueError as e:
        print(f"拒收: {e}", file=sys.stderr)
        return 1
    r["passes"] = passes(r)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
