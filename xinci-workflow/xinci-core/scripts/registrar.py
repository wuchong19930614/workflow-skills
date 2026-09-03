#!/usr/bin/env python3
"""xinci 候选账本 registrar:唯一的状态转移入口。

规则来源:xinci-core/生命周期契约.md(合法转移表 + 每转移证据要求)。
账本:<数据区>/账本/候选账本.json,本脚本独占写入,原子替换。
"""
import argparse
import hashlib
import json
import re
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import data_root
from _common import (atomic_save, check_actor, flock as _flock, funlock as _funlock, is_http_url,
                     ledger_path as _ledger_path, now as _now)
from _constants import GO_STATES, MIN_TRACK_SPAN_DAYS, MONETIZATION_LINES, SLUG_RE, TERMINAL

from run_controller import RunControllerError, require_active_round
from term_normalize import match_kind, normalize as normalize_term
from build_decision_html import render as render_decision_html
from run_policy import evaluate as evaluate_run_policy
from screen_index import DedupDecisionError, ScreenIndexError, check as check_screen_index
from trigger_pool import TriggerPoolError, current as current_triggers

# 数据区的定位统一走 data_root 模块:显式参数 > 环境变量 > 仓库配置 > 拒绝执行。
# 这里刻意不再留任何默认值——数据区放哪是用户的决定,脚本不猜(理由见 data_root.py)。

STATES = {
    "captured", "screened", "tracking", "formation_confirmed", "qualified",
    "build_ready", "pilot_ready", "fast_grab_ready", "hold",
    "rejected", "expired", "superseded", "withdrawn", "built", "disqualified", "no_site",
}
# 决策终局的唯一出边:被更好措辞的候选取代
SUPERSEDABLE_FINAL = {"disqualified", "no_site"}
OBS_STAGES = {"scan", "track", "qualify", "decide"}

