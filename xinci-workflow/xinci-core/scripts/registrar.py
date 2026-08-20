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
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

# 文件锁跨平台:POSIX 用 fcntl.flock,Windows(如 Codex 多环境)降级 msvcrt.locking
try:
    import fcntl

    def _flock(f):
        fcntl.flock(f, fcntl.LOCK_EX)

    def _funlock(f):
        fcntl.flock(f, fcntl.LOCK_UN)
except ImportError:  # Windows
    import msvcrt

    def _flock(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def _funlock(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

# 数据区在仓库根(代码与数据分离):xinci-workflow/xinci-core/scripts/ 向上三级
DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[3] / "数据" / "新词工作流"

STATES = {
    "captured", "screened", "tracking", "formation_confirmed", "qualified",
    "build_ready", "pilot_ready", "fast_grab_ready", "hold",
    "rejected", "expired", "superseded", "withdrawn", "built", "disqualified", "no_site",
}
# 设计终态词汇为前五个;disqualified/no_site 是决策终局,除 superseded 外无出边,并入终态集
TERMINAL = {"rejected", "expired", "superseded", "withdrawn", "built", "disqualified", "no_site"}
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
# 形成期以周计(生命周期契约):-track 观察最早与最新须相隔 ≥7 天,单次连续运行凑不出形成确认
MIN_TRACK_SPAN_DAYS = 7


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


OBS_FIELDS = {"slug", "observed_at", "stage", "source_urls", "points", "gates"}


def _check_observation(path: Path, ref: str, slug) -> None:
    """观察文件内容校验,与 数据结构/observation.schema.json 全量对齐
    (含 additionalProperties: false——多余字段多半是仪式性填充,数据极简原则拒收)。"""
    try:
        obs = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RegistrarError(f"观察文件不是合法 JSON: {ref}")
    _require(isinstance(obs, dict), f"观察文件必须是 JSON 对象: {ref}")
    for k in ("slug", "observed_at", "stage", "points"):
        _require(bool(obs.get(k)), f"观察文件缺必填字段 {k}: {ref}")
    unknown = sorted(set(obs) - OBS_FIELDS)
    _require(not unknown, f"观察文件含 schema 外字段 {unknown}(数据极简,勿加仪式性字段): {ref}")
    _require(slug is None or obs["slug"] == slug,
             f"观察文件 slug={obs['slug']!r} 与候选 {slug!r} 不一致: {ref}")
    try:
        datetime.fromisoformat(obs["observed_at"])
    except (TypeError, ValueError):
        raise RegistrarError(f"观察文件 observed_at 必须是 ISO 8601 时间: {ref}")
    _require(obs["stage"] in OBS_STAGES, f"观察文件 stage 必须属于 {sorted(OBS_STAGES)}: {ref}")
    _require(Path(ref).stem.endswith(f"-{obs['stage']}"),
             f"观察文件 stage={obs['stage']!r} 与文件名不一致(约定 <日期>-<阶段>.json): {ref}")
    pts = obs["points"]
    _require(isinstance(pts, list) and len(pts) >= 1 and all(isinstance(x, str) and x for x in pts),
             f"观察文件 points 必须是非空字符串数组: {ref}")
    urls = obs.get("source_urls", [])
    _require(isinstance(urls, list) and all(isinstance(u, str) and u for u in urls),
             f"观察文件 source_urls 必须是字符串数组: {ref}")
    gates = obs.get("gates", {})
    _require(isinstance(gates, dict) and all(isinstance(v, str) for v in gates.values()),
             f"观察文件 gates 必须是 闸门→字符串结论 的对象: {ref}")


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
    return decision_ref


def register(data_root, slug, term, source_url, task, evidence,
             source_note="", aliases=None, by="xinci-scan", gates=None, expiry=None):
    """注册新候选(→captured)。

    gates 可选:扫描漏斗中"本轮没走完深审"的存活候选注册成 captured 排队时,带上已得的
    闸门结论,下轮按 gates 补跑缺的门(缺 G1 的先补 G1)再进深审(xinci-scan 第 3/4 层)。

    expiry 可选,但**带 gates 时必填**:排队位每轮进多出少,没有 expiry 就没有过期出口,
    窗口过了的方向会在队列里无声腐烂(report_status 只按 expiry 提示到期候选)。"""
    data_root = Path(data_root)
    _require(bool(slug and term and source_url and task), "slug/term/source_url/task 均不可为空")
    with _locked(data_root):
        return _register_locked(data_root, slug, term, source_url, task, evidence,
                                source_note, aliases, by, gates, expiry)


def _register_locked(data_root, slug, term, source_url, task, evidence,
                     source_note, aliases, by, gates=None, expiry=None):
    ledger = _load(data_root)
    _require(slug not in ledger["candidates"], f"候选已存在: {slug}")
    refs = _check_evidence(data_root, evidence, slug=slug)
    _require(len(refs) >= 1, "注册候选要求至少 1 个证据文件")
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
        "lane": "new",
        "first_observed_at": now,
        "last_checked_at": now,
        "expiry": expiry,
        "source": {"url": source_url, "note": source_note},
        "task": task,
        "window_estimate": None,
        "play": None,
        "gates": dict(gates or {}),
        "score": None,
        "invalidation": [],
        "evidence_refs": refs,
        "decision_ref": None,
        "superseded_by": None,
        "history": [dict({"at": now, "from": None, "to": "captured", "by": by},
                         **({"gates": dict(gates)} if gates else {}),
                         **({"expiry": expiry} if expiry else {}))],
    }
    _save(data_root, ledger)
    return ledger["candidates"][slug]


def transition(data_root, slug, to, by, gates=None, window_estimate=None, expiry=None,
               invalidation=None, score=None, decision_ref=None, play=None,
               reason=None, evidence=None, superseded_by=None):
    data_root = Path(data_root)
    with _locked(data_root):
        return _transition_locked(data_root, slug, to, by, gates, window_estimate, expiry,
                                  invalidation, score, decision_ref, play,
                                  reason, evidence, superseded_by)


def _transition_locked(data_root, slug, to, by, gates, window_estimate, expiry,
                       invalidation, score, decision_ref, play,
                       reason, evidence, superseded_by):
    ledger = _load(data_root)
    _require(slug in ledger["candidates"], f"候选不存在: {slug}")
    rec = ledger["candidates"][slug]
    frm = rec["state"]
    _require(to in STATES, f"未知状态: {to}")

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
    merged_refs = rec["evidence_refs"] + [r for r in refs if r not in rec["evidence_refs"]]

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
        _require(len(refs) >= 1, "captured→screened 要求本次至少 1 个证据")
        if g3 == G3_WINDOW_BET:
            _require(window_estimate == "days",
                     f"G3={G3_WINDOW_BET} 只适用于窗口以天计的候选(临时空位寿命以天计),"
                     f"当前 window_estimate={window_estimate!r}")
            _require(bool(reason),
                     f"G3={G3_WINDOW_BET} 要求 reason(降级依据:数到哪些免费实现、"
                     "为何判定它们只是还没被收录)")
            _require(by != "xinci-run",
                     f"G3={G3_WINDOW_BET} 出闸意味着接受额外窗口赌注风险,"
                     "不在连续运行的标准授权内;须由用户在单步模式下确认")
    elif to == "rejected":
        _require(bool(reason), "rejected 要求 reason(失败闸门 + 现场证据要点)")
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
    # history 条目附本次提交的参数快照:gates/score 等字段会被后续转移覆盖,
    # 没有快照就无法回答"当时的闸门结论是什么"(如 G1 pass→veto 的翻转史)。
    entry = {"at": now, "from": frm, "to": to, "by": by}
    for key, value in (("reason", reason), ("gates", gates), ("window_estimate", window_estimate),
                       ("expiry", expiry), ("invalidation", invalidation), ("score", score),
                       ("play", play), ("decision_ref", decision_ref),
                       ("superseded_by", superseded_by)):
        if value not in (None, {}, [], ""):
            entry[key] = value
    rec["history"].append(entry)
    rec["state"] = to
    _save(data_root, ledger)
    return rec


def checked(data_root, slug, evidence, by="xinci-track"):
    """复查登记:更新 last_checked_at、追加证据,不改状态。

    追加一条 from==to 的 history 条目(与 amend 同构),记录谁在何时复查、登记了哪份观察:
    连续运行模式下 by=xinci-run 是"标准授权、未经逐条确认"的印记,不写 history 就丢了,
    复查次数也只能靠 evidence_refs 文件名反推。"""
    data_root = Path(data_root)
    _require(bool(by), "checked 要求 by(执行的 skill 名)")
    with _locked(data_root):
        ledger = _load(data_root)
        _require(slug in ledger["candidates"], f"候选不存在: {slug}")
        rec = ledger["candidates"][slug]
        _require(rec["state"] not in TERMINAL, f"终态候选无需复查: {rec['state']}")
        refs = _check_evidence(data_root, evidence, slug=slug)
        _require(len(refs) >= 1, "checked 要求至少 1 个证据文件")
        rec["evidence_refs"] += [r for r in refs if r not in rec["evidence_refs"]]
        now = _now()
        rec["last_checked_at"] = now
        rec["history"].append({"at": now, "from": rec["state"], "to": rec["state"],
                               "by": by, "checked": refs})
        _save(data_root, ledger)
        return rec


def amend(data_root, slug, by, reason, expiry=None, add_aliases=None, add_invalidation=None,
          gates=None):
    """观察性字段修订(不改状态):续期 expiry、追加 aliases/invalidation、
    给 captured 候选补记闸门结论。
    经用户确认后调用;reason 必填并写入 history,保证账本自解释。

    gates 只对 `captured` 开放:排队位/挂起位的闸门结论是逐轮累积的,而 captured→captured
    不是转移、transition 写不了它——上轮已注册的排队候选本轮才跑出的结论(典型是还债深审
    判出 G3=veto_window_bet)只能从这里进账本,否则结论只剩在观察文件里,账本上看不见这个
    挂起。出闸之后的 gates 一律由 transition 校验着写,本口径不给它们留后门;而 captured
    上的补记绕不过任何校验——出闸(captured→screened)与 rejected 都会重新按合并结果验。"""
    data_root = Path(data_root)
    _require(bool(reason), "amend 要求 reason(如:用户确认续期的理由)")
    add_aliases = list(add_aliases or [])
    add_invalidation = list(add_invalidation or [])
    _require(bool(expiry) or add_aliases or add_invalidation or gates,
             "amend 要求至少提供一个可改字段:expiry / add_aliases / add_invalidation / gates")
    with _locked(data_root):
        ledger = _load(data_root)
        _require(slug in ledger["candidates"], f"候选不存在: {slug}")
        rec = ledger["candidates"][slug]
        _require(rec["state"] not in TERMINAL, f"终态候选不可修订: {rec['state']}")
        amended = []
        entry = {"at": _now(), "from": rec["state"], "to": rec["state"], "by": by, "reason": reason}
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
    p.add_argument("--gates", default="", help="已得的闸门结论,如 G0=pass,G4=pass,G5=pass,G1=pass"
                                              "(排队的 captured 候选用;缺哪门下轮补哪门)")
    p.add_argument("--expiry", help="排队位的失效日 YYYY-MM-DD(带 --gates 时必填)")

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

    p = sub.add_parser("amend", help="观察性字段修订(不改状态):续期 expiry、"
                                     "追加 aliases/invalidation、captured 补记闸门结论")
    p.add_argument("--slug", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--expiry")
    p.add_argument("--add-alias", action="append", default=[])
    p.add_argument("--add-invalidation", default="", help="分号分隔")
    p.add_argument("--gates", default="", help="仅 captured 候选:补记本轮跑出的闸门结论,"
                                              "如 G3=veto_window_bet(captured→captured 不是转移,"
                                              "排队位的 gates 只能从这里写)")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "register":
            rec = register(a.data_root, a.slug, a.term, a.source_url, a.task, a.evidence,
                           source_note=a.source_note,
                           aliases=[x for x in a.aliases.split(",") if x], by=a.by,
                           gates=_parse_gates(a.gates), expiry=a.expiry)
        elif a.cmd == "transition":
            rec = transition(a.data_root, a.slug, a.to, a.by,
                             gates=_parse_gates(a.gates), window_estimate=a.window_estimate,
                             expiry=a.expiry,
                             invalidation=[x for x in a.invalidation.split(";") if x] or None,
                             score=a.score, decision_ref=a.decision_ref, play=a.play,
                             reason=a.reason, evidence=a.evidence, superseded_by=a.superseded_by)
        elif a.cmd == "amend":
            rec = amend(a.data_root, a.slug, by=a.by, reason=a.reason, expiry=a.expiry,
                        add_aliases=a.add_alias,
                        add_invalidation=[x for x in a.add_invalidation.split(";") if x],
                        gates=_parse_gates(a.gates))
        else:
            rec = checked(a.data_root, a.slug, a.evidence, by=a.by)
    except RegistrarError as e:
        print(f"registrar 拒绝: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"slug": rec["slug"], "state": rec["state"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
