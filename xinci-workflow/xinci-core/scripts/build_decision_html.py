#!/usr/bin/env python3
"""决策书 html 生成器:从 md 单向生成同名 html(单文件、内联样式、双击即开)。

md 是唯一事实来源(生命周期契约);html 永不手写、永不手改——改 md 后重跑本脚本。
只覆盖决策书实际用到的 Markdown 子集:标题、列表、表格、引用、代码块、粗斜体、行内代码、链接、分隔线。

排版目标:决策书是长文档(十几节、大量表格与粗体标注),所以
- 自动生成含全部层级(h2/h3/h4)的目录,宽屏为侧边固定栏、窄屏折在正文之上;
- 粗体不用警示色(全篇上百处会刺眼),改用字重加深色;
- 表格去竖线、可横向滚动;引用块作为关键披露的 callout。
渲染必须保持确定性:锚点 id 按标题出现顺序编号,不含时间戳或随机量。
"""
import argparse
import hashlib
import html as html_mod
import re
import sys
from pathlib import Path

STYLE = """
:root {
  color-scheme: light dark;
  --bg: #fff; --surface: #f6f7f9; --text: #2c333c; --heading: #0b0f14;
  --muted: #66707d; --border: #dfe3e8; --accent: #0a5ca8; --accent-soft: #eaf2fb;
  --code-bg: #eef1f5;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #10141a; --surface: #1a2028; --text: #c1cad5; --heading: #fff;
    --muted: #8b95a3; --border: #2a3138; --accent: #6cb2f5; --accent-soft: #16222f;
    --code-bg: #232b35;
  }
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 17px/1.75 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { display: grid; grid-template-columns: 1fr; gap: 2.25rem;
  max-width: 78rem; margin: 0 auto; padding: 2.5rem 1.5rem 5rem; }
main { min-width: 0; }
.doc-h { grid-column: 1 / -1; }
.doc-h h1 { margin-bottom: 0; }
p, li { max-width: 46rem; }

h1 { font-size: 1.85rem; line-height: 1.25; letter-spacing: -.01em; color: var(--heading);
  margin: 0 0 1.6rem; padding-bottom: .9rem;
  background: linear-gradient(90deg, var(--accent) 0 5rem, var(--border) 5rem)
    bottom left / 100% 2px no-repeat; }
h2 { font-size: 1.3rem; letter-spacing: -.005em; color: var(--heading);
  margin: 3rem 0 1rem; padding-bottom: .4rem; border-bottom: 1px solid var(--border); }
h3 { font-size: 1.06rem; color: var(--heading); margin: 2rem 0 .6rem; }
h4 { font-size: .98rem; color: var(--heading); margin: 1.5rem 0 .5rem; }
h1:first-child, h2:first-child { margin-top: 0; }
/* 正文首节的标题前面还有一个锚点 span,靠它自己的 :first-child 收不掉上边距 */
main > .a:first-child + h2 { margin-top: 0; }

strong { font-weight: 650; color: var(--heading); }
a { color: var(--accent); text-underline-offset: .18em; }
ul, ol { padding-left: 1.4rem; margin: .9rem 0; }
li { margin: .35rem 0; }
li::marker { color: var(--muted); }

.tw { overflow-x: auto; margin: 1.3rem 0; }
table { border-collapse: collapse; width: 100%; font-size: .95rem; }
th { text-align: left; font-weight: 650; color: var(--heading); background: var(--surface);
  border-bottom: 2px solid var(--border); padding: .55rem .7rem; white-space: nowrap; }
td { padding: .55rem .7rem; border-bottom: 1px solid var(--border); vertical-align: top; }
table tr:hover td { background: var(--accent-soft); }

/* 决策书里行内代码上百处(状态码、精确措辞),给边框会满页像按钮:只用底色区分 */
code { font-family: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;
  font-size: .89em; background: var(--code-bg); color: var(--heading);
  padding: .12em .4em; border-radius: 4px;
  -webkit-box-decoration-break: clone; box-decoration-break: clone;
  overflow-wrap: break-word; }
pre { background: var(--surface); border: 1px solid var(--border); padding: .9rem 1.1rem;
  border-radius: 6px; overflow-x: auto; font-size: .9rem; line-height: 1.55; }
pre code { background: none; border: none; padding: 0; font-size: 1em; }

blockquote { margin: 1.4rem 0; padding: .9rem 1.1rem; background: var(--accent-soft);
  border-left: 3px solid var(--accent); border-radius: 0 5px 5px 0; }
blockquote p { margin: 0; }
hr { border: none; height: 1px; background: var(--border); opacity: .55; margin: 2.75rem 0; }
/* md 每节末尾的 --- 紧接下一节标题时是双重分隔:h2 自己已有上间距与下边框 */
hr:has(+ .a + h2) { display: none; }

.a { display: block; height: 0; scroll-margin-top: 1.5rem; }

.toc { font-size: .85rem; line-height: 1.45; }
.toc-t { margin: 0 0 .7rem; font-size: .7rem; font-weight: 650; letter-spacing: .09em;
  text-transform: uppercase; color: var(--muted); }
.toc ul { list-style: none; margin: 0; padding: 0; border-left: 1px solid var(--border); }
.toc li { margin: 0; max-width: none; }
.toc a { display: block; padding: .3rem 0 .3rem .8rem; margin-left: -1px;
  color: var(--muted); text-decoration: none; border-left: 2px solid transparent; }
.toc a:hover { color: var(--accent); border-left-color: var(--accent); background: var(--accent-soft); }
.toc li.l3 a { padding-left: 1.7rem; font-size: .95em; }
.toc li.l4 a { padding-left: 2.6rem; font-size: .92em; }

@media (min-width: 1080px) {
  .wrap { grid-template-columns: 15.5rem minmax(0, 1fr); gap: 2rem 3.5rem; }
  .toc { position: sticky; top: 2.5rem; align-self: start;
    max-height: calc(100vh - 5rem); overflow-y: auto; }
}
@media (max-width: 1079px) {
  .toc { border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.1rem;
    background: var(--surface); max-height: 16rem; overflow-y: auto; }
}

footer { margin-top: 4rem; padding-top: 1rem; border-top: 1px solid var(--border);
  font-size: .78rem; color: var(--muted); }

@media print {
  .toc { display: none; }
  .wrap { display: block; max-width: none; padding: 0; }
  a { color: inherit; }
  h2 { margin-top: 1.6rem; }
}
"""


