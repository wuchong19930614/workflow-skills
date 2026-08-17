#!/usr/bin/env python3
"""xinci 候选账本 registrar:唯一的状态转移入口。

规则来源:xinci-core/生命周期契约.md(合法转移表 + 每转移证据要求)。
账本:数据/新词工作流/账本/候选账本.json,本脚本独占写入,原子替换。
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[2] / "数据" / "新词工作流"

STATES = {
    "captured", "screened", "tracking", "formation_confirmed", "qualified",
    "build_ready", "pilot_ready", "fast_grab_ready", "hold",
    "rejected", "expired", "superseded", "withdrawn", "built", "disqualified", "no_site",
}
# 设计终态词汇为前五个;disqualified/no_site 是决策终局,除 superseded 外无出边,并入终态集
TERMINAL = {"rejected", "expired", "superseded", "withdrawn", "built", "disqualified", "no_site"}

LEGAL = {
    ("captured", "screened"), ("captured", "rejected"),
    ("screened", "rejected"), ("screened", "tracking"), ("screened", "fast_grab_ready"),
    ("tracking", "formation_confirmed"), ("tracking", "expired"), ("tracking", "rejected"),
    ("formation_confirmed", "qualified"), ("formation_confirmed", "disqualified"),
    ("qualified", "build_ready"), ("qualified", "pilot_ready"),
    ("qualified", "hold"), ("qualified", "no_site"),
    ("hold", "build_ready"), ("hold", "pilot_ready"), ("hold", "no_site"), ("hold", "disqualified"),
    ("fast_grab_ready", "built"), ("fast_grab_ready", "expired"),
    ("build_ready", "built"), ("pilot_ready", "built"),
    ("built", "tracking"),  # 升级通路,仅用户发起
}

SCREEN_GATES = ("G0", "G1", "G2", "G3", "G4", "G5")
QUALIFY_GATES = ("G6", "G7", "G8")
WINDOWS = {"days", "weeks", "months"}
BUILD_PLAYS = {"single_domain", "cluster_expansion"}


class RegistrarError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ledger_path(data_root: Path) -> Path:
    return Path(data_root) / "账本" / "候选账本.json"


def _load(data_root: Path) -> dict:
    p = _ledger_path(data_root)
    if not p.is_file():
        return {"schema_version": 1, "candidates": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def _save(data_root: Path, ledger: dict) -> None:
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise RegistrarError(msg)


def _check_evidence(data_root: Path, refs) -> list:
    refs = list(refs or [])
    for r in refs:
        _require((Path(data_root) / r).is_file(), f"证据文件不存在: {r}")
    return refs


def _check_date(value: str, field: str) -> str:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        raise RegistrarError(f"{field} 必须是 YYYY-MM-DD 日期: {value!r}")
    return value


def _check_gates(gates: dict, names, context: str) -> None:
    gates = gates or {}
    missing = [g for g in names if gates.get(g) != "pass"]
    _require(not missing, f"{context} 要求闸门 {'/'.join(names)} 全部 pass,未满足: {missing}")


def _check_decision_files(data_root: Path, decision_ref: str) -> str:
    _require(bool(decision_ref), "该转移要求 decision_ref(决策书 md 路径)")
    md = Path(data_root) / decision_ref
    _require(md.is_file() and md.suffix == ".md", f"决策书 md 不存在: {decision_ref}")
    html = md.with_suffix(".html")
    _require(html.is_file(), f"决策书双格式要求同名 html 同批存在,缺: {html.name}")
    return decision_ref


def register(data_root, slug, term, source_url, task, evidence,
             source_note="", aliases=None, by="xinci-scan"):
    data_root = Path(data_root)
    _require(bool(slug and term and source_url and task), "slug/term/source_url/task 均不可为空")
    ledger = _load(data_root)
    _require(slug not in ledger["candidates"], f"候选已存在: {slug}")
    refs = _check_evidence(data_root, evidence)
    _require(len(refs) >= 1, "注册候选要求至少 1 个证据文件")
    now = _now()
    ledger["candidates"][slug] = {
        "slug": slug,
        "term": term,
        "aliases": list(aliases or []),
        "state": "captured",
        "lane": "new",
        "first_observed_at": now,
        "last_checked_at": now,
        "expiry": None,
        "source": {"url": source_url, "note": source_note},
        "task": task,
        "window_estimate": None,
        "play": None,
        "gates": {},
        "score": None,
        "invalidation": [],
        "evidence_refs": refs,
        "decision_ref": None,
        "superseded_by": None,
        "history": [{"at": now, "from": None, "to": "captured", "by": by}],
    }
    _save(data_root, ledger)
    return ledger["candidates"][slug]


def transition(data_root, slug, to, by, gates=None, window_estimate=None, expiry=None,
               invalidation=None, score=None, decision_ref=None, play=None,
               reason=None, evidence=None, superseded_by=None):
    data_root = Path(data_root)
    ledger = _load(data_root)
    _require(slug in ledger["candidates"], f"候选不存在: {slug}")
    rec = ledger["candidates"][slug]
    frm = rec["state"]
    _require(to in STATES, f"未知状态: {to}")

    if to in {"withdrawn", "superseded"}:
        _require(frm not in TERMINAL, f"终态候选不可再转移: {frm}")
        if to == "withdrawn":
            _require(bool(reason), "withdrawn 要求 reason")
        else:
            _require(bool(superseded_by) and superseded_by != slug
                     and superseded_by in ledger["candidates"],
                     f"superseded 要求 superseded_by 指向账本中已存在的其他候选: {superseded_by!r}")
    else:
        _require((frm, to) in LEGAL, f"非法转移: {frm} -> {to}")

    refs = _check_evidence(data_root, evidence)
    merged_refs = rec["evidence_refs"] + [r for r in refs if r not in rec["evidence_refs"]]

    if to == "screened":
        _check_gates(gates, SCREEN_GATES, "captured→screened")
        _require(window_estimate in WINDOWS, f"window_estimate 必须属于 {sorted(WINDOWS)}")
        _require(len(refs) >= 1, "captured→screened 要求本次至少 1 个证据")
    elif to == "rejected":
        _require(bool(reason), "rejected 要求 reason(失败闸门 + 现场证据要点)")
    elif to == "tracking":
        if frm == "built":  # 升级通路
            _require(bool(reason), "built→tracking 要求 reason(升级理由)")
            _check_date(expiry, "expiry")
        else:
            _check_date(expiry, "expiry")
            _require(bool(invalidation), "screened→tracking 要求至少 1 条失效条件")
            _require(len(refs) >= 1, "screened→tracking 要求本次至少 1 个证据")
    elif to == "fast_grab_ready":
        _check_decision_files(data_root, decision_ref)
        _check_date(expiry, "expiry")
        _require(play in (None, "fast_grab"), "快道 play 只能是 fast_grab")
        play = "fast_grab"
    elif to == "formation_confirmed":
        track_obs = [r for r in merged_refs if "-track" in Path(r).name]
        _require(len(track_obs) >= 2,
                 f"tracking→formation_confirmed 要求 ≥2 个追踪期观察(-track 证据),当前 {len(track_obs)}")
        _check_gates(gates, ("G1",), "tracking→formation_confirmed")
        _require(len(refs) >= 1, "tracking→formation_confirmed 要求本次至少 1 个证据")
    elif to == "expired":
        _require(bool(reason), "expired 要求 reason(expiry 已过经用户确认 / 失效条件命中)")
    elif to == "qualified":
        _require(isinstance(score, int) and score >= 80, f"qualified 要求整数 score ≥80,当前 {score!r}")
        _check_gates(gates, QUALIFY_GATES, "formation_confirmed→qualified")
        _require(len(refs) >= 1, "formation_confirmed→qualified 要求本次至少 1 个证据")
    elif to == "disqualified":
        _require(bool(reason), "disqualified 要求 reason(决定性缺口:哪一项、差多少)")
    elif to in {"build_ready", "pilot_ready"}:
        _check_decision_files(data_root, decision_ref)
        _require(play in BUILD_PLAYS, f"play 必须属于 {sorted(BUILD_PLAYS)},当前 {play!r}")
    elif to in {"hold", "no_site"}:
        _require(bool(reason), f"{to} 要求 reason")
        _require(decision_ref is None, "no-go 结论不出决策书,不得携带 decision_ref(数据极简原则)")

    now = _now()
    rec["evidence_refs"] = merged_refs
    if gates:
        rec["gates"].update(gates)
    if window_estimate:
        rec["window_estimate"] = window_estimate
    if expiry:
        rec["expiry"] = expiry
    if invalidation:
        rec["invalidation"] = list(dict.fromkeys(rec["invalidation"] + list(invalidation)))
    if score is not None:
        rec["score"] = score
    if decision_ref:
        rec["decision_ref"] = decision_ref
    if play:
        rec["play"] = play
    if superseded_by:
        rec["superseded_by"] = superseded_by
    rec["history"].append({"at": now, "from": frm, "to": to, "by": by, **({"reason": reason} if reason else {})})
    rec["state"] = to
    _save(data_root, ledger)
    return rec


def checked(data_root, slug, evidence, by="xinci-track"):
    """复查登记:更新 last_checked_at、追加证据,不改状态。"""
    data_root = Path(data_root)
    ledger = _load(data_root)
    _require(slug in ledger["candidates"], f"候选不存在: {slug}")
    rec = ledger["candidates"][slug]
    _require(rec["state"] not in TERMINAL, f"终态候选无需复查: {rec['state']}")
    refs = _check_evidence(data_root, evidence)
    _require(len(refs) >= 1, "checked 要求至少 1 个证据文件")
    rec["evidence_refs"] += [r for r in refs if r not in rec["evidence_refs"]]
    rec["last_checked_at"] = _now()
    _save(data_root, ledger)
    return rec


def _parse_gates(text):
    if not text:
        return None
    out = {}
    for part in text.split(","):
        k, _, v = part.partition("=")
        out[k.strip()] = v.strip()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="xinci 候选账本 registrar")
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("register", help="注册新候选(→captured)")
    p.add_argument("--slug", required=True)
    p.add_argument("--term", required=True)
    p.add_argument("--source-url", required=True)
    p.add_argument("--source-note", default="")
    p.add_argument("--task", required=True)
    p.add_argument("--aliases", default="", help="逗号分隔")
    p.add_argument("--evidence", action="append", required=True)
    p.add_argument("--by", default="xinci-scan")

    p = sub.add_parser("transition", help="状态转移")
    p.add_argument("--slug", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--gates", default="", help="如 G1=pass,G2=pass")
    p.add_argument("--window-estimate", choices=sorted(WINDOWS))
    p.add_argument("--expiry")
    p.add_argument("--invalidation", default="", help="分号分隔")
    p.add_argument("--score", type=int)
    p.add_argument("--decision-ref")
    p.add_argument("--play")
    p.add_argument("--reason")
    p.add_argument("--evidence", action="append")
    p.add_argument("--superseded-by")

    p = sub.add_parser("checked", help="复查登记(不改状态)")
    p.add_argument("--slug", required=True)
    p.add_argument("--evidence", action="append", required=True)
    p.add_argument("--by", default="xinci-track")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "register":
            rec = register(a.data_root, a.slug, a.term, a.source_url, a.task, a.evidence,
                           source_note=a.source_note,
                           aliases=[x for x in a.aliases.split(",") if x], by=a.by)
        elif a.cmd == "transition":
            rec = transition(a.data_root, a.slug, a.to, a.by,
                             gates=_parse_gates(a.gates), window_estimate=a.window_estimate,
                             expiry=a.expiry,
                             invalidation=[x for x in a.invalidation.split(";") if x] or None,
                             score=a.score, decision_ref=a.decision_ref, play=a.play,
                             reason=a.reason, evidence=a.evidence, superseded_by=a.superseded_by)
        else:
            rec = checked(a.data_root, a.slug, a.evidence, by=a.by)
    except RegistrarError as e:
        print(f"registrar 拒绝: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"slug": rec["slug"], "state": rec["state"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
