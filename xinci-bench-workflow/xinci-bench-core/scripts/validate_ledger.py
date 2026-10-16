#!/usr/bin/env python3
"""账本、种子池、淘汰索引、快道原料池的不变式校验;有错非零退出。单元测试通过不能代替它。"""
import argparse
import sys
from pathlib import Path

import bench_model
import data_root
import ledger as L
import quick_model as QM
import quick_pool
import write_observation as W
from _common import REJECTS_REL, SEEDS_REL, BenchError, is_date, load_json, load_ledger, sha256_file, today

REQUIRED = ("slug", "title", "site_type", "lane", "state", "benchmarks", "clusters", "crowding", "paid",
            "model", "decision", "evidence_refs", "bindings", "history")
REQUIRED_QUICK = ("slug", "title", "site_type", "lane", "state", "object", "terms", "volume", "serp", "watch",
                  "follow_up", "model", "decision", "evidence_refs", "bindings", "history")


def _history_errors(slug, rec):
    errs, hist = [], rec["history"]
    legal = L.LEGAL_BY_LANE[rec["lane"]]
    if not hist or hist[0].get("from") is not None or hist[0].get("to") != "found":
        return [f"{slug}: history 须以 null → found 开始"]
    for h in hist[1:]:
        if h.get("to") not in legal.get(h.get("from"), set()):
            errs.append(f"{slug}: history 含非法转移 {h.get('from')} → {h.get('to')}")
    if hist[-1]["to"] != rec["state"]:
        errs.append(f"{slug}: 状态 {rec['state']} 与 history 末条 {hist[-1]['to']} 不一致")
    return errs


def _forecast_block_errors(slug, rec):
    """预判模型的账本记录:forecast 块键齐全,开玩日与对象首次公开日一致,复核日 = 开玩日 + 7 天。"""
    f = rec.get("forecast")
    if not isinstance(f, dict):
        return [f"{slug}: 预判模型须有 forecast 块"] if rec["state"] in ("go", "watching") else []
    missing = [k for k in L.FORECAST_KEYS if k not in f]
    if missing:
        return [f"{slug}: forecast 块缺字段 {missing}"]
    errs, first_public = [], (rec.get("object") or {}).get("first_public")
    if f["playable_at"] != first_public:
        errs.append(f"{slug}: forecast.playable_at {f['playable_at']} 与 object.first_public {first_public} 不一致")
    elif is_date(f["playable_at"]):
        review_at = QM.forecast_dates(f["playable_at"])["review_at"]
        if f["review_at"] != review_at:
            errs.append(f"{slug}: forecast.review_at {f['review_at']} 应为开玩日后 {QM.QUICK_ASSUMPTIONS['review_days']} 天 {review_at}")
    return errs


def _quick_errors(slug, rec, on):
    errs, dec = [], rec.get("decision") or {}
    if "basis" in rec and rec["basis"] != "forecast":
        errs.append(f"{slug}: basis 只能是 forecast(现行方向不写这个字段),现为 {rec['basis']!r}")
    if rec["state"] in ("go", "watching") or dec.get("gate") == "volume":
        try:
            if QM.recompute(rec) != rec.get("model"):
                errs.append(f"{slug}: 快道模型重算与账本不一致")
        except BenchError as exc:
            errs.append(f"{slug}: 快道模型无法重算: {exc}")
        except (KeyError, AttributeError, TypeError) as exc:                   # 记录残缺:报错,不崩
            errs.append(f"{slug}: 快道模型无法重算(记录残缺): {type(exc).__name__} {exc}")
    model = rec.get("model")
    if isinstance(model, dict) and model.get("basis") == "forecast":
        errs += _forecast_block_errors(slug, rec)
    if rec["state"] == "watching":
        w = rec.get("watch") or {}
        if not w.get("expires_at"):
            errs.append(f"{slug}: 观察中须有到期日")
        elif on > w["expires_at"]:
            errs.append(f"{slug}: 观察已于 {w['expires_at']} 到期,须按 go 或 volume 否决结算")
    if rec["state"] == "go":
        fu = rec.get("follow_up") or {}
        bad = [k for k in ("go_at", "launch_by", "started_at", "launched_at")
               if fu.get(k) is not None and not is_date(fu[k])]
        if fu.get("status") not in L.FOLLOW_UP_STATUSES or not fu.get("launch_by"):
            errs.append(f"{slug}: 快道 go 的建站跟进缺失或状态无效")
        elif bad:
            errs.append(f"{slug}: 建站跟进的日期无效 {bad}(须为日历上存在的 YYYY-MM-DD)")
        elif fu["status"] == "launched" and not fu.get("launched_at"):
            errs.append(f"{slug}: 已上线须有上线日期")
    if dec.get("gate") and dec["gate"] not in L.QUICK_GATES:
        errs.append(f"{slug}: 快道否决门无效 {dec['gate']}")
    return errs


