import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import init_workspace
import write_observation as W
from _common import QUICK_POOL_REL, QUICK_REJECTS_REL, SUGGEST_DIR_REL, BenchError, load_json
import helpers as H
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

    def test_signal_rising_checked(self):
        obs = quick_signal_obs()
        obs["readings"]["items"][0]["rising"] = "breakout"
        W.validate(obs)
        obs["readings"]["items"][0]["rising"] = 250
        W.validate(obs)
        obs["readings"]["items"][0]["rising"] = "huge"
        with self.assertRaisesRegex(BenchError, "rising"):
            W.validate(obs)

    def test_signal_playable_at_checked(self):
        obs = quick_signal_obs()
        obs["readings"]["items"][0].update(playable_at="2026-11-20", stage="closed beta")   # 未来日期可以
        W.validate(obs)
        obs["readings"]["items"][0]["playable_at"] = "2026-11-31"
        with self.assertRaisesRegex(BenchError, "playable_at"):
            W.validate(obs)
        obs["readings"]["items"][0].update(playable_at="2026-11-20", stage="")
        with self.assertRaisesRegex(BenchError, "stage"):
            W.validate(obs)

    def test_signal_platform_checked(self):
        obs = quick_signal_obs()
        obs["readings"]["items"][0]["platform"] = "roblox"
        W.validate(obs)
        obs["readings"]["items"][0]["platform"] = ""
        with self.assertRaisesRegex(BenchError, "platform"):
            W.validate(obs)

    def test_signal_source_checked(self):
        obs = quick_signal_obs()
        obs["readings"]["items"][0]["source"] = "twitter"
        with self.assertRaisesRegex(BenchError, "来源"):
            W.validate(obs)



class ReferenceObservationTest(unittest.TestCase):
    def test_valid_reference(self):
        obs = H.reference_obs(task_ratio=0.2)
        W.validate(obs)
        r = obs["readings"]
        self.assertEqual((r["object_volume_pre"], r["task_volume_post"], r["r"], r["full_60_days"]), (10000, 2000, 0.2, True))
        self.assertEqual(r["object_window"], ["2026-06-22", "2026-06-28"])

    def test_wardogs_numbers(self):
        obs = H.reference_obs(object="Wardogs", category="open_world_survival", playable_at="2026-08-22",
                              object_ratio=1.0646, task_ratio=0.1447, anchor_volume=8100,
                              task_window=("2026-09-04", "2026-09-17"))
        W.validate(obs)
        r = obs["readings"]
        self.assertEqual((r["object_volume_pre"], r["task_volume_post"], r["r"], r["full_60_days"]), (8623, 1172, 0.1359, False))

    def test_refusals(self):
        bad = {
            "object_window": lambda r: r.update(object_window=["2026-06-21", "2026-06-27"]),   # 不是开玩日前第 9 到第 3 天
            "task_window_len": lambda r: r.update(task_window=["2026-07-05", "2026-07-20"]),  # 不是 14 天
            "task_window_early": lambda r: r.update(task_window=["2026-06-30", "2026-07-13"]),  # 早于开玩日
            "task_window_late": lambda r: r.update(task_window=["2026-08-20", "2026-09-02"]),   # 超出开玩后 60 天
            "r": lambda r: r.update(r=0.3),
            "volume": lambda r: r.update(object_volume_pre=12000),
            "category": lambda r: r.update(category="rpg"),
            "task": lambda r: r.update(task="Tier List"),
            "source": lambda r: r.update(anchor_source="guess"),
            "zero_object": lambda r: r.update(object_ratio=0, object_volume_pre=0),
            "full_early": lambda r: r.update(full_60_days=True, playable_at="2026-08-22",
                                             task_window=["2026-09-04", "2026-09-17"],
                                             object_window=["2026-08-13", "2026-08-19"]),  # 观察日不到开玩后 60 天
        }
        for name, mutate in bad.items():
            obs = H.reference_obs()
            mutate(obs["readings"])
            with self.subTest(name), self.assertRaises(BenchError):
                W.validate(obs)

    def test_refusal_reasons(self):
        """每条拒收都要因为它自己的原因,不能被别的检查顺带挡掉(尤其是除零与"提前凑满 60 天")。"""
        bad = {
            "object_window": (lambda r: r.update(object_window=["2026-06-21", "2026-06-27"]), "object_window"),
            "task_window_len": (lambda r: r.update(task_window=["2026-07-05", "2026-07-20"]), "14 天"),
            "task_window_early": (lambda r: r.update(task_window=["2026-06-30", "2026-07-13"]), "不能早于开玩日"),
            "task_window_late": (lambda r: r.update(task_window=["2026-08-20", "2026-09-02"]), "开玩后 60 天"),
            "task_window_not_before_observed": (lambda r: r.update(task_window=["2026-10-04", "2026-10-17"],
                                                                   playable_at="2026-10-01",
                                                                   object_window=["2026-09-22", "2026-09-28"]),
                                                "早于观察日"),
            "r": (lambda r: r.update(r=0.3), "r 须等于"),
            "volume": (lambda r: r.update(object_volume_pre=12000), "object_volume_pre"),
            "task_volume": (lambda r: r.update(task_volume_post=2500), "task_volume_post"),
            "category": (lambda r: r.update(category="rpg"), "category"),
            "task": (lambda r: r.update(task="Tier List"), "task 须"),
            "source": (lambda r: r.update(anchor_source="guess"), "anchor_source"),
            "zero_object": (lambda r: r.update(object_ratio=0, object_volume_pre=0), "object_ratio"),
            "tiny_object_volume": (lambda r: r.update(object_ratio=0.00001, object_volume_pre=0), "object_volume_pre"),
            "negative_task_ratio": (lambda r: r.update(task_ratio=-0.1), "task_ratio"),
            "full_not_bool": (lambda r: r.update(full_60_days="yes"), "full_60_days"),
            "full_early": (lambda r: r.update(full_60_days=True, playable_at="2026-08-22",
                                              task_window=["2026-09-04", "2026-09-17"],
                                              object_window=["2026-08-13", "2026-08-19"]), "full_60_days"),
            "blank_object": (lambda r: r.update(object="  "), "object"),
            "bad_playable_at": (lambda r: r.update(playable_at="2026-02-30"), "playable_at"),
        }
        for name, (mutate, reason) in bad.items():
            obs = H.reference_obs()
            mutate(obs["readings"])
            with self.subTest(name), self.assertRaisesRegex(BenchError, reason):
                W.validate(obs)

    def test_reference_slug_null_and_folder(self):
        with H.TmpRoot() as root:
            ref = W.write(root, H.reference_obs())
            self.assertTrue(ref.startswith("证据/_quick/") and ref.endswith("-quick_reference.json"))
        obs = dict(H.reference_obs(), slug="x")
        with self.assertRaises(BenchError):
            W.validate(obs)

    def test_volume_term_optional(self):
        W.validate(H.quick_volume_obs("x", term="Wardogs"))
        with self.assertRaises(BenchError):
            W.validate(H.quick_volume_obs("x", term="  "))

    def test_volume_without_term_still_valid(self):
        obs = H.quick_volume_obs("x")
        self.assertNotIn("term", obs["readings"])
        W.validate(obs)
        self.assertEqual(H.quick_volume_obs("x", observed_at="2026-10-14T03:00:00+00:00")["observed_at"],
                         "2026-10-14T03:00:00+00:00")


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
