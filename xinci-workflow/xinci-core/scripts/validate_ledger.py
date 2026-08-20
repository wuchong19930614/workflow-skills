#!/usr/bin/env python3
"""账本与运行清单完整性校验。出错(errors)非零退出;孤儿证据目录仅警告(warnings)。

registrar 在转移时已校验证据齐备性;本脚本的职责是捕获绕过 registrar 的改动
(手工编辑、外部工具损坏),因此复检各状态的不变式。

检查项:
- state 在状态词汇表内;history 末项 to == state;history 每项含 at/to/by;
- history 链连续:每项 from == 前一项 to(amend/checked 条目 from==to,链天然连续);
- evidence_refs 均为数据区内相对路径且存在于磁盘;
- expiry 若存在则可解析为日期;
- 状态不变式:screened 必有 window_estimate;tracking 必有 expiry;
  captured 若带闸门结论(排队位)必有 expiry(否则窗口过了无处可去、无声腐烂);
  fast_grab_ready 必有 expiry、window_estimate=days、play=fast_grab、score 为 null(快道不得声称全站分数);
  过 screened 的非终态必有 G0–G5 全 pass(G3 可为 veto_window_bet 快道降级结论);
  带 G3=veto_window_bet 的候选只能停在 captured(挂起待确认)/screened/fast_grab_ready 或终态,
  且在 screened/fast_grab_ready 上 window_estimate=days;qualified 及其后继(build_ready/pilot_ready/hold)必有 G6–G8 全 pass;
  formation_confirmed 及其后继必有 ≥2 个 -track 观察且跨度 ≥7 天;
  qualified/build_ready/pilot_ready/hold 必有整数 score ≥80(hold 是认定后的搁置,分数已经产生);
  build_ready/pilot_ready 的 play ∈ {single_domain, cluster_expansion};
- go 决策态(build_ready/pilot_ready/fast_grab_ready)必须有 decision_ref,且 md+html 双文件存在;
- hold/no_site 不得携带 decision_ref(no-go 不出决策书);
- 证据/ 下无账本外孤儿目录(警告)。

运行清单检查项(对齐 数据结构/run-manifest.schema.json,见 validate_runs):
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

from registrar import (STATES, DEFAULT_DATA_ROOT, WINDOWS, BUILD_PLAYS,
                       SCREEN_GATES, QUALIFY_GATES, MIN_TRACK_SPAN_DAYS,
                       G3_WINDOW_BET, TERMINAL, RegistrarError, _obs_time,
                       SLUG_RE, VALID_ACTORS, _check_decision_files,
                       _check_gate_payload, _check_gate_evidence)
from run_state import RunStateError, load_session
from run_manifest import validate_runs
from transaction_journal import TransactionError, list_pending
from dedup_decisions import DedupDecisionError, load as load_dedup_decisions
from term_normalize import match_kind

GO_STATES = {"build_ready", "pilot_ready", "fast_grab_ready"}
NO_GO_STATES = {"hold", "no_site"}
# 带分数的状态:认定产生分数,其后继一路带着它。hold 也在内——生命周期契约明确
# "hold 本身已带着 G6–G8 全 pass 与分数",它只能从 qualified 转入,分数不会被清空。
SCORED_STATES = {"qualified", "build_ready", "pilot_ready", "hold"}
# 过了 screened 的非终态:G0–G5 应全 pass(复查翻转即原子转出,不存在带 veto 的中间态)
SCREEN_PASSED_STATES = {"screened", "tracking", "formation_confirmed", "qualified",
                        "build_ready", "pilot_ready", "fast_grab_ready", "hold"}
# 过了认定的状态:G6–G8 应全 pass
QUALIFY_PASSED_STATES = {"qualified", "build_ready", "pilot_ready", "hold"}
# 过了形成确认的状态:≥2 个 -track 观察且跨度达标
FORMED_STATES = {"formation_confirmed", "qualified", "build_ready", "pilot_ready", "hold"}
# G3 快道降级结论(veto_window_bet)的候选只准停在这些状态:
#   captured        —— 深审已出结论、但转移尚未被确认的挂起位(连续运行模式必经此处:
#                      registrar 拒收 by=xinci-run 的该出口,候选只能挂着等用户单步确认);
#   screened        —— 已确认窗口赌注风险、等决策;
#   fast_grab_ready —— 快道决策态;
#   终态            —— 已终结。
# 禁止的是 tracking 及其后继:那等于让窗口赌注候选绕过 G3 走到全站。
WINDOW_BET_STATES = {"captured", "screened", "fast_grab_ready"} | TERMINAL


def validate(data_root):
    data_root = Path(data_root)
    errors, warnings = [], []
    ledger_path = data_root / "账本" / "候选账本.json"
    if not ledger_path.is_file():
        return [f"账本不存在: {ledger_path}(先运行 init_workspace.py)"], warnings
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
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

        # 状态不变式(registrar 转移时已强制,此处防手工编辑绕过)
        if state == "screened" and rec.get("window_estimate") not in WINDOWS:
            errors.append(f"{where} screened 必有 window_estimate ∈ {sorted(WINDOWS)},"
                          f"当前 {rec.get('window_estimate')!r}")
        if state == "screened" and not expiry:
            errors.append(f"{where} screened 必有 expiry(窗口失效日)")
        if state == "tracking" and not expiry:
            errors.append(f"{where} tracking 必有 expiry")
        if state == "captured" and rec.get("gates") and not expiry:
            errors.append(f"{where} captured 带闸门结论(排队位)必有 expiry:"
                          "排队位每轮进多出少,没有 expiry 就没有过期出口,方向会无声腐烂")
        if state == "fast_grab_ready":
            if not expiry:
                errors.append(f"{where} fast_grab_ready 必有 expiry")
            if rec.get("window_estimate") != "days":
                errors.append(f"{where} fast_grab_ready 必有 window_estimate=days,"
                              f"当前 {rec.get('window_estimate')!r}")
            if rec.get("play") != "fast_grab":
                errors.append(f"{where} fast_grab_ready 的 play 必须是 fast_grab,当前 {rec.get('play')!r}")
            if rec.get("score") is not None:
                errors.append(f"{where} 快道不得声称全站分数,score 应为 null,当前 {rec.get('score')!r}")
        gates = rec.get("gates", {})
        try:
            _check_gate_payload(gates)
        except RegistrarError as e:
            errors.append(f"{where} {e}")
        g3 = gates.get("G3")
        if state in SCREEN_PASSED_STATES:
            bad = [g for g in SCREEN_GATES if g != "G3" and gates.get(g) != "pass"]
            if g3 not in ("pass", G3_WINDOW_BET):
                bad.append("G3")
            if bad:
                errors.append(f"{where} {state} 要求 G0–G5 全 pass"
                              f"(G3 可为 {G3_WINDOW_BET}),未满足: {bad}")
        if g3 == G3_WINDOW_BET:
            # 降级结论只通向快道:出现在 tracking 及其后继意味着绕过了 G3
            if state not in WINDOW_BET_STATES:
                errors.append(f"{where} G3={G3_WINDOW_BET} 的候选只能是 captured(挂起待确认)/"
                              f"screened/fast_grab_ready 或终态,当前 {state}"
                              "——进入该状态意味着绕过了 G3")
            if state in {"screened", "fast_grab_ready"} and rec.get("window_estimate") != "days":
                errors.append(f"{where} G3={G3_WINDOW_BET} 要求 window_estimate=days,"
                              f"当前 {rec.get('window_estimate')!r}")
        if state in QUALIFY_PASSED_STATES:
            bad = [g for g in QUALIFY_GATES if gates.get(g) != "pass"]
            if bad:
                errors.append(f"{where} {state} 要求 G6–G8 全 pass,未满足: {bad}")
        if state in FORMED_STATES:
            track_refs = [r for r in rec.get("evidence_refs", [])
                          if Path(r).stem.endswith("-track") and (data_root / r).is_file()]
            if len(track_refs) < 2:
                errors.append(f"{where} {state} 要求 ≥2 个 -track 观察,当前 {len(track_refs)}")
            else:
                try:
                    times = [_obs_time(data_root, r) for r in track_refs]
                    span = (max(times) - min(times)).days
                    if span < MIN_TRACK_SPAN_DAYS:
                        errors.append(f"{where} {state} 要求 -track 观察跨度 ≥{MIN_TRACK_SPAN_DAYS} 天,"
                                      f"当前 {span} 天")
                except RegistrarError as e:
                    errors.append(f"{where} {e}")
        if state in SCORED_STATES:
            score = rec.get("score")
            if not (isinstance(score, int) and score >= 80):
                errors.append(f"{where} {state} 必有整数 score ≥80,当前 {score!r}")
        if state in {"build_ready", "pilot_ready"} and rec.get("play") not in BUILD_PLAYS:
            errors.append(f"{where} {state} 的 play 必须属于 {sorted(BUILD_PLAYS)},当前 {rec.get('play')!r}")

        ref = rec.get("decision_ref")
        if state in GO_STATES:
            if not ref:
                errors.append(f"{where} go 决策态缺 decision_ref")
            else:
                md = data_root / ref
                if not md.is_file():
                    errors.append(f"{where} 决策书 md 缺失: {ref}")
                if not md.with_suffix(".html").is_file():
                    errors.append(f"{where} 决策书 html 缺失(双格式要求): {md.with_suffix('.html').name}")
                if md.is_file() and md.with_suffix(".html").is_file():
                    try:
                        _check_decision_files(data_root, ref)
                    except RegistrarError as e:
                        errors.append(f"{where} 决策书校验失败: {e}")
        if state in NO_GO_STATES and ref:
            errors.append(f"{where} no-go 结论不应携带 decision_ref: {ref}")

    try:
        pending = list_pending(data_root)
        if pending:
            errors.append(f"存在未恢复跨文件事务: {[x.get('tx_id') for x in pending]};"
                          "执行 run_controller.py recover")
    except TransactionError as e:
        errors.append(str(e))
    try:
        decisions = load_dedup_decisions(data_root)
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
                except RunControllerError as e:
                    errors.append(f"去重裁决[{i}] run_id 无效: {e}")
    except DedupDecisionError as e:
        errors.append(str(e))

    evidence_dir = data_root / "证据"
    if evidence_dir.is_dir():
        for d in sorted(evidence_dir.iterdir()):
            if d.is_dir() and d.name not in candidates:
                warnings.append(f"孤儿证据目录(账本无此候选): 证据/{d.name}")
    return errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="校验 xinci 候选账本与运行清单完整性")
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    a = ap.parse_args(argv)
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
