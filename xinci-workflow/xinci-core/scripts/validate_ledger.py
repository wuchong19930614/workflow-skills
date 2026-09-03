#!/usr/bin/env python3
"""账本与运行清单完整性校验。出错(errors)非零退出;孤儿证据目录仅警告(warnings)。

registrar 在转移时已校验证据齐备性;本脚本的职责是捕获绕过 registrar 的改动
(手工编辑、外部工具损坏),因此复检各状态的不变式。

检查项:
- state 在状态词汇表内;history 末项 to == state;history 每项含 at/to/by;
- history 链连续:每项 from == 前一项 to(amend/checked 条目 from==to,链天然连续);
- evidence_refs 均为数据区内相对路径且存在于磁盘;
- expiry 若存在则可解析为日期;
- 状态不变式(条目与机器码见 registrar.check_state_invariants,registrar 转移写入前与本脚本
  共用同一函数):screened 必有 window_estimate/expiry;tracking 必有 expiry;captured 带闸门结论
  必有 expiry;fast_grab_ready 的 expiry/window_estimate=days/play=fast_grab/score=null;
  过 screened 者 G0/G1/G2/G4/G5=pass 且 G3 ∈ {pass, veto_window_bet};veto_window_bet 只能停在
  captured/screened/fast_grab_ready/终态;qualified 及后继 G6–G8 全 pass、≥2 个 -track 且跨度 ≥7 天、
  score≥80、income_score 1–20、g6_passed_lines 合法且与 →qualified 快照/qualify 观察一致;
  build_ready/pilot_ready 的 play 合法;go 态必有 decision_ref 且 md+html 双文件;
  hold/no_site 不得携带 decision_ref;
- 证据/ 下无账本外孤儿目录(警告)。

运行清单检查项(字段白名单见 run_manifest.RUN_FIELDS / RUN_ROUND_FIELDS,见 validate_runs):
文件名约定、必填 date/skill、字段白名单、类型、文件名与内容一致性、rounds 结构,
以及扫描漏斗自洽性(funnel 四个去向加总 == extracted,即每个被提取的方向都有归宿;
extracted 记去重后进入筛选的方向数,消化存量 captured 的深审记可选的 carryover_audited)。
funnel 的**存在性**按日期阈值强制:FUNNEL_REQUIRED_FROM 起的 xinci-scan 清单必须带顶层
funnel,xinci-run 清单的每一轮必须带 rounds[].funnel(该轮没扫描就把 extracted 与四个去向五项全写 0)。阈值之前
的历史清单豁免——那时规则还没立,回填只能编造数字。
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import data_root
from _common import ledger_path, load_ledger
from registrar import (STATES, RegistrarError, SLUG_RE, VALID_ACTORS,
                       _check_gate_evidence, check_state_invariants)
from run_state import RunStateError, load_session
from run_manifest import validate_runs
from term_normalize import match_kind
from screen_index import DedupDecisionError, load_decisions, validate_index
from trigger_pool import TriggerPoolError, load as load_trigger_pool


def validate(data_root):
    data_root = Path(data_root)
    errors, warnings = [], []
    if not ledger_path(data_root).is_file():
        return [f"账本不存在: {ledger_path(data_root)}(先运行 init_workspace.py)"], warnings
    try:
        ledger = load_ledger(data_root)
    except json.JSONDecodeError as e:
        return [f"账本不是合法 JSON: {e}"], warnings

    candidates = ledger.get("candidates", {})
    for slug, rec in candidates.items():
        where = f"[{slug}]"
        if not SLUG_RE.fullmatch(slug) or rec.get("slug") != slug:
            errors.append(f"{where} slug 必须是 kebab-case 且记录内 slug 与账本键一致")
        state = rec.get("state")
        if state not in STATES:
            errors.append(f"{where} 未知状态: {state!r}")
        hist = rec.get("history", [])
        if not hist:
            errors.append(f"{where} history 为空")
        else:
            if hist[-1].get("to") != state:
                errors.append(f"{where} history 末项 to={hist[-1].get('to')!r} 与 state={state!r} 不一致")
            for i, h in enumerate(hist):
                for k in ("at", "to", "by"):
                    if not h.get(k):
                        errors.append(f"{where} history[{i}] 缺字段 {k}")
                if i > 0 and h.get("from") != hist[i - 1].get("to"):
                    errors.append(f"{where} history[{i}] 断链: from={h.get('from')!r} "
                                  f"≠ 前项 to={hist[i - 1].get('to')!r}")
                if h.get("by") not in VALID_ACTORS:
                    errors.append(f"{where} history[{i}] by 非法: {h.get('by')!r}")
                if h.get("by") == "xinci-run":
                    run_id = h.get("run_id")
                    round_number = h.get("round")
                    if not run_id:
                        # 兼容运行会话机制建立前的真实历史，不把旧记录伪造为新会话。
                        if (h.get("at") or "")[:10] >= "2026-08-20":
                            errors.append(f"{where} history[{i}] by=xinci-run 缺 run_id")
                    else:
                        try:
                            session = load_session(data_root, run_id)
                        except RunStateError as e:
                            errors.append(f"{where} history[{i}] run_id 无效: {e}")
                        else:
                            if ((h.get("at") or "")[:10] >= "2026-08-20"
                                    and (not isinstance(round_number, int)
                                         or isinstance(round_number, bool)
                                         or not 1 <= round_number <= session["max_rounds"])):
                                errors.append(f"{where} history[{i}] by=xinci-run 缺合法 round")
                if h.get("gates") and (h.get("at") or "")[:10] >= "2026-08-20":
                    try:
                        _check_gate_evidence(data_root, h.get("evidence"), h["gates"],
                                             f"{where} history[{i}]")
                    except RegistrarError as e:
                        errors.append(str(e))
        for r in rec.get("evidence_refs", []):
            rel = Path(r)
            if rel.is_absolute() or ".." in rel.parts:
                errors.append(f"{where} 证据路径必须是数据区内的相对路径: {r}")
            elif not (data_root / r).is_file():
                errors.append(f"{where} 证据文件缺失: {r}")
        expiry = rec.get("expiry")
        if expiry:
            try:
                date.fromisoformat(expiry)
            except ValueError:
                errors.append(f"{where} expiry 不可解析: {expiry!r}")

        # 状态不变式:与 registrar 转移写入前的复核共用同一函数(registrar.check_state_invariants),
        # 此处防手工编辑绕过;每条错误带 [INV-<code>] 机器码。
        errors.extend(f"{where} {e}" for e in check_state_invariants(data_root, rec))

    try:
        decisions = load_decisions(data_root)
        seen_decision_ids = set()
        for i, row in enumerate(decisions, 1):
            required = ("decision_id", "reason", "decided_at", "actor", "term_task",
                        "matched_task", "term_evidence_urls", "matched_evidence_urls")
            missing = [k for k in required if not row.get(k)]
            if missing:
                errors.append(f"去重裁决[{i}] 缺字段 {missing}")
            if match_kind(row.get("term", ""), row.get("matched", "")) != "probable":
                errors.append(f"去重裁决[{i}] 两个措辞当前不是疑似重复关系")
            if row.get("decision_id") in seen_decision_ids:
                errors.append(f"去重裁决[{i}] decision_id 重复")
            if row.get("supersedes") and row["supersedes"] not in seen_decision_ids:
                errors.append(f"去重裁决[{i}] supersedes 未指向更早的裁决")
            seen_decision_ids.add(row.get("decision_id"))
            if row.get("actor") == "xinci-run":
                try:
                    load_session(data_root, row.get("run_id"))
                except RunStateError as e:
                    errors.append(f"去重裁决[{i}] run_id 无效: {e}")
    except DedupDecisionError as e:
        errors.append(str(e))

    errors.extend(validate_index(data_root))
    try:
        load_trigger_pool(data_root)
    except TriggerPoolError as e:
        errors.append(str(e))

    evidence_dir = data_root / "证据"
    if evidence_dir.is_dir():
        for d in sorted(evidence_dir.iterdir()):
            if d.is_dir() and d.name not in candidates:
                warnings.append(f"孤儿证据目录(账本无此候选): 证据/{d.name}")
    return errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="校验 xinci 候选账本与运行清单完整性")
    ap.add_argument("--data-root", default=None,
                    help="数据区路径。不给则按 XINCI_DATA_ROOT 环境变量、再按仓库配置 .xinci-data-root 解析;都没有则拒绝执行并提示先问用户")
    a = ap.parse_args(argv)
    # 数据区未配置时在这里就停,并打印「先问用户」的指引,
    # 不让空路径流进下游写操作(理由见 data_root.py)。
    a.data_root = data_root.resolve_or_exit(a.data_root)
    errors, warnings = validate(a.data_root)
    errors += validate_runs(a.data_root)
    for w in warnings:
        print(f"警告: {w}")
    for e in errors:
        print(f"错误: {e}", file=sys.stderr)
    print(f"校验完成:{len(errors)} 个错误,{len(warnings)} 个警告")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
