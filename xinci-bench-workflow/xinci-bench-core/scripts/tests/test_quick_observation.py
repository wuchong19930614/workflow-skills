import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import init_workspace
import write_observation as W
from _common import QUICK_POOL_REL, QUICK_REJECTS_REL, SUGGEST_DIR_REL, BenchError, load_json
from helpers import (TmpRoot, quick_brief_obs, quick_screen_obs, quick_signal_obs, quick_volume_obs)


class QuickObservationTest(unittest.TestCase):
    def test_round_trip_and_folders(self):
        with TmpRoot() as root:
            sig = W.write(root, quick_signal_obs())
            self.assertTrue(sig.startswith("证据/_quick/") and sig.endswith("-quick_signal.json"))
            for obs in (quick_screen_obs("q"), quick_volume_obs("q"), quick_brief_obs("q")):
                self.assertTrue(W.write(root, obs).startswith("证据/q/"))

    def test_ratio_out_of_range_rejected(self):
        with self.assertRaisesRegex(BenchError, "0.2–5"):
            W.validate(quick_volume_obs("q", anchor_volume=74000, new_mean=5.0, anchor_mean=72.0))

    def test_estimate_must_match(self):
        obs = quick_volume_obs("q")
        obs["readings"]["estimate_7d"] = 90000
        with self.assertRaisesRegex(BenchError, "estimate_7d"):
            W.validate(obs)

    def test_serp_conclusion_needs_preflight(self):
        with self.assertRaisesRegex(BenchError, "preflight"):
            W.validate(quick_screen_obs("q", preflight=False))
        early = quick_screen_obs("q", fail={"Q1": False, "Q5": None, "Q6": None}, preflight=False)
        W.validate(early)                      # Q1 已不过,没看首页,不需要预检

    def test_occupied_needs_domain(self):
        with self.assertRaisesRegex(BenchError, "occupied_by"):
            W.validate(quick_screen_obs("q", fail={"Q5": False}))
        W.validate(quick_screen_obs("q", fail={"Q5": False}, occupied_by="small-tool.com"))

    def test_stage_must_be_quick(self):
        obs = quick_brief_obs("q")
        obs["stage"] = "assess"
        with self.assertRaisesRegex(BenchError, "stage"):
            W.validate(obs)

    def test_trends_less_than_one_marker_refused(self):
        obs = quick_volume_obs("q", series=["<1"] * 5 + list(range(20, 45)))
        with self.assertRaisesRegex(BenchError, "非负数"):
            W.validate(obs)

    def test_anchor_date_must_exist(self):
        with self.assertRaisesRegex(BenchError, "anchor_measured_at"):
            W.validate(quick_volume_obs("q", measured="2026-02-30"))
        obs = quick_signal_obs()
        obs["readings"]["items"][0]["seen_at"] = "2026-13-01"
        with self.assertRaisesRegex(BenchError, "seen_at"):
            W.validate(obs)

    def test_volume_needs_all_six_countries(self):
        obs = quick_volume_obs("q")
        obs["readings"]["countries"] = obs["readings"]["countries"][:5]
        with self.assertRaisesRegex(BenchError, "6 国"):
            W.validate(obs)

    def test_non_us_anchor_needs_semrush(self):
        obs = quick_volume_obs("q", others={"GB": (8000, 30.0, 40.0)})
        obs["readings"]["countries"][1]["anchor_source"] = "lexicon"
        with self.assertRaisesRegex(BenchError, "Semrush"):
            W.validate(obs)

    def test_total_and_trend_geo_checked(self):
        obs = quick_volume_obs("q", others={"GB": (8000, 30.0, 40.0)})
        self.assertEqual(obs["readings"]["estimate_7d"], 56000)
        W.validate(obs)
        obs["readings"]["estimate_7d"] = 50000
        with self.assertRaisesRegex(BenchError, "合计"):
            W.validate(obs)
        obs = quick_volume_obs("q", others={"GB": (8000, 30.0, 40.0)})
        obs["readings"]["trend_geo"] = "GB"
        with self.assertRaisesRegex(BenchError, "trend_geo"):
            W.validate(obs)

    def test_nothing_readable_refused(self):
        obs = quick_volume_obs("q")
        obs["readings"]["countries"][0] = {"geo": "US", "readable": False, "basis": "全为 0"}
        with self.assertRaisesRegex(BenchError, "至少"):
            W.validate(obs)

    def test_signal_source_checked(self):
        obs = quick_signal_obs()
        obs["readings"]["items"][0]["source"] = "twitter"
        with self.assertRaisesRegex(BenchError, "来源"):
            W.validate(obs)



class QuickWorkspaceTest(unittest.TestCase):
    def test_init_creates_quick_area(self):
        with TmpRoot() as root:
            self.assertTrue((root / "证据" / "_quick").is_dir())
            self.assertTrue((root / SUGGEST_DIR_REL).is_dir())
            self.assertEqual(load_json(root / QUICK_REJECTS_REL), {"schema_version": 1, "terms": {}})
            self.assertEqual((root / QUICK_POOL_REL).read_text(encoding="utf-8"), "")
            self.assertEqual(init_workspace.init_workspace(root), [])


if __name__ == "__main__":
    unittest.main()
