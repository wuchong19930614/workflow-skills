#!/usr/bin/env python3
"""共用原语:时间戳、原子写、账本路径与读取。顶层不依赖任何其他工作流模块。"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    """UTC 秒级 ISO 时间戳,所有落盘时间字段统一用它。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_save(path, obj) -> None:
    """先写同目录临时文件再 os.replace,读者永远看不到半截 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def ledger_path(data_root) -> Path:
    return Path(data_root) / "账本" / "候选账本.json"


def load_ledger(data_root) -> dict:
    p = ledger_path(data_root)
    if not p.is_file():
        raise FileNotFoundError(f"账本不存在: {p}(先运行 init_workspace.py)")
    return json.loads(p.read_text(encoding="utf-8"))
