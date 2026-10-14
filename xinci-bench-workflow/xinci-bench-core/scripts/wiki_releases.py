#!/usr/bin/env python3
"""快道上线日历:从 Wikipedia "List of video games released in <年>" 取未来 N 天上线的新游戏,按词条浏览量排热度。

只留原创(Original)与抢先体验(Early access)、有独立词条、英文区能玩的;移植、重制、正式版(抢先体验早就开了)不算新对象。
浏览量一条一条查(中间停顿),遇到 429 就停,剩下的列为"未取"。取数函数可注入,测试不联网。
输出的 items 是 quick_signal 原料格式(source=wikipedia、term=null、带 playable_at 与 stage),由执行者并进本次信号观察。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from _common import BenchError, require, today

NEW_TYPES = ("Original", "Early access")
QUARTERS = (("January–March", 1, 3), ("April–June", 4, 6), ("July–September", 7, 9), ("October–December", 10, 12))
MONTHS = {m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"), 1)}
PAGE = "List_of_video_games_released_in_{year}"
API = "https://en.wikipedia.org/w/api.php"
VIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
         "{article}/daily/{start}/{end}")
# Wikimedia 要求写明身份;想加联系方式就设环境变量 XINCI_UA_CONTACT
UA = "xinci-bench/0.1 (personal research, low volume)" + (
    f" {os.environ['XINCI_UA_CONTACT']}" if os.environ.get("XINCI_UA_CONTACT") else "")
PAUSE_SECONDS = 1.5


class RateLimited(Exception):
    """HTTP 429:停下,剩下的不查。"""


class NotFound(Exception):
    """词条没有浏览量数据(太新或改名):记为查不到,继续下一条。"""


def _cells(chunk):
    """一行表格的各个单元格;去掉 rowspan 之类的属性前缀。"""
    out = []
    for line in chunk.split("\n"):
        if not line.startswith("| "):
            continue
        cell = line[2:].strip()
        m = re.match(r'^((?:\w+="[^"]*"\s*)+)\|\s*(.*)$', cell)
        out.append(m.group(2).strip() if m else cell)
    return out


def _plain(text):
    text = re.sub(r"\{\{sort\|[^|{}]*\|(.*?)\}\}", r"\1", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    return re.sub(r"\s+", " ", text.replace("''", "")).strip()


def _article(title_cell):
    """标题整个是一个链接时才算这款游戏的词条;链到小节或只链了一部分(原著、系列)的,浏览量不代表它。"""
    m = re.search(r"\[\[([^|\]]+)(?:\|([^\]]*))?\]\]", title_cell)
    if not m or "#" in m.group(1):
        return None
    shown = (m.group(2) or m.group(1)).strip()
    bare = lambda s: re.sub(r"^The ", "", s)
    title = _plain(re.sub(r"\s*\([^)]*\)\s*$", "", title_cell))
    return m.group(1).strip() if bare(title) == bare(shown) else None


def parse_rows(wikitext, year) -> list:
    """把一节发售表拆成行:日期(跨行沿用上一行)、标题、词条、平台、类型、类别、地区。只有月份没有日的跳过。"""
    rows, cur = [], None
    for chunk in wikitext.split("\n|-")[1:]:
        cells = _cells(chunk)
        if not cells:
            continue
        m = re.fullmatch(r"(%s) (\d{1,2})" % "|".join(MONTHS), cells[0])
        if m:
            cur = date(year, MONTHS[m.group(1)], int(m.group(2))).isoformat()
            cells = cells[1:]
        elif re.fullmatch(r"(%s)|TBA|Q\d" % "|".join(MONTHS), cells[0]):
            cur = None                 # 只写到月份:日期不明
            continue
        ti = next((i for i, c in enumerate(cells) if "''" in c), None)
        if cur is None or ti is None or len(cells) < ti + 3:
            continue                   # 标题跨行的续行(同一款游戏的另一组平台)不重复算
        title_cell = cells[ti]
        region = re.search(r"''\s*\(([^)]*)\)\s*$", title_cell)
        rows.append({"date": cur, "title": _plain(re.sub(r"\s*\([^)]*\)\s*$", "", title_cell)),
                     "article": _article(title_cell), "platforms": cells[ti + 1], "type": _plain(cells[ti + 2]),
                     "genre": _plain(cells[ti + 3]) if len(cells) > ti + 3 else "",
                     "region": region.group(1) if region else None})
    return rows


def _english(region):
    return region is None or any(k in region for k in ("WW", "NA", "EU", "UK", "AU"))


def window(rows, on, days=30) -> list:
    """未来 days 天(含今天)上线的新游戏:原创或抢先体验、有独立词条、英文区能玩;同名只留最早一天。"""
    try:
        start = date.fromisoformat(on)
    except ValueError as exc:
        raise BenchError(f"on 须为日历上存在的 YYYY-MM-DD: {on}") from exc
    end = (start + timedelta(days=days)).isoformat()
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["date"]):
        if not (on <= r["date"] <= end) or r["type"] not in NEW_TYPES or not r["article"] or not _english(r["region"]):
            continue
        if r["article"] in seen:
            continue
        seen.add(r["article"])
        out.append(r)
    return out


def sections_for(on, days=30) -> list:
    """窗口覆盖的 (年, 小节标题),跨年时连下一年的一起。"""
    start = date.fromisoformat(on)
    end = start + timedelta(days=days)
    out, d = [], start
    while d <= end:
        q = next(q for q in QUARTERS if q[1] <= d.month <= q[2])
        if (d.year, q[0]) not in out:
            out.append((d.year, q[0]))
        d = date(d.year + 1, 1, 1) if q[2] == 12 else date(d.year, q[2] + 1, 1)
    return out


def rank(rows, fetch_views, on, sleep=time.sleep) -> dict:
    """一条一条查近 30 天浏览量,按浏览量从高到低排(查不到的排最后);遇到 429 停下,剩下的进 not_fetched。"""
    ranked, not_fetched = [], []
    for i, r in enumerate(rows):
        if not_fetched:
            not_fetched.append(r["title"])
            continue
        if i:
            sleep(PAUSE_SECONDS)
        try:
            views = fetch_views(r["article"], on)
        except RateLimited:
            not_fetched.append(r["title"])
            continue
        except NotFound:
            views = None
        ranked.append(dict(r, views_30d=views))
    ranked.sort(key=lambda r: (r["views_30d"] is None, -(r["views_30d"] or 0), r["date"]))
    return {"ranked": ranked, "not_fetched": not_fetched}


def to_items(ranked, top, seen_at) -> list:
    """前 top 个转成 quick_signal 原料:只有对象、没有说法,带开玩日期与阶段。"""
    return [{"source": "wikipedia", "object": r["title"], "term": None,
             "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(r["article"].replace(" ", "_")),
             "seen_at": seen_at, "playable_at": r["date"], "stage": r["type"], "views_30d": r["views_30d"]}
            for r in ranked[:top]]


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RateLimited(url) from exc
        if exc.code == 404:
            raise NotFound(url) from exc
        raise


def fetch_section(year, title) -> str:
    """取某年发售表的某一节 wikitext;那一年的页面还没有时返回空串。"""
    page = PAGE.format(year=year)
    try:
        secs = _get(f"{API}?action=parse&page={page}&prop=sections&format=json")
    except NotFound:
        return ""
    if "error" in secs:
        return ""
    idx = next((s["index"] for s in secs["parse"]["sections"] if s["line"] == title), None)
    if idx is None:
        return ""
    time.sleep(PAUSE_SECONDS)
    return _get(f"{API}?action=parse&page={page}&prop=wikitext&section={idx}&format=json")["parse"]["wikitext"]["*"]


def fetch_views(article, on) -> int:
    end = date.fromisoformat(on) - timedelta(days=1)
    start = end - timedelta(days=29)
    url = VIEWS.format(article=urllib.parse.quote(article.replace(" ", "_"), safe=""),
                       start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
    return sum(i["views"] for i in _get(url)["items"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=30, help="未来多少天内上线的(默认 30)")
    ap.add_argument("--top", type=int, default=20, help="按浏览量取前几个进原料(默认 20)")
    ap.add_argument("--output", required=True, help="结果 JSON 写到哪(放 scratchpad,之后并进 quick_signal)")
    a = ap.parse_args(argv)
    on = today()
    try:
        rows, urls = [], []
        for year, title in sections_for(on, a.days):
            text = fetch_section(year, title)
            if text:
                urls.append(f"https://en.wikipedia.org/wiki/{PAGE.format(year=year)}")
                rows += parse_rows(text, year)
            time.sleep(PAUSE_SECONDS)
        require(rows, "发售表一行都没取到,本次不写 Wikipedia 来源")
        cand = window(rows, on, a.days)
        out = rank(cand, fetch_views, on)
    except (BenchError, OSError, ValueError, KeyError, RateLimited) as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    result = {"on": on, "window_days": a.days, "source_urls": urls, "rows": len(rows), "candidates": len(cand),
              "items": to_items(out["ranked"], a.top, on), "not_fetched": out["not_fetched"]}
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("on", "rows", "candidates", "not_fetched")}
                     | {"前几名": [(i["object"], i["playable_at"], i["views_30d"]) for i in result["items"][:10]]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
