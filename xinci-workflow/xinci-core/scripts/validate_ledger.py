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
  过 screened 的非终态必有 G0–G5 全 pass(G3 可为 veto_window_bet 快道豁免);
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
import re
import sys
from datetime import date
from pathlib import Path

from registrar import (STATES, DEFAULT_DATA_ROOT, WINDOWS, BUILD_PLAYS,
                       SCREEN_GATES, QUALIFY_GATES, MIN_TRACK_SPAN_DAYS,
                       G3_WINDOW_BET, TERMINAL, RegistrarError, _obs_time)

# 运行清单字段白名单:与 数据结构/run-manifest.schema.json 的 properties 逐字对齐
# (schema 声明 additionalProperties: false,越界字段一律拒收)
RUN_FIELDS = {"date", "skill", "sources_opened", "sources_blocked",
              "candidates_touched", "billable_calls", "notes", "rounds", "funnel"}
RUN_ROUND_FIELDS = {"round", "sources_opened", "sources_blocked", "candidates_touched",
                    "billable_calls", "notes", "funnel"}
# 扫描漏斗(xinci-scan 四层):四个去向必须加总等于 extracted——每个被提取的方向都要有归宿。
# extracted 记的是**去重后**进入第 2 层筛选的方向数:第 0 层 screen_index check 命中的方向
# 已经在索引/账本里有归宿(上一次的记录),再计一次等于要求它二次归宿,等式必然算不平。
FUNNEL_SINKS = ("rejected_zero_cost", "rejected_g1", "deep_audited", "queued")
FUNNEL_FIELDS = ("extracted",) + FUNNEL_SINKS
# 可选、不参与等式:本轮消化**存量 captured**(上轮排队的债)所做的深审数。
# 它不属于本轮 extracted,计入任一去向都会破坏等式;但它是全流程最贵的动作,
# 只还债不扫新的轮次 funnel 五项(extracted 与四个去向)全 0,没有这个字段就看不出那一轮花了什么。
FUNNEL_CARRYOVER = "carryover_audited"
FUNNEL_ALL_FIELDS = FUNNEL_FIELDS + (FUNNEL_CARRYOVER,)
# funnel 存在性从这一天起强制。此前的清单豁免:规则是 2026-08-19 立的,
# 而首份 xinci-run 清单正是"提取了 5 条以上、只有 1 条有归宿"的案例——真实数字已不可考,
# 回填等于编造。历史保持原样,新清单一律带 funnel。
FUNNEL_REQUIRED_FROM = "2026-08-19"
RUN_SKILLS = {"xinci-scan", "xinci-track", "xinci-qualify", "xinci-decide", "xinci-run"}
RUN_STR_ARRAYS = ("sources_opened", "sources_blocked", "candidates_touched", "notes")
RUN_NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:-(\d{4}))?-(xinci-[a-z]+)")

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
# G3 快道豁免(veto_window_bet)的候选只准停在这些状态:
#   captured        —— 深审已出结论、但转移尚未被确认的挂起位(连续运行模式必经此处:
#                      registrar 拒收 by=xinci-run 的该出口,候选只能挂着等用户单步确认);
#   screened        —— 已确认豁免、等决策;
#   fast_grab_ready —— 快道决策态;
#   终态            —— 已终结。
# 禁止的是 tracking 及其后继:那等于让豁免候选绕过 G3 走到全站。
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


def _check_funnel(obj, where, errors):
    """漏斗自洽性:extracted == 四个去向之和。

    这条等式是"留痕纪律"的可校验形式:2026-08-18 首次 xinci-run 从 Apple Dev News
    提取了 5 条以上变更却只有 1 条走到 G1,其余既未注册也未进淘汰索引——无声丢弃使
    下轮重复评估。有了等式,漏掉的归宿会当场报错。

    两条不参与等式的口径(否则必然算不平):去重命中的方向不计入 extracted;
    消化存量 captured 的深审记 carryover_audited,不记 deep_audited。"""
    f = obj.get("funnel")
    if f is None:
        return
    if not isinstance(f, dict):
        errors.append(f"{where} funnel 必须是对象,当前 {type(f).__name__}")
        return
    unknown = sorted(set(f) - set(FUNNEL_ALL_FIELDS))
    if unknown:
        errors.append(f"{where} funnel 含 schema 外字段 {unknown}")
    missing = [k for k in FUNNEL_FIELDS if k not in f]
    if missing:
        errors.append(f"{where} funnel 缺字段 {missing}")
        return
    bad = [k for k in FUNNEL_ALL_FIELDS if k in f
           and (not isinstance(f[k], int) or isinstance(f[k], bool) or f[k] < 0)]
    if bad:
        errors.append(f"{where} funnel 各项必须是非负整数,不合格: {bad}")
        return
    total = sum(f[k] for k in FUNNEL_SINKS)
    if total != f["extracted"]:
        errors.append(f"{where} funnel 去向加总 {total} ≠ extracted {f['extracted']}"
                      f"(每个被提取的方向都要有归宿:秒弃/G1否决/深审/排队,不许无声丢弃)")


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

        for k in RUN_STR_ARRAYS:
            _check_str_array(obj, k, where, errors)
        _check_int(obj, "billable_calls", where, errors)
        _check_funnel(obj, where, errors)

        enforce_funnel = bool(run_date) and run_date >= FUNNEL_REQUIRED_FROM
        if enforce_funnel and skill == "xinci-scan" and obj.get("funnel") is None:
            errors.append(f"{where} xinci-scan 清单必须带 funnel"
                          f"(自 {FUNNEL_REQUIRED_FROM} 起强制:每个被提取的方向都要有归宿)")

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
            _check_funnel(rnd, rw, errors)
            if enforce_funnel and rnd.get("funnel") is None:
                errors.append(f"{rw} 必须带 funnel"
                              f"(自 {FUNNEL_REQUIRED_FROM} 起强制;"
                              "本轮没扫描就把 extracted 与四个去向五项全写 0)")
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