LEGAL = {
    ("captured", "screened"), ("captured", "rejected"), ("captured", "expired"),
    ("screened", "rejected"), ("screened", "tracking"), ("screened", "fast_grab_ready"),
    # screened→expired:出闸后窗口自己过期(始终没排上快道/入库)的干净出口。
    # 与 captured→expired 同一条理由——它没有失败的闸门,不该被硬塞进 rejected。
    ("screened", "expired"),
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
# G3 三分(闸门契约 G3):pass=位置没被占;veto=被占满,出局;
# veto_window_bet=任务被做完但那些实现只因太新还没被收录,位置仅空几天——
# 只准走快道,禁止进 tracking(否则绕过 G3 走到全站),且不在连续运行的标准授权内。
# 被本出口拒收后(by=xinci-run),候选带着该结论挂在 captured 等用户单步确认:
# captured 是合法的挂起位,不要把它硬塞进 rejected——它没有失败的闸门。
G3_WINDOW_BET = "veto_window_bet"
QUALIFY_GATES = ("G6", "G7", "G8")
WINDOWS = {"days", "weeks", "months"}
BUILD_PLAYS = {"single_domain", "cluster_expansion"}
EXPIRY_TRIGGERS = {"date", "invalidation", "window_closed"}
# 自该日起新观察必须明示使用 schema v2；更早的 v1 历史证据继续只读兼容。
OBS_V2_REQUIRED_FROM = date(2026, 9, 2)
# 两条赛道(lane)。原 schema 已把 lane 预留为"本套固定为 new;为未来成熟词道预留"。
# 2026-08-23 开放 mature:两条盈利线(订阅 / 广告)对量级的要求方向相反,
# 广告线必须有真实搜索量才可能成立,而"查无"正是 new 道的定义属性——
# 所以广告线只能在 mature 道上工作,且该道不适用 new 道的 Semrush 禁令。
LANES = {"new", "mature"}
VALID_ACTORS = {"xinci-scan", "xinci-track", "xinci-qualify", "xinci-decide", "xinci-run",
                "xinci-mature", "user"}
GATE_NAMES = {f"G{i}" for i in range(9)}
GATE_VALUES = {"pass", "veto", G3_WINDOW_BET}
LEGACY_G6_LINES = {"subscription", "advertising"}

# ---- 状态不变式涉及的状态集合(check_state_invariants 与 validate_ledger 共用) ----
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


class RegistrarError(Exception):
    pass


def _load(data_root: Path) -> dict:
    p = _ledger_path(data_root)
    if not p.is_file():
        return {"schema_version": 1, "candidates": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def _save(data_root: Path, ledger: dict) -> None:
    atomic_save(_ledger_path(data_root), ledger)


@contextmanager
def _locked(data_root: Path):
    """账本互斥锁:load-modify-save 全程持有,防止并发会话(如 xinci-run 与手动操作)丢更新。"""
    lock_path = _ledger_path(data_root).parent
    lock_path.mkdir(parents=True, exist_ok=True)
    with open(lock_path / ".lock", "w") as f:
        _flock(f)
        try:
            yield
        finally:
            _funlock(f)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise RegistrarError(msg)


def _check_actor(data_root: Path, by: str, run_id=None) -> None:
    """验证执行身份与连续运行会话，禁止靠伪造 --by 绕过授权边界(实现见 _common.check_actor)。"""
    check_actor(data_root, by, run_id, actors=VALID_ACTORS, error_cls=RegistrarError)


def _open_ledger(data_root: Path, slug: str, by: str, run_id=None, *,
                 new_lane=None):
    """五个写入口共同的开场四件套(须在 _locked 内调用):
    验执行身份 → 读账本 → 定位候选 → 验 lane 边界。返回 (ledger, rec)。

    new_lane 给出时是注册语义:候选必须尚不存在,lane 边界按 (by, new_lane, "captured") 验,
    rec 返回 None。"""
    _check_actor(data_root, by, run_id)
    ledger = _load(data_root)
    if new_lane is not None:
        _require(slug not in ledger["candidates"], f"候选已存在: {slug}")
        _check_run_lane_boundary(by, new_lane, "captured")
        return ledger, None
    _require(slug in ledger["candidates"], f"候选不存在: {slug}")
    rec = ledger["candidates"][slug]
    _check_run_lane_boundary(by, rec.get("lane", "new"), rec["state"])
    return ledger, rec


MATURE_MANUAL_STATES = {"captured", "screened", "tracking"}


def _check_run_lane_boundary(by: str, lane: str, state: str) -> None:
    """两条 lane 边界:mature 前半程不属于 xinci-run 的标准授权范围;反向地,
    xinci-mature 只承接 mature 道,不碰 new。"""
    _require(not (by == "xinci-run" and lane == "mature"
                  and state in MATURE_MANUAL_STATES),
             f"xinci-run 不自动推进 mature 前半程(state={state});"
             "单步调用 xinci-mature 推进到 formation_confirmed,"
             "或显式单步调用 xinci-decide 处理已合法 screened 的快道候选")
    _require(not (by == "xinci-mature" and lane != "mature"),
             f"xinci-mature 只承接 lane=mature(当前 lane={lane!r});"
             "new 道的发现与前半程用 xinci-scan")
    _require(not (by in {"xinci-scan", "xinci-track"} and lane != "new"),
             f"{by} 只承接 lane=new(当前 lane={lane!r});"
             "mature 道在 formation_confirmed 前由 xinci-mature 承接")


def _run_history_fields(data_root: Path, run_id):
    """在真正追加 history 时重验活动轮次，并把轮号绑定到审计条目。"""
    if not run_id:
        return {}
    try:
        session = require_active_round(data_root, run_id)
    except RunControllerError as e:
        raise RegistrarError(str(e))
    return {"run_id": run_id, "round": session["current_round"]}


def _window_bet_confirmation(data_root: Path, rec: dict, run_id) -> dict:
    """连续模式窗口赌注出闸的确认核对:该 run 的 session 对该 slug 有用户确认,
    且候选 history 里尚无引用这条确认的出闸记录(确认只能消费一次)。返回要写进
    出闸 history 条目的消费凭据。"""
    try:
        session = require_active_round(data_root, run_id)
    except RunControllerError as e:
        raise RegistrarError(str(e))
    confirmation = session.get("confirmations", {}).get(rec["slug"])
    _require(bool(confirmation) and confirmation.get("risk") == "window_bet",
             f"G3={G3_WINDOW_BET} 出闸要求用户单步确认;"
             "先运行 run_controller.py confirm-window-bet")
    token = {"confirmed_at": confirmation["confirmed_at"], "run_id": run_id}
    _require(not any(h.get("window_bet_confirmation") == token for h in rec.get("history") or []),
             f"候选 {rec['slug']} 的窗口赌注确认已被 history 中的出闸记录消费;"
             "确认只能使用一次")
    return token


def _check_gate_payload(gates) -> None:
    gates = gates or {}
    unknown = sorted(set(gates) - GATE_NAMES)
    _require(not unknown, f"未知闸门: {unknown}")
    bad = sorted(k for k, v in gates.items() if v not in GATE_VALUES)
    _require(not bad, f"闸门结论只能是 {sorted(GATE_VALUES)},不合格: {bad}")


def _check_run_g1_preflight(data_root: Path, by: str, run_id, gates) -> None:
    """连续模式提交任何 G1 结论时，重验当前轮的浏览器预检(begin-round 时写进 session)。"""
    if by != "xinci-run" or "G1" not in (gates or {}):
        return
    try:
        session = require_active_round(data_root, run_id)
    except RunControllerError as e:
        raise RegistrarError(f"xinci-run 提交 G1 要求当前轮次的浏览器预检: {e}")
    # round_executor_id 缺失只可能来自升级前已打开的轮次或库级兼容调用；
    # 新 CLI 的 begin-round 已强制 executor-id。兼容旧轮，不替它创造新授权。
    if session.get("round_executor_id") is None:
        return
    preflight = session.get("current_round_preflight")
    _require(preflight is not None,
             "xinci-run 提交 G1 要求当前轮次的浏览器预检:begin-round 时未提交 --browser-* 四项")
    _require(preflight.get("g1_ready") is True,
             "xinci-run 提交 G1 要求浏览器预检满足可控/桌面/美区/未登录")


def _check_url(value: str, field: str) -> None:
    _require(is_http_url(value), f"{field} 必须是 http(s) URL: {value!r}")


def _check_evidence(data_root: Path, refs, slug=None) -> list:
    refs = list(refs or [])
    for r in refs:
        rel = Path(r)
        _require(not rel.is_absolute() and ".." not in rel.parts,
                 f"证据路径必须是数据区内的相对路径(禁绝对路径与 ..): {r}")
        f = Path(data_root) / r
        _require(f.is_file(), f"证据文件不存在: {r}")
        if rel.parts and rel.parts[0] == "证据" and rel.suffix == ".json":
            _require(slug is None or (len(rel.parts) >= 3 and rel.parts[1] == slug),
                     f"证据文件必须位于 证据/{slug}/ 目录下: {r}")
            _check_observation(f, r, slug)
    return refs


OBS_FIELDS = {"schema_version", "slug", "observed_at", "stage", "source_urls", "points", "gates",
              "g6_lines", "g6_tentative_lines", "g6_entry_veto", "income_score", "window_bet",
              "naming_status", "formation_signals", "cluster_counterfactual"}
WINDOW_BET_FIELDS = {"implementation_urls", "lag_sample_url", "lag_days", "rationale"}


def _check_observation(path: Path, ref: str, slug) -> None:
    """观察文件内容校验,与 数据结构/observation.schema.json 全量对齐
    (含 additionalProperties: false——多余字段多半是仪式性填充,数据极简原则拒收)。"""
    try:
        obs = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RegistrarError(f"观察文件不是合法 JSON: {ref}")
    _require(isinstance(obs, dict), f"观察文件必须是 JSON 对象: {ref}")
    _require(obs.get("schema_version", 1) in {1, 2},
             f"观察文件 schema_version 只能是 1/2: {ref}")
    for k in ("slug", "observed_at", "stage", "points"):
        _require(bool(obs.get(k)), f"观察文件缺必填字段 {k}: {ref}")
    unknown = sorted(set(obs) - OBS_FIELDS)
    _require(not unknown, f"观察文件含 schema 外字段 {unknown}(数据极简,勿加仪式性字段): {ref}")
    _require(slug is None or obs["slug"] == slug,
             f"观察文件 slug={obs['slug']!r} 与候选 {slug!r} 不一致: {ref}")
    try:
        observed = datetime.fromisoformat(obs["observed_at"])
    except (TypeError, ValueError):
        raise RegistrarError(f"观察文件 observed_at 必须是 ISO 8601 时间: {ref}")
    _require(observed.tzinfo is not None, f"观察文件 observed_at 必须带时区: {ref}")
    if observed.date() >= OBS_V2_REQUIRED_FROM:
        _require(obs.get("schema_version") == 2,
                 f"自 {OBS_V2_REQUIRED_FROM.isoformat()} 起的新观察必须明示写 schema_version=2: {ref}")
    _require(obs["stage"] in OBS_STAGES, f"观察文件 stage 必须属于 {sorted(OBS_STAGES)}: {ref}")
    _require(Path(ref).stem.endswith(f"-{obs['stage']}"),
             f"观察文件 stage={obs['stage']!r} 与文件名不一致(约定 <日期>-<阶段>.json): {ref}")
    pts = obs["points"]
    _require(isinstance(pts, list) and len(pts) >= 1 and all(isinstance(x, str) and x for x in pts),
             f"观察文件 points 必须是非空字符串数组: {ref}")
    urls = obs.get("source_urls", [])
    _require(isinstance(urls, list) and all(isinstance(u, str) and u for u in urls),
             f"观察文件 source_urls 必须是字符串数组: {ref}")
    for url in urls:
        _check_url(url, f"观察文件 source_urls({ref})")
    gates = obs.get("gates", {})
    _require(isinstance(gates, dict) and all(isinstance(v, str) for v in gates.values()),
             f"观察文件 gates 必须是 闸门→字符串结论 的对象: {ref}")
    _check_gate_payload(gates)
    g6_lines = obs.get("g6_lines")
    if g6_lines is not None:
        _require(isinstance(g6_lines, dict)
                 and LEGACY_G6_LINES <= set(g6_lines) <= MONETIZATION_LINES,
                 f"观察文件 g6_lines 至少包含 subscription/advertising 且不得含未知盈利线: {ref}")
        _require(all(v in {"pass", "veto", "N/A"} for v in g6_lines.values()),
                 f"观察文件 g6_lines 结论只能是 pass/veto/N/A: {ref}")
        if obs.get("schema_version", 1) >= 2:
            _require(set(g6_lines) == MONETIZATION_LINES,
                     f"schema v2 的 g6_lines 必须完整包含六条盈利线: {ref}")
    g6_tentative_lines = obs.get("g6_tentative_lines")
    if g6_tentative_lines is not None:
        _require(obs["stage"] in {"scan", "track"},
                 f"观察文件 g6_tentative_lines 只适用于 scan/track 窗口期: {ref}")
        _require(g6_lines is None,
                 f"观察文件不得同时写 g6_tentative_lines 与正式 g6_lines: {ref}")
        _require(isinstance(g6_tentative_lines, dict)
                 and LEGACY_G6_LINES <= set(g6_tentative_lines) <= MONETIZATION_LINES,
                 f"观察文件 g6_tentative_lines 至少包含 subscription/advertising 且不得含未知盈利线: {ref}")
        _require(all(v in {"tentative_pass", "tentative_veto", "N/A"}
                     for v in g6_tentative_lines.values()),
                 f"观察文件 g6_tentative_lines 结论只能是 "
                 f"tentative_pass/tentative_veto/N/A: {ref}")
        if obs.get("schema_version", 1) >= 2:
            _require(set(g6_tentative_lines) == MONETIZATION_LINES,
                     f"schema v2 的 g6_tentative_lines 必须完整包含六条盈利线: {ref}")
    if obs["stage"] in {"scan", "track"} and "G3" in gates:
        _require(g6_tentative_lines is not None,
                 f"scan/track 观察提交 G3 时必须同时写 g6_tentative_lines: {ref}")
    entry_veto = obs.get("g6_entry_veto")
    if entry_veto is not None:
        allowed = {"repeat_paid_task", "official_count_class", "self_serve_legal_effect"}
        _require(obs["stage"] in {"scan", "track"}
                 and isinstance(entry_veto, dict)
                 and set(entry_veto) == {"criterion", "reason"}
                 and entry_veto.get("criterion") in allowed
                 and isinstance(entry_veto.get("reason"), str)
                 and entry_veto["reason"].strip(),
                 f"观察文件 g6_entry_veto 必须是 scan/track 的结构性入口否决: {ref}")
        _require(g6_lines is None and "G6" not in gates,
                 f"g6_entry_veto 不得伪装成正式 G6: {ref}")
        if entry_veto.get("criterion") == "self_serve_legal_effect":
            _require(g6_tentative_lines is None,
                     f"self_serve_legal_effect 仅表示所有声称交付均依法无效的全局否决，"
                     f"不得同时写暂定盈利线；只影响部分线时改为逐线判定: {ref}")
        _require(bool(urls), f"g6_entry_veto 必须包含实际打开的 source_urls: {ref}")
    naming_status = obs.get("naming_status")
    if naming_status is not None:
        _require(obs["stage"] == "track" and naming_status in {"unstable", "stabilized"},
                 f"观察文件 naming_status 只适用于 track 且必须为 unstable/stabilized: {ref}")
    formation_signals = obs.get("formation_signals")
    if formation_signals is not None:
        allowed_signals = {"autocomplete", "semrush_rows", "sustained_discussion",
                           "repeated_independent_queries"}
        _require(obs["stage"] == "track" and isinstance(formation_signals, list)
                 and len(formation_signals) == len(set(formation_signals))
                 and all(x in allowed_signals for x in formation_signals),
                 f"观察文件 formation_signals 只适用于 track，且必须是合法且不重复的形成信号数组: {ref}")
    cluster = obs.get("cluster_counterfactual")
    if cluster is not None:
        required = {"atomic_task_completed", "batch_processing", "monitoring", "audit_trail",
                    "export_integration", "multi_jurisdiction", "decision", "reason"}
        _require(isinstance(cluster, dict) and set(cluster) == required
                 and all(isinstance(cluster[k], bool) for k in required - {"decision", "reason"})
                 and cluster.get("decision") in {"viable_cluster", "atomic_only"}
                 and isinstance(cluster.get("reason"), str) and cluster["reason"].strip(),
                 f"观察文件 cluster_counterfactual 必须完整记录原子任务与六种扩展反事实: {ref}")
        extensions = ("batch_processing", "monitoring", "audit_trail",
                      "export_integration", "multi_jurisdiction")
        if cluster["decision"] == "atomic_only":
            _require(cluster["atomic_task_completed"] and not any(cluster[k] for k in extensions),
                     f"cluster_counterfactual=atomic_only 要求原子任务已完成且五种扩展均不成立: {ref}")
        else:
            _require(cluster["atomic_task_completed"] and any(cluster[k] for k in extensions),
                     f"cluster_counterfactual=viable_cluster 要求原子任务已完成且至少一种扩展成立: {ref}")
    if gates.get("G1") == "veto":
        _require(cluster is not None and cluster.get("decision") == "atomic_only",
                 f"G1=veto 必须由 cluster_counterfactual=atomic_only 支撑，不能只凭原子任务判死: {ref}")
    obs_income_score = obs.get("income_score")
    if obs_income_score is not None:
        _require(isinstance(obs_income_score, int) and not isinstance(obs_income_score, bool)
                 and 1 <= obs_income_score <= 20,
                 f"观察文件 income_score 必须是 1–20 的整数: {ref}")
    window_bet = obs.get("window_bet")
    if window_bet is not None:
        _require(isinstance(window_bet, dict), f"观察文件 window_bet 必须是对象: {ref}")
        unknown = sorted(set(window_bet) - WINDOW_BET_FIELDS)
        _require(not unknown, f"观察文件 window_bet 含未知字段 {unknown}: {ref}")
        _require(set(window_bet) == WINDOW_BET_FIELDS,
                 f"观察文件 window_bet 必须完整包含 {sorted(WINDOW_BET_FIELDS)}: {ref}")
        implementations = window_bet["implementation_urls"]
        _require(isinstance(implementations, list) and implementations,
                 f"window_bet implementation_urls 必须是非空数组: {ref}")
        for url in implementations:
            _check_url(url, f"window_bet implementation_urls({ref})")
        _check_url(window_bet["lag_sample_url"], f"window_bet lag_sample_url({ref})")
        _require(isinstance(window_bet["lag_days"], int) and window_bet["lag_days"] >= 0,
                 f"window_bet lag_days 必须是非负整数: {ref}")
        _require(isinstance(window_bet["rationale"], str) and window_bet["rationale"].strip(),
                 f"window_bet rationale 必须是非空字符串: {ref}")
        cited = set(implementations + [window_bet["lag_sample_url"]])
        _require(cited <= set(urls), f"window_bet 使用的 URL 必须全部列入 source_urls: {ref}")


def _load_observation(data_root: Path, ref: str) -> dict:
    return json.loads((Path(data_root) / ref).read_text(encoding="utf-8"))


def _has_no_applicable_tentative_g6(data_root: Path, refs, lane: str) -> bool:
    """本次窗口期证据是否证明没有任何适用盈利线。

    暂定结论只存在于 observation.g6_tentative_lines,不得伪装成正式 gates.G6。
    因此已注册的 captured/tracking 候选按该理由出清时,registrar 直接核对本次证据。
    """
    observations = [_load_observation(data_root, ref) for ref in refs
                    if Path(ref).parts and Path(ref).parts[0] == "证据"
                    and Path(ref).suffix == ".json"]
    for obs in observations:
        if obs.get("stage") not in {"scan", "track"}:
            continue
        lines = obs.get("g6_tentative_lines")
        if not isinstance(lines, dict):
            continue
        applicable = [value for value in lines.values() if value != "N/A"]
        no_line = bool(applicable) and all(value == "tentative_veto" for value in applicable)
        if no_line:
            _require(bool(obs.get("source_urls")),
                     "暂定 G6 无适用盈利线的支撑观察必须包含实际打开的 source_urls")
            return True
    return False


def _has_structural_g6_entry_veto(data_root: Path, refs) -> bool:
    """只有所有声称的自助交付在法律上均无效，才是整候选的结构性否决。

    repeat_paid_task 只约束 subscription；official_count_class 只约束依赖该统计
    口径的算式。二者可作为逐线判断的依据，但不得单独授权整候选 rejected。
    """
    for ref in refs:
        if not (Path(ref).parts and Path(ref).parts[0] == "证据" and Path(ref).suffix == ".json"):
            continue
        obs = _load_observation(data_root, ref)
        entry = obs.get("g6_entry_veto")
        if (obs.get("stage") in {"scan", "track"} and isinstance(entry, dict)
                and entry.get("criterion") == "self_serve_legal_effect"):
            _require(bool(obs.get("source_urls")), "G6 结构性入口否决必须包含实际打开的 source_urls")
            return True
    return False


def _check_gate_evidence(data_root: Path, refs, gates, context: str) -> None:
    """闸门提交必须由本次新观察直接支撑，不能拿无关文件充数。"""
    gates = gates or {}
    if not gates:
        return
    observations = [_load_observation(data_root, ref) for ref in refs
                    if Path(ref).parts and Path(ref).parts[0] == "证据"
                    and Path(ref).suffix == ".json"]
    _require(bool(observations), f"{context} 提交 gates 时必须同时提交本次 observation 证据")
    for gate, value in gates.items():
        claims = [obs.get("gates", {}).get(gate) for obs in observations
                  if gate in (obs.get("gates") or {})]
        _require(bool(claims), f"{context} 的 {gate}={value} 未出现在本次 observation.gates 中")
        _require(all(v == value for v in claims),
                 f"{context} 的 {gate}={value} 与本次 observation.gates 冲突: {claims}")
        supporters = [obs for obs in observations if obs.get("gates", {}).get(gate) == value]
        _require(all(obs.get("source_urls") for obs in supporters),
                 f"{context} 的 {gate}={value} 支撑观察必须包含实际打开的 source_urls")
        if gate == "G3" and value == G3_WINDOW_BET:
            _require(any(obs.get("window_bet") for obs in supporters),
                     "G3=veto_window_bet 必须有结构化 window_bet 证据"
                     "(免费实现 URL、上一个同类对象收录时差、天数和理由)")


def _check_evidence_reuse(data_root: Path, rec: dict, refs) -> None:
    """拒收「已被历史条目引用、但当前内容已不再支撑那条历史闸门」的观察文件。

    出处是 2026-08-22 的一次真实事故:连续运行复用同日文件名 `<日期>-scan.json`
    写本轮观察,覆盖了同一路径上前一次的观察,使 24 条 history 的闸门失去证据支撑,
    最后由 validate_ledger 事后才发现。把这道检查提到写入时,让它 fail fast——
    覆盖已被引用的证据是不可逆的信息损失,事后只能靠 git 或原文侥幸恢复。
    """
    for ref in refs:
        for i, h in enumerate(rec.get("history") or []):
            if ref not in (h.get("evidence") or []):
                continue
            claimed = h.get("gates") or {}
            if not claimed:
                continue
            try:
                obs_gates = _load_observation(data_root, ref).get("gates") or {}
            except (OSError, ValueError):
                continue
            lost = {g: v for g, v in claimed.items() if obs_gates.get(g) != v}
            _require(not lost,
                     f"观察文件 {ref} 已被 history[{i}] 引用并提交 "
                     + ",".join(f"{g}={v}" for g, v in sorted(lost.items()))
                     + ",但该文件当前内容已不再支撑这些结论——极可能是复用同名文件把上一次的观察覆盖了。"
                       "请另起文件名(如加 <HHMM> 后缀)写本次观察,不要覆盖已被引用的证据。")


def _obs_time(data_root: Path, ref: str) -> datetime:
    """读观察文件的 observed_at,统一为 aware datetime(naive 视为 UTC)。"""
    obs = json.loads((Path(data_root) / ref).read_text(encoding="utf-8"))
    try:
        dt = datetime.fromisoformat(obs["observed_at"])
    except (KeyError, TypeError, ValueError):
        raise RegistrarError(f"观察文件 observed_at 不可解析为 ISO 8601: {ref}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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
    rel = Path(decision_ref)
    _require(not rel.is_absolute() and ".." not in rel.parts,
             f"决策书路径必须是数据区内的相对路径(禁绝对路径与 ..): {decision_ref}")
    md = Path(data_root) / decision_ref
    _require(md.is_file() and md.suffix == ".md", f"决策书 md 不存在: {decision_ref}")
    html = md.with_suffix(".html")
    _require(html.is_file(), f"决策书双格式要求同名 html 同批存在,缺: {html.name}")
    raw = md.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    html_text = html.read_text(encoding="utf-8")
    marker = re.search(r'<meta name="xinci-source-sha256" content="([a-f0-9]{64})">', html_text)
    _require(marker and marker.group(1) == digest,
             "决策书 html 不是由当前 md 生成(缺源哈希或 md 修改后未重新生成);")
    _require(html_text == render_decision_html(md),
             "决策书 html 内容与当前 md 的确定性渲染结果不一致;禁止伪造 meta 或手改 html")
    md_text = raw.decode("utf-8")
    required = ["失效条件", "下一步人工动作"]
    missing = [title for title in required if not re.search(rf"^#+\s+.*{title}", md_text, re.MULTILINE)]
    _require(not missing, f"决策书缺必需章节: {missing}")
    return decision_ref


def _inv(code: str, msg: str) -> str:
    """状态不变式错误统一带机器码前缀 [INV-<code>]:文案可改,码不改,测试与外部工具按码识别。"""
    return f"[INV-{code}] {msg}"


def check_state_invariants(data_root, rec: dict) -> list:
    """对一条候选记录返回它违反的状态不变式(文案列表,空即合规)。

    这是 registrar 各目标状态准入条件的"记录视角"版本:转移成功写入前对写入后的记录调一次
    (拒绝任何会写出不合规记录的转移);validate_ledger 对账本每条记录调同一函数,捕获绕过
    registrar 的手工编辑。两处共用同一份条目,不再各抄一遍。

    只看记录本身(含 history 与其引用的观察文件);"本次提交至少 1 个证据"、"reason 必填"
    这类只在转移瞬间有意义的条件仍留在 transition 里。
    """
    data_root = Path(data_root)
    errors = []
    state = rec.get("state")
    expiry = rec.get("expiry")
    hist = rec.get("history") or []

    if state == "screened" and rec.get("window_estimate") not in WINDOWS:
        errors.append(_inv("screened-window",
                           f"screened 必有 window_estimate ∈ {sorted(WINDOWS)},"
                           f"当前 {rec.get('window_estimate')!r}"))
    if state == "screened" and not expiry:
        errors.append(_inv("screened-expiry", "screened 必有 expiry(窗口失效日)"))
    if state == "tracking" and not expiry:
        errors.append(_inv("tracking-expiry", "tracking 必有 expiry"))
    if state == "captured" and rec.get("gates") and not expiry:
        errors.append(_inv("captured-queue-expiry",
                           "captured 带闸门结论(排队位)必有 expiry:"
                           "排队位每轮进多出少,没有 expiry 就没有过期出口,方向会无声腐烂"))
    if state == "fast_grab_ready":
        if not expiry:
            errors.append(_inv("fast-grab-expiry", "fast_grab_ready 必有 expiry"))
        if rec.get("window_estimate") != "days":
            errors.append(_inv("fast-grab-window",
                               f"fast_grab_ready 必有 window_estimate=days,"
                               f"当前 {rec.get('window_estimate')!r}"))
        if rec.get("play") != "fast_grab":
            errors.append(_inv("fast-grab-play",
                               f"fast_grab_ready 的 play 必须是 fast_grab,当前 {rec.get('play')!r}"))
        if rec.get("score") is not None:
            errors.append(_inv("fast-grab-score",
                               f"快道不得声称全站分数,score 应为 null,当前 {rec.get('score')!r}"))
    gates = rec.get("gates") or {}
    try:
        _check_gate_payload(gates)
    except RegistrarError as e:
        errors.append(_inv("gates-payload", str(e)))
    g3 = gates.get("G3")
    if state in SCREEN_PASSED_STATES:
        bad = [g for g in SCREEN_GATES if g != "G3" and gates.get(g) != "pass"]
        if g3 not in ("pass", G3_WINDOW_BET):
            bad.append("G3")
        if bad:
            errors.append(_inv("screen-gates",
                               f"{state} 要求 G0/G1/G2/G4/G5=pass,"
                               f"G3=pass 或 {G3_WINDOW_BET},未满足: {bad}"))
    if g3 == G3_WINDOW_BET:
        # 降级结论只通向快道:出现在 tracking 及其后继意味着绕过了 G3
        if state not in WINDOW_BET_STATES:
            errors.append(_inv("window-bet-state",
                               f"G3={G3_WINDOW_BET} 的候选只能是 captured(挂起待确认)/"
                               f"screened/fast_grab_ready 或终态,当前 {state}"
                               "——进入该状态意味着绕过了 G3"))
        if state in {"screened", "fast_grab_ready"} and rec.get("window_estimate") != "days":
            errors.append(_inv("window-bet-window",
                               f"G3={G3_WINDOW_BET} 要求 window_estimate=days,"
                               f"当前 {rec.get('window_estimate')!r}"))
    if state in QUALIFY_PASSED_STATES:
        bad = [g for g in QUALIFY_GATES if gates.get(g) != "pass"]
        if bad:
            errors.append(_inv("qualify-gates", f"{state} 要求 G6–G8 全 pass,未满足: {bad}"))
    if state in FORMED_STATES:
        track_refs = [r for r in rec.get("evidence_refs", [])
                      if Path(r).stem.endswith("-track") and (data_root / r).is_file()]
        if len(track_refs) < 2:
            errors.append(_inv("track-count",
                               f"{state} 要求 ≥2 个 -track 观察,当前 {len(track_refs)}"))
        else:
            try:
                times = [_obs_time(data_root, r) for r in track_refs]
                span = (max(times) - min(times)).days
                if span < MIN_TRACK_SPAN_DAYS:
                    errors.append(_inv("track-span",
                                       f"{state} 要求 -track 观察跨度 ≥{MIN_TRACK_SPAN_DAYS} 天,"
                                       f"当前 {span} 天"))
            except RegistrarError as e:
                errors.append(_inv("track-obs-time", str(e)))
    if state in SCORED_STATES:
        score = rec.get("score")
        if not (isinstance(score, int) and score >= 80):
            errors.append(_inv("score", f"{state} 必有整数 score ≥80,当前 {score!r}"))
        income_score = rec.get("income_score")
        if not (isinstance(income_score, int) and not isinstance(income_score, bool)
                and 1 <= income_score <= 20):
            errors.append(_inv("income-score",
                               f"{state} 必有 1–20 的整数 income_score,当前 {income_score!r}"))
        lines = rec.get("g6_passed_lines")
        if not (isinstance(lines, list) and lines and len(lines) == len(set(lines))
                and set(lines) <= MONETIZATION_LINES):
            errors.append(_inv("g6-lines",
                               f"{state} 必有非空且合法的 g6_passed_lines,当前 {lines!r}"))
        elif rec.get("lane") == "new" and "advertising" in lines:
            errors.append(_inv("g6-advertising", "lane=new 的 g6_passed_lines 不得包含 advertising"))
        qualified_entry = next((h for h in reversed(hist) if h.get("to") == "qualified"), None)
        if qualified_entry is None:
            errors.append(_inv("qualified-snapshot", f"{state} 缺 →qualified history 快照"))
        else:
            if qualified_entry.get("income_score") != income_score:
                errors.append(_inv("snapshot-income",
                                   "顶层 income_score 与 →qualified history 快照不一致"))
            if qualified_entry.get("g6_passed_lines") != lines:
                errors.append(_inv("snapshot-lines",
                                   "顶层 g6_passed_lines 与 →qualified history 快照不一致"))
            qualify_obs = []
            for ref in qualified_entry.get("evidence", []):
                try:
                    obs = json.loads((data_root / ref).read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if (obs.get("stage") == "qualify"
                        and obs.get("gates", {}).get("G6") == "pass"):
                    qualify_obs.append(obs)
            if not qualify_obs:
                errors.append(_inv("qualify-obs", "→qualified history 缺结构化 G6 qualify 观察"))
            elif isinstance(lines, list):
                def lines_match(obs):
                    observed = obs.get("g6_lines") or {}
                    return (all(observed.get(line) == "pass" for line in lines)
                            and not any(value == "pass" and line not in lines
                                        for line, value in observed.items())
                            and (rec.get("lane") != "new"
                                 or observed.get("advertising") == "N/A"))
                if any(not lines_match(obs) for obs in qualify_obs):
                    errors.append(_inv("qualify-obs-lines", "qualify 观察 g6_lines 与账本不一致"))
                if any(obs.get("income_score") != income_score for obs in qualify_obs):
                    errors.append(_inv("qualify-obs-income", "qualify 观察 income_score 与账本不一致"))
    if state in {"build_ready", "pilot_ready"} and rec.get("play") not in BUILD_PLAYS:
        errors.append(_inv("build-play",
                           f"{state} 的 play 必须属于 {sorted(BUILD_PLAYS)},当前 {rec.get('play')!r}"))

    ref = rec.get("decision_ref")
    if state in GO_STATES:
        if not ref:
            errors.append(_inv("decision-ref", "go 决策态缺 decision_ref"))
        else:
            md = data_root / ref
            html = md.with_suffix(".html")
            if not md.is_file():
                errors.append(_inv("decision-md", f"决策书 md 缺失: {ref}"))
            if not html.is_file():
                errors.append(_inv("decision-html", f"决策书 html 缺失(双格式要求): {html.name}"))
            if md.is_file() and html.is_file():
                try:
                    _check_decision_files(data_root, ref)
                except RegistrarError as e:
                    errors.append(_inv("decision-files", f"决策书校验失败: {e}"))
    if state in NO_GO_STATES and ref:
        errors.append(_inv("nogo-decision-ref", f"no-go 结论不应携带 decision_ref: {ref}"))
    return errors


def register(data_root, slug, term, source_url, task, evidence,
             source_note="", aliases=None, by="xinci-scan", gates=None, expiry=None,
             run_id=None, lane="new", origin=None, trigger_ref=None,
             site_thesis=None, task_families=None):
    """注册新候选(→captured)。

    gates 可选:扫描漏斗中"本轮没走完深审"的存活候选注册成 captured 排队时,带上已得的
    闸门结论,下轮按 gates 补跑缺的门(缺 G1 的先补 G1)再进深审(xinci-scan 第 3/4 层)。

    expiry 可选,但**带 gates 时必填**:排队位每轮进多出少,没有 expiry 就没有过期出口,
    窗口过了的方向会在队列里无声腐烂(report_status 只按 expiry 提示到期候选)。"""
    data_root = Path(data_root)
    _require(bool(slug and term and source_url and task), "slug/term/source_url/task 均不可为空")
    _require(bool(SLUG_RE.fullmatch(slug)), "slug 必须是 kebab-case 小写字母/数字/连字符")
    _check_gate_payload(gates)
    _check_url(source_url, "source_url")
    task_families = list(dict.fromkeys(task_families or []))
    with _locked(data_root):
        return _register_locked(data_root, slug, term, source_url, task, evidence,
                                source_note, aliases, by, gates, expiry, run_id, lane,
                                origin, trigger_ref, site_thesis, task_families)


def require_formal_admission(data_root, by, run_id, term=None, origin=None, trigger_ref=None):
    """正式 CLI 写入口的硬闸；迁移与单元测试可继续直接调用库函数。"""
    if by != "xinci-run":
        return
    policy = evaluate_run_policy(data_root, run_id)
    _require(policy.get("formal_admission") is True,
             "运行策略禁止新增正式候选: mode=" + str(policy.get("mode"))
             + "; " + "; ".join(policy.get("reasons") or ["未满足 admission 条件"]))
    _require(origin in {"signal", "trigger"},
             "xinci-run register 必须声明 --origin signal|trigger")
    if origin == "trigger":
        _require(bool(trigger_ref), "origin=trigger 要求 --trigger-id")
        try:
            trigger = current_triggers(data_root).get(trigger_ref)
        except TriggerPoolError as e:
            raise RegistrarError(str(e))
        _require(trigger and trigger.get("status") == "approved",
                 "--trigger-id 必须指向 approved trigger")
        _require(normalize_term(trigger.get("query", "")) == normalize_term(term or ""),
                 "candidate term 必须与 approved trigger.query 精确归一化一致")
    else:
        _require(not trigger_ref, "origin=signal 不得携带 --trigger-id")


def _check_not_duplicate(data_root: Path, wanted_names) -> None:
    """注册期去重:term 与每个 alias 都不得与账本候选或淘汰方向索引重复。

    匹配逻辑与 screen_index.check 完全同一份(精确命中即重复;疑似重复须有 distinct 裁决,
    same 裁决即重复);索引损坏时 strict 读取直接拒绝,不能带着读不全的索引放行。
    """
    try:
        found = check_screen_index(data_root, wanted_names, strict=True)
    except ScreenIndexError as e:
        raise RegistrarError(f"{e};不能安全去重注册")
    except DedupDecisionError as e:
        raise RegistrarError(str(e))

    def owner(hit):
        return "账本候选" if hit.get("gate") == "账本" else "淘汰方向索引"

    for hit in found["seen"]:
        if match_kind(hit["term"], hit["matched"]) == "exact":
            raise RegistrarError(f"term/alias {hit['term']!r} 已存在于{owner(hit)}"
                                 f"({hit['matched']!r}: {hit['reason']});不得重复注册")
        raise RegistrarError(f"去重裁决已判定 {hit['term']!r} 与{owner(hit)}的 "
                             f"{hit['matched']!r} 为 same;不得重复注册")
    for hit in found["review"]:
        raise RegistrarError(f"term/alias {hit['term']!r} 与{owner(hit)}的 {hit['matched']!r} 疑似重复;"
                             "先用 screen_index.py resolve 登记 same/distinct 裁决")


def _register_locked(data_root, slug, term, source_url, task, evidence,
                     source_note, aliases, by, gates=None, expiry=None, run_id=None,
                     lane="new", origin=None, trigger_ref=None,
                     site_thesis=None, task_families=None):
    ledger, _ = _open_ledger(data_root, slug, by, run_id, new_lane=lane)
    _check_run_g1_preflight(data_root, by, run_id, gates)
    if by == "xinci-run":
        _require(isinstance(site_thesis, str) and site_thesis.strip(),
                 "xinci-run 新候选必须记录 site_thesis")
        _require(len(task_families) >= 2 and all(isinstance(x, str) and x.strip()
                                                 for x in task_families),
                 "xinci-run 新候选必须记录至少两个独立 task_family")
    _check_not_duplicate(data_root, [term] + list(aliases or []))
    _require(lane in LANES, f"lane 只能是 {sorted(LANES)},当前 {lane!r}")
    refs = _check_evidence(data_root, evidence, slug=slug)
    _require(len(refs) >= 1, "注册候选要求至少 1 个证据文件")
    _check_gate_evidence(data_root, refs, gates, "register")
    if gates:
        _require(bool(expiry),
                 "带 gates 注册(排队位)要求 expiry:排队位每轮进多出少,"
                 "没有 expiry 就没有过期出口,窗口过了的方向会在队列里无声腐烂")
    if expiry:
        _check_date(expiry, "expiry")
    now = _now()
    ledger["candidates"][slug] = {
        "slug": slug,
        "term": term,
        "aliases": list(aliases or []),
        "state": "captured",
        "lane": lane,
        "first_observed_at": now,
        "last_checked_at": now,
        "expiry": expiry,
        "source": {"url": source_url, "note": source_note},
        "task": task,
        **({"site_thesis": site_thesis.strip()} if site_thesis else {}),
        **({"task_families": list(task_families)} if task_families else {}),
        **({"origin": origin} if origin else {}),
        **({"trigger_ref": trigger_ref} if trigger_ref else {}),
        "window_estimate": None,
        "play": None,
        "gates": dict(gates or {}),
        "score": None,
        "income_score": None,
        "g6_passed_lines": [],
        "invalidation": [],
        "evidence_refs": refs,
        "decision_ref": None,
        "superseded_by": None,
        "recheck_after": None,
        "history": [dict({"at": now, "from": None, "to": "captured", "by": by,
                          "evidence": refs},
                         **_run_history_fields(data_root, run_id),
                         **({"gates": dict(gates)} if gates else {}),
                         **({"expiry": expiry} if expiry else {}))],
    }
    _save(data_root, ledger)
    return ledger["candidates"][slug]


def transition(data_root, slug, to, by, gates=None, window_estimate=None, expiry=None,
               invalidation=None, score=None, income_score=None, g6_passed_lines=None,
               decision_ref=None, play=None,
               reason=None, evidence=None, superseded_by=None, expiry_trigger=None,
               run_id=None):
    data_root = Path(data_root)
    _check_gate_payload(gates)
    with _locked(data_root):
        return _transition_locked(data_root, slug, to, by, gates, window_estimate, expiry,
                                  invalidation, score, income_score, g6_passed_lines,
                                  decision_ref, play,
                                  reason, evidence, superseded_by, expiry_trigger, run_id)


def _transition_locked(data_root, slug, to, by, gates, window_estimate, expiry,
                       invalidation, score, income_score, g6_passed_lines,
                       decision_ref, play,
                       reason, evidence, superseded_by, expiry_trigger, run_id):
    ledger, rec = _open_ledger(data_root, slug, by, run_id)
    _check_run_g1_preflight(data_root, by, run_id, gates)
    frm = rec["state"]
    _require(to in STATES, f"未知状态: {to}")
    if to != "qualified":
        _require(income_score is None and g6_passed_lines is None,
                 "income_score / g6_passed_lines 只能在 →qualified 时提交")

    if to == "withdrawn":
        _require(frm not in TERMINAL, f"终态候选不可再转移: {frm}")
        _require(bool(reason), "withdrawn 要求 reason")
    elif to == "superseded":
        # 决策终局(disqualified/no_site)的唯一出边即 superseded;其余终态无出边
        _require(frm not in TERMINAL or frm in SUPERSEDABLE_FINAL,
                 f"终态候选不可再转移: {frm}")
        _require(bool(superseded_by) and superseded_by != slug
                 and superseded_by in ledger["candidates"],
                 f"superseded 要求 superseded_by 指向账本中已存在的其他候选: {superseded_by!r}")
    else:
        _require((frm, to) in LEGAL, f"非法转移: {frm} -> {to}")

    refs = _check_evidence(data_root, evidence, slug=slug)
    _check_gate_evidence(data_root, refs, gates, f"{frm}→{to}")
    _check_evidence_reuse(data_root, rec, refs)
    merged_refs = rec["evidence_refs"] + [r for r in refs if r not in rec["evidence_refs"]]
    window_bet_confirmation = None

    if to == "screened":
        # 闸门结论是候选的累积属性:排队的 captured 候选注册时已带 G0/G4/G5/G1,
        # 下轮只补交 G2/G3 即可(xinci-scan 第 4 层的排队机制),故按合并结果校验。
        # 注:formation_confirmed 的 G1 与 qualified 的 G6–G8 仍只看本次提交——
        # 前者契约要求"本次重跑 G1",后者是认定阶段一次性做完的。
        merged_gates = dict(rec["gates"], **(gates or {}))
        _check_gates(merged_gates, [g for g in SCREEN_GATES if g != "G3"], "captured→screened")
        g3 = merged_gates.get("G3")
        _require(g3 in ("pass", G3_WINDOW_BET),
                 f"captured→screened 要求 G3=pass 或 {G3_WINDOW_BET}(临时空位降级出口),当前 {g3!r}")
        _require(window_estimate in WINDOWS, f"window_estimate 必须属于 {sorted(WINDOWS)}")
        _require(bool(expiry), "captured→screened 要求 expiry(窗口失效日)")
        _check_date(expiry, "expiry")
        _require(len(refs) >= 1, "captured→screened 要求本次至少 1 个证据")
        if g3 == G3_WINDOW_BET:
            _require(window_estimate == "days",
                     f"G3={G3_WINDOW_BET} 只适用于窗口以天计的候选(临时空位寿命以天计),"
                     f"当前 window_estimate={window_estimate!r}")
            _require(bool(reason),
                     f"G3={G3_WINDOW_BET} 要求 reason(降级依据:数到哪些免费实现、"
                     "为何判定它们只是还没被收录)")
            if by == "xinci-run":
                window_bet_confirmation = _window_bet_confirmation(data_root, rec, run_id)
    elif to == "rejected":
        _require(bool(reason), "rejected 要求 reason(失败闸门 + 现场证据要点)")
        if frm in {"captured", "tracking"}:
            merged_gates = dict(rec.get("gates") or {}, **(gates or {}))
            no_tentative_line = _has_no_applicable_tentative_g6(
                data_root, refs, rec.get("lane", "new"))
            structural_g6_veto = _has_structural_g6_entry_veto(data_root, refs)
            _require(any(v == "veto" for v in merged_gates.values()) or no_tentative_line
                     or structural_g6_veto,
                     f"{frm}→rejected 要求至少一道实际检查的闸门=veto,"
                     "或本次 scan/track 证据的 g6_tentative_lines 证明没有适用盈利线;"
                     "或 g6_entry_veto 证明 G6 深算前结构性不成立;"
                     "没有失败闸门且未过期的候选应保留,到期候选走 expired")
    elif to == "tracking":
        if frm == "built":  # 升级通路
            _require(bool(reason), "built→tracking 要求 reason(升级理由)")
            _check_date(expiry, "expiry")
            # 快道降级结论不可继承:想走全站必须重跑 G3 拿真 pass
            if rec["gates"].get("G3") == G3_WINDOW_BET:
                _require((gates or {}).get("G3") == "pass",
                         f"该候选 G3={G3_WINDOW_BET}(快道降级结论);built→tracking 升级要求"
                         "本次重跑 G3 并取得 pass,降级结论只在快道这一次有效")
        else:
            _require(rec["gates"].get("G3") != G3_WINDOW_BET,
                     f"G3={G3_WINDOW_BET} 的候选只能走快道(→fast_grab_ready)或 rejected;"
                     "不得进入 tracking——临时空位风险不会随时间变好(通用工具正在收录),"
                     "放它进追踪等于让它绕过 G3 走到全站")
            _check_date(expiry, "expiry")
            _require(bool(invalidation), "screened→tracking 要求至少 1 条失效条件")
            _require(len(refs) >= 1, "screened→tracking 要求本次至少 1 个证据")
    elif to == "fast_grab_ready":
        _require(rec.get("window_estimate") == "days",
                 f"快道只收 window_estimate=days 的 screened 候选,当前 {rec.get('window_estimate')!r}")
        _check_decision_files(data_root, decision_ref)
        _check_date(expiry, "expiry")
        _require(play in (None, "fast_grab"), "快道 play 只能是 fast_grab")
        play = "fast_grab"
    elif to == "formation_confirmed":
        track_obs = [r for r in merged_refs if Path(r).stem.endswith("-track")]
        _require(len(track_obs) >= 2,
                 f"tracking→formation_confirmed 要求 ≥2 个追踪期观察(-track 证据),当前 {len(track_obs)}")
        times = [_obs_time(data_root, r) for r in track_obs]
        span = (max(times) - min(times)).days
        _require(span >= MIN_TRACK_SPAN_DAYS,
                 f"tracking→formation_confirmed 要求 -track 观察时间跨度 ≥{MIN_TRACK_SPAN_DAYS} 天"
                 f"(形成期以周计,单次运行无法压缩),当前 {span} 天")
        _check_gates(gates, ("G1",), "tracking→formation_confirmed")
        _require(len(refs) >= 1, "tracking→formation_confirmed 要求本次至少 1 个证据")
        current_track = [_load_observation(data_root, r) for r in refs
                         if Path(r).stem.endswith("-track")]
        _require(any(obs.get("naming_status") == "stabilized" for obs in current_track),
                 "tracking→formation_confirmed 要求本次 track 观察明确 naming_status=stabilized")
        _require(any(bool(obs.get("formation_signals")) for obs in current_track),
                 "tracking→formation_confirmed 要求本次 track 观察至少记录 1 项 formation_signals")
    elif to == "expired":
        _require(bool(reason),
                 "expired 要求 reason(失效日已到 / 失效条件命中 / 快道窗口关闭)")
        _require(bool(rec.get("expiry")), "expired 要求候选已有 expiry;无失效日不得用过期出口")
        _require(expiry_trigger in EXPIRY_TRIGGERS,
                 f"expired 要求 expiry_trigger 属于 {sorted(EXPIRY_TRIGGERS)},"
                 f"当前 {expiry_trigger!r}")
        allowed_triggers = {
            "captured": {"date"},
            "screened": {"date"},
            "tracking": {"date", "invalidation"},
            "fast_grab_ready": {"date", "window_closed"},
        }
        _require(expiry_trigger in allowed_triggers.get(frm, set()),
                 f"{frm}→expired 不接受 expiry_trigger={expiry_trigger};"
                 f"允许 {sorted(allowed_triggers.get(frm, set()))}")
        if expiry_trigger == "date":
            expiry_date = date.fromisoformat(rec["expiry"])
            _require(expiry_date <= date.today(),
                     f"expiry 尚未到期:{rec['expiry']};不得提前转 expired")
        elif expiry_trigger == "invalidation":
            _require(bool(rec.get("invalidation")),
                     "tracking 以 invalidation 触发 expired 时,候选必须已有失效条件")
            _require(any(condition in reason for condition in rec["invalidation"]),
                     "tracking 以 invalidation 触发 expired 时,reason 必须原样点名至少一条已登记失效条件")
    elif to == "qualified":
        _require(isinstance(score, int) and score >= 80, f"qualified 要求整数 score ≥80,当前 {score!r}")
        _require(isinstance(income_score, int) and not isinstance(income_score, bool)
                 and 1 <= income_score <= 20,
                 f"qualified 要求 income_score 为 1–20 的整数(收入维度不得为 0),"
                 f"当前 {income_score!r}")
        lines = list(dict.fromkeys(g6_passed_lines or []))
        allowed_lines = MONETIZATION_LINES
        _require(lines and set(lines) <= allowed_lines,
                 "qualified 要求 g6_passed_lines 至少包含一条合法盈利线")
        _require(rec.get("lane") != "new" or "advertising" not in lines,
                 "lane=new 的广告线结构上不适用,g6_passed_lines 不得包含 advertising")
        g6_passed_lines = lines
        _check_gates(gates, QUALIFY_GATES, "formation_confirmed→qualified")
        _require(len(refs) >= 1, "formation_confirmed→qualified 要求本次至少 1 个证据")
        observations = [_load_observation(data_root, ref) for ref in refs
                        if Path(ref).suffix == ".json"]
        qualify_obs = [obs for obs in observations
                       if obs.get("stage") == "qualify"
                       and obs.get("gates", {}).get("G6") == "pass"]
        _require(bool(qualify_obs),
                 "formation_confirmed→qualified 要求 qualify 观察结构化记录 G6")
        for obs in qualify_obs:
            observed_lines = obs.get("g6_lines") or {}
            _require(all(observed_lines.get(line) == "pass" for line in lines),
                     "qualify 观察 g6_lines 中的每条 g6_passed_lines 必须为 pass")
            _require(not any(value == "pass" and line not in lines
                             for line, value in observed_lines.items()),
                     "qualify 观察不得含未写入 g6_passed_lines 的 pass")
            if rec.get("lane") == "new":
                _require(observed_lines.get("advertising") == "N/A",
                         "lane=new 的 advertising 必须为 N/A")
        _require(all(obs.get("income_score") == income_score for obs in qualify_obs),
                 "qualify 观察 income_score 必须与 transition 参数一致")
    elif to == "disqualified":
        _require(bool(reason), "disqualified 要求 reason(决定性缺口:哪一项、差多少)")
        _require(len(refs) >= 1, "disqualified 要求本次至少 1 个 qualify 证据")
        qualify_obs = [_load_observation(data_root, ref) for ref in refs
                       if Path(ref).stem.endswith("-qualify")]
        _require(bool(qualify_obs), "disqualified 要求本次提交 qualify observation")
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
    if income_score is not None:
        rec["income_score"] = income_score
    if g6_passed_lines is not None:
        rec["g6_passed_lines"] = g6_passed_lines
    if decision_ref:
        rec["decision_ref"] = decision_ref
    if play:
        rec["play"] = play
    if superseded_by:
        rec["superseded_by"] = superseded_by
    if to == "rejected":
        merged_gates = dict(rec.get("gates") or {}, **(gates or {}))
        vetoes = {g for g, v in merged_gates.items() if v == "veto"}
        # SERP 型结论可腐烂，默认 30 天后进入复核清单；结构性 G0/G4/G5 不自动复活。
        rec["recheck_after"] = ((date.today() + timedelta(days=30)).isoformat()
                                if vetoes and vetoes <= {"G1", "G2", "G3"} else None)
    # history 条目附本次提交的参数快照:gates/score 等字段会被后续转移覆盖,
    # 没有快照就无法回答"当时的闸门结论是什么"(如 G1 pass→veto 的翻转史)。
    entry = {"at": now, "from": frm, "to": to, "by": by}
    entry.update(_run_history_fields(data_root, run_id))
    if window_bet_confirmation:
        # 确认的消费凭据写在出闸条目上:同一 (run_id, confirmed_at) 在 history 里只能出现一次,
        # 单次消费语义由此保证,不再需要跨文件事务。
        entry["window_bet_confirmation"] = window_bet_confirmation
    if refs:
        entry["evidence"] = refs
    for key, value in (("reason", reason), ("gates", gates), ("window_estimate", window_estimate),
                       ("expiry", expiry), ("invalidation", invalidation), ("score", score),
                       ("income_score", income_score), ("g6_passed_lines", g6_passed_lines),
                       ("play", play), ("decision_ref", decision_ref),
                       ("superseded_by", superseded_by), ("expiry_trigger", expiry_trigger)):
        if value not in (None, {}, [], ""):
            entry[key] = value
    rec["history"].append(entry)
    rec["state"] = to
    # 写入前对写入后的记录复核状态不变式:与 validate_ledger 共用同一份条目,
    # 转移瞬间就拒绝任何会写出不合规记录的提交,而不是等事后校验才发现。
    violations = check_state_invariants(data_root, rec)
    _require(not violations, f"{frm}→{to} 后的记录违反状态不变式: " + "; ".join(violations))
    _save(data_root, ledger)
    return rec


def reopen(data_root, slug, by, reason, evidence, run_id=None):
    """用新现场证据受控重开可逆的 SERP 型 rejected 候选。"""
    data_root = Path(data_root)
    _require(bool(reason), "reopen 要求 reason(什么事实发生了变化)")
    with _locked(data_root):
        # reopen 的来源态是 rejected，但目标态是 captured；lane 授权必须按目标态校验，
        # 否则 xinci-run 会绕过 mature 前半程边界，阶段 skill 也能跨 lane 重开。
        ledger, rec = _open_ledger(data_root, slug, by, run_id)
        _require(rec["state"] == "rejected", "reopen 只受理 rejected 候选")
        lane = rec.get("lane", "new")
        _check_run_lane_boundary(by, lane, "captured")
        allowed = ({"xinci-track", "xinci-run", "user"} if lane == "new"
                   else {"xinci-mature", "user"})
        _require(by in allowed,
                 f"lane={lane} 的受控重开只允许 {sorted(allowed)},当前 by={by!r}")
        vetoes = {g for g, v in (rec.get("gates") or {}).items() if v == "veto"}
        _require(vetoes and vetoes <= {"G1", "G2", "G3"},
                 "只有 G1/G2/G3 的可逆 SERP 型否决可重开;G0/G4/G5 结构性否决保持终态")
        refs = _check_evidence(data_root, evidence, slug=slug)
        _require(bool(refs), "reopen 要求至少 1 份新的现场证据")
        merged = rec["evidence_refs"] + [r for r in refs if r not in rec["evidence_refs"]]
        _require(len(merged) > len(rec["evidence_refs"]), "reopen 证据必须是账本中尚未登记的新观察")
        rejection = next((h for h in reversed(rec.get("history", []))
                          if h.get("to") == "rejected"), None)
        _require(bool(rejection and rejection.get("at")), "rejected 候选缺拒绝时间,不能安全重开")
        try:
            rejected_at = datetime.fromisoformat(rejection["at"])
        except (TypeError, ValueError):
            raise RegistrarError("拒绝历史时间不可解析,不能安全重开")
        if rejected_at.tzinfo is None:
            rejected_at = rejected_at.replace(tzinfo=timezone.utc)
        new_gates = {}
        for ref in refs:
            observed_at = _obs_time(data_root, ref)
            _require(observed_at > rejected_at,
                     f"reopen 证据必须晚于最近拒绝时间 {rejection['at']}: {ref}")
            obs = json.loads((Path(data_root) / ref).read_text(encoding="utf-8"))
            new_gates.update(obs.get("gates") or {})
        _check_run_g1_preflight(data_root, by, run_id, new_gates)
        not_flipped = sorted(g for g in vetoes if new_gates.get(g) != "pass")
        _require(not not_flipped,
                 f"reopen 新证据必须把原 veto 闸门明确翻转为 pass,尚未翻转: {not_flipped}")
        now = _now()
        rec["evidence_refs"] = merged
        rec["state"] = "captured"
        rec["last_checked_at"] = now
        rec["gates"] = {}
        rec["window_estimate"] = None
        rec["expiry"] = None
        rec["recheck_after"] = None
        rec["history"].append({"at": now, "from": "rejected", "to": "captured", "by": by,
                               "reason": reason, "reopened": True, "evidence": refs,
                               **_run_history_fields(data_root, run_id)})
        _save(data_root, ledger)
        return rec


def checked(data_root, slug, evidence, by="xinci-track", run_id=None, same_day_reason=None):
    """复查登记:更新 last_checked_at、追加证据,不改状态。

    追加一条 from==to 的 history 条目(与 amend 同构),记录谁在何时复查、登记了哪份观察:
    连续运行模式下 by=xinci-run 是"标准授权、未经逐条确认"的印记,不写 history 就丢了,
    复查次数也只能靠 evidence_refs 文件名反推。

    同一自然日不重复复查:SERP 在几小时内不会变,当日再查一遍是空烧。边界按天划而不按
    run 划——同一天的两次运行同样受限。确需当日重测(典型是上次复查时浏览器环境被污染)
    时传 same_day_reason,理由会写进 history。"""
    data_root = Path(data_root)
    _require(bool(by), "checked 要求 by(执行的 skill 名)")
    with _locked(data_root):
        ledger, rec = _open_ledger(data_root, slug, by, run_id)
        _require(rec["state"] not in TERMINAL, f"终态候选无需复查: {rec['state']}")
        now = _now()
        refs = _check_evidence(data_root, evidence, slug=slug)
        _require(len(refs) >= 1, "checked 要求至少 1 个证据文件")
        if not same_day_reason:
            # 比的是观察实际发生的那一天(observed_at),不是登记时间:一天之内补录两份
            # 不同日期的观察是正常的,同一天把 SERP 又跑一遍才是空烧。只比 -track 观察,
            # 注册当天先 scan 后 track 不受影响。
            def _track_days(items):
                return {_obs_time(data_root, r).date() for r in items
                        if Path(r).stem.endswith("-track")}
            dup = sorted(_track_days(refs) & _track_days(rec["evidence_refs"]))
            if dup:
                raise RegistrarError(
                    f"{slug} 已有 {dup[0]} 的 -track 观察,同日不重复复查:SERP 在几小时内"
                    "不会变,再跑一遍是空烧(边界按天划,不按 run 划)。确需当日重测时传 "
                    "--same-day-reason 说明理由,它会记进 history")
        rec["evidence_refs"] += [r for r in refs if r not in rec["evidence_refs"]]
        rec["last_checked_at"] = now
        entry = {"at": now, "from": rec["state"], "to": rec["state"],
                 "by": by, "checked": refs, **_run_history_fields(data_root, run_id)}
        if same_day_reason:
            entry["same_day_reason"] = same_day_reason
        rec["history"].append(entry)
        _save(data_root, ledger)
        return rec


def amend(data_root, slug, by, reason, expiry=None, add_aliases=None, add_invalidation=None,
          gates=None, evidence=None, run_id=None):
    """观察性字段修订(不改状态):续期 expiry、追加 aliases/invalidation、
    给 captured 候选补记闸门结论。
    经用户确认后调用;reason 必填并写入 history,保证账本自解释。

    gates 只对 `captured` 开放:排队位/挂起位的闸门结论是逐轮累积的,而 captured→captured
    不是转移、transition 写不了它——上轮已注册的排队候选本轮才跑出的结论(典型是还债深审
    判出 G3=veto_window_bet)只能从这里进账本,否则结论只剩在观察文件里,账本上看不见这个
    挂起。出闸之后的 gates 一律由 transition 校验着写,本口径不给它们留后门;而 captured
    上的补记绕不过任何校验——出闸(captured→screened)与 rejected 都会重新按合并结果验。"""
    data_root = Path(data_root)
    _check_gate_payload(gates)
    _require(bool(reason), "amend 要求 reason(如:用户确认续期的理由)")
    add_aliases = list(add_aliases or [])
    add_invalidation = list(add_invalidation or [])
    _require(bool(expiry) or add_aliases or add_invalidation or gates,
             "amend 要求至少提供一个可改字段:expiry / add_aliases / add_invalidation / gates")
    with _locked(data_root):
        ledger, rec = _open_ledger(data_root, slug, by, run_id)
        _check_run_g1_preflight(data_root, by, run_id, gates)
        _require(rec["state"] not in TERMINAL, f"终态候选不可修订: {rec['state']}")
        amended = []
        refs = _check_evidence(data_root, evidence, slug=slug)
        _check_gate_evidence(data_root, refs, gates, "amend")
        _check_evidence_reuse(data_root, rec, refs)
        if refs:
            rec["evidence_refs"] += [r for r in refs if r not in rec["evidence_refs"]]
            amended.append("evidence")
        entry = {"at": _now(), "from": rec["state"], "to": rec["state"], "by": by, "reason": reason}
        entry.update(_run_history_fields(data_root, run_id))
        if expiry:
            _check_date(expiry, "expiry")
            rec["expiry"] = expiry
            amended.append("expiry")
            entry["expiry"] = expiry
        if add_aliases:
            rec["aliases"] = list(dict.fromkeys(rec["aliases"] + add_aliases))
            amended.append("aliases")
            entry["add_aliases"] = add_aliases
        if add_invalidation:
            rec["invalidation"] = list(dict.fromkeys(rec["invalidation"] + add_invalidation))
            amended.append("invalidation")
            entry["add_invalidation"] = add_invalidation
        if gates:
            _require(rec["state"] == "captured",
                     "amend --gates 只用于 captured 候选(排队位/挂起位)补记闸门结论:"
                     "出闸之后的 gates 由 transition 校验着写,不得从这里绕过;"
                     f"当前状态 {rec['state']}")
            _require(bool(rec.get("expiry")),
                     "captured 带闸门结论即排队位,补记 gates 后必须有 expiry"
                     "(本次给 --expiry,或候选已有):没有过期出口的方向会在队列里无声腐烂")
            rec["gates"].update(gates)
            amended.append("gates")
            entry["gates"] = gates
            entry["evidence"] = refs
        entry["amend"] = amended
        rec["history"].append(entry)
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


_RUN_ID_HELP = "by=xinci-run 时必填的活动运行会话"
_REQUIRED = {"required": True}
_APPEND = {"action": "append"}
# CLI 参数表:每个子命令 → (help, [(flag, add_argument 关键字), ...])。
# 同名参数在不同子命令下 required / default / help 各不相同,所以按子命令逐条列出、不跨命令合并。
# 这张表就是 CLI 表面本身(SKILL.md 按它写调用):参数名、类型、默认值、help 文案改一处都算改接口。
CLI_SPEC = {
    "register": ("注册新候选(→captured)", [
        ("--slug", _REQUIRED),
        ("--term", _REQUIRED),
        ("--source-url", _REQUIRED),
        ("--source-note", {"default": ""}),
        ("--task", _REQUIRED),
        ("--site-thesis", {"help": "独立站为何成立的一句话假设;xinci-run 必填"}),
        ("--task-family", {"action": "append", "default": [],
                           "help": "站点可拥有的独立任务家族;xinci-run 至少两项"}),
        ("--lane", {"default": "new", "choices": sorted(["new", "mature"]),
                    "help": "new=新词道(默认);mature=成熟错价词道,广告线只能在此道工作"}),
        ("--aliases", {"default": "", "help": "逗号分隔"}),
        ("--evidence", {"action": "append", "required": True}),
        ("--by", {"default": "xinci-scan"}),
        ("--run-id", {"help": _RUN_ID_HELP}),
        ("--origin", {"choices": ["signal", "trigger"],
                      "help": "xinci-run 注册必填；trigger 还须 --trigger-id"}),
        ("--trigger-id", {}),
        ("--gates", {"default": "", "help": "已得的闸门结论,如 G0=pass,G4=pass,G5=pass,G1=pass"
                                            "(排队的 captured 候选用;缺哪门下轮补哪门)"}),
        ("--expiry", {"help": "排队位的失效日 YYYY-MM-DD(带 --gates 时必填)"}),
    ]),
    "transition": ("状态转移", [
        ("--slug", _REQUIRED),
        ("--to", _REQUIRED),
        ("--by", _REQUIRED),
        ("--run-id", {"help": _RUN_ID_HELP}),
        ("--gates", {"default": "", "help": "如 G1=pass,G2=pass"}),
        ("--window-estimate", {"choices": sorted(WINDOWS)}),
        ("--expiry", {}),
        ("--expiry-trigger", {"choices": sorted(EXPIRY_TRIGGERS),
                              "help": "转 expired 时必填:date / invalidation / window_closed"}),
        ("--invalidation", {"default": "", "help": "分号分隔"}),
        ("--score", {"type": int}),
        ("--income-score", {"type": int, "help": "收入可行性维度得分;qualified 必填且须为 1–20"}),
        ("--g6-passed-lines", {"default": "", "help": "qualified 必填;逗号分隔通过的盈利线"}),
        ("--decision-ref", {}),
        ("--play", {}),
        ("--reason", {}),
        ("--evidence", _APPEND),
        ("--superseded-by", {}),
    ]),
    "checked": ("复查登记(不改状态)", [
        ("--slug", _REQUIRED),
        ("--evidence", {"action": "append", "required": True}),
        ("--by", {"default": "xinci-track"}),
        ("--run-id", {"help": _RUN_ID_HELP}),
        ("--same-day-reason", {"help": "当日已复查过仍要重测时的理由(如上次复查环境被污染);会记进 history"}),
    ]),
    "amend": ("观察性字段修订(不改状态):续期 expiry、追加 aliases/invalidation、captured 补记闸门结论", [
        ("--slug", _REQUIRED),
        ("--by", _REQUIRED),
        ("--run-id", {"help": _RUN_ID_HELP}),
        ("--reason", _REQUIRED),
        ("--expiry", {}),
        ("--add-alias", {"action": "append", "default": []}),
        ("--add-invalidation", {"default": "", "help": "分号分隔"}),
        ("--gates", {"default": "", "help": "仅 captured 候选:补记本轮跑出的闸门结论,"
                                            "如 G3=veto_window_bet(captured→captured 不是转移,"
                                            "排队位的 gates 只能从这里写)"}),
        ("--evidence", {"action": "append", "help": "补记 gates 时必填:本次 observation 证据"}),
    ]),
    "reopen": ("用新证据重开 G1/G2/G3 可逆 SERP 型 rejected 候选", [
        ("--slug", _REQUIRED),
        ("--by", _REQUIRED),
        ("--run-id", {}),
        ("--reason", _REQUIRED),
        ("--evidence", {"action": "append", "required": True}),
    ]),
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="xinci 候选账本 registrar")
    ap.add_argument("--data-root", default=None,
                    help="数据区路径。不给则按 XINCI_DATA_ROOT 环境变量、再按仓库配置 .xinci-data-root 解析;都没有则拒绝执行并提示先问用户")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd, (help_text, params) in CLI_SPEC.items():
        p = sub.add_parser(cmd, help=help_text)
        for flag, kwargs in params:
            p.add_argument(flag, **kwargs)

    a = ap.parse_args(argv)
    # 数据区未配置时在这里就停,并打印「先问用户」的指引,
    # 不让空路径流进下游写操作(理由见 data_root.py)。
    a.data_root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.cmd == "register":
            require_formal_admission(a.data_root, a.by, a.run_id, a.term,
                                     a.origin, a.trigger_id)
            rec = register(a.data_root, a.slug, a.term, a.source_url, a.task, a.evidence,
                           source_note=a.source_note,
                           aliases=[x for x in a.aliases.split(",") if x], by=a.by,
                           gates=_parse_gates(a.gates), expiry=a.expiry, run_id=a.run_id,
                           lane=a.lane, origin=a.origin, trigger_ref=a.trigger_id,
                           site_thesis=a.site_thesis, task_families=a.task_family)
        elif a.cmd == "transition":
            rec = transition(a.data_root, a.slug, a.to, a.by,
                             gates=_parse_gates(a.gates), window_estimate=a.window_estimate,
                             expiry=a.expiry,
                             invalidation=[x for x in a.invalidation.split(";") if x] or None,
                             score=a.score, income_score=a.income_score,
                             g6_passed_lines=[x.strip() for x in a.g6_passed_lines.split(",")
                                              if x.strip()] or None,
                             decision_ref=a.decision_ref, play=a.play,
                             reason=a.reason, evidence=a.evidence, superseded_by=a.superseded_by,
                             expiry_trigger=a.expiry_trigger, run_id=a.run_id)
        elif a.cmd == "amend":
            rec = amend(a.data_root, a.slug, by=a.by, reason=a.reason, expiry=a.expiry,
                        add_aliases=a.add_alias,
                        add_invalidation=[x for x in a.add_invalidation.split(";") if x],
                        gates=_parse_gates(a.gates), evidence=a.evidence, run_id=a.run_id)
        elif a.cmd == "checked":
            rec = checked(a.data_root, a.slug, a.evidence, by=a.by, run_id=a.run_id,
                          same_day_reason=a.same_day_reason)
        else:
            rec = reopen(a.data_root, a.slug, by=a.by, reason=a.reason,
                         evidence=a.evidence, run_id=a.run_id)
    except RegistrarError as e:
        print(f"registrar 拒绝: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"slug": rec["slug"], "state": rec["state"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
