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
        self.assertFalse(M.passes({"base": 499.99}))
        self.assertTrue(M.passes({"base": 500}))

    def test_volume_needed_roundtrip(self):
        r = M.model("info", 100000, aio_present=True, strong_complete_count=1)
        again = M.model("info", r["volume_needed_for_500"], aio_present=True, strong_complete_count=1)
        self.assertAlmostEqual(again["base"], 500, delta=1)

    def test_invalid_form_and_volume(self):
        with self.assertRaises(ValueError):
            M.model("saas", 100000)
        with self.assertRaises(ValueError):
            M.model("info", 0)
        with self.assertRaises(ValueError):
            M.model("info", 100000, niche="finance")
        with self.assertRaises(ValueError):
            M.model("info", 100000, strong_complete_count=3)


if __name__ == "__main__":
    unittest.main()
