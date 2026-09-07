#!/usr/bin/env python3
"""各脚本共用的底层原语:时间戳、原子写、文件锁、URL 校验、账本路径、执行身份校验。

本模块顶层不依赖任何其他工作流模块,只做机械去重;每个函数的语义与被合并前的
各处复制品保持一致,业务规则(错误类型、缺文件时的默认值)仍留在调用方。
唯一例外是 check_actor 需要读运行会话,它在函数体内延迟导入 run_controller
(run_controller 自身 import 本模块,顶层互相引用会成环)。
"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

# 文件锁跨平台:POSIX 用 fcntl.flock,Windows(如 Codex 多环境)降级 msvcrt.locking
try:
    import fcntl

    def flock(f):
        fcntl.flock(f, fcntl.LOCK_EX)

    def funlock(f):
        fcntl.flock(f, fcntl.LOCK_UN)
except ImportError:  # pragma: no cover - Windows fallback
    import msvcrt

    def flock(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def funlock(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def now() -> str:
    """UTC 秒级 ISO 时间戳,所有落盘时间字段统一用它。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_save(path, obj) -> None:
    """先写同目录临时文件再 os.replace,保证读者永远看不到半截 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def is_http_url(value) -> bool:
    """只接受带主机名的 http(s) 字符串;非字符串一律视为非法。"""
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_aware_timestamp(value, where, error_cls):
    """解析 ISO 时间并要求带时区;非法时抛调用方指定的异常类型。"""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise error_cls(f"{where} 必须是 ISO 时间")
    if parsed.tzinfo is None:
        raise error_cls(f"{where} 必须带时区")
    return parsed


def span_days(days) -> int:
    """一组日期里最早与最新的自然日差:形成跨度判据的唯一实现。

    按自然日算而不按满 24 小时算,原因是同一条判据此前有两个实现且互相矛盾:
    run_policy 的天花板计算按自然日、registrar 的转移校验按 24 小时,于是
    2026-09-07 出现"策略说本次复查即可凑齐跨度、registrar 判 6 天拒收"的现场,
    被拒后又撞上同日不重复复查规则,当天再无合法出路。自然日也是人预判到期日
    时的读法(最早观察那天 + 7 天),跨度提醒与看板都按它显示。
    """
    return (max(days) - min(days)).days


def ledger_path(data_root) -> Path:
    return Path(data_root) / "账本" / "候选账本.json"


def load_ledger(data_root) -> dict:
    """读候选账本原文并解析。缺文件/损坏时原样抛出 FileNotFoundError /
    json.JSONDecodeError / UnicodeDecodeError,由调用方决定默认值或报错方式。"""
    return json.loads(ledger_path(data_root).read_text(encoding="utf-8"))


def track_observation_days(data_root, rec) -> list:
    """该候选已登记的 -track 观察日期(只读侧共用)。

    读不出的证据跳过:看板、提醒与策略计算不因一份证据损坏而崩。registrar 不用
    这一版——它在转移时必须对坏证据大声报错,而不是静默少算一份跨度。
    """
    days = []
    for ref in rec.get("evidence_refs", []) or []:
        if not str(ref).endswith("-track.json"):
            continue
        try:
            obs = json.loads((Path(data_root) / ref).read_text(encoding="utf-8"))
            days.append(datetime.fromisoformat(obs["observed_at"]).date())
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return sorted(days)


def formation_eligible_date(track_days, min_span_days):
    """最早 -track 观察那天 + 跨度下限 = 最早可提交形成确认的自然日。

    预判到期日时读这一个数,不要拿账本 history 里 tracking 那条的时间戳去加 7 天:
    两者可以差几十分钟(实测 cpr-avcp:history 03:42Z、观察文件 04:10Z),按 history
    推算会早到被拒。
    """
    return (min(track_days) + timedelta(days=min_span_days)) if track_days else None


def check_actor(data_root, by, run_id, *, actors, error_cls):
    """执行身份与连续运行会话的授权校验(registrar / trigger_pool / screen_index 裁决共用)。

    - by 必须属于 actors;
    - by=xinci-run 必须带 run_id,且指向活动、已 begin-round 的会话,返回该会话对象;
    - 其他 actor 不得携带 run_id;存在活动连续运行时拒绝单步写入
      (单步写入会破坏授权与顺序,先恢复或结束该运行)。返回 None。
    会话层的错误统一转成调用方的 error_cls,禁止靠伪造 --by 绕过授权边界。
    """
    from run_controller import RunControllerError, active_sessions, require_active_round
    if by not in actors:
        raise error_cls(f"by 必须属于 {sorted(actors)},当前 {by!r}")
    try:
        active = active_sessions(data_root)
        if by == "xinci-run":
            if not run_id:
                raise error_cls("by=xinci-run 要求 --run-id")
            return require_active_round(data_root, run_id)
        if run_id:
            raise error_cls("单步模式不得携带 run_id")
        if active:
            raise error_cls(f"存在活动连续运行 {active[0]['run_id']};单步写入会破坏授权与顺序,"
                            "请先恢复或结束该运行")
    except RunControllerError as e:
        raise error_cls(str(e))
    return None
