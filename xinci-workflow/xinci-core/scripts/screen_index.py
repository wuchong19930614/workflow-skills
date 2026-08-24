#!/usr/bin/env python3
"""淘汰方向索引(结构化):批量去重查询与批量追加。

为什么不再用追加式 .md:广度扫描把素材量提到数百条/轮后,秒弃条目按 85% 计
一天就有两三百行,一周上千行。开局去重若把整份索引读进上下文,几轮就吃掉
几十 k token——而它的唯一用途只是回答"这个方向见过没有"。改成 JSONL + 脚本
查询后,上下文里只留命中结果,索引本身多大都不进上下文。

存储:<数据区>/淘汰方向.jsonl,每行一条:
  {"date": "2026-08-18", "term": "...", "gate": "G0", "reason": "...",
   "pattern": "可选,结构性模式名(归并统计用)"}

命令:
  check   从 stdin 逐行读待查方向,报告哪些见过(附原因)、哪些是新的
  append  从 stdin 逐行读 JSON 或 "词|门|理由[|模式]",批量追加
  resolve 登记疑似重复的 same/distinct 裁决，后续 check 与 registrar 共用
  stats   总量、按闸门分布、累计 ≥3 次仍未归并的模式(兜底提醒;建类本身发现即做)
"""
import argparse
import json
import sys
from pathlib import Path

import data_root
from registrar import _flock, _funlock
from dedup_decisions import DedupDecisionError, find as find_decision, resolve as resolve_decision
from term_normalize import match_kind, normalize, similar

INDEX_NAME = "淘汰方向.jsonl"
MERGE_THRESHOLD = 3  # stats 的兜底提醒线:累计 ≥3 次仍未归并的模式该被注意了;建类本身发现即做(陷阱类别.md 追加规则)

# 当前闸门版本。闸门契约每次实质修订都要在这里进号。
# 为什么需要它:索引条目是永久的("永不复活"),而闸门会改。2026-08-23 的反向回测
# (闸门校准.md)改了 G3 的否决线并给深审加了 G6 入口预检,此前按旧闸门写下的
# 1400 余条永久否决因此可能包含误杀。记下版本号,check 才能把"旧闸门下的否决"
# 单独标出来,让闸门修订可以触发选择性重开,而不是把错误永久固化。
GATE_VERSION = "2026-08-23b"  # b: G6 两条盈利线 + G3 占位否决条件化 + 赛道推论(同日第二次实质修订)
def _index_path(data_root) -> Path:
    return Path(data_root) / INDEX_NAME


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

    走完 G2/G3 深审后被否决的候选按留痕分界注册进账本再转 rejected、不入本索引
    (G1 否决相反,只入索引),因此只查索引的去重会漏掉它们
    (实测:ppwr empty space ratio 深审死在 G3、在账本 rejected,只查索引会报"新")。
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
                        "date": (rec.get("first_observed_at") or "")[:10],
                        "task": rec.get("task", "")})
    return out


def check(data_root, terms) -> dict:
    """返回 exact seen、需要快审的 probable review，以及 fresh。

    同时查淘汰索引与账本——开局去重一条命令覆盖两处,不必把任何一方读进上下文。
    """
    known = load(data_root) + _ledger_entries(data_root)
    seen, review, fresh = [], [], []
    for term in terms:
        if not normalize(term):
            continue
        hit = next((rec for rec in known if match_kind(term, rec["term"]) == "exact"), None)
        probable = None
        same = None
        if not hit:
            for rec in known:
                if match_kind(term, rec["term"]) != "probable":
                    continue
                decision = find_decision(data_root, term, rec["term"])
                if decision and decision["decision"] == "distinct":
                    continue
                if decision and decision["decision"] == "same":
                    same = rec
                    break
                probable = rec
                break
        row = lambda rec: {"term": term, "matched": rec["term"], "gate": rec.get("gate", ""),
                           "reason": rec.get("reason", ""), "date": rec.get("date", ""),
                           "matched_task": rec.get("task", ""),
                           "source_urls": rec.get("source_urls", []),
                           "gate_version": rec.get("gate_version", ""),
                           # 该否决是否出自当前闸门。False 表示它写在闸门修订之前,
                           # 可能是旧判据下的误杀,值得按现行闸门重看一遍。
                           "current_gates": rec.get("gate_version", "") == GATE_VERSION}
        if hit:
            seen.append(row(hit))
        elif same:
            seen.append(row(same))
        elif probable:
            review.append(row(probable))
        else:
            fresh.append(term)
    return {"seen": seen, "review": review, "fresh": fresh}