def check_direction(root, slug, rec, on=None) -> list:
    on = on or today()
    lane = rec.get("lane")
    if lane not in L.LANES:
        return [f"{slug}: 缺 lane 或取值无效(须为 {L.LANES})"]
    missing = [k for k in (REQUIRED if lane == "bench" else REQUIRED_QUICK) if k not in rec]
    if missing:
        return [f"{slug}: 缺字段 {missing}"]
    errs = []
    if rec["slug"] != slug:
        errs.append(f"{slug}: 记录里的 slug 是 {rec['slug']}")
    if rec["state"] not in L.STATES:
        errs.append(f"{slug}: 未知状态 {rec['state']}")
    errs += _history_errors(slug, rec)
    for ref in rec["evidence_refs"]:
        try:
            W.read(root, ref)
        except BenchError as exc:
            errs.append(f"{slug}: 观察不可用 {ref}: {exc}")
    if rec["state"] == "found":
        if rec.get("decision") is not None or rec.get("bindings") is not None:
            errs.append(f"{slug}: found 不应带 decision/bindings,说明结算未完成;用同一条 settle.py 命令重跑")
        return errs
    dec = rec.get("decision") or {}
    if dec.get("verdict") != rec["state"]:
        errs.append(f"{slug}: decision.verdict 与状态不一致")
    if not L.docs_consistent(root, slug):
        errs.append(f"{slug}: 决策书 md/html 缺失,或 html 内嵌的源 SHA 与 md 不符")
    elif sha256_file(L.doc_paths(root, slug)[0]) != dec.get("doc_sha256"):
        errs.append(f"{slug}: 决策书 md 与账本不一致(md 的 SHA 不等于结算时记录的 doc_sha256,疑似被手改);"
                    "事实没变时用同一条 settle.py 命令重跑重建")
    for f in (rec.get("bindings") or {}).get("files", []):
        p = Path(root) / f["ref"]
        if not p.is_file() or sha256_file(p) != f["sha256"]:
            errs.append(f"{slug}: 绑定观察已变动或丢失 {f['ref']}")
    if not rec.get("bindings"):
        errs.append(f"{slug}: 终态、搁置或观察中须有绑定")
    if lane == "quick":
        return errs + _quick_errors(slug, rec, on)
    if rec["state"] == "go" or dec.get("gate") == "revenue":
        try:
            model = bench_model.compute(rec)
            if model != rec.get("model"):
                errs.append(f"{slug}: 模型重算与账本不一致")
            elif model["passes"] is not (rec["state"] == "go"):
                errs.append(f"{slug}: 模型结论与状态不符")
        except BenchError as exc:
            errs.append(f"{slug}: 模型无法重算: {exc}")
    return errs


def check_seeds(root) -> list:
    errs = []
    pool = load_json(Path(root) / SEEDS_REL)
    for d, s in pool.get("seeds", {}).items():
        if s.get("source") not in ("legacy", "sibling", "serp", "geo", "community"):
            errs.append(f"种子 {d}: 来源无效")
        if s.get("role") not in ("benchmark", "sibling") or s.get("status") not in ("pending", "checked"):
            errs.append(f"种子 {d}: role 或 status 无效")
    rejects = load_json(Path(root) / REJECTS_REL)
    for d, e in rejects.get("domains", {}).items():
        if (e.get("recheck_after") is not None) != (e.get("failed") == ["B3"]):
            errs.append(f"淘汰 {d}: 只有单独 B3 不过才设复查日期")
        if not str(e.get("observation", "")).startswith("证据/_scan/"):
            errs.append(f"淘汰 {d}: 缺 scan 观察引用")
    return errs


def check_quick_files(root) -> list:
    errs = []
    for r in quick_pool._read_pool(root):
        if r.get("status") not in quick_pool.STATUSES:
            errs.append(f"原料 {r.get('id')}: status 无效")
    for term, e in quick_pool._rejects(root)["terms"].items():
        if e.get("gate") not in quick_pool.QUICK_GATES or not str(e.get("observation", "")).startswith("证据/"):
            errs.append(f"快道淘汰 {term}: gate 或观察引用无效")
    return errs


def check_all(root, on=None) -> list:
    ledger = load_ledger(root)
    errs = [] if ledger.get("schema_version") == 1 else ["账本 schema_version 须为 1"]
    for slug, rec in ledger.get("directions", {}).items():
        errs += check_direction(root, slug, rec, on)
    return errs + check_seeds(root) + check_quick_files(root)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    errs = check_all(root)
    for e in errs:
        print("错误: " + e)
    print(f"校验完成:{len(errs)} 个错误")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
