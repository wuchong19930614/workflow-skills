import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import settle as S
import validate_ledger as V
import write_observation as W
from _common import BenchError, load_ledger, save_ledger
from helpers import TmpRoot, quick_brief_obs, quick_screen_obs, quick_volume_obs, setup_quick

ON = "2026-10-20"
WATCH_VOL = dict(anchor_volume=9900, new_mean=50.0, anchor_mean=99.0)     # 约 5,000 月搜索量 → 基准 1,000


class SettleQuickTest(unittest.TestCase):
    def test_go_initialises_follow_up_and_doc(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            rec = S.settle(root, slug, "go", None, "首页没人做,量够", "新域名多久能排上去", on=ON)
            self.assertEqual(rec["follow_up"]["status"], "pending")
            self.assertEqual(rec["follow_up"]["launch_by"], "2026-10-27")
            self.assertEqual(rec["model"]["scenarios"]["base"]["visits"], 10000)
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn("## 立即建站", md)
            self.assertIn("## 第二部分 最小版本建站简报", md)
            self.assertEqual(V.check_all(root, on=ON), [])

    def test_go_needs_brief_and_fast_build(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root, brief=False)
            with self.assertRaisesRegex(BenchError, "quick_brief"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            L.update(root, slug, {}, [W.write(root, quick_brief_obs(slug, build_days=5))])
            with self.assertRaisesRegex(BenchError, "3 天"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            self.assertIsNone(load_ledger(root)["directions"][slug]["decision"])

    def test_spike_refuses_go_and_allows_oneoff(self):
        with TmpRoot() as root:
            spike = quick_volume_obs("gag2-calculator", series=[0] * 10 + [100] + [5] * 19)
            slug, _ = setup_quick(root, volume=spike)
            with self.assertRaisesRegex(BenchError, "冲高回落"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            rec = S.settle(root, slug, "rejected", "oneoff", "冲高回落", "u", on=ON)
            self.assertEqual(rec["state"], "rejected")

    def test_watching_then_go(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root, volume=quick_volume_obs("gag2-calculator", **WATCH_VOL))
            with self.assertRaisesRegex(BenchError, "不到 1 万"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            rec = S.settle(root, slug, "watching", None, "量还不够,在涨", "能不能涨到 5 万", on=ON)
            self.assertEqual(rec["watch"]["expires_at"], "2026-11-19")
            self.assertEqual(V.check_all(root, on=ON), [])
            ref = W.write(root, quick_volume_obs(slug))                  # 复查时量涨到 5 万
            chk = L.watch_check(root, slug, [ref], on="2026-10-27")
            self.assertEqual(chk["suggestion"], "go")
            S.settle(root, slug, "go", None, "涨够了", "u", on="2026-10-27")
            self.assertEqual(len(list((root / "文档" / "历史").glob(f"{slug}-*.md"))), 1)
            self.assertEqual(V.check_all(root, on="2026-10-27"), [])

    def test_watching_expiry(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root, volume=quick_volume_obs("gag2-calculator", **WATCH_VOL))
            S.settle(root, slug, "watching", None, "r", "u", on=ON)
            with self.assertRaisesRegex(BenchError, "到期"):
                S.settle(root, slug, "rejected", "volume", "r", "u", on="2026-11-01")
            self.assertTrue(any("到期" in e for e in V.check_all(root, on="2026-11-20")))
            self.assertEqual(L.watch_check(root, slug, on="2026-11-19")["suggestion"], "rejected:volume")
            rec = S.settle(root, slug, "rejected", "volume", "30 天没涨够", "u", on="2026-11-19")
            self.assertEqual(rec["decision"]["gate"], "volume")
            self.assertEqual(V.check_all(root, on="2026-11-20"), [])

    def test_occupied_needs_failed_screen(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            with self.assertRaisesRegex(BenchError, "Q5"):
                S.settle(root, slug, "rejected", "occupied", "r", "u", on=ON)
            ref = W.write(root, quick_screen_obs(slug, term=f"{slug} term", fail={"Q5": False}, occupied_by="new-tool.com"))
            L.update(root, slug, {}, [ref])
            self.assertEqual(S.settle(root, slug, "rejected", "occupied", "有人做了", "u", on=ON)["state"], "rejected")

    def test_quick_gate_codes_only(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            with self.assertRaisesRegex(BenchError, "gate"):
                S.settle(root, slug, "rejected", "revenue", "r", "u", on=ON)


class FollowUpTest(unittest.TestCase):
    def test_only_forward(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            with self.assertRaisesRegex(BenchError, "前进"):
                L.follow_up(root, slug, "launched", on="2026-10-21")
            with self.assertRaisesRegex(BenchError, "域名"):
                L.follow_up(root, slug, "started", on="2026-10-21")
            L.follow_up(root, slug, "started", domain="gag2calc.com", on="2026-10-21")
            fu = L.follow_up(root, slug, "launched", on="2026-10-25")
            self.assertEqual((fu["status"], fu["launched_at"]), ("launched", "2026-10-25"))
            with self.assertRaisesRegex(BenchError, "理由"):
                L.follow_up(root, slug, "abandoned")
            self.assertEqual(V.check_all(root, on=ON), [])

    def test_dates_checked(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            with self.assertRaisesRegex(BenchError, "YYYY-MM-DD"):
                L.follow_up(root, slug, "started", domain="x.com", on="10/21")
            with self.assertRaisesRegex(BenchError, "早于"):
                L.follow_up(root, slug, "started", domain="x.com", on="2026-10-19")
            L.follow_up(root, slug, "started", domain="x.com", on="2026-10-22")
            with self.assertRaisesRegex(BenchError, "早于"):
                L.follow_up(root, slug, "launched", on="2026-10-21")

    def test_validate_catches_tampered_quick_model(self):
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            ledger = load_ledger(root)
            ledger["directions"][slug]["model"]["scenarios"]["base"]["visits"] = 99999
            save_ledger(root, ledger)
            self.assertTrue(any("快道模型重算" in e for e in V.check_all(root, on=ON)))


if __name__ == "__main__":
    unittest.main()
