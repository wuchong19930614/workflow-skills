#!/usr/bin/env python3
"""机会报告的 html 生成器:从 md 单向生成同名 html(单文件、内联样式、双击即开)。

与 xinci-workflow 的 build_decision_html.py 同一套逻辑,但零依赖地各存一份——
两套工作流的报告结构不同(这边有「为什么是这个词」的叙述节与可折叠的现场要点),
互相 import 会让任一边改版都牵动另一边。

md 是唯一事实来源;html 永不手写、永不手改——由 build_report.py 重建 md 后重跑本脚本。
只覆盖机会报告实际用到的 Markdown 子集:h1/h2/h3、表格、有序与无序列表、
粗体、行内代码、链接、水平线。渲染保持确定性:锚点按标题顺序编号,不含时间戳。

排版目标是"打开就是一页人话":单栏窄版、无侧边目录(叙述节只有五个小标题,一屏能看完),
九节数据表格与现场要点都折进 details,要反查再点开。
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
  --bg:#fff; --surface:#f6f7f9; --text:#2c333c; --heading:#0b0f14;
  --muted:#66707d; --border:#dfe3e8; --accent:#0a5ca8; --accent-soft:#eaf2fb;
  --code-bg:#eef1f5; --good:#0f7a52;
}
@media (prefers-color-scheme: dark) {
  :root { --bg:#10141a; --surface:#1a2028; --text:#c1cad5; --heading:#fff;
    --muted:#8b95a3; --border:#2a3138; --accent:#6cb2f5; --accent-soft:#16222f;
    --code-bg:#232b35; --good:#4cc38a; }
}
*{box-sizing:border-box} html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);
 font:17px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
 "Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
 -webkit-font-smoothing:antialiased}
.wrap{max-width:46rem;margin:0 auto;padding:2.5rem 1.5rem 5rem}
main{min-width:0} .doc-h{grid-column:1/-1} .doc-h h1{margin-bottom:0}
p,li{max-width:44rem}
h1{font-size:1.85rem;line-height:1.25;letter-spacing:-.01em;color:var(--heading);
 margin:0 0 1.6rem;padding-bottom:.9rem;
 background:linear-gradient(90deg,var(--accent) 0 5rem,var(--border) 5rem) bottom left/100% 2px no-repeat}
h2{font-size:1.3rem;letter-spacing:-.005em;color:var(--heading);margin:3rem 0 1rem;
 padding-bottom:.4rem;border-bottom:1px solid var(--border)}
h3{font-size:1.06rem;color:var(--heading);margin:2rem 0 .6rem}
h1:first-child,h2:first-child{margin-top:0}
main>.a:first-child+h2{margin-top:0}
strong{font-weight:650;color:var(--heading)}
a{color:var(--accent);text-underline-offset:.18em}
ul,ol{padding-left:1.4rem;margin:.9rem 0} li{margin:.45rem 0}
li::marker{color:var(--muted)}
.tw{overflow-x:auto;margin:1.3rem 0}
table{border-collapse:collapse;width:100%;font-size:.95rem}
th{text-align:left;font-weight:650;color:var(--heading);background:var(--surface);
 border-bottom:2px solid var(--border);padding:.55rem .7rem;white-space:nowrap}
td{padding:.55rem .7rem;border-bottom:1px solid var(--border);vertical-align:top}
table tr:hover td{background:var(--accent-soft)}
code{font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
 font-size:.89em;background:var(--code-bg);color:var(--heading);padding:.12em .4em;
 border-radius:4px;overflow-wrap:break-word}
hr{border:0;border-top:1px solid var(--border);margin:2.5rem 0}
/* 开篇那句结论单独立起来,读者第一眼只看它 */
.lede{background:var(--accent-soft);border-left:3px solid var(--accent);
 border-radius:0 6px 6px 0;padding:1rem 1.2rem;margin:1.4rem 0;max-width:44rem}
.lede p{margin:0}
details{margin:1.4rem 0;border:1px solid var(--border);border-radius:6px;
 background:var(--surface);padding:.4rem .9rem}
details summary{cursor:pointer;font-weight:650;color:var(--heading);padding:.5rem 0}
details[open] summary{border-bottom:1px solid var(--border);margin-bottom:.6rem}
footer{margin-top:4rem;padding-top:1.2rem;border-top:1px solid var(--border);
 color:var(--muted);font-size:.85rem;max-width:44rem}
"""

_STASH = "\x00"


