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
            last = same_run[-1]
            previous = last['progress']
            expected_round = previous['round'] + int(last['skill'] == 'xinci-simple-verify' and previous['outcome'] == 'completed')
            if previous['next_step'] == 'done':
                raise RunLogError('该运行已完成；不能追加新阶段')
            if progress['round'] != expected_round or current != previous['next_step']:
                raise RunLogError('阶段或轮次与最近恢复位置不一致')
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


def plan(root, run_id=None):
    from _common import load_ledger
    rows = records(root)
    structured = [r for r in rows if r.get('progress')]
    selected = [r for r in structured if run_id is None or r['progress']['run_id'] == run_id]
    latest = selected[-1] if selected else None
    found = sum(r['state'] == 'found' for r in load_ledger(root)['candidates'].values())
    root_rows = [r for r in structured if r['progress']['source_kind'] == 'root'
                 and r['skill'] == 'xinci-simple-scan' and r['progress']['outcome'] == 'completed']
    source_rows = [r for r in structured if r['skill'] == 'xinci-simple-scan'
                   and r['progress']['outcome'] == 'completed']
    rotation = {'root':'small_site', 'small_site':'forum', 'forum':'root'}
    next_source = rotation[source_rows[-1]['progress']['source_kind']] if source_rows else 'root'
    action = 'verify' if found >= 5 else 'scan'
    resume = None
    if latest:
        p = latest['progress']
        if p['next_step'] != 'done':
            resume = dict(p)
            action = p['next_step']
            if latest['skill'] == 'xinci-simple-verify' and p['outcome'] == 'completed':
                resume['round'] += 1
                action = 'verify' if found >= 5 else 'scan'
    return {'found_count': found, 'action': action, 'resume': resume,
            'next_source': next_source,
            'last_completed_root': root_rows[-1]['progress']['seed_value'] if root_rows else None,
            'latest_log': latest['_path'] if latest else None,
            'legacy_logs_present': any(not r.get('progress') for r in rows)}


def main(argv=None):
    import data_root
    ap = argparse.ArgumentParser(description="写运行清单")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--date")
    ap.add_argument("--plan", action="store_true")
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
