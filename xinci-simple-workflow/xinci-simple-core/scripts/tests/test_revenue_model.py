# revenue_model:四形态、两条折减、$500 边界、反推与正算一致、非法输入报错。
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import revenue_model as M


class RevenueModelTest(unittest.TestCase):
    def test_info_tech(self):
        r = M.model("info", 714286, niche="tech")
        self.assertAlmostEqual(r["base"], 500, delta=1)
        self.assertAlmostEqual(r["downside"], 250, delta=1)
        self.assertAlmostEqual(r["upside"], 750, delta=1)
        self.assertEqual(r["assumptions_version"], M.VERSION)
        self.assertEqual(r["threshold"], M.THRESHOLD)

    def test_threshold_is_200(self):
        """2026-09-09 用户拍板:门槛由 500 降为 200。"""
        self.assertEqual(M.THRESHOLD, 200)
        self.assertEqual(M.VERSION, "2026-09-09.2")

    def test_lookup_home_rpm(self):
        r = M.model("lookup", 100000, niche="home")
        self.assertAlmostEqual(r["base"], 100000 * 0.07 / 1000 * 18, places=2)

    def test_tool_ctr_10(self):
        r = M.model("tool", 100000)
        self.assertAlmostEqual(r["base"], 100000 * 0.10 / 1000 * 10, places=2)

    def test_commercial(self):
        r = M.model("commercial", 100000)
        self.assertAlmostEqual(r["base"], 100000 * 0.07 * 0.15 * 0.03 * 30, places=2)

    def test_mixed_takes_conservative(self):
        info = M.model("info", 100000)["base"]
        com = M.model("commercial", 100000)["base"]
        self.assertAlmostEqual(M.model("mixed", 100000)["base"], min(info, com), places=2)

    def test_aio_haircut(self):
        plain = M.model("info", 100000)["base"]
        self.assertAlmostEqual(M.model("info", 100000, aio_present=True)["base"], plain * 0.6, places=2)

    def test_strong_complete_haircut_and_stack(self):
        plain = M.model("info", 100000)["base"]
        self.assertAlmostEqual(M.model("info", 100000, strong_complete_count=1)["base"], plain * 0.7, places=2)
        self.assertAlmostEqual(M.model("info", 100000, strong_complete_count=2)["base"], plain * 0.7, places=2)
        self.assertAlmostEqual(M.model("info", 100000, aio_present=True, strong_complete_count=2)["base"],
                               plain * 0.6 * 0.7, places=2)

    def test_threshold_boundary(self):
        self.assertFalse(M.passes({"base": M.THRESHOLD - 0.01}))
        self.assertTrue(M.passes({"base": M.THRESHOLD}))
        # 旧门槛下过不了、新门槛下过得了的真实候选:wire size(base 234.59)
        self.assertTrue(M.passes({"base": 234.59}))

    def test_volume_needed_roundtrip(self):
        r = M.model("info", 100000, aio_present=True, strong_complete_count=1)
        again = M.model("info", r["volume_needed_for_threshold"], aio_present=True, strong_complete_count=1)
        self.assertAlmostEqual(again["base"], M.THRESHOLD, delta=1)

    def test_wire_size_case_passes_under_new_threshold(self):
        """首跑实测:wire size 310,300 / tool / home / AIO 折减 / K=1 → base 234.59,新门槛下过线。"""
        r = M.model("tool", 310300, niche="home", aio_present=True, strong_complete_count=1)
        self.assertAlmostEqual(r["base"], 234.59, delta=0.5)
        self.assertTrue(r["base"] >= M.THRESHOLD)
        self.assertAlmostEqual(r["volume_needed_for_threshold"], 264550, delta=600)

    def test_invalid_form_and_volume(self):
        with self.assertRaises(ValueError):
            M.model("saas", 100000)
        with self.assertRaises(ValueError):
            M.model("info", 0)
        with self.assertRaises(ValueError):
            M.model("info", 100000, niche="finance")
        with self.assertRaises(ValueError):
            M.model("info", 100000, strong_complete_count=3)

class UpperBoundTest(unittest.TestCase):
    def test_unknown_form_does_not_prematurely_reject(self):
        self.assertFalse(M.upper_bound(71150)['can_reject'])  # commercial still possible
        self.assertTrue(M.upper_bound(71150, ['tool'], ['home'])['can_reject'])
        self.assertEqual(M.upper_bound(71150, ['tool'], ['home'])['upper_bound'], 128.07)

    def test_upper_bound_dominates_allowed_forms(self):
        upper = M.upper_bound(100000)
        for form in M.FORMS:
            for niche in M.RPM:
                self.assertGreaterEqual(upper['upper_bound'], M.model(form, 100000, niche, True, 2)['base'])

    def test_nonfinite_bool_and_empty_options_rejected(self):
        for value in (float('nan'), float('inf'), True, -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                M.model('tool', value)
        with self.assertRaises(ValueError):
            M.upper_bound(100000, [], ['home'])
        with self.assertRaises(ValueError):
            M.model('tool', 100000, aio_present='false')


if __name__ == "__main__":
    unittest.main()
