# 文档与代码的数值、字段、代码表必须一致:改一边忘了另一边时这里会失败。
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bench_model as M
import ledger as L
import quick_model as QM
import seed_import as I
import validate_ledger as V
import write_observation as W

CORE = Path(__file__).resolve().parents[2]
WORKFLOW = CORE.parent


def text(name):
    return (CORE / name).read_text(encoding="utf-8")


class ContractTest(unittest.TestCase):
    def test_contract_numbers_match_code(self):
        c = text("选站契约.md")
        a = M.ASSUMPTIONS
        self.assertIn(f"**{a['version']}**", c)
        self.assertIn(f"{W.LIMITS['max_age_months']} 个月", c)
        self.assertIn(f"≤ {W.LIMITS['max_authority_score']}", c)
        self.assertIn(f"≥ {W.LIMITS['min_us_organic']:,}/月", c)
        self.assertIn(f"{a['coef']['low']} / {a['coef']['base']} / {a['coef']['high']}", c)
        self.assertIn(f"{a['crowded_base_coef']}（crowding ≥ {a['crowded_at']}）", c)
        self.assertIn(f"{a['share_cap']:.0%}", c)
        self.assertIn(f"{a['journey_min_visits']:,}", c)
        self.assertIn(f"${a['rpm']['adsense']:.0f}", c)
        self.assertIn(f"${a['rpm']['mediavine_journey']:.0f}", c)
        p = a["paid_conversion"]
        self.assertIn(f"{p['low']:.1%} / {p['base']:.1%} / {p['high']:.1%}", c)
        self.assertIn(f"${a['threshold']:.0f}", c)

    def test_contract_lists_every_gate_and_scope_code(self):
        c = text("选站契约.md")
        for code in L.GATES + L.SCOPE_ITEMS:
            self.assertIn(f"`{code}`", c)

    def test_platform_blacklist_documented(self):
        doc = text("数据采集.md")
        for d in I.PLATFORMS:
            self.assertIn(d, doc)


class SchemaTest(unittest.TestCase):
    def test_observation_schema_matches_validator(self):
        s = json.loads(text("数据结构/observation.schema.json"))
        self.assertEqual(tuple(s["properties"]["kind"]["enum"]), W.KINDS)
        self.assertEqual({k: tuple(v) for k, v in s["readings_required"].items()}, W.REQUIRED)

    def test_direction_schema_matches_ledger(self):
        s = json.loads(text("数据结构/direction.schema.json"))
        self.assertEqual(tuple(s["required"]), V.REQUIRED)
        self.assertEqual(tuple(s["properties"]["benchmarks"]["items"]["required"]), L.BENCH_KEYS)
        self.assertEqual(tuple(s["properties"]["clusters"]["items"]["required"]), L.CLUSTER_KEYS)
        self.assertEqual(tuple(s["properties"]["site_type"]["enum"]), L.SITE_TYPES)



class QuickContractTest(unittest.TestCase):
    def test_quick_numbers_match_code(self):
        c, a = text("选站契约.md"), QM.QUICK_ASSUMPTIONS
        s = a["share"]
        lo, hi = a["anchor_ratio"]
        for needle in (f"**{a['version']}**", f"{s['low']:.0%} / {s['base']:.0%} / {s['high']:.0%}",
                       f"×{a['aio_factor']}", f"{a['threshold_visits']:,} 访问", f"基准预计月收入 ≥ ${a['single_site_revenue']:.0f}",
                       f"美国 ${a['rpm_adsense']:.0f}/千访问", f"其他英文国家 ${a['rpm_other_en']:.0f}/千访问",
                       "、".join(a["countries"]), f"≤ {a['new_days']} 天", f"| 观察期 | {a['watch_days']} 天 |",
                       f"峰值 × {a['oneoff_ratio']:.0%}", f"前 7 天 × {a['trend_floor']:.0%}", f"{lo}–{hi:g}",
                       f"| 原料保留 | {a['pool_days']} 天 |", f"{a['max_serp_per_run']} 个词", f"判 go 后 {a['launch_days']} 天",
                       " / ".join(str(m) for m in a["milestones"]) + " 天", f"基准预计 × {a['stop_ratio']:.0%}"):
            self.assertIn(needle, c)

    def test_task_words_and_quick_gates_documented(self):
        c = text("选站契约.md")
        self.assertIn("、".join(QM.TASK_WORDS), c)
        for g in L.QUICK_GATES:
            self.assertIn(f"`{g}`", c)

    def test_direction_schema_quick_required(self):
        s = json.loads(text("数据结构/direction.schema.json"))
        self.assertEqual(tuple(s["quick_required"]), V.REQUIRED_QUICK)


class SkillTest(unittest.TestCase):
    def test_skills_named_and_point_to_contract(self):
        for name in ("xinci-bench-scan", "xinci-bench-assess", "xinci-bench-status", "xinci-bench-run",
                     "xinci-bench-quick"):
            body = (WORKFLOW / name / "SKILL.md").read_text(encoding="utf-8")
            m = re.match(r"---\nname: (\S+)\ndescription: '(.+)'\n---\n", body)
            self.assertIsNotNone(m, name)
            self.assertEqual(m.group(1), name)
            if name != "xinci-bench-status":
                self.assertIn("选站契约.md", body)

if __name__ == "__main__":
    unittest.main()
