"""测试共用:临时数据区、造候选、造观察文件。"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import init_workspace  # noqa: E402


class TmpRoot:
    """with TmpRoot() as root: ... 自动 init_workspace 并清理。"""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        init_workspace.init_workspace(self.root)
        return self.root

    def __exit__(self, *exc):
        self._tmp.cleanup()


def write_obs(root, slug, name, **fields) -> str:
    """写一份观察文件,返回数据区相对路径。"""
    obs = {"slug": slug, "observed_at": "2026-09-10T05:40:00+00:00", "stage": "scan",
           "source_urls": ["https://www.semrush.com/analytics/keywordmagic/"], "points": ["x"]}
    obs.update(fields)
    p = root / "证据" / slug / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obs, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"证据/{slug}/{name}"


CLUSTER = {"total_volume": 182000,
           "keywords": [{"term": "heic to jpg", "volume": 90500, "kd": 38},
                        {"term": "heic to jpg converter", "volume": 40500, "kd": 41}]}
SEED = {"type": "root", "value": "Converter", "queried_at": "2026-09-10T03:12:00+00:00"}
PROXY = {"kd": 38, "low_dr_count": 4, "ugc_count": 2, "content_age_median_days": 540}
VERIFY_OBS = {
    "stage": "verify",
    "browser_preflight": {"controllable": True, "desktop": True, "region": "us", "logged_out": True,
                          "evidence": "Sign in 可见;#gb 无账号元素"},
    "query_url": "https://www.google.com/search?q=heic+to+jpg+converter&gl=us&hl=en&pws=0",
    "ai_overview": {"present": True, "completes_task": False, "excerpt": "lists converters"},
    "serp_top10": [
        {"pos": 1, "domain": "cloudconvert.com", "dr": 78, "type": "tool", "completes_task": True, "dated": "2026-06"},
        {"pos": 2, "domain": "reddit.com", "dr": 92, "type": "forum", "completes_task": False, "dated": "2024-01"},
    ],
    "page2_note": "第二页起为博客与问答",
    "trends_12m": "全年平稳",
    "scope_recheck": {"ymyl": False, "firsthand": False, "brand_nav": False, "news": False},
    "source_urls": ["https://www.google.com/search?q=heic+to+jpg+converter&gl=us&hl=en&pws=0"],
    "points": ["首屏 AIO 只罗列工具名"],
}
REVENUE = {"downside": 320, "base": 640, "upside": 960, "volume_needed_for_threshold": 56875,
           "threshold": 200, "assumptions_version": "2026-09-09.2"}
