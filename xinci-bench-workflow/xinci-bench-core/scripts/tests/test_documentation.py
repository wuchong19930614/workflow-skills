# 文档与代码的数值、字段、代码表必须一致:改一边忘了另一边时这里会失败。
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bench_model as M
import ledger as L
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


if __name__ == "__main__":
    unittest.main()
