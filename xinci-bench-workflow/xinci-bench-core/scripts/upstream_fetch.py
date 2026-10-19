#!/usr/bin/env python3
"""非游戏上游新对象(用户 2026-10-19 定):Product Hunt 新品、Show HN(50 分以上)、GitHub 近 7 天新建的高星项目、
联邦公报新发布的规则。

每个对象(政策除外)顺手查 1 次自动补全("<对象名> "),标出补全里带任务说法的(计算器、查询、追踪等);
有任务说法的拼成原料放进 items,由人挑选后并进本次 quick_signal,再走 suggest_snapshot 与速判。
政策条目名称太长、补全查不出东西,只列出来由人判断。已在原料池里的对象不再查补全。
取数函数可注入,测试不联网;某个源取不到不影响其他源。
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import data_root
import quick_model as QM
import quick_pool
import suggest_snapshot as S
from _common import BenchError, require

SOURCES = ("producthunt", "hackernews", "github", "policy")
WINDOW_DAYS = 7
LIMIT = 20                                              # 每个源最多取多少个对象
HN_MIN_POINTS = 50
INTERVAL = 1.0                                          # 两次补全请求之间的秒数,同 suggest_snapshot
# 任务说法:快道任务词再加两个"查询"类说法
UPSTREAM_TASK_WORDS = QM.TASK_WORDS + ("lookup", "finder")
UA = "xinci-bench/0.1 (personal research, low volume)"
_ATOM = "{http://www.w3.org/2005/Atom}"
_HN_SPLIT = re.compile(r"\s+[–—-]\s+|:\s+")
_TASK_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in UPSTREAM_TASK_WORDS) + r")\b")


def source_urls(on: str) -> dict:
    since = _since(on)
    ts = int(datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp())
    q = urllib.parse.urlencode
    return {
        "producthunt": "https://www.producthunt.com/feed",
        "hackernews": "https://hn.algolia.com/api/v1/search_by_date?" + q(
            {"tags": "show_hn", "numericFilters": f"points>{HN_MIN_POINTS},created_at_i>={ts}", "hitsPerPage": 100}),
        "github": "https://api.github.com/search/repositories?" + q(
            {"q": f"created:>={since}", "sort": "stars", "order": "desc", "per_page": 50}),
        "policy": "https://www.federalregister.gov/api/v1/documents.json?" + q(
            {"conditions[type][]": "RULE", "conditions[publication_date][gte]": since, "order": "newest",
             "per_page": 100}),
    }


def _since(on: str) -> str:
    require(isinstance(on, str) and len(on) >= 10, f"日期须为 YYYY-MM-DD(收到 {on!r})")
    return (date.fromisoformat(on[:10]) - timedelta(days=WINDOW_DAYS)).isoformat()


def _text(s) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _cand(source, obj, url, published, note):
    return {"source": source, "object": obj.strip(), "url": url, "published": published, "note": note}


def parse_producthunt(text: str, since: str) -> list:
    out = []
    for e in ET.fromstring(text).iter(_ATOM + "entry"):
        published = (e.findtext(_ATOM + "published") or "")[:10]
        title = e.findtext(_ATOM + "title") or ""
        link = next((l.get("href") for l in e.iter(_ATOM + "link") if l.get("rel", "alternate") == "alternate"), None)
        if published < since or not title.strip() or not link:
            continue
        content = e.findtext(_ATOM + "content") or ""
        first = re.search(r"<p>(.*?)</p>", content, re.S)          # 第一段是一句话介绍,后面是讨论、链接
        out.append(_cand("producthunt", title, link, published, _text(first.group(1) if first else content)))
    return out


def hn_object(title: str) -> str:
    t = re.sub(r"^\s*show hn:\s*", "", title, flags=re.I)
    return _HN_SPLIT.split(t, maxsplit=1)[0].strip()


def parse_hackernews(text: str, since: str) -> list:
    out = []
    for h in json.loads(text).get("hits", []):
        published = (h.get("created_at") or "")[:10]
        if published < since or (h.get("points") or 0) <= HN_MIN_POINTS or not hn_object(h.get("title") or ""):
            continue
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        out.append(_cand("hackernews", hn_object(h["title"]), url, published, f"{h['title']}({h['points']} 分)"))
    return out


def parse_github(text: str, since: str) -> list:
    out = []
    for r in json.loads(text).get("items", []):
        published = (r.get("created_at") or "")[:10]
        if published < since or not r.get("name"):
            continue
        note = f"{r.get('description') or ''}({r.get('stargazers_count', 0)} star)"
        out.append(_cand("github", r["name"], r["html_url"], published, note))
    return out


def parse_policy(text: str, since: str) -> list:
    out = []
    for d in json.loads(text).get("results", []):
        published = d.get("publication_date") or ""
        if published < since or not (d.get("title") or "").strip():
            continue
        agencies = "、".join(a.get("name", "") for a in d.get("agencies") or [] if a.get("name"))
        out.append(_cand("policy", d["title"], d["html_url"], published, f"{d.get('type') or 'Rule'} · {agencies}"))
    return out


PARSERS = {"producthunt": parse_producthunt, "hackernews": parse_hackernews, "github": parse_github,
           "policy": parse_policy}


def fetch_text(url: str) -> str:
    headers = {"User-Agent": UA}
    if "api.github.com" in url:
        headers["Accept"] = "application/vnd.github+json"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def task_hits(suggestions) -> list:
    hits = []
    for s in suggestions:
        n = quick_pool.normalize_term(s) if s and s.strip() else ""
        if n and _TASK_RE.search(n) and n not in hits:
            hits.append(n)
    return hits


def fetch_all(root, on=None, text_fetcher=None, suggest_fetcher=None, sleeper=time.sleep, sources=SOURCES,
              limit=LIMIT, gl="us", interval=INTERVAL) -> dict:
    """取各源近 7 天的新对象,非政策对象各查 1 次补全;返回各源统计、候选、可并进 quick_signal 的原料。"""
    on = on or date.today().isoformat()
    require(sources and all(s in SOURCES for s in sources), f"sources 须取自 {SOURCES}")
    require(isinstance(limit, int) and limit > 0, "limit 须为正整数")
    require(gl in S.GLS, f"gl 须为 {S.GLS}")
    since, urls = _since(on), source_urls(on)
    get = text_fetcher or fetch_text
    sug = suggest_fetcher or (lambda q: S.fetch(q, gl))
    known = {quick_pool.normalize_term(r["object"]) for r in quick_pool._read_pool(root)}
    stats, candidates, items, queried = {}, [], [], 0
    for src in sources:
        try:
            got = PARSERS[src](get(urls[src]), since)[:limit]
        except Exception as exc:                  # 网络、限流、格式错误:记下,接着取别的源
            stats[src] = {"url": urls[src], "count": 0, "error": f"{type(exc).__name__}: {exc}"}
            continue
        stats[src] = {"url": urls[src], "count": len(got)}
        for c in got:
            c["known"] = quick_pool.normalize_term(c["object"]) in known
            c["task_hits"] = None
            if src == "policy" or c["known"]:
                candidates.append(c)
                continue
            q = f"{c['object']} "
            if queried:
                sleeper(interval)
            queried += 1
            try:
                c["task_hits"] = task_hits(sug(q))
            except Exception as exc:
                c["suggest_error"] = f"{type(exc).__name__}: {exc}"
                candidates.append(c)
                continue
            c["suggest_url"] = S.url_for(q, gl)
            for t in c["task_hits"]:
                items.append({"source": src, "object": c["object"], "term": t, "url": c["url"], "seen_at": on[:10],
                              "suggest_url": c["suggest_url"]})
            candidates.append(c)
    return {"seen_at": on[:10], "since": since, "gl": gl, "sources": stats, "suggest_queries": queried,
            "candidates": candidates, "items": items}


def main(argv=None, text_fetcher=None, suggest_fetcher=None, sleeper=time.sleep):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--on", help="以哪天为准(默认今天),取这天往前 7 天")
    ap.add_argument("--sources", help="只取哪些源(逗号分隔),默认全部:" + "、".join(SOURCES))
    ap.add_argument("--limit", type=int, default=LIMIT, help=f"每个源最多取多少个对象,默认 {LIMIT}")
    ap.add_argument("--gl", default="us", help="补全的国家:us(默认)、gb、ca、au、nz、ie")
    ap.add_argument("--output", required=True, help="结果 JSON(人挑选 items 后并进本次 quick_signal)")
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        srcs = SOURCES
        if a.sources:
            srcs = tuple(x.strip() for x in a.sources.split(",") if x.strip())
        out = fetch_all(root, a.on, text_fetcher, suggest_fetcher, sleeper, srcs, a.limit, a.gl)
        Path(a.output).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    except (BenchError, OSError, ValueError) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"候选": len(out["candidates"]), "带任务说法的原料": len(out["items"]),
                      "补全查询": out["suggest_queries"],
                      "各源": {k: v.get("error") or v["count"] for k, v in out["sources"].items()},
                      "写入": a.output}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
