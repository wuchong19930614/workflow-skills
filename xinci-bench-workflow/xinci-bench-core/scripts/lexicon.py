#!/usr/bin/env python3
"""旧词库与旧裁决查询,只读:按包含匹配,词按量降序。"""
import argparse
import json
import sys
from pathlib import Path

import data_root
from _common import LEXICON_REL, VERDICTS_REL, BenchError, load_json, require


def match(root, text, limit=50) -> dict:
    q = (text or "").strip().lower()
    require(q, "查询词不能为空")
    lex_p, ver_p = Path(root) / LEXICON_REL, Path(root) / VERDICTS_REL
    require(lex_p.is_file() and ver_p.is_file(), "旧词库未导入,先运行 seed_import.py")
    words = load_json(lex_p)["words"]
    hits = sorted(((t, w) for t, w in words.items() if q in t),
                  key=lambda x: (-(x[1]["volume"] or 0), x[0]))
    ver = load_json(ver_p)["candidates"]
    vhits = {s: v for s, v in ver.items()
             if q in s.replace("-", " ") or q in str(v.get("primary_keyword") or "").lower()}
    return {"query": q, "keyword_count": len(hits),
            "volume_sum": sum(w["volume"] or 0 for _, w in hits),
            "keywords": [{"term": t, **w} for t, w in hits[:limit]], "verdicts": vhits}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root")
    ap.add_argument("--match", required=True)
    ap.add_argument("--limit", type=int, default=50)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        print(json.dumps(match(root, a.match, a.limit), ensure_ascii=False, indent=2))
    except BenchError as exc:
        print(f"拒收: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
