#!/usr/bin/env python3
"""账本不变式校验。错误非零退出;警告只打印。"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

import ledger as L
import qualification as Q
import investment as I
import json


def validate(root):
    root = Path(root)
    errors, warnings = [], []
    ledger = L.load(root)
    slugs = set()
    for slug, rec in ledger["candidates"].items():
        slugs.add(slug)
        st = rec.get("state")
        if st not in L.STATES:
            errors.append(f"{slug}: 状态不在词汇表: {st}")
        for ref in rec.get("evidence_refs", []):
            if not (root / ref).is_file():
                errors.append(f"{slug}: 证据文件不存在: {ref}")
        hist = rec.get("history") or []
        if not hist:
            errors.append(f"{slug}: history 为空")
        elif hist[-1].get("to") != st:
            errors.append(f"{slug}: history 末项 {hist[-1].get('to')} != state {st}")
        try:
            if 'investment' in rec:
                I.check_baseline(rec['investment'])
            feedback = I.feedback_path(root, slug)
            if feedback.exists():
                I.validate_feedback(root, rec, json.loads(feedback.read_text()))
        except (Q.QualificationError, KeyError, TypeError, ValueError, OSError) as exc:
            errors.append(f'{slug}: 投入/反馈校验失败：{exc}')
        if st == "verified":
            bound_refs = []
            try:
                bound_refs = Q.check_bound(root, rec)
            except (Q.QualificationError, KeyError, TypeError, ValueError) as exc:
                errors.append(f'{slug}: {exc}')
            if rec.get("form") not in L.FORMS:
                errors.append(f"{slug}: verified 缺 form")
            rev = rec.get("revenue") or {}
            if not all(k in rev for k in L.REVENUE_KEYS):
                errors.append(f"{slug}: verified 缺 revenue 字段")
            md_rel, html_rel = f"报告/{slug}.md", f"报告/{slug}.html"
            md_path, html_path = root / md_rel, root / html_rel
            if not md_path.is_file():
                errors.append(f"{slug}: 报告缺失 {md_rel}")
            elif not html_path.is_file():
                # md 在而 html 不在是错误:go 态要求双格式(照 xinci 的规矩)
                errors.append(f"{slug}: 报告缺 html —— {html_rel} 不存在,重跑 build_report_html.py")
            else:
                if bound_refs:
                    import build_report as B
                    try:
                        observations = [Q.read_observation(root, ref, slug)[0] for ref in bound_refs]
                        if md_path.read_text(encoding='utf-8') != B.render_groups(rec, observations):
                            errors.append(f'{slug}: md 与绑定数据生成内容不一致，禁止手改报告')
                    except (Q.QualificationError, KeyError, TypeError):
                        pass  # 资格错误已在上方报告
                want = hashlib.sha256(md_path.read_bytes()).hexdigest()
                m = re.search(r'name="xinci-simple-source-sha256" content="([0-9a-f]{64})"',
                              html_path.read_text(encoding="utf-8"))
                if not m:
                    errors.append(f"{slug}: {html_rel} 内缺源 SHA-256 标记,不是脚本生成的")
                elif m.group(1) != want:
                    errors.append(f"{slug}: {html_rel} 的源 SHA-256 与当前 md 不一致"
                                  f"(md 改过但 html 未重新生成),重跑 build_report_html.py")
    ev_dir = root / "证据"
    if ev_dir.is_dir():
        for d in ev_dir.iterdir():
            if d.is_dir() and d.name not in slugs:
                warnings.append(f"孤儿证据目录(账本无此候选): 证据/{d.name}")
    return errors, warnings


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="校验账本不变式")
    ap.add_argument("--data-root", default=None)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    errors, warnings = validate(root)
    for w in warnings:
        print("警告: " + w)
    for e in errors:
        print("错误: " + e)
    print(f"校验完成:{len(errors)} 个错误,{len(warnings)} 个警告")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
