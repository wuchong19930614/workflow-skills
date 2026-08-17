#!/usr/bin/env python3
"""账本完整性校验。出错(errors)非零退出;孤儿证据目录仅警告(warnings)。

检查项:
- state 在状态词汇表内;history 末项 to == state;history 每项含 at/to/by;
- evidence_refs 均存在于磁盘;
- expiry 若存在则可解析为日期;
- go 决策态(build_ready/pilot_ready/fast_grab_ready)必须有 decision_ref,且 md+html 双文件存在;
- hold/no_site 不得携带 decision_ref(no-go 不出决策书);
- 证据/ 下无账本外孤儿目录(警告)。
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from registrar import STATES, DEFAULT_DATA_ROOT

GO_STATES = {"build_ready", "pilot_ready", "fast_grab_ready"}
NO_GO_STATES = {"hold", "no_site"}


def validate(data_root):
    data_root = Path(data_root)
    errors, warnings = [], []
    ledger_path = data_root / "账本" / "候选账本.json"
    if not ledger_path.is_file():
        return [f"账本不存在: {ledger_path}(先运行 init_workspace.py)"], warnings
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"账本不是合法 JSON: {e}"], warnings

    candidates = ledger.get("candidates", {})
    for slug, rec in candidates.items():
        where = f"[{slug}]"
        state = rec.get("state")
        if state not in STATES:
            errors.append(f"{where} 未知状态: {state!r}")
        hist = rec.get("history", [])
        if not hist:
            errors.append(f"{where} history 为空")
        else:
            if hist[-1].get("to") != state:
                errors.append(f"{where} history 末项 to={hist[-1].get('to')!r} 与 state={state!r} 不一致")
            for i, h in enumerate(hist):
                for k in ("at", "to", "by"):
                    if not h.get(k):
                        errors.append(f"{where} history[{i}] 缺字段 {k}")
        for r in rec.get("evidence_refs", []):
            if not (data_root / r).is_file():
                errors.append(f"{where} 证据文件缺失: {r}")
        expiry = rec.get("expiry")
        if expiry:
            try:
                date.fromisoformat(expiry)
            except ValueError:
                errors.append(f"{where} expiry 不可解析: {expiry!r}")
        ref = rec.get("decision_ref")
        if state in GO_STATES:
            if not ref:
                errors.append(f"{where} go 决策态缺 decision_ref")
            else:
                md = data_root / ref
                if not md.is_file():
                    errors.append(f"{where} 决策书 md 缺失: {ref}")
                if not md.with_suffix(".html").is_file():
                    errors.append(f"{where} 决策书 html 缺失(双格式要求): {md.with_suffix('.html').name}")
        if state in NO_GO_STATES and ref:
            errors.append(f"{where} no-go 结论不应携带 decision_ref: {ref}")

    evidence_dir = data_root / "证据"
    if evidence_dir.is_dir():
        for d in sorted(evidence_dir.iterdir()):
            if d.is_dir() and d.name not in candidates:
                warnings.append(f"孤儿证据目录(账本无此候选): 证据/{d.name}")
    return errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="校验 xinci 候选账本完整性")
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    a = ap.parse_args(argv)
    errors, warnings = validate(a.data_root)
    for w in warnings:
        print(f"警告: {w}")
    for e in errors:
        print(f"错误: {e}", file=sys.stderr)
    print(f"校验完成:{len(errors)} 个错误,{len(warnings)} 个警告")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