_STASH = "\x00"


def _inline(text: str) -> str:
    """行内标记:行内代码先占位存起来,再在**整行**上跑粗体/斜体/链接,最后还原。

    不能按代码片段切开分段处理:决策书里大量粗体跨着行内代码,
    例如 `**go — 走快道,`screened → fast_grab_ready`,expiry = …**`。
    分段跑会让 `**` 的起止落在不同片段里,正则匹配不到,字面 `**` 就漏到页面上。
    """
    codes = []

    def stash(m):
        codes.append(html_mod.escape(m.group(1)))
        return f"{_STASH}{len(codes) - 1}{_STASH}"

    stashed = re.sub(r"`([^`]+)`", stash, text.replace(_STASH, ""))
    out = _inline_nocode(stashed)
    return re.sub(rf"{_STASH}(\d+){_STASH}",
                  lambda m: f"<code>{codes[int(m.group(1))]}</code>", out)


def _inline_nocode(text: str) -> str:
    t = html_mod.escape(text, quote=False)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*\s][^*]*)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    return t


def _table(rows: list) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    has_header = len(cells) >= 2 and all(re.fullmatch(r":?-{2,}:?", c) for c in cells[1])
    body, out = cells[2:] if has_header else cells[1:], ["<table>"]
    if has_header:
        out.append("<tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cells[0]) + "</tr>")
        out.extend("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
    else:
        out.extend("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in cells)
    out.append("</table>")
    return '<div class="tw">' + "\n".join(out) + "</div>"


def md_to_html_body(md: str):
    """返回 (body_html, headings);headings 为 [(level, 纯文本, anchor_id)],供目录使用。

    锚点放在标题**之前**作为独立空元素,不写进 <h2> 标签本身——标题标签的形态
    是本模块的对外契约(registrar 比对完整渲染结果,测试断言 <h2>x</h2>)。
    """
    lines, blocks, headings, i = md.splitlines(), [], [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            code = html_mod.escape("\n".join(lines[i + 1:j]))
            blocks.append(f"<pre><code>{code}</code></pre>")
            i = j + 1
            continue
        if not line.strip():
            i += 1
            continue
        m = re.match(r"(#{1,4})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            inner = _inline(m.group(2).strip())
            if level >= 2:
                anchor = f"s{len(headings) + 1}"
                headings.append((level, _strip_tags(inner), anchor))
                blocks.append(f'<span class="a" id="{anchor}"></span>')
            blocks.append(f"<h{level}>{inner}</h{level}>")
            i += 1
            continue
        if re.fullmatch(r"(-{3,}|\*{3,})", line.strip()):
            blocks.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            blocks.append(_table(lines[i:j]))
            i = j
            continue
        if re.match(r"\s*[-*]\s+", line) or re.match(r"\s*\d+\.\s+", line):
            ordered = bool(re.match(r"\s*\d+\.\s+", line))
            pat = r"\s*\d+\.\s+" if ordered else r"\s*[-*]\s+"
            items, j = [], i
            while j < len(lines) and re.match(pat, lines[j]):
                items.append(re.sub(pat, "", lines[j], count=1))
                j += 1
            tag = "ol" if ordered else "ul"
            blocks.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            i = j
            continue
        if line.lstrip().startswith(">"):
            quote, j = [], i
            while j < len(lines) and lines[j].lstrip().startswith(">"):
                quote.append(lines[j].lstrip()[1:].lstrip())
                j += 1
            blocks.append(f"<blockquote><p>{_inline(' '.join(quote))}</p></blockquote>")
            i = j
            continue
        para, j = [], i
        while j < len(lines) and lines[j].strip() and not re.match(
                r"(#{1,4}\s|```|\s*[-*]\s|\s*\d+\.\s|\s*\||\s*>)", lines[j]):
            para.append(lines[j].strip())
            j += 1
        blocks.append(f"<p>{_inline(' '.join(para))}</p>")
        i = j
    return "\n".join(blocks), headings


def _strip_tags(inline_html: str) -> str:
    """目录条目只要文字:去掉 <code>/<strong> 一类行内标签,保留已转义的实体。"""
    return re.sub(r"<[^>]+>", "", inline_html)


def _toc(headings: list) -> str:
    """全层级目录(h2/h3/h4 都列出,不遗漏);少于 3 个标题时不值得占一栏。"""
    if len(headings) < 3:
        return ""
    items = "".join(
        f'<li class="l{level}"><a href="#{anchor}">{text}</a></li>'
        for level, text, anchor in headings
    )
    return ('<nav class="toc" aria-label="目录">\n<p class="toc-t">目录</p>\n'
            f"<ul>{items}</ul>\n</nav>")


def render(md_path: Path) -> str:
    raw = md_path.read_bytes()
    md = raw.decode("utf-8")
    source_sha256 = hashlib.sha256(raw).hexdigest()
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    title = html_mod.escape(m.group(1).strip()) if m else md_path.stem
    body, headings = md_to_html_body(md)
    toc = _toc(headings)
    header = ""
    if body.startswith("<h1>"):
        # 文档标题提到栅格顶部横跨两列:宽屏更大气,窄屏时读者先看标题再看目录
        cut = body.find("</h1>") + len("</h1>")
        header = f'<header class="doc-h">{body[:cut]}</header>\n'
        body = body[cut:].lstrip("\n")
    doc = (
        "<!doctype html>\n<html lang=\"zh\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<meta name=\"xinci-source-sha256\" content=\"{source_sha256}\">\n"
        f"<title>{title}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n"
        f"<div class=\"wrap\">\n{header}{toc}\n<main>\n"
        f"{body}\n"
        f"<footer>本页由 build_decision_html.py 生成自 {html_mod.escape(md_path.name)}(md 是唯一事实来源);"
        "勿手改本文件,改 md 后重新生成。</footer>\n</main>\n</div>\n</body>\n</html>\n"
    )
    return doc


def build(md_path: Path) -> Path:
    doc = render(md_path)
    out = md_path.with_suffix(".html")
    out.write_text(doc, encoding="utf-8")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="从决策书 md 生成同名单文件 html")
    ap.add_argument("md", help="决策书 md 路径")
    a = ap.parse_args(argv)
    md_path = Path(a.md)
    if not (md_path.is_file() and md_path.suffix == ".md"):
        print(f"不是可读的 md 文件: {a.md}", file=sys.stderr)
        return 2
    out = build(md_path)
    print(f"已生成: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
