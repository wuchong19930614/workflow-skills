# build_report:9 节齐全、数值来自输入、缺 verify 观察报错、缺 revenue 报错、写到 报告/<slug>.md。
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_report as B
import ledger as L
from helpers import TmpRoot, write_obs, CLUSTER, SEED, PROXY, REVENUE, VERIFY_OBS

SECTIONS = ("## 1. 主关键词与簇", "## 2. 形态与意图", "## 3. 量级证据", "## 4. 竞争现场",
            "## 5. AI Overview 状态", "## 6. 季节性", "## 7. 收入三情景", "## 8. 范围排除复核",
            "## 9. 建议 play 与风险")


def verified(root, slug="heic-to-jpg-converter", volume=182000):
    ev = write_obs(root, slug, "2026-09-10-scan.json", semrush_preview={
        "queried_at": "2026-09-10", "filters": "US, KD<=49, exclude nav", "note": "前 50 行"})
    L.register(root, slug=slug, primary_keyword="heic to jpg converter", cluster=dict(CLUSTER, total_volume=volume),
               seed=SEED, proxy=dict(PROXY, rank_score=0.71), evidence=[ev], by="t", reason="r")
    vev = write_obs(root, slug, "2026-09-11-verify.json", **VERIFY_OBS)
    L.transition(root, slug, to="verified", evidence=[vev], by="t", reason="base 640",
                 form="tool", revenue=dict(REVENUE, base=640))
    return slug


class BuildReportTest(unittest.TestCase):
    def test_nine_sections_and_values(self):
        with TmpRoot() as root:
            slug = verified(root, volume=120000)  # < 150,000 → single_domain
            path = B.build(root, slug)
            self.assertEqual(path, root / "报告" / f"{slug}.md")
            text = path.read_text(encoding="utf-8")
            for s in SECTIONS:
                self.assertIn(s, text)
            self.assertIn("heic to jpg converter", text)
            self.assertIn("120,000", text)
            self.assertIn("cloudconvert.com", text)
            self.assertIn("640", text)
            self.assertIn("56,875", text)
            self.assertIn("2026-09-09.2", text)
            self.assertIn("lists converters", text)
            self.assertIn("single_domain", text)

    def test_play_cluster_expansion_when_large(self):
        with TmpRoot() as root:
            slug = verified(root, volume=400000)
            self.assertIn("cluster_expansion", B.build(root, slug).read_text(encoding="utf-8"))

    def test_requires_verify_observation(self):
        with TmpRoot() as root:
            ev = write_obs(root, "s", "2026-09-10-scan.json")
            L.register(root, slug="s", primary_keyword="s", cluster=CLUSTER, seed=SEED, proxy=PROXY,
                       evidence=[ev], by="t", reason="r")
            with self.assertRaises(B.ReportError):
                B.build(root, "s")

    def test_requires_verified_state(self):
        with TmpRoot() as root:
            ev = write_obs(root, "s", "2026-09-10-scan.json")
            L.register(root, slug="s", primary_keyword="s", cluster=CLUSTER, seed=SEED, proxy=PROXY,
                       evidence=[ev], by="t", reason="r")
            write_obs(root, "s", "2026-09-11-verify.json", **VERIFY_OBS)
            with self.assertRaises(B.ReportError):
                B.build(root, "s")

    def test_dr_missing_is_disclosed_not_counted_as_zero(self):
        """dr 全为 null 时不得报'0 个 DR>=50',必须说明 DR 未取——否则报告会与 verify 判定矛盾。"""
        with TmpRoot() as root:
            slug = "null-dr"
            ev = write_obs(root, slug, "2026-09-10-scan.json")
            L.register(root, slug=slug, primary_keyword="null dr", cluster=dict(CLUSTER, total_volume=120000),
                       seed=SEED, proxy=PROXY, evidence=[ev], by="t", reason="r")
            vo = dict(VERIFY_OBS)
            vo["serp_top10"] = [
                {"pos": 1, "domain": "a.com", "dr": None, "type": "tool", "completes_task": True, "dated": None},
                {"pos": 2, "domain": "b.com", "dr": None, "type": "forum", "completes_task": False, "dated": None},
            ]
            vev = write_obs(root, slug, "2026-09-11-verify.json", **vo)
            L.transition(root, slug, to="verified", evidence=[vev], by="t", reason="r",
                         form="tool", revenue=dict(REVENUE, base=640))
            text = B.build(root, slug).read_text(encoding="utf-8")
            # 允许出现"0 个",但必须紧跟披露行,否则报告会与 verify 判定矛盾
            self.assertIn("DR 未取", text)
            self.assertIn("a.com", text)
            self.assertIn("K 值以 verify 观察的结论为准", text)

    def test_known_dr_counted_normally(self):
        with TmpRoot() as root:
            slug = "known-dr"
            ev = write_obs(root, slug, "2026-09-10-scan.json")
            L.register(root, slug=slug, primary_keyword="known dr", cluster=dict(CLUSTER, total_volume=120000),
                       seed=SEED, proxy=PROXY, evidence=[ev], by="t", reason="r")
            vo = dict(VERIFY_OBS)
            vo["serp_top10"] = [
                {"pos": 1, "domain": "big.com", "dr": 84, "type": "tool", "completes_task": True, "dated": "2026-06"},
                {"pos": 2, "domain": "small.com", "dr": 28, "type": "tool", "completes_task": True, "dated": "2026-05"},
            ]
            vev = write_obs(root, slug, "2026-09-11-verify.json", **vo)
            L.transition(root, slug, to="verified", evidence=[vev], by="t", reason="r",
                         form="tool", revenue=dict(REVENUE, base=640))
            text = B.build(root, slug).read_text(encoding="utf-8")
            self.assertIn("**1** 个（big.com）", text)
            self.assertNotIn("DR 未取", text)

    def test_uses_latest_verify_observation(self):
        with TmpRoot() as root:
            slug = verified(root)
            write_obs(root, slug, "2026-09-12-verify.json", **dict(VERIFY_OBS, trends_12m="十二月起量"))
            self.assertIn("十二月起量", B.build(root, slug).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
