#!/usr/bin/env python3
"""共用原语:时间戳、原子写、SHA-256、数据区内固定路径。不依赖任何其他工作流模块。"""
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

LEDGER_REL = "账本/方向账本.json"
SEEDS_REL = "种子/种子池.json"
MANUAL_SEEDS_REL = "种子/手工种子.json"
REJECTS_REL = "淘汰索引/域名.json"
LEXICON_REL = "词库/旧词库.json"
VERDICTS_REL = "词库/旧裁决.json"

SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


class BenchError(Exception):
    """所有脚本共用的拒收错误;文案直接给执行者看。"""


def require(cond, msg):
    if not cond:
        raise BenchError(msg)


def now() -> str:
    """UTC 秒级 ISO 时间戳,所有落盘时间字段统一用它。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def stamp() -> str:
    """文件名用的 UTC 时间戳,精确到微秒。"""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def atomic_save(path, obj) -> None:
    """先写同目录临时文件再 os.replace,读者永远看不到半截 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_ledger(root) -> dict:
    p = Path(root) / LEDGER_REL
    require(p.is_file(), f"账本不存在: {p}(先运行 init_workspace.py)")
    return load_json(p)


def save_ledger(root, ledger) -> None:
    atomic_save(Path(root) / LEDGER_REL, ledger)