def _inline(text: str) -> str:
    """行内标记 → html。先把行内代码挖出来,避免其中的 * 与 _ 被当成强调。"""
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return f"{_STASH}{len(codes) - 1}{_STASH}"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html_mod.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(rf"{_STASH}(\d+){_STASH}",
                  lambda m: f"<code>{html_mod.escape(codes[int(m.group(1))])}</code>", text)
    return text


def _table(rows: list) -> str:
    head, body = rows[0], rows[2:]          # rows[1] 是 |---| 分隔行
    th = "".join(f"<th>{_inline(c)}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_to_html_body(md: str):
    out, headings, i = [], [], 0
    lines = md.split("\n")
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1:
                out.append(f"<h1>{_inline(text)}</h1>")
            else:
                idx = len(headings)
                headings.append((level, text, f"s{idx}"))
                out.append(f'<span class="a" id="s{idx}"></span><h{level}>{_inline(text)}</h{level}>')
            i += 1
            continue
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            out.append(_table(rows))
            continue
        if re.match(r"^\d+\.\s", line.strip()):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            out.append("<ol>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ol>")
            continue
        if line.strip().startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:])
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
            continue
        if re.match(r"^-{3,}$", line.strip()):
            out.append("<hr>")
            i += 1
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,3}\s|\||- |\d+\.\s|-{3,}$)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out), headings


def _decorate(body: str) -> str:
    """html 独有的三处排版,目的是"打开就是一页人话":

    1. 开篇那句结论加底色,读者第一眼只看它;
    2. 「附:现场要点」折起来——它是机器化的采集记录;
    3. 九节数据表格整体折起来——叙述节已经把结论说完,数据是给人反查的,
       不该占正文视线。md 里保持平铺(它是给 AI 与审计读的)。
    """
    body = re.sub(r"(<h2>为什么是这个词</h2>)\s*(<p>一句话：.*?</p>)",
                  lambda m: f'{m.group(1)}<div class="lede">{m.group(2)}</div>',
                  body, count=1, flags=re.S)
    # 先折现场要点(它在最后),再折数据节,顺序反了会把 details 嵌错
    m = re.search(r'<span class="a" id="s\d+"></span><h2>附：现场要点</h2>', body)
    if m:
        body = (body[:m.start()]
                + '<details><summary>附：现场要点（采集与判定的原始记录）</summary>'
                + body[m.end():] + "</details>")
    # 数据节从第 1 节开始,到现场要点的 details 之前(或文末)
    m = re.search(r'<hr>\s*(<span class="a" id="s\d+"></span><h2>1\. )', body)
    if not m:
        return body
    start = m.start(1)
    tail = body.find('<details><summary>附：现场要点', start)
    if tail < 0:
        tail = len(body)
    return (body[:start]
            + '<details><summary>完整数据与证据（九节，每个数字的出处）</summary>'
            + body[start:tail] + "</details>" + body[tail:])


def render(md_path: Path) -> str:
    raw = md_path.read_bytes()
    md = raw.decode("utf-8")
    source_sha256 = hashlib.sha256(raw).hexdigest()
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    title = html_mod.escape(m.group(1).strip()) if m else md_path.stem
    body, _ = md_to_html_body(md)
    header = ""
    if body.startswith("<h1>"):
        cut = body.find("</h1>") + len("</h1>")
        header = f'<header class="doc-h">{body[:cut]}</header>\n'
        body = body[cut:].lstrip("\n")
    body = _decorate(body)
    return ("<!doctype html>\n<html lang=\"zh\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<meta name=\"xinci-simple-source-sha256\" content=\"{source_sha256}\">\n"
            f"<title>{title}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n"
            f"<div class=\"wrap\">\n{header}<main>\n{body}\n"
            f"<footer>本页由 build_report_html.py 生成自 {html_mod.escape(md_path.name)}"
            "（md 是唯一事实来源）；勿手改本文件，由报告脚本重建 md 后重新生成。</footer>\n"
            "</main>\n</div>\n</body>\n</html>\n")


def build(md_path: Path) -> Path:
    out = Path(md_path).with_suffix(".html")
    out.write_text(render(Path(md_path)), encoding="utf-8")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="从机会报告 md 生成同名单文件 html")
    ap.add_argument("md", help="报告 md 路径")
    a = ap.parse_args(argv)
    md_path = Path(a.md)
    if not (md_path.is_file() and md_path.suffix == ".md"):
        print(f"不是可读的 md 文件: {a.md}", file=sys.stderr)
        return 2
    print(f"已生成: {build(md_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
