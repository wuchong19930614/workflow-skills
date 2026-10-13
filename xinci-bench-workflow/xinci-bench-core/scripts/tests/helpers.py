"""测试共用:临时数据区、各 kind 的合法观察、走到可结算状态的方向。"""
import copy
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


def _all_pass(**over):
    checks = {k: {"pass": True, "basis": f"{k} 依据"} for k in ("B1", "B2", "B3", "B4", "B5")}
    checks.update(over)
    return checks


BASE = {"observed_at": "2026-10-13T08:00:00+00:00", "source_urls": ["https://example.org/x"],
        "semrush_calls": 1, "points": ["要点"]}


def scan_obs(*domains, failing=None):
    """domains 全部 B1–B5 通过;failing={域名: {"B3": False}} 让指定项不过、其后留 null。"""
    items = []
    for d in domains:
        items.append({"domain": d, "registered_at": "2025-12-29", "aged_domain": False,
                      "authority_score": 11, "us_organic_now": 5400, "checks": _all_pass()})
    for d, fails in (failing or {}).items():
        checks = _all_pass()
        for k, v in fails.items():
            checks[k] = {"pass": v, "basis": f"{k} 读数"}
        items.append({"domain": d, "registered_at": "2025-01-01", "aged_domain": False,
                      "authority_score": 20, "us_organic_now": 1200, "checks": checks})
    return {**BASE, "slug": None, "stage": "scan", "kind": "scan", "readings": {"domains": items}}


def benchmark_obs(slug, domain="example-bench.com", **over):
    r = {"domain": domain, "traffic_start": "2026-04", "us_organic_now": 5400, "us_organic_m12": None,
         "curve": {"3": 500, "6": 5400, "12": None}, "referring_domains": 40,
         "anchor_summary": "品牌词与网址为主", "link_driven": False, "algo_risk": False,
         "update_readings": "3/6/8 月更新前后平稳", "ads_txt": "google.com, pub-1, DIRECT", "pricing": None}
    r.update(over)
    return {**BASE, "slug": slug, "stage": "assess", "kind": "benchmark", "readings": r}


def demand_obs(slug, clusters=None):
    clusters = clusters or [{"id": "core", "seed_term": "what county am i in", "volume": 100000,
                             "measured_at": "2026-10-13", "coverage": "benchmark", "near_me": False}]
    return {**BASE, "slug": slug, "stage": "assess", "kind": "demand",
            "readings": {"clusters": clusters, "keyword_count": 1500,
                         "competitor_traffic": [{"domain": "example-big.com", "traffic": 21000,
                                                 "basis": "Organic Research 按 /county/ 筛"}],
                         "crowding": 2, "new_sites": ["example-bench.com"]}}


PREFLIGHT = {"controllable": True, "desktop": True, "region": "us", "logged_out": True,
             "evidence": "Sign in 可见;页脚 United States"}


def serp_obs(slug, cluster_id="core", answered=False, **over):
    r = {"query": "what county am i in", "cluster_id": cluster_id, "answered": answered,
         "answered_basis": "AI 概览只推荐工具,不给县名", "benchmark_position": 4,
         "ai_overview": {"present": True, "completes_task": answered, "cited_domains": ["example-bench.com"],
                         "recommends_tools": True},
         "top10": [{"pos": 1, "domain": "example-big.com", "type": "tool", "authority_score": 38}]}
    r.update(over)
    return {**BASE, "slug": slug, "stage": "assess", "kind": "serp", "browser_preflight": dict(PREFLIGHT),
            "source_urls": ["https://www.google.com/search?q=what+county+am+i+in&gl=us&hl=en&pws=0"], "readings": r}


def diff_obs(slug, copy_only=False):
    gaps = [] if copy_only else [{"benchmark_now": "只查县", "ours": "同时给学区与选区",
                                  "evidence": "证据/example/serp 观察里标杆页只有县"}]
    return {**BASE, "slug": slug, "stage": "assess", "kind": "differentiation",
            "readings": {"copy_only": copy_only, "gaps": gaps}}


def delivery_obs(slug, feasible=True):
    return {**BASE, "slug": slug, "stage": "assess", "kind": "delivery",
            "readings": {"data_sources": ["Census Geocoder(公有领域)"], "license": "美国联邦政府作品,公有领域",
                         "hours": {"dev": 20, "data": 5, "content": 10}, "cash_first_year": 15,
                         "monthly_hours": 2, "feasible": feasible, "basis": "接口实测可用"}}


def brief_obs(slug):
    return {**BASE, "slug": slug, "stage": "assess", "kind": "brief",
            "readings": {"positioning": "按当前位置或地址一次给出县、学区和选区",
                         "pages": [{"path": "/", "target_query": "what county am i in", "volume": 74000,
                                    "page_type": "tool", "deliverable": "定位后给出县名与边界"}],
                         "tech_hosting": "Astro 静态站 + Cloudflare Pages 免费版",
                         "monetization_plan": "先接 AdSense,第 12 个月过 1 万访问后申请 Mediavine Journey",
                         "seo_notes": ["县名页不做批量模板"], "geo_notes": ["首屏给一句可引用的答案"],
                         "risks": ["同方向已有 2 个新站"]}}


def benchmark_record(domain="example-bench.com", **over):
    b = {"domain": domain, "registered_at": "2025-12-29", "aged_domain": False, "traffic_start": "2026-04",
         "authority_score": 11, "us_organic_now": 5400, "us_organic_m12": None, "covered_demand": 100000,
         "link_driven": False, "algo_risk": False, "monetization": ["adsense"], "clean": True}
    b.update(over)
    return b


def cluster_record(**over):
    c = {"id": "core", "seed_term": "what county am i in", "volume": 100000, "measured_at": "2026-10-13",
         "coverage": "benchmark", "near_me": False, "answered": False, "counted": True}
    c.update(over)
    return c


def model_record(benchmarks=None, clusters=None, crowding=1, paid=None, site_type="tool"):
    """给 bench_model.compute 用的最小方向记录。"""
    return {"site_type": site_type, "benchmarks": benchmarks or [benchmark_record()],
            "clusters": clusters or [cluster_record()], "crowding": crowding,
            "paid": paid or {"applicable": False, "price_month": None, "evidence": None}}


def deep(obj):
    return copy.deepcopy(obj)


def setup_direction(root, slug="example-county", us_organic_m12=20000, stale=False):
    """登记 + 写齐六类观察 + 补数,返回 (slug, 引用列表)。us_organic_m12=20000 时基准恰好 1 万访问(过线)。

    每个方向用自己的标杆域名 <slug>.example.com,避免触发"同标杆须写理由"。
    """
    import ledger
    import write_observation as W
    domain = f"{slug}.example.com"
    scan_ref = W.write(root, scan_obs(domain))
    ledger.register(root, slug, "按地址查所属县", "tool", domain, scan_ref, "初核全过")
    refs = [W.write(root, o) for o in (benchmark_obs(slug, domain, us_organic_m12=us_organic_m12), demand_obs(slug),
                                        serp_obs(slug), diff_obs(slug), delivery_obs(slug), brief_obs(slug))]
    measured = "2026-01-01" if stale else "2026-10-13"
    ledger.update(root, slug, {"benchmarks": [benchmark_record(domain, us_organic_m12=us_organic_m12)],
                               "clusters": [cluster_record(measured_at=measured)], "crowding": 2}, refs)
    return slug, [scan_ref] + refs


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
