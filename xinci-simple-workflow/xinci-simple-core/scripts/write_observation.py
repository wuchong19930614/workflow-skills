"""观察只追加：JSON 输入从文件读取；文件名包含时间与随机后缀，不覆盖旧文件。"""
import argparse
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import data_root
import qualification as Q


def write(root, obs):
    slug, stage = obs.get('slug'), obs.get('stage')
    Q.require(isinstance(slug, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]*', slug), 'slug 无效')
    Q.require(stage in ('scan', 'verify'), 'stage 无效')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    ref = f'证据/{slug}/{stamp}-{uuid.uuid4().hex[:8]}-{stage}.json'
    path = Path(root) / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(obs, f, ensure_ascii=False, indent=2)
        f.write('\n')
    try:
        Q.read_observation(root, ref, slug)
    except Q.QualificationError:
        path.unlink()
        raise
    return ref


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root')
    ap.add_argument('--input', required=True)
    a = ap.parse_args(argv)
    root = data_root.resolve_or_exit(a.data_root)
    try:
        print(write(root, json.loads(Path(a.input).read_text(encoding='utf-8'))))
    except (OSError, ValueError) as exc:
        print(f'拒收: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
