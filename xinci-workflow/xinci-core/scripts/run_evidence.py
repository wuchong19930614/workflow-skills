"""新运行的现场证据及工作包校验；历史会话不追溯修改。"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from _common import parse_aware_timestamp


def read_ref(root, ref):
    root = Path(root).resolve()
    if not isinstance(ref, str) or not ref:
        raise ValueError("缺少数据区相对证据路径")
    rel = Path(ref)
    path = (root / rel).resolve()
    if rel.is_absolute() or ".." in rel.parts or not path.is_relative_to(root):
        raise ValueError("证据路径越界")
    raw = path.read_bytes()
    if not raw.strip():
        raise ValueError("证据文件为空")
    return raw


def preflight_evidence(root, ref, run_id, executor_id, declared, started_at):
    raw = read_ref(root, ref)
    obj = json.loads(raw)
    if obj.get("run_id") != run_id or obj.get("executor_id") != executor_id:
        raise ValueError("预检证据必须属于本运行及本轮执行者")
    when = parse_aware_timestamp(obj.get("observed_at"), "预检时间", ValueError)
    now = datetime.now(timezone.utc)
    if when < datetime.fromisoformat(started_at) or not 0 <= (now - when).total_seconds() <= 900:
        raise ValueError("预检证据必须在本运行开始后、最近15分钟内现场采集")
    capture = read_ref(root, obj.get("capture_ref"))
    if obj.get("observed") != {k: declared[k] for k in ("controllable", "desktop", "region", "logged_out")}:
        raise ValueError("预检声明与现场证据不一致")
    if not isinstance(obj.get("observation"), str) or not obj["observation"].strip():
        raise ValueError("预检必须说明实际可见的浏览器、桌面、登录和地区依据")
    if declared["g1_ready"]:
        url = urlparse(obj.get("query_url", ""))
        query = parse_qs(url.query)
        if (url.scheme != "https" or url.hostname != "www.google.com" or url.path != "/search"
                or not query.get("q") or any(query.get(k) != [v] for k, v in
                                            {"gl": "us", "hl": "en", "pws": "0"}.items())):
            raise ValueError("G1 要求 Google 查询及 gl=us/hl=en/pws=0")
        if obj.get("privacy_context") not in {"incognito", "isolated_logged_out"}:
            raise ValueError("须核实无痕或独立未登录上下文")
        # 文本或截图均可；字段用于人工审计，不能假称机器能识别截图真伪。
        if not obj.get("login_indicator") or not obj.get("privacy_evidence"):
            raise ValueError("须填写登录态可见标志及隔离上下文的核验依据")
    return {"ref": ref, "sha256": hashlib.sha256(raw).hexdigest(),
            "capture_ref": obj["capture_ref"], "capture_sha256": hashlib.sha256(capture).hexdigest(),
            "observed_at": obj["observed_at"]}


def verify_pinned(root, pinned):
    for key, digest in (("ref", "sha256"), ("capture_ref", "capture_sha256")):
        if hashlib.sha256(read_ref(root, pinned[key])).hexdigest() != pinned[digest]:
            raise ValueError("已绑定的预检证据被修改")


def work_package(obj, round_type):
    if (not isinstance(obj, dict) or set(obj) != {"targets", "completion"}
            or not isinstance(obj["targets"], list) or not obj["targets"]
            or not all(isinstance(x, str) and x.strip() for x in obj["targets"])
            or len(set(obj["targets"])) != len(obj["targets"])
            or not isinstance(obj["completion"], str) or not obj["completion"].strip()):
        raise ValueError("工作包要求非空唯一 targets 及 completion；开轮时明确本轮范围")
    return obj


def work_results(root, package, rows, started_at):
    if not isinstance(rows, list) or len(rows) != len(package["targets"]):
        raise ValueError("收尾必须逐项交代工作包全部 targets")
    seen = set()
    substantive = False
    for row in rows:
        if (not isinstance(row, dict) or row.get("target") not in package["targets"]
                or row["target"] in seen or row.get("outcome") not in {"completed", "blocked", "deferred"}
                or not isinstance(row.get("reason"), str) or not row["reason"].strip()
                or not isinstance(row.get("evidence_refs"), list) or not row["evidence_refs"]):
            raise ValueError("工作结果须包含 target/outcome/reason/evidence_refs，且不得重复")
        when = parse_aware_timestamp(row.get("observed_at"), "工作结果时间", ValueError)
        if not datetime.fromisoformat(started_at) <= when <= datetime.now(timezone.utc):
            raise ValueError("工作结果必须发生在本轮内")
        for ref in row["evidence_refs"]:
            read_ref(root, ref)
        substantive |= row["outcome"] == "completed"
        seen.add(row["target"])
    return substantive
