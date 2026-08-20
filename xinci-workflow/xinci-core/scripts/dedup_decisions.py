#!/usr/bin/env python3
"""疑似重复方向的 same/distinct 裁决登记。"""
import json
import os
import tempfile
import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from term_normalize import normalize

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


FILE_NAME = "去重裁决.jsonl"
DECISIONS = {"same", "distinct"}
ACTORS = {"xinci-scan", "xinci-run", "user"}
RUN_ID_RE = re.compile(r"^run-\d{8}T\d{6}Z-[a-f0-9]{8}$")
DECISION_ID_RE = re.compile(r"^dd-[a-f0-9]{16}$")
FIELDS = {"decision_id", "term", "matched", "decision", "reason", "actor", "run_id",
          "term_task", "matched_task", "term_evidence_urls", "matched_evidence_urls",
          "decided_at", "supersedes"}


class DedupDecisionError(Exception):
    pass


@contextmanager
def _locked(data_root):
    path = Path(data_root) / f".{FILE_NAME}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_UN)


def _key(a, b):
    pair = sorted((normalize(a), normalize(b)))
    return "\0".join(pair)


def _check_url(url):
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_record(obj, where="去重裁决"):
    if not isinstance(obj, dict) or set(obj) - FIELDS:
        raise DedupDecisionError(f"{where} 字段非法")
    required = {"decision_id", "term", "matched", "decision", "reason", "actor",
                "term_task", "matched_task", "term_evidence_urls",
                "matched_evidence_urls", "decided_at"}
    if any(not obj.get(k) for k in required):
        raise DedupDecisionError(f"{where} 缺必填审计字段")
    if not DECISION_ID_RE.fullmatch(obj["decision_id"]):
        raise DedupDecisionError(f"{where} decision_id 非法")
    if obj["decision"] not in DECISIONS or obj["actor"] not in ACTORS:
        raise DedupDecisionError(f"{where} decision/actor 非法")
    if obj["actor"] == "xinci-run":
        if not RUN_ID_RE.fullmatch(obj.get("run_id") or ""):
            raise DedupDecisionError(f"{where} xinci-run 缺合法 run_id")
    elif obj.get("run_id"):
        raise DedupDecisionError(f"{where} 非 xinci-run 不得携带 run_id")
    for field in ("term_evidence_urls", "matched_evidence_urls"):
        urls = obj[field]
        if not isinstance(urls, list) or not urls or not all(_check_url(x) for x in urls):
            raise DedupDecisionError(f"{where} {field} 必须是非空 http(s) URL 数组")
    try:
        decided = datetime.fromisoformat(obj["decided_at"])
    except (TypeError, ValueError):
        raise DedupDecisionError(f"{where} decided_at 非法")
    if decided.tzinfo is None:
        raise DedupDecisionError(f"{where} decided_at 必须带时区")
    if decided.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise DedupDecisionError(f"{where} decided_at 不得晚于当前时间")
    if not normalize(obj["term"]) or not normalize(obj["matched"]):
        raise DedupDecisionError(f"{where} term/matched 不可为空")
    if set(obj["term_evidence_urls"]) & set(obj["matched_evidence_urls"]):
        raise DedupDecisionError(f"{where} 两侧 evidence URL 必须独立,不可复用")
    if (obj["decision"] == "distinct"
            and normalize(obj["term_task"]) == normalize(obj["matched_task"])):
        raise DedupDecisionError(f"{where} distinct 裁决的两侧 concrete task 不得相同")


def load(data_root):
    path = Path(data_root) / FILE_NAME
    if not path.is_file():
        return []
    out = []
    latest = {}
    decision_ids = set()
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            raise DedupDecisionError(f"去重裁决第 {i} 行损坏")
        validate_record(obj, f"去重裁决第 {i} 行")
        if obj["decision_id"] in decision_ids:
            raise DedupDecisionError(f"去重裁决第 {i} 行 decision_id 全局重复")
        decision_ids.add(obj["decision_id"])
        if obj["actor"] == "xinci-run":
            try:
                from run_controller import load_session, RunControllerError
                load_session(data_root, obj["run_id"])
            except RunControllerError as e:
                raise DedupDecisionError(f"去重裁决第 {i} 行 run_id 无效: {e}")
        key = _key(obj["term"], obj["matched"])
        prior = latest.get(key)
        if prior:
            if obj.get("supersedes") != prior["decision_id"]:
                raise DedupDecisionError(f"去重裁决第 {i} 行必须 supersedes 当前生效裁决")
        elif obj.get("supersedes"):
            raise DedupDecisionError(f"去重裁决第 {i} 行 supersedes 未指向同词对的旧裁决")
        latest[key] = obj
        out.append(obj)
    return out


