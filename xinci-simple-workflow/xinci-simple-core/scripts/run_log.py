#!/usr/bin/env python3
"""运行清单:阶段进度只追加，保存预算、恢复位置与来源游标。"""
import argparse
import json
import uuid
from datetime import datetime, timezone
import re
import sys
from pathlib import Path

from _common import atomic_save

SKILLS = ("xinci-simple-scan", "xinci-simple-verify")


class RunLogError(Exception):
    pass


def record(root, *, date, skill, sources_opened, candidates_touched, billable_calls, notes,
           suffix=None, progress=None) -> Path:
    if skill not in SKILLS:
        raise RunLogError(f"skill 须为 {SKILLS}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
        raise RunLogError("date 须为 YYYY-MM-DD")
    if not isinstance(billable_calls, int) or billable_calls < 0:
        raise RunLogError("billable_calls 须为非负整数")
    if progress is not None:
        required = ('run_id','round','max_rounds','source_kind','seed_value','outcome','next_step')
        if not all(k in progress for k in required):
            raise RunLogError('progress 字段不完整')
        if (not re.fullmatch(r'[a-zA-Z0-9-]+', progress['run_id'])
                or type(progress['round']) is not int or type(progress['max_rounds']) is not int
                or not 1 <= progress['round'] <= progress['max_rounds']):
            raise RunLogError('运行 ID 或轮次预算无效')
        if (progress['source_kind'] not in ('root','small_site','forum')
                or not isinstance(progress['seed_value'], str) or not progress['seed_value'].strip()
                or progress['outcome'] not in ('started','completed','blocked','skipped')
                or progress['next_step'] not in ('scan','verify','done')):
            raise RunLogError('来源、结果或下一步无效')
        outcome, step = progress['outcome'], progress['next_step']
        current = 'scan' if skill == 'xinci-simple-scan' else 'verify'
        expected = current if outcome in ('started','blocked') else (
            'verify' if current == 'scan' else ('done' if progress['round'] == progress['max_rounds'] else 'scan'))
        if step != expected or (outcome == 'skipped' and current != 'scan'):
            raise RunLogError('next_step 与阶段/轮次不一致；只能跳过发现阶段')
        history = records(root)
        same_run = [r for r in history if (r.get('progress') or {}).get('run_id') == progress['run_id']]
        if same_run:
            cursor = next_position(same_run[-1])
            if cursor is None:
                raise RunLogError('该运行已完成；不能追加新阶段')
            if progress['round'] != cursor['round'] or current != cursor['stage']:
                raise RunLogError('阶段或轮次与最近恢复位置不一致')
        elif any(next_position(row) is not None for row in latest_runs(history).values()):
            raise RunLogError('存在未完成运行，须先恢复；不能创建新 run_id')
        elif progress['round'] != 1:
            raise RunLogError('新运行必须从第 1 轮开始')
        for prior in history:
            old = prior.get('progress') or {}
            if old.get('run_id') == progress['run_id']:
                if old.get('max_rounds') != progress['max_rounds']:
                    raise RunLogError('同一 run_id 的预算不能改变')
                if (old.get('round') == progress['round'] and prior['skill'] == skill
                        and old.get('outcome') in ('completed','skipped')
                        and progress['outcome'] in ('completed','skipped')):
                    raise RunLogError('同一轮同一阶段不能重复完成')
        suffix = suffix or (progress['run_id'] + '-r' + str(progress['round']) + '-' + uuid.uuid4().hex[:8])
    name = f"{date}-{skill}" + (f"-{suffix}" if suffix else "") + ".json"
    path = Path(root) / "运行" / name
    if path.exists():
        raise RunLogError(f"运行清单已存在,同日再次运行请传 --suffix HHMM: {path.name}")
    seen, urls = set(), []
    for u in sources_opened or []:
        if u not in seen:
            seen.add(u)
            urls.append(u)
    atomic_save(path, {
        "date": date, "skill": skill, "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "sources_opened": urls,
        "candidates_touched": sorted(set(candidates_touched or [])),
        "billable_calls": billable_calls,
        "notes": list(notes or []),
        **({"schema_version": 2, "progress": progress} if progress is not None else {}),
    })
    return path


def records(root):
    rows = []
    for path in (Path(root) / '运行').glob('*.json'):
        row = json.loads(path.read_text(encoding='utf-8'))
        row['_path'] = str(path)
        rows.append(row)
    return sorted(rows, key=lambda r: (r['recorded_at'], r['_path']))


def latest_runs(rows):
    latest = {}
    for row in rows:
        if row.get('progress'):
            latest[row['progress']['run_id']] = row
    return latest


def next_position(row):
    p = row['progress']
    if p['next_step'] == 'done':
        return None
    return {'stage': p['next_step'], 'round': p['round'] + int(
        row['skill'] == 'xinci-simple-verify' and p['outcome'] == 'completed')}


def plan(root, run_id=None):
    from _common import load_ledger
    rows = records(root)
    structured = [r for r in rows if r.get('progress')]
    latest = latest_runs(rows)
    active = {key: row for key, row in latest.items() if next_position(row) is not None}
    if run_id is not None and run_id not in latest:
        raise RunLogError('指定 run_id 不存在')
    conflict = run_id is None and len(active) > 1
    selected = latest.get(run_id) if run_id else (next(iter(active.values())) if len(active) == 1 else None)
    found = sum(r['state'] == 'found' for r in load_ledger(root)['candidates'].values())
    scans = [r for r in structured if r['skill'] == 'xinci-simple-scan' and r['progress']['outcome'] == 'completed']
    roots = [r for r in scans if r['progress']['source_kind'] == 'root']
    rotation = {'root':'small_site', 'small_site':'forum', 'forum':'root'}
    source = rotation[scans[-1]['progress']['source_kind']] if scans else 'root'
    resume, action = None, 'scan'
    if selected:
        cursor = next_position(selected)
        if cursor:
            resume = dict(selected['progress'], round=cursor['round'], next_step=cursor['stage'])
            action = cursor['stage']
        else:
            action = 'done'
    if conflict:
        action = None
    # A skipped scan is still a real log action, never silently jump to verify.
    return {'found_count': found, 'action': action, 'scan_outcome': 'skipped' if action == 'scan' and found >= 5 else None,
            'resume': resume, 'conflict': conflict, 'active_run_ids': sorted(active),
            'next_source': source, 'last_completed_root': roots[-1]['progress']['seed_value'] if roots else None,
            'latest_log': selected['_path'] if selected else None,
            'legacy_logs_present': any(not r.get('progress') for r in rows)}


def finish(root, *, run_id, outcome='completed', sources_opened=None, candidates_touched=None,
           billable_calls=0, notes=None):
    """结束已 started/blocked 阶段；不接受重复完成，防止重复计费。"""
    row = latest_runs(records(root)).get(run_id)
    if not row or row['progress']['outcome'] not in ('started','blocked'):
        raise RunLogError('finish 须针对 started/blocked 阶段；阶段已结束时不要重记计费')
    if outcome not in ('completed','blocked','skipped'):
        raise RunLogError('finish outcome 无效')
    p = dict(row['progress'], outcome=outcome)
    stage = row['skill'].removeprefix('xinci-simple-')
    p['next_step'] = stage if outcome == 'blocked' else ('verify' if stage == 'scan' else (
        'done' if p['round'] == p['max_rounds'] else 'scan'))
    return record(root, date=datetime.now(timezone.utc).date().isoformat(), skill=row['skill'],
                  sources_opened=sources_opened, candidates_touched=candidates_touched,
                  billable_calls=billable_calls, notes=notes, progress=p)


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="写运行清单")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--date")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--finish", action="store_true")
    ap.add_argument("--run-id")
    ap.add_argument("--round", type=int)
    ap.add_argument("--max-rounds", type=int)
    ap.add_argument("--source-kind", choices=("root","small_site","forum"))
    ap.add_argument("--seed-value")
    ap.add_argument("--outcome", choices=("started","completed","blocked","skipped"))
    ap.add_argument("--next-step", choices=("scan","verify","done"))
    ap.add_argument("--skill", choices=SKILLS)
    ap.add_argument("--suffix", default=None)
    ap.add_argument("--source-opened", action="append", default=[])
    ap.add_argument("--candidate-touched", action="append", default=[])
    ap.add_argument("--billable-calls", type=int, default=0)
    ap.add_argument("--note", action="append", default=[])
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        if a.plan:
            print(json.dumps(plan(root, a.run_id), ensure_ascii=False, indent=2))
            return 0
        if a.finish:
            print(finish(root, run_id=a.run_id, outcome=a.outcome or 'completed', sources_opened=a.source_opened,
                         candidates_touched=a.candidate_touched, billable_calls=a.billable_calls, notes=a.note))
            return 0
        progress = {'run_id': a.run_id, 'round': a.round, 'max_rounds': a.max_rounds,
                    'source_kind': a.source_kind, 'seed_value': a.seed_value,
                    'outcome': a.outcome, 'next_step': a.next_step}
        if any(v is None for v in progress.values()):
            raise RunLogError('写清单须提供 --run-id/--round/--max-rounds/--source-kind/--seed-value/--outcome/--next-step')
        p = record(root, date=a.date, skill=a.skill, sources_opened=a.source_opened,
                   candidates_touched=a.candidate_touched, billable_calls=a.billable_calls,
                   notes=a.note, suffix=a.suffix, progress=progress)
    except RunLogError as e:
        print(f"拒收: {e}", file=sys.stderr)
        return 1
    print(f"已写 {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
