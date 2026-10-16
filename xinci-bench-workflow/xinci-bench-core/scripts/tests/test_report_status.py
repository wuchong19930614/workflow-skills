import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import helpers as H
import ledger as L
import quick_pool
import report_status as RS
import settle
import write_observation as W
from helpers import TmpRoot, setup_direction, task_volume
from test_quick_pregame import two_task_go


class ReportStatusTest(unittest.TestCase):
    def test_counts_go_and_parked(self):
        with TmpRoot() as root:
            setup_direction(root, slug="good")
            settle.settle(root, "good", "go", None, "r", "u", on="2026-10-20")
            setup_direction(root, slug="later")
            settle.settle(root, "later", "parked", None, "曲线读不出", "u", on="2026-10-20")
            st = RS.status(root, on="2027-02-01")
            self.assertEqual(st["counts"], {"found": 0, "go": 1, "rejected": 0, "parked": 1, "watching": 0})
            self.assertEqual(st["go"][0]["base_total"], 160.0)
            self.assertTrue(st["parked"][0]["overdue"])

    def test_empty_workspace(self):
        with TmpRoot() as root:
            st = RS.status(root)
            self.assertEqual(st["semrush_calls_total"], 0)
            self.assertEqual(st["found_ranked"], [])


class QuickStatusTest(unittest.TestCase):
    def test_upcoming_listed_with_run_window(self):
        import quick_pool
        with TmpRoot() as root:
            row = {"source": "wikipedia", "object": "Soon Game", "term": None, "url": "https://en.wikipedia.org/x",
                   "seen_at": "2026-10-14", "playable_at": "2026-10-20", "stage": "Early access"}
            quick_pool.add_items(root, [row], "证据/_quick/20261014T080000000000Z-abcd1234-quick_signal.json")
            q = RS.status(root, on="2026-10-14")["quick"]
            self.assertEqual(q["pool_pending"], 0)                    # 还没开玩,不算待看
            self.assertEqual(q["upcoming"], [{"object": "Soon Game", "stage": "Early access", "playable_at": "2026-10-20",
                                              "run_from": "2026-10-20", "run_to": "2026-10-23"}])


    def test_pending_go_on_top_and_milestones(self):
        import ledger
        from helpers import setup_quick
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            settle.settle(root, slug, "go", None, "r", "u", on="2026-10-20")
            q = RS.status(root, on="2026-10-28")["quick"]
            self.assertEqual(q["pending_go"][0]["slug"], slug)
            self.assertTrue(q["pending_go"][0]["overdue"])            # 建议 10-27 前上线
            ledger.follow_up(root, slug, "started", domain="x.com", on="2026-10-28")
            ledger.follow_up(root, slug, "launched", on="2026-11-01")
            q = RS.status(root, on="2026-12-01")["quick"]
            self.assertEqual(q["pending_go"], [])
            self.assertEqual([m["day"] for m in q["milestones_due"]], [14, 30])

    def test_banner_is_first_line_with_formatted_numbers(self):
        import contextlib
        import io
        from helpers import setup_quick
        with TmpRoot() as root:
            slug, _ = setup_quick(root)
            settle.settle(root, slug, "go", None, "r", "u")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                RS.main(["--data-root", str(root)])
            first = buf.getvalue().splitlines()[0]
            self.assertTrue(first.startswith(f"【立即建站】{slug}:基准约 10,000 次访问、$40.00/月"), first)



SIGNAL = "证据/_quick/20261013T080000000000Z-abcd1234-quick_signal.json"
OBJECT = "Monster Hunter Outlanders"


def pool_row(obj, playable_at, stage="Early access"):
    return {"source": "wikipedia", "object": obj, "term": None, "url": "https://en.wikipedia.org/x",
            "seen_at": "2026-10-13", "playable_at": playable_at, "stage": stage}


def go_forecast(root, **kw):
    """开玩前预判就判 go 的方向(开玩日 10-29,复核日 11-05,下四分位预测 90000)。"""
    slug, _ = H.setup_forecast(root, **kw)
    settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")
    return slug


def watching_forecast(root):
    slug, _ = H.setup_forecast(root, object_us=450000)
    settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
    return slug


def mho_reference(task, obj=OBJECT):
    """怪物猎人新作开玩后第 15 天写下的参照(开玩日 10-29,任务词窗口 10-30 到 11-12)。"""
    return H.reference_obs(object=obj, task=task, playable_at="2026-10-29", task_window=("2026-10-30", "2026-11-12"),
                           observed_at="2026-11-13T08:00:00+00:00")


