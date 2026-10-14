import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import write_observation as W
from _common import BenchError
from helpers import OBJ, TmpRoot, quick_screen_obs, setup_direction, setup_quick

ON = "2026-10-20"


def term(slug):
    return [{"term": f"{slug} term", "source": "autocomplete", "first_seen": "2026-10-13"}]


class RegisterQuickTest(unittest.TestCase):
    def test_needs_all_six_pass(self):
        with TmpRoot() as root:
            ref = W.write(root, quick_screen_obs("q", term="q term", fail={"Q5": False}, occupied_by="x.com"))
            with self.assertRaisesRegex(BenchError, "六条"):
                L.register_quick(root, "q", "t", "tool", dict(OBJ), term("q"), ref, "r")

    def test_object_must_be_new(self):
        with TmpRoot() as root:
            ref = W.write(root, quick_screen_obs("q", term="q term"))
            old = dict(OBJ, type="other", first_public="2026-06-01")
            with self.assertRaisesRegex(BenchError, "90 天"):
                L.register_quick(root, "q", "t", "tool", old, term("q"), ref, "r")
            future = dict(OBJ, first_public="2026-11-01")
            with self.assertRaisesRegex(BenchError, "未来"):
                L.register_quick(root, "q", "t", "tool", future, term("q"), ref, "r")

    def test_game_window_is_14_days(self):
        with TmpRoot() as root:                                   # 速判观察日 2026-10-13
            ref = W.write(root, quick_screen_obs("q", term="q term"))
            with self.assertRaisesRegex(BenchError, "14 天"):
                L.register_quick(root, "q", "t", "tool", dict(OBJ, first_public="2026-09-28"), term("q"), ref, "r")
            app = dict(OBJ, type="other", first_public="2026-09-28")          # 非游戏仍按 90 天
            rec = L.register_quick(root, "q", "t", "tool", app, term("q"), ref, "r")
            self.assertEqual(rec["object"]["type"], "other")
        with TmpRoot() as root:
            ref = W.write(root, quick_screen_obs("q", term="q term"))
            rec = L.register_quick(root, "q", "t", "tool", dict(OBJ, first_public="2026-09-29"), term("q"), ref, "r")
            self.assertEqual(rec["object"]["type"], "game")                   # 第 14 天还算

    def test_object_type_required(self):
        with TmpRoot() as root:
            ref = W.write(root, quick_screen_obs("q", term="q term"))
            bare = {k: v for k, v in OBJ.items() if k != "type"}
            with self.assertRaisesRegex(BenchError, "type"):
                L.register_quick(root, "q", "t", "tool", bare, term("q"), ref, "r")
            with self.assertRaisesRegex(BenchError, "type"):
                L.register_quick(root, "q", "t", "tool", dict(OBJ, type="movie"), term("q"), ref, "r")

    def test_term_cannot_belong_to_two_directions(self):
        with TmpRoot() as root:
            setup_quick(root, slug="a")
            ref = W.write(root, quick_screen_obs("b", term="a term"))
            with self.assertRaisesRegex(BenchError, "已属于方向 a"):
                L.register_quick(root, "b", "t", "tool", dict(OBJ), term("a"), ref, "r")

    def test_term_match_ignores_case_and_spaces(self):
        with TmpRoot() as root:
            setup_quick(root, slug="a")
            ref = W.write(root, quick_screen_obs("b", term="A  Term"))
            loud = [{"term": "A  Term", "source": "autocomplete", "first_seen": "2026-10-13"}]
            with self.assertRaisesRegex(BenchError, "已属于方向 a"):
                L.register_quick(root, "b", "t", "tool", dict(OBJ), loud, ref, "r")

    def test_screen_must_be_about_a_registered_term(self):
        with TmpRoot() as root:
            ref = W.write(root, quick_screen_obs("b", term="something else"))
            with self.assertRaisesRegex(BenchError, "速判的词"):
                L.register_quick(root, "b", "t", "tool", dict(OBJ), term("b"), ref, "r")

    def test_update_terms_cannot_clash(self):
        with TmpRoot() as root:
            setup_quick(root, slug="a")
            setup_quick(root, slug="b")
            with self.assertRaisesRegex(BenchError, "已属于方向 a"):
                L.update(root, "b", {"terms": term("b") + [{"term": "A term", "source": "autocomplete",
                                                            "first_seen": "2026-10-13"}]})
            L.update(root, "b", {"terms": term("b") + [{"term": "b extra", "source": "autocomplete",
                                                        "first_seen": "2026-10-13"}]})

    def test_register_consumes_pool_items(self):
        import quick_pool
        with TmpRoot() as root:
            item = {"source": "autocomplete", "object": "Grow a Garden 2", "term": "gag2-calculator term",
                    "url": "https://suggestqueries.google.com/x", "seen_at": "2026-10-13"}
            quick_pool.add_items(root, [item], "证据/_quick/x-quick_signal.json")
            setup_quick(root)
            self.assertEqual(quick_pool.pending(root), [])

    def test_rank_and_update_by_lane(self):
        with TmpRoot() as root:
            setup_direction(root, slug="bench-one")
            slug, _ = setup_quick(root)
            self.assertEqual([r["slug"] for r in L.rank(root, on=ON)], ["bench-one"])
            with self.assertRaisesRegex(BenchError, "不可补"):
                L.update(root, slug, {"benchmarks": []})


if __name__ == "__main__":
    unittest.main()
