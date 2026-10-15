import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_pool as P
from _common import LEDGER_REL, SEEDS_REL, VERDICTS_REL, BenchError, load_json
from helpers import TmpRoot, write_json

OBS = "证据/_quick/20261013T080000000000Z-abcd1234-quick_signal.json"
OBS2 = "证据/_quick/20261014T080000000000Z-ef567890-quick_signal.json"


def item(term, seen="2026-10-13"):
    return {"source": "autocomplete", "object": "Grow a Garden 2", "term": term,
            "url": "https://suggestqueries.google.com/x", "seen_at": seen}


class QuickPoolTest(unittest.TestCase):
    def test_add_and_dedup(self):
        with TmpRoot() as root:
            out = P.add_items(root, [item("Grow A Garden 2  Calculator"), item("grow a garden 2 calculator")], OBS)
            self.assertEqual(len(out["added"]), 1)
            self.assertEqual(out["skipped"][0]["reason"], "已在原料池")
            self.assertEqual(len(P.pending(root)), 1)

    def test_skip_rejected_existing_and_old_verdicts(self):
        with TmpRoot() as root:
            P.reject_term(root, "old news term", "oneoff", "证据/q/x.json")
            write_json(root / LEDGER_REL, {"schema_version": 1, "directions": {"gag2": {"lane": "quick", "terms": [
                {"term": "gag2 term", "source": "autocomplete", "first_seen": "2026-10-13"}]}}})
            write_json(root / VERDICTS_REL, {"schema_version": 1, "candidates": {
                "tide-chart": {"primary_keyword": "tide chart", "state": "parked", "gate": None, "reason": "x"}}})
            out = P.add_items(root, [item("old news term"), item("gag2 term"), item("tide chart"), item("fresh one")], OBS)
            self.assertEqual([r["term"] for r in out["added"]], ["fresh one"])
            reasons = {s["term"]: s["reason"] for s in out["skipped"]}
            self.assertIn("快道淘汰过", reasons["old news term"])
            self.assertIn("已有方向 gag2", reasons["gag2 term"])
            self.assertIn("旧裁决 tide-chart", reasons["tide chart"])

    def test_object_only_items_dedup_by_object(self):
        with TmpRoot() as root:
            obj = {"source": "steamcharts", "object": "New Game", "term": None,
                   "url": "https://steamcharts.com/top", "seen_at": "2026-10-13"}
            out = P.add_items(root, [obj, dict(obj, object="NEW  game")], OBS)
            self.assertEqual((len(out["added"]), out["skipped"][0]["reason"]), (1, "已在原料池"))

    def test_same_batch_second_source_recorded(self):
        with TmpRoot() as root:
            out = P.add_items(root, [dict(item("dup term"), source="trends_rising", rising=300), item("Dup  Term")], OBS)
            self.assertEqual(len(out["added"]), 1)
            row = P.pending(root)[0]
            self.assertEqual([a["source"] for a in row["also_seen"]], ["autocomplete"])   # 同一批里第二个来源也记下

    def test_upcoming_held_until_playable(self):
        with TmpRoot() as root:
            soon = {"source": "wikipedia", "object": "Soon Game", "term": None, "url": "https://en.wikipedia.org/x",
                    "seen_at": "2026-10-14", "playable_at": "2026-10-20", "stage": "Early access"}
            far = dict(soon, object="Far Game", playable_at="2026-11-30")
            P.add_items(root, [soon, far, item("live term", seen="2026-10-14")], OBS)
            self.assertEqual([r["term"] for r in P.pending(root, on="2026-10-14")], ["live term"])
            up = P.upcoming(root, on="2026-10-14")
            self.assertEqual([(r["object"], r["playable_at"], r["stage"]) for r in up],
                             [("Soon Game", "2026-10-20", "Early access")])      # 14 天以外的不列
            self.assertEqual([r["object"] for r in P.upcoming(root, on="2026-10-14", days=60)], ["Soon Game", "Far Game"])
            self.assertIn("Soon Game", [r["object"] for r in P.pending(root, on="2026-10-20")])

    def test_upcoming_expiry_counts_from_playable_at(self):
        with TmpRoot() as root:
            row = {"source": "trends_rising", "object": "Beta Game", "term": None, "url": "https://trends.google.com/x",
                   "seen_at": "2026-10-01", "playable_at": "2026-10-20", "rising": "breakout"}
            P.add_items(root, [row], OBS)
            self.assertEqual(P.expire(root, on="2026-10-27"), [])               # 开玩后第 7 天还留着
            self.assertEqual(len(P.expire(root, on="2026-10-28")), 1)

    def test_new_sighting_updates_playable_at(self):
        with TmpRoot() as root:
            row = {"source": "wikipedia", "object": "Delayed Game", "term": None, "url": "https://en.wikipedia.org/x",
                   "seen_at": "2026-10-13", "playable_at": "2026-10-20", "stage": "Original"}
            P.add_items(root, [row], OBS)
            P.add_items(root, [dict(row, source="trends_rising", seen_at="2026-10-14", playable_at="2026-11-03",
                                    stage="closed beta")], OBS2)
            up = P.upcoming(root, on="2026-10-14", days=30)
            self.assertEqual((up[0]["playable_at"], up[0]["stage"]), ("2026-11-03", "closed beta"))   # 以最新看到的为准

    def test_pending_priority(self):
        with TmpRoot() as root:
            P.add_items(root, [dict(item(None), object="Only Object"), item("plain term", seen="2026-10-10"),
                               dict(item("hot term"), rising=300), dict(item("breakout term"), rising="breakout"),
                               item("multi term", seen="2026-10-12")], OBS)
            out = P.add_items(root, [dict(item("Multi  Term"), source="trends_rising")], OBS2)
            self.assertEqual(out["skipped"][0]["reason"], "已在原料池")
            order = [r["term"] or r["object"] for r in P.pending(root)]
            # 有说法 > 来源多 > 飙升幅度(breakout 最大) > 先看到的;只有对象的排最后
            self.assertEqual(order, ["multi term", "breakout term", "hot term", "plain term", "Only Object"])
            self.assertEqual([a["source"] for a in P.pending(root)[0]["also_seen"]], ["trends_rising"])
            self.assertEqual(len(P.pending(root, top=2)), 2)

    def test_expire_after_seven_days(self):
        with TmpRoot() as root:
            P.add_items(root, [item("a", seen="2026-10-01"), item("b", seen="2026-10-12")], OBS)
            self.assertEqual(len(P.expire(root, on="2026-10-13")), 1)
            self.assertEqual([r["term"] for r in P.pending(root)], ["b"])

    def test_expired_item_can_come_back(self):
        with TmpRoot() as root:
            P.add_items(root, [item("slow riser", seen="2026-10-01")], OBS)
            P.expire(root, on="2026-10-13")
            out = P.add_items(root, [item("slow riser", seen="2026-10-20")], OBS)
            self.assertEqual(len(out["added"]), 1)
            self.assertEqual([(r["term"], r["seen_at"]) for r in P.pending(root)], [("slow riser", "2026-10-20")])

    def test_reject_consumes_pending_item(self):
        with TmpRoot() as root:
            P.add_items(root, [item("gag2 calculator")], OBS)
            P.reject_term(root, "GAG2  Calculator", "occupied", "证据/q/x.json")
            self.assertEqual(P.pending(root), [])
            out = P.add_items(root, [item("gag2 calculator")], OBS)
            self.assertIn("快道淘汰过", out["skipped"][0]["reason"])

    def test_mark(self):
        with TmpRoot() as root:
            row = P.add_items(root, [item("a")], OBS)["added"][0]
            P.mark(root, [row["id"]], "used")
            self.assertEqual(P.pending(root), [])
            with self.assertRaisesRegex(BenchError, "没有"):
                P.mark(root, ["nope"], "used")

    def test_reject_gate_checked(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "gate"):
                P.reject_term(root, "x", "revenue", "证据/q/x.json")

    def test_occupied_small_site_becomes_bench_seed(self):
        with TmpRoot() as root:
            P.reject_term(root, "gag2 calculator", "occupied", "证据/q/x.json", seed_domain="https://www.GAG2calc.com/")
            seed = load_json(root / SEEDS_REL)["seeds"]["gag2calc.com"]
            self.assertEqual((seed["source"], seed["role"]), ("serp", "benchmark"))
            self.assertIn("gag2 calculator", seed["source_ref"])
            with self.assertRaisesRegex(BenchError, "occupied"):
                P.reject_term(root, "other", "scope", "证据/q/y.json", seed_domain="z.com")

    def test_needs_signal_observation(self):
        with TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "quick_signal"):
                P.add_items(root, [item("a")], "证据/q/x.json")


if __name__ == "__main__":
    unittest.main()
