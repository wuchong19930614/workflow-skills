#!/usr/bin/env python3
"""决策书 html 生成器:从 md 单向生成同名 html(单文件、内联样式、双击即开)。

md 是唯一事实来源(生命周期契约);html 永不手写、永不手改——改 md 后重跑本脚本。
只覆盖决策书实际用到的 Markdown 子集:标题、列表、表格、引用、代码块、粗斜体、行内代码、链接、分隔线。
"""
import argparse
import html as html_mod
import re
import sys
from pathlib import Path

STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0 auto; padding: 2.5rem 1.5rem 4rem; max-width: 46rem;
  font: 16px/1.7 -apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  color: #1a1a1a; background: #fff; }
h1 { font-size: 1.7rem; line-height: 1.3; border-bottom: 2px solid #d0d0d0; padding-bottom: .4rem; }
h2 { font-size: 1.25rem; margin-top: 2.2rem; border-bottom: 1px solid #e0e0e0; padding-bottom: .25rem; }
h3 { font-size: 1.05rem; margin-top: 1.6rem; }
strong { color: #b3261e; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #ccc; padding: .4rem .6rem; text-align: left; vertical-align: top; }
th { background: rgba(127,127,127,.12); }
code { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: .92em;
  background: rgba(127,127,127,.15); padding: .1em .3em; border-radius: 3px; }
pre { background: rgba(127,127,127,.12); padding: .8rem 1rem; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { margin: 1rem 0; padding: .2rem 1rem; border-left: 4px solid #b0b0b0; color: #555; }
hr { border: none; border-top: 1px solid #d0d0d0; margin: 2rem 0; }
footer { margin-top: 3rem; font-size: .8rem; color: #888; border-top: 1px solid #e0e0e0; padding-top: .8rem; }
@media (prefers-color-scheme: dark) {
  body { color: #e6e6e6; background: #121212; }
  strong { color: #ff8a80; }
  blockquote { color: #aaa; }
}
"""


def _inline(text: str) -> str:
    """行内标记:先转义,再按 行内代码 → 粗体 → 斜体 → 链接 处理。"""
    out, pos = [], 0
    for m in re.finditer(r"`([^`]+)`", text):
        out.append(_inline_nocode(text[pos:m.start()]))
        out.append(f"<code>{html_mod.escape(m.group(1))}</code>")
        pos = m.end()
    out.append(_inline_nocode(text[pos:]))
    return "".join(out)


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
    return "\n".join(out)


def md_to_html_body(md: str) -> str:
    lines, blocks, i = md.splitlines(), [], 0
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
            blocks.append(f"<h{level}>{_inline(m.group(2).strip())}</h{level}>")
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
    return "\n".join(blocks)


def build(md_path: Path) -> Path:
    md = md_path.read_text(encoding="utf-8")
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    title = html_mod.escape(m.group(1).strip()) if m else md_path.stem
    doc = (
        "<!doctype html>\n<html lang=\"zh\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{title}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n"
        f"{md_to_html_body(md)}\n"
        f"<footer>本页由 build_decision_html.py 生成自 {html_mod.escape(md_path.name)}(md 是唯一事实来源);"
        "勿手改本文件,改 md 后重新生成。</footer>\n</body>\n</html>\n"
    )
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