def append(data_root, records) -> int:
    """批量追加。只自动跳过归一化完全相等项；相似长尾不得被永久误杀。"""
    data_root = Path(data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    p = _index_path(data_root)
    lock_path = data_root / f".{INDEX_NAME}.lock"
    with open(lock_path, "w") as lock:
        _flock(lock)
        try:
            existing = [normalize(r["term"]) for r in load(data_root)]
            lines, added = [], 0
            for rec in records:
                term = (rec.get("term") or "").strip()
                norm = normalize(term)
                if not norm or norm in existing:
                    continue
                existing.append(norm)
                row = {"date": rec.get("date", ""), "term": term,
                       "gate": rec.get("gate", ""), "reason": rec.get("reason", ""),
                       "gate_version": rec.get("gate_version") or GATE_VERSION,
                       # 赛道。2026-08-23 开放 mature 道后新增:索引原本只服务新词道,
                       # 不分道会让两条道的淘汰理由混在一起(新词道死于"Google 已答",
                       # mature 道死于"量级不够"或"防守太强",不是同一件事)。
                       # 历史 1502 行全部产自新词道,缺字段即视为 new,语义不变。
                       "lane": rec.get("lane") or "new"}
                if rec.get("pattern"):
                    row["pattern"] = rec["pattern"]
                if rec.get("task"):
                    row["task"] = rec["task"]
                if rec.get("source_urls"):
                    row["source_urls"] = rec["source_urls"]
                lines.append(json.dumps(row, ensure_ascii=False))
                added += 1
            if lines:
                with open(p, "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
        finally:
            _funlock(lock)
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
    ap.add_argument("--data-root", default=None,
                    help="数据区路径。不给则按 XINCI_DATA_ROOT 环境变量、再按仓库配置 .xinci-data-root 解析;都没有则拒绝执行并提示先问用户")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="从 stdin 逐行读待查方向,报告见过/新的")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("append", help='从 stdin 逐行读 JSON 或 "词|门|理由[|模式]"')
    p.add_argument("--date", default="", help="统一日期 YYYY-MM-DD(行内未给时使用)")

    sub.add_parser("stats", help="总量、闸门分布、累计 ≥3 次仍未归并的模式(兜底提醒)")
    p = sub.add_parser("resolve", help="登记疑似重复裁决")
    p.add_argument("--term", required=True)
    p.add_argument("--matched", required=True)
    p.add_argument("--decision", choices=["same", "distinct"], required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--term-task", required=True)
    p.add_argument("--matched-task", help="索引旧条目缺 task 时必须人工重建并填写")
    p.add_argument("--term-evidence-url", action="append", required=True)
    p.add_argument("--matched-evidence-url", action="append",
                   help="历史条目的独立来源;未给时可使用索引记录自身 source_urls")
    p.add_argument("--by", choices=["xinci-scan", "xinci-run", "user"], default="user")
    p.add_argument("--run-id")
    p.add_argument("--supersedes", help="修订错误裁决时指向当前 decision_id")

    a = ap.parse_args(argv)
    # 数据区未配置时在这里就停,并打印「先问用户」的指引,
    # 不让空路径流进下游写操作(理由见 data_root.py)。
    a.data_root = data_root.resolve_or_exit(a.data_root)

    if a.cmd == "check":
        terms = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
        r = check(a.data_root, terms)
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            stale = sum(1 for s in r["seen"] + r["review"] if not s["current_gates"])
            print(f"待查 {len(terms)} 条:精确见过 {len(r['seen'])},疑似重复待快审 {len(r['review'])},新 {len(r['fresh'])}")
            if stale:
                print(f"  其中 {stale} 条出自旧闸门(当前闸门版本 {GATE_VERSION}),按现行判据可能是误杀,值得重看")
            for s in r["seen"]:
                tag = "见过" if s["current_gates"] else "见过·旧闸门"
                print(f"  [{tag}] {s['term']} ← {s['date']} {s['matched']} ({s['gate']}: {s['reason']})")
            for s in r["review"]:
                tag = "疑似重复·须快审" if s["current_gates"] else "疑似重复·须快审·旧闸门"
                print(f"  [{tag}] {s['term']} ≈ {s['date']} {s['matched']} ({s['gate']}: {s['reason']})")
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

    if a.cmd == "resolve":
        known = load(a.data_root) + _ledger_entries(a.data_root)
        target = next((r for r in known if normalize(r["term"]) == normalize(a.matched)), None)
        if not target:
            print("裁决拒绝:matched 必须精确指向当前索引或账本条目", file=sys.stderr)
            return 2
        if match_kind(a.term, target["term"]) != "probable":
            print("裁决拒绝:这两个措辞当前不是疑似重复关系", file=sys.stderr)
            return 2
        try:
            matched_task = a.matched_task or target.get("task")
            if not matched_task:
                print("裁决拒绝:历史 matched 条目缺 concrete task;"
                      "先重建证据并传 --matched-task", file=sys.stderr)
                return 2
            row = resolve_decision(
                a.data_root, a.term, target["term"], a.decision, a.reason,
                actor=a.by, term_task=a.term_task, matched_task=matched_task,
                term_evidence_urls=a.term_evidence_url,
                matched_evidence_urls=a.matched_evidence_url or target.get("source_urls"),
                run_id=a.run_id, supersedes=a.supersedes)
        except DedupDecisionError as e:
            print(f"裁决拒绝:{e}", file=sys.stderr)
            return 2
        print(json.dumps(row, ensure_ascii=False))
        return 0

    s = stats(a.data_root)
    print(f"索引总量: {s['total']}")
    print("按闸门:", json.dumps(s["by_gate"], ensure_ascii=False))
    if s["patterns"]:
        print("模式计数:", json.dumps(s["patterns"], ensure_ascii=False))
    if s["merge_due"]:
        print(f"累计 ≥{MERGE_THRESHOLD} 次仍未归并的模式(兜底提醒,建类应发现即做),该归并进陷阱类别.md: {s['merge_due']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
