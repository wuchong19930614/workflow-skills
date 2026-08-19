#!/usr/bin/env python3
"""淘汰方向索引(结构化):批量去重查询与批量追加。

为什么不再用追加式 .md:广度扫描把素材量提到数百条/轮后,秒弃条目按 85% 计
一天就有两三百行,一周上千行。开局去重若把整份索引读进上下文,几轮就吃掉
几十 k token——而它的唯一用途只是回答"这个方向见过没有"。改成 JSONL + 脚本
查询后,上下文里只留命中结果,索引本身多大都不进上下文。

存储:数据/新词工作流/淘汰方向.jsonl,每行一条:
  {"date": "2026-08-18", "term": "...", "gate": "G0", "reason": "...",
   "pattern": "可选,结构性模式名(归并统计用)"}

命令:
  check   从 stdin 逐行读待查方向,报告哪些见过(附原因)、哪些是新的
  append  从 stdin 逐行读 JSON 或 "词|门|理由[|模式]",批量追加
  stats   总量、按闸门分布、达到归并阈值(≥3 次)的模式
"""
import argparse
import json
import re
import sys
from pathlib import Path

from registrar import DEFAULT_DATA_ROOT, _flock, _funlock

INDEX_NAME = "淘汰方向.jsonl"
MERGE_THRESHOLD = 3  # 同一结构性模式出现 3 次即应归并进陷阱类别(陷阱类别.md 追加规则)
_PUNCT = re.compile(r"[(){}\[\]（）【】,，.。:：;；/／\\\-—–_'\"“”‘’!！?？]+")


def _index_path(data_root) -> Path:
    return Path(data_root) / INDEX_NAME


def normalize(term: str) -> str:
    """归一化:小写、去标点、压空白。措辞微差不应被当成新方向重复评估。"""
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", (term or "").lower())).strip()


def _informative(tokens) -> bool:
    """交集里至少要有一个有信息量的词,否则 "3"/"8"/"api" 这类会把一切都匹上。"""
    return any(len(x) >= 3 and not x.isdigit() for x in tokens)


# 词集合重叠阈值。取值受两个真实约束夹逼:
#   保留 "qwen 3.8 27b vram requirements" 与 "Qwen 3.8 27B(vram/quantization…)" 的 5/6≈0.83;
#   排除只差一个词的相邻方向(如 "…number 0" 与 "…number 1" 的 3/4=0.75)。
# 偏保守是有意的:漏判只是重复评估一轮,误判会把一个真机会永久筛掉。
OVERLAP_THRESHOLD = 0.8


