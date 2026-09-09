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
    obs["semrush_preview"] = {"queried_at": "2026-09-10", "filters": "US phrase KD<=49 exclude nav/adult", "note": "test preview"}
    obs.update(fields)
    p = root / "证据" / slug / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obs, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"证据/{slug}/{name}"


CLUSTER = {"total_volume": 600000,
           "keywords": [{"term": "heic to jpg", "volume": 300000, "kd": 38},
                        {"term": "heic to jpg converter", "volume": 200000, "kd": 41}]}
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

# v2 complete observation; intentionally incomplete observations are constructed explicitly in tests.
VERIFY_OBS.update(
    schema_version=2,
    direct_answer={'featured_snippet_completes_task': False, 'native_widget_completes_task': False, 'evidence': '首屏无完整直答'},
    serp_structure={'blocked': False, 'evidence': '内页、小站与论坛分布'},
    trends={'status': 'nonseasonal', 'evidence': '12 个月持续有量，无三个月集中峰值', 'source_url': 'https://trends.google.com/trends/explore?geo=US'},
    scope_evidence='图像文件转换；不涉及安全或需实测的产品评价',
    task_group={'id': 'convert', 'keywords': ['heic to jpg', 'heic to jpg converter'],
                'representative_keyword': 'heic to jpg converter', 'form': 'tool', 'niche': 'tech',
                'coverage_reason': '两种措辞都要求上传同类文件执行转换'})
for row in VERIFY_OBS['serp_top10']:
    row.update(url='https://' + row['domain'] + '/example', fresh=True, format_match=True)
for pos in range(3, 11):
    VERIFY_OBS['serp_top10'].append({'pos': pos, 'domain': f'example{pos}.com', 'url': f'https://example{pos}.com/',
                                   'dr': 20, 'type': 'article', 'completes_task': False})


def revenue_for(root, slug, evidence):
    import ledger as L
    import qualification as Q
    return Q.assess(root, L.load(root)['candidates'][slug], evidence)[1]


def register_candidate(root, slug='heic-to-jpg-converter', volume=600000):
    import ledger as L
    ev = write_obs(root, slug, '2026-09-10-scan.json')
    L.register(root, slug=slug, primary_keyword=slug.replace('-', ' '), cluster=dict(CLUSTER, total_volume=volume),
               seed=SEED, proxy=PROXY, evidence=[ev], by='test', reason='准入')
    return slug


def verified_candidate(root, slug='heic-to-jpg-converter'):
    import ledger as L
    register_candidate(root, slug)
    ev = write_obs(root, slug, '2026-09-11-verify.json', **VERIFY_OBS)
    L.transition(root, slug, to='verified', evidence=[ev], by='test', reason='已核验',
                 form='tool', revenue=revenue_for(root, slug, [ev]))
    return slug