def find(data_root, term, matched):
    wanted = _key(term, matched)
    return next((x for x in reversed(load(data_root))
                 if _key(x.get("term", ""), x.get("matched", "")) == wanted), None)


def resolve(data_root, term, matched, decision, reason, *, actor, term_task, matched_task,
            term_evidence_urls, matched_evidence_urls, run_id=None, supersedes=None):
    if decision not in DECISIONS:
        raise DedupDecisionError(f"decision 必须属于 {sorted(DECISIONS)}")
    if not normalize(term) or not normalize(matched) or normalize(term) == normalize(matched):
        raise DedupDecisionError("裁决只用于两个非空且非完全相同的措辞")
    if not reason:
        raise DedupDecisionError("去重裁决要求 reason(任务为何相同或不同)")
    if actor not in ACTORS:
        raise DedupDecisionError(f"actor 必须属于 {sorted(ACTORS)}")
    if actor == "xinci-run" and not RUN_ID_RE.fullmatch(run_id or ""):
        raise DedupDecisionError("actor=xinci-run 要求合法 run_id")
    if actor != "xinci-run" and run_id:
        raise DedupDecisionError("非 xinci-run 裁决不得携带 run_id")
    if not term_task or not matched_task:
        raise DedupDecisionError("去重裁决必须写明两边的 concrete task")
    term_evidence_urls = list(term_evidence_urls or [])
    matched_evidence_urls = list(matched_evidence_urls or [])
    if not term_evidence_urls or not all(_check_url(x) for x in term_evidence_urls):
        raise DedupDecisionError("待查方向要求至少一个 http(s) evidence URL")
    if not matched_evidence_urls or not all(_check_url(x) for x in matched_evidence_urls):
        raise DedupDecisionError("历史 matched 方向要求至少一个独立的 http(s) evidence URL")
    if set(term_evidence_urls) & set(matched_evidence_urls):
        raise DedupDecisionError("两侧 evidence URL 必须独立,不可复用")
    if decision == "distinct" and normalize(term_task) == normalize(matched_task):
        raise DedupDecisionError("distinct 裁决必须写明两个不同的 concrete task")
    try:
        from run_controller import active_sessions, require_active_round, RunControllerError
        if actor == "xinci-run":
            require_active_round(data_root, run_id)
        elif active_sessions(data_root):
            raise DedupDecisionError("存在活动连续运行;裁决必须使用 actor=xinci-run 与活动 run_id")
    except RunControllerError as e:
        raise DedupDecisionError(str(e))
    with _locked(data_root):
        existing = find(data_root, term, matched)
        if existing:
            if not supersedes:
                if existing["decision"] != decision:
                    raise DedupDecisionError("已有相反裁决;用 revise/--supersedes 追加修订,不得覆盖")
                return existing
            if existing.get("decision_id") != supersedes:
                raise DedupDecisionError("supersedes 必须指向该词对当前生效的 decision_id")
        elif supersedes:
            raise DedupDecisionError("没有可修订的现有裁决")
        row = {
            "decision_id": f"dd-{secrets.token_hex(8)}",
            "term": term.strip(), "matched": matched.strip(), "decision": decision,
            "reason": reason.strip(),
            "actor": actor,
            "term_task": term_task.strip(), "matched_task": matched_task.strip(),
            "term_evidence_urls": term_evidence_urls,
            "matched_evidence_urls": matched_evidence_urls,
            "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if run_id:
            row["run_id"] = run_id
        if supersedes:
            row["supersedes"] = supersedes
        path = Path(data_root) / FILE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        # 单行追加先写临时完整副本再替换，避免半行损坏。
        prior = path.read_text(encoding="utf-8") if path.is_file() else ""
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(prior)
            if prior and not prior.endswith("\n"):
                f.write("\n")
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
        return row
