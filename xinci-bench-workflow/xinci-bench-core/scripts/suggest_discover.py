#!/usr/bin/env python3
"""用自动补全按字母展开找新对象(用户 2026-10-19 定):不花 Trends。

Google 补全只往后接字,所以前缀写成"任务词在前":`tier list a` 补出 `tier list anime vanguards`,
`codes for a` 补出 `codes for anime zero`。每个前缀接 a–z 各查一次,存快照(和 suggest_snapshot 共用快照目录与"新"的规则:
以前所有快照里都没出现过的才算新,所以第一次跑只建基线、不出新对象)。新建议里拆出对象名,拼成"<对象> <任务词>"写成原料;
原料池、快道淘汰记录、已有方向与旧裁决里有的跳过。release date 前缀只记对象(说法留空,给即将开玩或预判看)。
"""
import argparse
import json
import re
import string
import sys
import time
from pathlib import Path

import data_root
import quick_pool
import suggest_snapshot as S
from _common import BenchError, now, require

# 前缀与对应的任务词(2026-10-19 实测这 4 个能补出具体对象;map of、calculator for 只补出地理与通用计算器,不用)
DISCOVER_PATTERNS = (
    {"prefix": "tier list", "task": "tier list"},
    {"prefix": "codes for", "task": "codes"},
    {"prefix": "best builds in", "task": "build"},
    {"prefix": "release date for", "task": None},
)
LETTERS = string.ascii_lowercase
INTERVAL = 1.0                                         # 两次补全请求之间的秒数,同 suggest_snapshot
_YEAR = re.compile(r"(19|20)\d\d")
_TRAILING_NOISE = {"update", "new", "today", "wiki", "reddit", "roblox", "codes", "list", "working", "active",
                   "latest", "redeem", "free", "pc", "mobile", "android", "ios", "game"}
_COUNTED = {"update", "season", "version", "part", "chapter"}      # 这些词后面跟的数字是版本号,一起去掉
_GENERIC = {"maker", "template", "templates", "app", "apps", "anime", "games", "game", "meme", "memes", "generator",
            "creator", "website", "online", "format", "ideas", "ranking", "rankings", "roblox", "free", "all", "the"}


def extract(suggestion: str, prefix: str):
    """建议 → (对象名, 平台);对象名拆不出或太泛时返回 (None, None)。"""
    s, p = quick_pool.normalize_term(suggestion), quick_pool.normalize_term(prefix) + " "
    if not s.startswith(p):
        return None, None
    tokens = s[len(p):].split()
    platform = "roblox" if "roblox" in tokens else None
    if tokens and tokens[0] == "roblox":
        tokens = tokens[1:]
    while tokens:
        last = tokens[-1]
        if _YEAR.fullmatch(last) or last in _TRAILING_NOISE:
            tokens.pop()
        elif last.isdigit() and len(tokens) >= 2 and tokens[-2] in _COUNTED:
            tokens = tokens[:-2]
        else:
            break
    obj = " ".join(tokens)
    if len(obj) < 2 or obj in _GENERIC:
        return None, None
    return obj, platform


def _known(root):
    rows = quick_pool._read_pool(root)
    objects = {quick_pool.normalize_term(r["object"]) for r in rows}
    terms = ({quick_pool._key(r) for r in rows} | set(quick_pool._rejects(root)["terms"])
             | set(quick_pool._known_terms(root)))
    return objects, terms


def discover(root, fetcher=None, sleeper=time.sleep, at=None, letters=LETTERS, patterns=DISCOVER_PATTERNS,
             gl="us", interval=INTERVAL) -> dict:
    """每个前缀 × 每个字母查一次补全;返回新对象原料(可直接并进 quick_signal)与统计。"""
    require(isinstance(letters, str) and letters and set(letters) <= set(LETTERS), "letters 须为 a–z 里的字母")
    require(gl in S.GLS, f"gl 须为 {S.GLS}")
    require(patterns and all(p in DISCOVER_PATTERNS for p in patterns), "patterns 须取自 DISCOVER_PATTERNS")
    at = at or now()
    fetch = fetcher or (lambda q: S.fetch(q, gl))
    known_objects, known_terms = _known(root)
    items, seen, errors = [], set(), []
    queries = baseline = skipped = 0
    for pat in patterns:
        for letter in letters:
            q = f"{pat['prefix']} {letter}"
            if queries:
                sleeper(interval)
            queries += 1
            snap = S.snapshot(root, q, fetch, at, gl)
            if snap.get("error"):
                errors.append({"query": q, "error": snap["error"]})
                continue
            if snap["first_time"]:
                baseline += 1
                continue
            for sug in snap["new_suggestions"]:
                obj, platform = extract(sug, pat["prefix"])
                if not obj:
                    continue
                term = f"{obj} {pat['task']}" if pat["task"] else None
                key = quick_pool.normalize_term(term or obj)
                if obj in known_objects or key in known_terms:
                    skipped += 1
                    continue
                if key in seen:
                    continue
                seen.add(key)
                item = {"source": "autocomplete", "object": obj, "term": term, "url": S.url_for(q, gl),
                        "seen_at": at[:10], "suggestion": sug}
                if platform:
                    item["platform"] = platform
                items.append(item)
    return {"seen_at": at[:10], "gl": gl, "patterns": [p["prefix"] for p in patterns], "queries": queries,
            "baseline_queries": baseline, "skipped_known": skipped, "errors": errors, "items": items}


def main(argv=None, fetcher=None, sleeper=time.sleep):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--gl", default="us", help="国家:us(默认)、gb、ca、au、nz、ie")
    ap.add_argument("--letters", default=LETTERS, help="要展开的字母,默认 a–z")
    ap.add_argument("--patterns", help="只跑哪些前缀(逗号分隔),默认全部:" + "、".join(p["prefix"] for p in DISCOVER_PATTERNS))
    ap.add_argument("--output", required=True, help="结果 JSON(items 并进本次 quick_signal)")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        pats = DISCOVER_PATTERNS
        if a.patterns:
            want = [x.strip() for x in a.patterns.split(",") if x.strip()]
            pats = tuple(p for p in DISCOVER_PATTERNS if p["prefix"] in want)
            require(len(pats) == len(want), f"patterns 只能取 {[p['prefix'] for p in DISCOVER_PATTERNS]}")
        out = discover(root, fetcher, sleeper, letters=a.letters, patterns=pats, gl=a.gl)
        Path(a.output).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    except (BenchError, OSError, ValueError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"新对象": len(out["items"]), "查询": out["queries"], "基线(第一次查,不出新对象)": out["baseline_queries"],
                      "已知跳过": out["skipped_known"], "失败": len(out["errors"]), "写入": a.output}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
