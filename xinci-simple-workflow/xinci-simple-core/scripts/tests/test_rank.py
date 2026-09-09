# rank:五项在 found 池内归一化(KD 反向),等权平均;缺失取 0.5;不否决。
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import rank as K
from helpers import TmpRoot, write_obs, CLUSTER, SEED


def mk(root, slug, kd, vol, low_dr, ugc, age):
    ev = write_obs(root, slug, "2026-09-10-scan.json")
    cluster = dict(CLUSTER, total_volume=vol)
    proxy = {"kd": kd, "low_dr_count": low_dr, "ugc_count": ugc, "content_age_median_days": age}
    L.register(root, slug=slug, primary_keyword=slug, cluster=cluster, seed=SEED, proxy=proxy,
               evidence=[ev], by="t", reason="r")


class RankTest(unittest.TestCase):
    def test_monotonic_each_dimension(self):
        with TmpRoot() as root:
            mk(root, "base", kd=30, vol=100000, low_dr=3, ugc=2, age=400)
            mk(root, "lower-kd", kd=10, vol=100000, low_dr=3, ugc=2, age=400)
            mk(root, "more-vol", kd=30, vol=300000, low_dr=3, ugc=2, age=400)
            mk(root, "more-lowdr", kd=30, vol=100000, low_dr=6, ugc=2, age=400)
            mk(root, "more-ugc", kd=30, vol=100000, low_dr=3, ugc=5, age=400)
            mk(root, "older", kd=30, vol=100000, low_dr=3, ugc=2, age=900)
            scores = K.rank_all(root)
            for better in ("lower-kd", "more-vol", "more-lowdr", "more-ugc", "older"):
                self.assertGreater(scores[better], scores["base"], better)

    def test_missing_field_neutral(self):
        with TmpRoot() as root:
            mk(root, "a", kd=30, vol=100000, low_dr=3, ugc=2, age=400)
            mk(root, "b", kd=10, vol=300000, low_dr=6, ugc=5, age=900)
            ev = write_obs(root, "c", "2026-09-10-scan.json")
            L.register(root, slug="c", primary_keyword="c", cluster=dict(CLUSTER, total_volume=200000),
                       seed=SEED, proxy={"kd": 20}, evidence=[ev], by="t", reason="r")
            scores = K.rank_all(root)
            self.assertTrue(0 <= scores["c"] <= 1)

    def test_writes_back_and_only_found(self):
        with TmpRoot() as root:
            mk(root, "a", kd=30, vol=100000, low_dr=3, ugc=2, age=400)
            mk(root, "b", kd=10, vol=300000, low_dr=6, ugc=5, age=900)
            ev = write_obs(root, "b", "2026-09-10-verify.json", stage="verify")
            L.transition(root, "b", to="rejected", evidence=[ev], by="t", reason="G1")
            scores = K.rank_all(root, write=True)
            self.assertIn("a", scores)
            self.assertNotIn("b", scores)
            self.assertEqual(L.load(root)["candidates"]["a"]["proxy"]["rank_score"], scores["a"])

    def test_single_candidate_gets_half(self):
        with TmpRoot() as root:
            mk(root, "a", kd=30, vol=100000, low_dr=3, ugc=2, age=400)
            self.assertEqual(K.rank_all(root)["a"], 0.5)


if __name__ == "__main__":
    unittest.main()
