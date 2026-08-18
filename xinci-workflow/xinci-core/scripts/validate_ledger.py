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
  fast_grab_ready 必有 expiry、window_estimate=days、play=fast_grab、score 为 null(快道不得声称全站分数);
  过 screened 的非终态必有 G0–G5 全 pass(G3 可为 veto_window_bet 快道豁免);
  带 G3=veto_window_bet 的候选只能停在 screened/fast_grab_ready 或终态,且 window_estimate=days;qualified 及其后继(build_ready/pilot_ready/hold)必有 G6–G8 全 pass;
  formation_confirmed 及其后继必有 ≥2 个 -track 观察且跨度 ≥7 天;
  qualified/build_ready/pilot_ready 必有整数 score ≥80;
  build_ready/pilot_ready 的 play ∈ {single_domain, cluster_expansion};
- go 决策态(build_ready/pilot_ready/fast_grab_ready)必须有 decision_ref,且 md+html 双文件存在;
- hold/no_site 不得携带 decision_ref(no-go 不出决策书);
- 证据/ 下无账本外孤儿目录(警告)。

运行清单检查项(对齐 数据结构/run-manifest.schema.json,见 validate_runs):
文件名约定、必填 date/skill、字段白名单、类型、文件名与内容一致性、rounds 结构。
"""
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from registrar import (STATES, DEFAULT_DATA_ROOT, WINDOWS, BUILD_PLAYS,
                       SCREEN_GATES, QUALIFY_GATES, MIN_TRACK_SPAN_DAYS,
                       G3_WINDOW_BET, TERMINAL, RegistrarError, _obs_time)

# 运行清单字段白名单:与 数据结构/run-manifest.schema.json 的 properties 逐字对齐
# (schema 声明 additionalProperties: false,越界字段一律拒收)
RUN_FIELDS = {"date", "skill", "started_at", "sources_opened", "sources_blocked",
              "candidates_touched", "billable_calls", "notes", "rounds"}
RUN_ROUND_FIELDS = {"round", "sources_opened", "sources_blocked", "candidates_touched",
                    "billable_calls", "notes"}
RUN_SKILLS = {"xinci-scan", "xinci-track", "xinci-qualify", "xinci-decide", "xinci-run"}
RUN_STR_ARRAYS = ("sources_opened", "sources_blocked", "candidates_touched", "notes")
RUN_NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:-(\d{4}))?-(xinci-[a-z]+)")

GO_STATES = {"build_ready", "pilot_ready", "fast_grab_ready"}
NO_GO_STATES = {"hold", "no_site"}
SCORED_STATES = {"qualified", "build_ready", "pilot_ready"}
# 过了 screened 的非终态:G0–G5 应全 pass(复查翻转即原子转出,不存在带 veto 的中间态)
SCREEN_PASSED_STATES = {"screened", "tracking", "formation_confirmed", "qualified",
                        "build_ready", "pilot_ready", "fast_grab_ready", "hold"}
# 过了认定的状态:G6–G8 应全 pass
QUALIFY_PASSED_STATES = {"qualified", "build_ready", "pilot_ready", "hold"}
# 过了形成确认的状态:≥2 个 -track 观察且跨度达标
FORMED_STATES = {"formation_confirmed", "qualified", "build_ready", "pilot_ready", "hold"}
# G3 快道豁免(veto_window_bet)的候选只准停在这些状态:等决策的 screened、快道决策态,或已终结
WINDOW_BET_STATES = {"screened", "fast_grab_ready"} | TERMINAL


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
        if state == "tracking" and not expiry:
            errors.append(f"{where} tracking 必有 expiry")
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
        g3 = gates.get("G3")
        if state in SCREEN_PASSED_STATES:
            bad = [g for g in SCREEN_GATES if g != "G3" and gates.get(g) != "pass"]
            if g3 not in ("pass", G3_WINDOW_BET):
                bad.append("G3")
            if bad:
                errors.append(f"{where} {state} 要求 G0–G5 全 pass"
                              f"(G3 可为 {G3_WINDOW_BET}),未满足: {bad}")
        if g3 == G3_WINDOW_BET:
            # 豁免只通向快道:出现在 tracking 及其后继意味着绕过了 G3
            if state not in WINDOW_BET_STATES:
                errors.append(f"{where} G3={G3_WINDOW_BET} 的候选只能是 screened/fast_grab_ready "
                              f"或终态,当前 {state}——进入该状态意味着绕过了 G3")
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
        if state in NO_GO_STATES and ref:
            errors.append(f"{where} no-go 结论不应携带 decision_ref: {ref}")

    evidence_dir = data_root / "证据"
    if evidence_dir.is_dir():
        for d in sorted(evidence_dir.iterdir()):
            if d.is_dir() and d.name not in candidates:
                warnings.append(f"孤儿证据目录(账本无此候选): 证据/{d.name}")
    return errors, warnings


def _check_str_array(obj, key, where, errors):
    v = obj.get(key)
    if v is None:
        return
    if not (isinstance(v, list) and all(isinstance(x, str) and x for x in v)):
        errors.append(f"{where} {key} 必须是非空字符串数组,当前 {v!r}")


def _check_int(obj, key, where, errors):
    v = obj.get(key)
    if v is None or (isinstance(v, int) and not isinstance(v, bool)):
        return
    errors.append(f"{where} {key} 必须是整数,当前 {v!r}")


def validate_runs(data_root):
    """运行清单校验(对齐 数据结构/run-manifest.schema.json)。

    运行清单不经 registrar 写入,全靠各 skill 手写,格式漂移无人察觉:首份真实清单
    (2026-08-17-xinci-scan)即用了 metered_calls / candidates_registered 等 schema 外
    字段,直到本校验加上才被发现。因此按 schema 全量校验,并额外查文件名与内容一致性。
    """
    data_root = Path(data_root)
    errors = []
    run_dir = data_root / "运行"
    if not run_dir.is_dir():
        return errors

    for path in sorted(run_dir.glob("*.json")):
        where = f"[运行/{path.name}]"
        name = RUN_NAME_RE.fullmatch(path.stem)
        if not name:
            errors.append(f"{where} 文件名不合约定 <YYYY-MM-DD>[-HHMM]-<skill>.json")
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"{where} 不是合法 JSON: {e}")
            continue
        if not isinstance(obj, dict):
            errors.append(f"{where} 必须是 JSON 对象")
            continue

        unknown = sorted(set(obj) - RUN_FIELDS)
        if unknown:
            errors.append(f"{where} 含 schema 外字段 {unknown}(数据极简,勿加仪式性字段)")
        for k in ("date", "skill"):
            if not obj.get(k):
                errors.append(f"{where} 缺必填字段 {k}")

        run_date = obj.get("date")
        if run_date:
            try:
                date.fromisoformat(run_date)
            except (TypeError, ValueError):
                errors.append(f"{where} date 不可解析: {run_date!r}")
            else:
                if name and run_date != name.group(1):
                    errors.append(f"{where} date={run_date} 与文件名日期 {name.group(1)} 不一致")

        skill = obj.get("skill")
        if skill and skill not in RUN_SKILLS:
            errors.append(f"{where} skill 必须属于 {sorted(RUN_SKILLS)},当前 {skill!r}")
        elif skill and name and skill != name.group(3):
            errors.append(f"{where} skill={skill!r} 与文件名 {name.group(3)!r} 不一致")

        started = obj.get("started_at")
        if started is not None:
            try:
                datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{where} started_at 必须是 ISO 8601 时间: {started!r}")

        for k in RUN_STR_ARRAYS:
            _check_str_array(obj, k, where, errors)
        _check_int(obj, "billable_calls", where, errors)

        rounds = obj.get("rounds")
        if rounds is None:
            continue
        if skill != "xinci-run":
            errors.append(f"{where} rounds 是 xinci-run 专用字段,当前 skill={skill!r}")
        if not isinstance(rounds, list):
            errors.append(f"{where} rounds 必须是数组,当前 {type(rounds).__name__}")
            continue
        for i, rnd in enumerate(rounds):
            rw = f"{where} rounds[{i}]"
            if not isinstance(rnd, dict):
                errors.append(f"{rw} 必须是对象")
                continue
            unknown = sorted(set(rnd) - RUN_ROUND_FIELDS)
            if unknown:
                errors.append(f"{rw} 含 schema 外字段 {unknown}")
            num = rnd.get("round")
            if not isinstance(num, int) or isinstance(num, bool):
                errors.append(f"{rw} 缺必填字段 round(整数),当前 {num!r}")
            for k in RUN_STR_ARRAYS:
                _check_str_array(rnd, k, rw, errors)
            _check_int(rnd, "billable_calls", rw, errors)
    return errors


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
