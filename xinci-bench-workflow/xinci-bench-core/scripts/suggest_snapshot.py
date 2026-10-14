#!/usr/bin/env python3
"""Google 自动补全快照:取建议、按查询存快照、和以前所有快照比,找出从没出现过的建议。

快道里唯一会联网的脚本;取数函数可注入,测试不联网。取数失败不写快照(不能当作"没有新建议")。
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import data_root
import quick_model as QM
from _common import SUGGEST_DIR_REL, BenchError, atomic_save, load_json, now, require

ENDPOINT = "https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl={gl}&q="
GLS = ("us", "gb", "ca", "au", "nz", "ie")              # 英文区 6 国
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"


def url_for(query: str, gl: str = "us") -> str:
    require(gl in GLS, f"gl 须为 {GLS}")
    return ENDPOINT.format(gl=gl) + urllib.parse.quote(query)


def fetch(query: str, gl: str = "us") -> list:
    req = urllib.request.Request(url_for(query, gl), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    require(isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list), "自动补全返回格式不对")
    return [str(s) for s in data[1]]


def snapshot_path(root, query: str, gl: str = "us") -> Path:
    """美国沿用原来的文件名;别的国家在名字和哈希里带上国家,各存各的快照。"""
    norm = re.sub(r"\s+", " ", query.strip().lower())
    key = norm if gl == "us" else f"{gl}:{norm}"
    name = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")[:70] or "q"
    suffix = "" if gl == "us" else f"-{gl}"
    return Path(root) / SUGGEST_DIR_REL / f"{name}{suffix}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:8]}.json"


def snapshot(root, query: str, fetcher=None, at=None, gl: str = "us") -> dict:
    """取一次建议并追加快照;返回全部建议、新冒出的建议、与上一次快照的间隔天数。

    同一查询隔几秒请求两次,返回的建议也会不同(2026-10-13 实测),所以"新"指以前所有快照里都没出现过。
    """
    at = at or now()
    fetcher = fetcher or (lambda q: fetch(q, gl))
    try:
        current = fetcher(query)
    except Exception as exc:          # 网络、限流、格式错误都不写快照
        return {"query": query, "error": f"{type(exc).__name__}: {exc}", "suggestions": [], "new_suggestions": [],
                "gap_days": None, "first_time": None}
    p = snapshot_path(root, query, gl)
    history = load_json(p) if p.is_file() else []
    prev = history[-1] if history else None
    seen = {s for h in history for s in h["suggestions"]}
    new = [s for s in current if s not in seen]
    gap = (date.fromisoformat(at[:10]) - date.fromisoformat(prev["fetched_at"][:10])).days if prev else None
    history.append({"fetched_at": at, "query": query, "gl": gl, "suggestions": current})
    atomic_save(p, history)
    return {"query": query, "gl": gl, "suggestions": current, "new_suggestions": new if prev else [],
            "gap_days": gap, "first_time": prev is None}


def expand(root, obj: str, fetcher=None, sleeper=time.sleep, interval=1.0, at=None, gl: str = "us") -> list:
    """对象名 + 空格,以及对象名 + 每个任务词;请求之间间隔 interval 秒。"""
    require(isinstance(obj, str) and obj.strip(), "对象名不能为空")
    queries = [obj.strip() + " "] + [f"{obj.strip()} {w}" for w in QM.TASK_WORDS]
    out = []
    for i, q in enumerate(queries):
        if i:
            sleeper(interval)
        out.append(snapshot(root, q, fetcher, at, gl))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--object", help="对象名,按任务词展开")
    g.add_argument("--query", help="单条查询")
    ap.add_argument("--gl", default="us", choices=GLS, help="哪个国家的自动补全,默认美国")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        out = expand(root, a.object, gl=a.gl) if a.object else [snapshot(root, a.query, gl=a.gl)]
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if all(r.get("error") for r in out) else 0


if __name__ == "__main__":
    raise SystemExit(main())