def similar(a: str, b: str) -> bool:
    """三种命中方式任一满足即算见过:

    1. 归一化后完全相等;
    2. 一方包含另一方(被包含者 ≥4 字符)——中文方向无空格分词,靠这条;
    3. 词集合重叠 ≥OVERLAP_THRESHOLD 且交集含信息量词——英文多词关键词靠这条。

    第 3 条要求两边都 ≥2 个词:单词方向做重叠匹配必然得 1.0,
    会让 "api" 命中一切含 api 的方向。单词只认前两条。
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if (len(na) >= 4 and na in nb) or (len(nb) >= 4 and nb in na):
        return True
    sa, sb = set(na.split()), set(nb.split())
    if min(len(sa), len(sb)) < 2:
        return False
    inter = sa & sb
    if not inter or not _informative(inter):
        return False
    return len(inter) / min(len(sa), len(sb)) >= OVERLAP_THRESHOLD


def load(data_root) -> list:
    p = _index_path(data_root)
    if not p.is_file():
        return []
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            print(f"警告: 第 {i} 行不是合法 JSON,已跳过", file=sys.stderr)
            continue
        if isinstance(rec, dict) and rec.get("term"):
            out.append(rec)
    return out


def _ledger_entries(data_root) -> list:
    """账本里的候选也是"见过"的:已注册的方向不该被重复评估。

    走到 G1 及之后才被否决的候选按留痕分界注册进账本、不入本索引,
    因此只查索引的去重会漏掉它们(实测:ppwr empty space ratio 在账本 rejected,
    只查索引会报"新")。
    """
    path = Path(data_root) / "账本" / "候选账本.json"
    if not path.is_file():
        return []
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    out = []
    for slug, rec in (ledger.get("candidates") or {}).items():
        names = [rec.get("term") or slug] + list(rec.get("aliases") or [])
        for name in names:
            out.append({"term": name, "gate": "账本",
                        "reason": f"已注册候选 {slug},当前状态 {rec.get('state')}",
                        "date": (rec.get("first_observed_at") or "")[:10]})
    return out


def check(data_root, terms) -> dict:
    """返回 {"seen": [{term, matched, gate, reason, date}], "fresh": [term]}。

    同时查淘汰索引与账本——开局去重一条命令覆盖两处,不必把任何一方读进上下文。
    """
    known = load(data_root) + _ledger_entries(data_root)
    seen, fresh = [], []
    for term in terms:
        if not normalize(term):
            continue
        hit = next((rec for rec in known if similar(term, rec["term"])), None)
        if hit:
            seen.append({"term": term, "matched": hit["term"], "gate": hit.get("gate", ""),
                         "reason": hit.get("reason", ""), "date": hit.get("date", "")})
        else:
            fresh.append(term)
    return {"seen": seen, "fresh": fresh}


def append(data_root, records) -> int:
    """批量追加。同一批内与已有索引内的重复条目都会被跳过(按归一化 term)。"""
    data_root = Path(data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    p = _index_path(data_root)
    existing = [r["term"] for r in load(data_root)]
    lines, added = [], 0
    for rec in records:
        term = (rec.get("term") or "").strip()
        if not term:
            continue
        if any(similar(term, e) for e in existing):
            continue
        existing.append(term)
        row = {"date": rec.get("date", ""), "term": term,
               "gate": rec.get("gate", ""), "reason": rec.get("reason", "")}
        if rec.get("pattern"):
            row["pattern"] = rec["pattern"]
        lines.append(json.dumps(row, ensure_ascii=False))
        added += 1
    if not lines:
        return 0
    with open(p, "a", encoding="utf-8") as f:
        _flock(f)
        try:
            f.write("\n".join(lines) + "\n")
        finally:
            _funlock(f)
    return added


def stats(data_root) -> dict:
    index = load(data_root)
    gates, patterns = {}, {}
    for r in index:
        g = r.get("gate") or "(未标注)"
        gates[g] = gates.get(g, 0) + 1
        if r.get("pattern"):
            patterns[r["pattern"]] = patterns.get(r["pattern"], 0) + 1
    return {"total": len(index), "by_gate": gates,
            "patterns": patterns,
            "merge_due": sorted(k for k, v in patterns.items() if v >= MERGE_THRESHOLD)}


def _parse_append_line(line: str) -> dict:
    line = line.strip()
    if not line:
        return {}
    if line.startswith("{"):
        return json.loads(line)
    parts = [x.strip() for x in line.split("|")]
    rec = {"term": parts[0]}
    for key, i in (("gate", 1), ("reason", 2), ("pattern", 3)):
        if len(parts) > i and parts[i]:
            rec[key] = parts[i]
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="淘汰方向索引:批量去重与追加")
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="从 stdin 逐行读待查方向,报告见过/新的")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("append", help='从 stdin 逐行读 JSON 或 "词|门|理由[|模式]"')
    p.add_argument("--date", default="", help="统一日期 YYYY-MM-DD(行内未给时使用)")

    sub.add_parser("stats", help="总量、闸门分布、达到归并阈值的模式")

    a = ap.parse_args(argv)

    if a.cmd == "check":
        terms = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
        r = check(a.data_root, terms)
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print(f"待查 {len(terms)} 条:见过 {len(r['seen'])},新 {len(r['fresh'])}")
            for s in r["seen"]:
                print(f"  [见过] {s['term']} ← {s['date']} {s['matched']} ({s['gate']}: {s['reason']})")
            for t in r["fresh"]:
                print(f"  [新] {t}")
        return 0

    if a.cmd == "append":
        recs = []
        for line in sys.stdin.read().splitlines():
            try:
                rec = _parse_append_line(line)
            except json.JSONDecodeError:
                print(f"跳过不合法 JSON 行: {line[:60]}", file=sys.stderr)
                continue
            if rec:
                rec.setdefault("date", a.date)
                recs.append(rec)
        n = append(a.data_root, recs)
        print(f"追加 {n} 条(输入 {len(recs)} 条,重复已跳过)")
        return 0

    s = stats(a.data_root)
    print(f"索引总量: {s['total']}")
    print("按闸门:", json.dumps(s["by_gate"], ensure_ascii=False))
    if s["patterns"]:
        print("模式计数:", json.dumps(s["patterns"], ensure_ascii=False))
    if s["merge_due"]:
        print(f"达到归并阈值(≥{MERGE_THRESHOLD})的模式,应归并进陷阱类别.md: {s['merge_due']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