def board(root, on):
    return RS.status(root, on=on)["quick"]


def cli_out(root, on):
    buf = io.StringIO()
    with mock.patch.object(RS, "today", return_value=on), contextlib.redirect_stdout(buf):
        RS.main(["--data-root", str(root)])
    return buf.getvalue()


class PregameStatusTest(unittest.TestCase):
    def test_window_lists_3_to_21_days(self):
        with TmpRoot() as root:
            rows = [pool_row("Too Soon", "2026-10-15"), pool_row("Edge Near", "2026-10-16"),
                    pool_row("Edge Far", "2026-11-03", stage="Open beta"), pool_row("Too Far", "2026-11-04")]
            quick_pool.add_items(root, rows, SIGNAL)
            q = board(root, "2026-10-13")
            self.assertEqual(q["forecast_window"],
                             [{"object": "Edge Near", "stage": "Early access", "playable_at": "2026-10-16", "days_ahead": 3},
                              {"object": "Edge Far", "stage": "Open beta", "playable_at": "2026-11-03", "days_ahead": 21}])
            self.assertEqual([u["object"] for u in q["upcoming"]], ["Too Soon", "Edge Near"])      # 即将开玩的原有口径(14 天内)不变

    def test_window_skips_used_and_already_playable(self):
        with TmpRoot() as root:
            quick_pool.add_items(root, [pool_row("Playing", "2026-10-13"), pool_row("Later", "2026-10-20")], SIGNAL)
            self.assertEqual([w["object"] for w in board(root, "2026-10-13")["forecast_window"]], ["Later"])
            quick_pool.consume(root, ["Later"])
            self.assertEqual(board(root, "2026-10-13")["forecast_window"], [])

    def test_review_due_and_warning(self):
        with TmpRoot() as root:
            slug = go_forecast(root)
            self.assertEqual(board(root, "2026-11-04")["forecast_reviews_due"], [])               # 复核日未到
            q = board(root, "2026-11-05")
            self.assertEqual(q["forecast_reviews_due"], [{"slug": slug, "state": "go", "review_at": "2026-11-05"}])
            self.assertTrue(q["pending_go"][0]["forecast"])
            ref = W.write(root, task_volume(slug, 10000))
            L.review_forecast(root, slug, [ref], on="2026-11-05")
            q = board(root, "2026-11-06")
            self.assertEqual((q["forecast_reviews_due"], q["forecast_warnings"]),
                             ([], [{"slug": slug, "actual": 10000, "forecast_p25": 90000}]))

    def test_review_that_does_not_stop_raises_no_warning(self):
        with TmpRoot() as root:
            slug = go_forecast(root)
            L.review_forecast(root, slug, [W.write(root, task_volume(slug, 30000))], on="2026-11-05")
            q = board(root, "2026-11-06")
            self.assertEqual((q["forecast_reviews_due"], q["forecast_warnings"]), ([], []))

    def test_abandoned_follow_up_drops_the_warning(self):
        with TmpRoot() as root:
            slug = go_forecast(root)
            L.review_forecast(root, slug, [W.write(root, task_volume(slug, 10000))], on="2026-11-05")
            self.assertEqual(len(board(root, "2026-11-06")["forecast_warnings"]), 1)
            L.follow_up(root, slug, "started", domain="mho-map.com", on="2026-11-06")
            self.assertEqual(len(board(root, "2026-11-06")["forecast_warnings"]), 1)              # 开建了还在提示
            L.follow_up(root, slug, "abandoned", reason="预判失准,停止投入", on="2026-11-06")
            self.assertEqual(board(root, "2026-11-06")["forecast_warnings"], [])

    def test_watching_review_due_until_first_check(self):
        with TmpRoot() as root:
            slug = watching_forecast(root)
            self.assertEqual(board(root, "2026-11-04")["forecast_reviews_due"], [])
            self.assertEqual(board(root, "2026-11-05")["forecast_reviews_due"],
                             [{"slug": slug, "state": "watching", "review_at": "2026-11-05"}])
            self.assertEqual(board(root, "2026-11-05")["pending_go"], [])
            screen = dict(H.quick_screen_obs(slug, term="mho map"), observed_at="2026-11-05T08:00:00+00:00")
            L.watch_check(root, slug, [W.write(root, screen), W.write(root, task_volume(slug, 30000))], on="2026-11-05")
            self.assertEqual(board(root, "2026-11-06")["forecast_reviews_due"], [])               # 复查过一次就不再催

    def test_watching_that_went_go_on_the_current_path_is_not_a_pregame_go(self):
        with TmpRoot() as root:
            slug = watching_forecast(root)
            screen = dict(H.quick_screen_obs(slug, term="mho map"), observed_at="2026-11-05T08:00:00+00:00")
            L.watch_check(root, slug, [W.write(root, screen), W.write(root, task_volume(slug, 60000))], on="2026-11-05")
            settle.settle(root, slug, "go", reason="开玩后量够了", biggest_unknown="热度", on="2026-11-05")
            q = board(root, "2026-11-06")
            self.assertEqual((q["pending_go"][0]["forecast"], q["forecast_reviews_due"]), (False, []))

    def test_current_path_and_found_directions_raise_nothing(self):
        with TmpRoot() as root:
            slug, _ = H.setup_quick(root)
            settle.settle(root, slug, "go", None, "r", "u", on="2026-10-14")
            H.setup_forecast(root)                                                 # 预判登记、还没结算:没有 forecast 块
            q = board(root, "2026-12-31")
            self.assertEqual([(g["slug"], g["forecast"]) for g in q["pending_go"]], [(slug, False)])
            for key in ("forecast_window", "forecast_reviews_due", "forecast_warnings", "forecast_slipped", "references_due"):
                self.assertEqual(q[key], [], key)

    def test_slipped_over_7_days(self):
        with TmpRoot() as root:
            slug = go_forecast(root)
            L.update(root, slug, {"object": {"first_public": "2026-11-05", "date_source": "https://example.org/delay"}},
                     on="2026-10-20")                                              # 顺延 7 天:不提醒
            self.assertEqual(board(root, "2026-10-21")["forecast_slipped"], [])
            L.update(root, slug, {"object": {"first_public": "2026-11-06", "date_source": "https://example.org/delay"}},
                     on="2026-10-21")                                              # 累计 8 天
            self.assertEqual(board(root, "2026-10-22")["forecast_slipped"],
                             [{"slug": slug, "first_public": "2026-11-06", "slipped_days": 8}])

    def test_slipped_watching_also_listed(self):
        with TmpRoot() as root:
            slug = watching_forecast(root)
            L.update(root, slug, {"object": {"first_public": "2026-11-12", "date_source": "https://example.org/delay"}},
                     on="2026-10-20")
            self.assertEqual(board(root, "2026-10-21")["forecast_slipped"],
                             [{"slug": slug, "first_public": "2026-11-12", "slipped_days": 14}])

    def test_references_due(self):
        with TmpRoot() as root:
            go_forecast(root)                                                      # 开玩日 10-29,参照库里没有 Monster Hunter Outlanders
            self.assertEqual(board(root, "2026-11-11")["references_due"], [])
            self.assertEqual(board(root, "2026-11-12")["references_due"],
                             [{"object": OBJECT, "task": "map", "action": "add", "due": "2026-11-12"}])
            W.write(root, mho_reference("map"))
            self.assertEqual(board(root, "2026-11-13")["references_due"], [])             # 补上之后不再提醒

    def test_references_due_add_is_one_row_per_task(self):
        with TmpRoot() as root:
            two_task_go(root)                                                      # 任务 map 与 codes
            self.assertEqual(board(root, "2026-11-12")["references_due"],
                             [{"object": OBJECT, "task": "codes", "action": "add", "due": "2026-11-12"},
                              {"object": OBJECT, "task": "map", "action": "add", "due": "2026-11-12"}])
            W.write(root, mho_reference("map", obj=OBJECT.lower()))                # 对象名按规范化比,大小写不同也算有了
            self.assertEqual(board(root, "2026-11-13")["references_due"],
                             [{"object": OBJECT, "task": "codes", "action": "add", "due": "2026-11-12"}])

    def test_references_due_add_covers_a_watching_direction(self):
        with TmpRoot() as root:
            watching_forecast(root)
            self.assertEqual(board(root, "2026-11-12")["references_due"],
                             [{"object": OBJECT, "task": "map", "action": "add", "due": "2026-11-12"}])

    def test_references_due_add_follows_a_slipped_playable_day(self):
        with TmpRoot() as root:
            slug = go_forecast(root)
            L.update(root, slug, {"object": {"first_public": "2026-11-12", "date_source": "https://example.org/delay"}},
                     on="2026-10-20")
            self.assertEqual(board(root, "2026-11-12")["references_due"], [])             # 原来的第 14 天(11-12)已不是
            self.assertEqual(board(root, "2026-11-26")["references_due"],
                             [{"object": OBJECT, "task": "map", "action": "add", "due": "2026-11-26"}])

    def test_references_due_update(self):
        with TmpRoot() as root:
            W.write(root, H.reference_obs(object="Wardogs", category="open_world_survival", task="map",
                                          playable_at="2026-08-22", task_window=("2026-08-26", "2026-09-08"),
                                          observed_at="2026-10-16T08:00:00+00:00"))          # 开玩后不满 60 天就写下的参照
            self.assertEqual(board(root, "2026-10-20")["references_due"], [])
            self.assertEqual(board(root, "2026-10-21")["references_due"],
                             [{"object": "Wardogs", "task": "map", "action": "update", "due": "2026-10-21"}])
            W.write(root, H.reference_obs(object="Wardogs", category="open_world_survival", task="map",
                                          playable_at="2026-08-22", task_window=("2026-08-26", "2026-09-08"),
                                          observed_at="2026-10-22T08:00:00+00:00"))          # 满 60 天后更新:full_60_days 为真
            self.assertEqual(board(root, "2026-10-22")["references_due"], [])

    def test_full_references_are_never_due_for_update(self):
        with TmpRoot() as root:
            H.write_references(root)                                               # 开玩日 07-01、观察日 10-16:已满 60 天
            self.assertEqual(board(root, "2026-12-31")["references_due"], [])

    def test_cli_prints_pregame_lines(self):
        with TmpRoot() as root:
            go_forecast(root)
            quick_pool.add_items(root, [pool_row("Next Game", "2026-11-10")], SIGNAL)
            out = cli_out(root, "2026-11-05")
            self.assertIn("可预判 Next Game:2026-11-10,还有 5 天(每轮最多预判 2 个)", out)
            self.assertIn("复核到期 mho-map:2026-11-05,测任务词的量后跑 ledger.py review-forecast(观察中的跑 watch-check)", out)
            self.assertTrue(out.splitlines()[0].startswith("【立即建站】mho-map(开玩前预判):基准约 "), out.splitlines()[0])
            self.assertNotIn("预判失准", out)
            self.assertNotIn("开玩日推迟", out)
            self.assertNotIn("补参照", out)

    def test_cli_prints_stop_slip_and_reference_lines(self):
        with TmpRoot() as root:
            slug = go_forecast(root)
            L.review_forecast(root, slug, [W.write(root, task_volume(slug, 10000))], on="2026-11-05")
            out = cli_out(root, "2026-11-12")
            self.assertIn("预判失准 mho-map:实测 10000 / 预测 90000,建议停止追加投入", out)
            self.assertIn(f"补参照 {OBJECT} map", out)
            self.assertNotIn("复核到期", out)

    def test_cli_prints_slip_and_update_lines(self):
        with TmpRoot() as root:
            slug = go_forecast(root)
            L.update(root, slug, {"object": {"first_public": "2026-11-12", "date_source": "https://example.org/delay"}},
                     on="2026-10-20")
            W.write(root, H.reference_obs(object="Wardogs", category="open_world_survival", task="map",
                                          playable_at="2026-08-22", task_window=("2026-08-26", "2026-09-08")))
            out = cli_out(root, "2026-10-21")
            self.assertIn("开玩日推迟 mho-map:累计 14 天,现为 2026-11-12,请重新评估", out)
            self.assertIn("更新参照 Wardogs map", out)

    def test_json_output_has_the_five_keys(self):
        with TmpRoot() as root:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                RS.main(["--data-root", str(root), "--json"])
            q = json.loads(buf.getvalue())["quick"]
            for key in ("forecast_window", "forecast_reviews_due", "forecast_warnings", "forecast_slipped", "references_due"):
                self.assertEqual(q[key], [], key)


class SemrushTodayLineTest(unittest.TestCase):
    def test_board_shows_today_usage(self):
        import contextlib
        import io
        with TmpRoot() as root:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                RS.main(["--data-root", str(root)])
            self.assertIn("今天 Semrush 已用 0/100 次", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
