import contextlib
import io
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import helpers as H
import quick_reference as QR
import write_observation as W
from _common import BenchError

ANCHOR = "map seed"


def series(term, start, n, term_vals, anchor_vals, anchor=ANCHOR):
    """xinciTrends 形状的曲线:从 start 起逐日 n 天,term_vals/anchor_vals 是 日期 → 值 的函数。"""
    days = [(date.fromisoformat(start) + timedelta(days=i)).isoformat() for i in range(n)]
    return {"geo": "US", "terms": [term, anchor], "time": f"{days[0]} {days[-1]}",
            "url": f"https://trends.google.com/trends/explore?date={days[0]}%20{days[-1]}&geo=US&q={term}",
            "dates": days, "values": [[term_vals(d), anchor_vals(d)] for d in days]}


def payload(**over):
    obj = series("Game A", "2026-06-22", 69, lambda d: 50, lambda d: 50)          # 对象名窗口比值 1.0
    task = series("game a map", "2026-06-22", 69, lambda d: 5, lambda d: 50)      # 任务词比值 0.1
    return {"object": "Game A", "category": "mmo_gacha", "task": "map", "task_term": "game a map",
            "playable_at": "2026-07-01", "anchor_term": ANCHOR, "anchor_volume": 10000,
            "anchor_source": "lexicon", "object_series": obj, "task_series": task, **over}


class WindowTest(unittest.TestCase):
    def test_time_range(self):
        self.assertEqual(QR.time_range("2026-07-01", "2026-10-16"), "2026-06-22 2026-08-29")
        self.assertEqual(QR.time_range("2026-10-01", "2026-10-16"), "2026-09-22 2026-10-15")

    def test_time_range_refuses_bad_dates(self):
        for play, on in (("2026-13-01", "2026-10-16"), ("2026-07-01", "2026-10-32"), ("2026-10-16", "2026-10-01")):
            with self.subTest(play=play, on=on), self.assertRaises(BenchError):
                QR.time_range(play, on)

    def test_window_ratio(self):
        s = series("x", "2026-06-22", 10, lambda d: 5, lambda d: 50)
        self.assertEqual(QR.window_ratio(s["dates"], s["values"], "2026-06-22", "2026-06-28"), 0.1)
        with self.assertRaises(BenchError):       # 窗口超出曲线:缺日期
            QR.window_ratio(s["dates"], s["values"], "2026-06-25", "2026-07-05")
        z = series("x", "2026-06-22", 10, lambda d: 5, lambda d: 0)
        with self.assertRaises(BenchError):       # 锚词均值为 0
            QR.window_ratio(z["dates"], z["values"], "2026-06-22", "2026-06-28")

    def test_best_window_picks_highest_14_days(self):
        # 开玩日 07-01 起 60 天;任务词在 07-20..08-02 这 14 天是 10,其余 2;锚词恒 50
        s = series("game a map", "2026-06-22", 69, lambda d: 10 if "2026-07-20" <= d <= "2026-08-02" else 2, lambda d: 50)
        w = QR.best_task_window(s["dates"], s["values"], "2026-07-01")
        self.assertEqual((w["window"], w["ratio"], w["full_60_days"]), (["2026-07-20", "2026-08-02"], 0.2, True))

    def test_best_window_ignores_days_after_60(self):
        # 开玩后第 60 天之后的高峰不算
        s = series("x", "2026-06-22", 80, lambda d: 90 if d > "2026-08-29" else 5, lambda d: 50)
        w = QR.best_task_window(s["dates"], s["values"], "2026-07-01")
        self.assertEqual((w["window"], w["ratio"]), (["2026-07-01", "2026-07-14"], 0.1))

    def test_ties_take_earliest_and_short_series_not_full(self):
        s = series("x", "2026-09-22", 24, lambda d: 5, lambda d: 50)          # 开玩后只有 15 天
        w = QR.best_task_window(s["dates"], s["values"], "2026-10-01")
        self.assertEqual((w["window"][0], w["full_60_days"]), ("2026-10-01", False))

    def test_under_14_days_refused(self):
        s = series("x", "2026-09-22", 20, lambda d: 5, lambda d: 50)          # 开玩后 11 天
        with self.assertRaises(BenchError):
            QR.best_task_window(s["dates"], s["values"], "2026-10-01")

    def test_weekly_series_refused(self):
        s = series("x", "2026-06-22", 69, lambda d: 5, lambda d: 50)
        s["dates"], s["values"] = s["dates"][::7], s["values"][::7]
        with self.assertRaises(BenchError):
            QR.best_task_window(s["dates"], s["values"], "2026-07-01")

    def test_curve_must_start_by_playable_day(self):
        s = series("x", "2026-07-05", 60, lambda d: 5, lambda d: 50)          # 曲线从开玩日之后才开始
        with self.assertRaises(BenchError):
            QR.best_task_window(s["dates"], s["values"], "2026-07-01")

    def test_anchor_zero_in_best_window_refused(self):
        s = series("x", "2026-06-22", 69, lambda d: 5, lambda d: 0)
        with self.assertRaises(BenchError):
            QR.best_task_window(s["dates"], s["values"], "2026-07-01")


class BuildTest(unittest.TestCase):
    def test_build_valid_observation(self):
        obs = QR.build_observation(payload(), at="2026-10-16T08:00:00+00:00")
        W.validate(obs)
        self.assertEqual((obs["readings"]["r"], obs["readings"]["object_volume_pre"]), (0.1, 10000))
        self.assertEqual(len(obs["source_urls"]), 2)
        self.assertEqual((obs["kind"], obs["stage"], obs["slug"], obs["semrush_calls"]), ("quick_reference", "quick", None, 0))
        self.assertEqual(obs["readings"]["object_window"], ["2026-06-22", "2026-06-28"])
        self.assertEqual((obs["readings"]["task_window"], obs["readings"]["full_60_days"]),
                         (["2026-07-01", "2026-07-14"], True))
        self.assertTrue(obs["points"])

    def test_semrush_calls_and_default_time(self):
        obs = QR.build_observation(payload(semrush_calls=2))
        self.assertEqual(obs["semrush_calls"], 2)
        self.assertTrue(obs["observed_at"].startswith("20"))

    def test_object_unreadable_refused(self):
        p = payload(object_series=series("Game A", "2026-06-22", 69, lambda d: 0, lambda d: 50))
        with self.assertRaisesRegex(BenchError, "读不出"):
            QR.build_observation(p, at="2026-10-16T08:00:00+00:00")

    def test_series_terms_must_match(self):
        with self.assertRaises(BenchError):
            QR.build_observation(payload(anchor_term="other anchor"), at="2026-10-16T08:00:00+00:00")
        with self.assertRaises(BenchError):
            QR.build_observation(payload(task_term="game a codes"), at="2026-10-16T08:00:00+00:00")

    def test_series_must_be_us(self):
        p = payload()
        p["task_series"]["geo"] = "GB"
        with self.assertRaises(BenchError):
            QR.build_observation(p, at="2026-10-16T08:00:00+00:00")

    def test_missing_key_and_bad_anchor_volume_refused(self):
        p = payload()
        del p["task"]
        with self.assertRaisesRegex(BenchError, "task"):
            QR.build_observation(p, at="2026-10-16T08:00:00+00:00")
        with self.assertRaises(BenchError):
            QR.build_observation(payload(anchor_volume="10000"), at="2026-10-16T08:00:00+00:00")

    def test_validator_still_applies(self):
        with self.assertRaises(BenchError):       # 观察日太早:任务词窗口还没走完
            QR.build_observation(payload(), at="2026-07-10T08:00:00+00:00")
        with self.assertRaises(BenchError):       # 类别不在清单里
            QR.build_observation(payload(category="puzzle"), at="2026-10-16T08:00:00+00:00")


class LibraryTest(unittest.TestCase):
    def test_quantiles(self):
        self.assertEqual(QR.quantiles([0.1, 0.2, 0.3]), (0.15, 0.2))
        self.assertEqual(QR.quantiles([0.1, 0.2, 0.3, 0.4]), (0.175, 0.25))
        self.assertEqual(QR.quantiles([0.3, 0.1, 0.2]), (0.15, 0.2))              # 与输入顺序无关
        self.assertEqual(QR.quantiles([0.2]), (0.2, 0.2))
        with self.assertRaises(BenchError):
            QR.quantiles([])

    def test_rates_scope_fallback_and_shortage(self):
        with H.TmpRoot() as root:
            for i, (cat, r) in enumerate([("mmo_gacha", 0.1), ("mmo_gacha", 0.2), ("roblox", 0.3)]):
                W.write(root, H.reference_obs(object=f"Game {i}", category=cat, task_ratio=r))
            lib = QR.load_library(root)
            got = QR.rates(lib, "map", "mmo_gacha")
            self.assertEqual((got["scope"], got["references"], got["r_p25"], got["r_median"]), ("task_type", 3, 0.15, 0.2))
            self.assertEqual(len(got["reference_refs"]), 3)
            self.assertIsNone(QR.rates(lib, "build", "mmo_gacha"))
            W.write(root, H.reference_obs(object="Game 9", category="mmo_gacha", task_ratio=0.3))
            got = QR.rates(QR.load_library(root), "map", "mmo_gacha")
            self.assertEqual((got["scope"], got["references"]), ("category", 3))

    def test_library_keeps_latest_per_object_task(self):
        with H.TmpRoot() as root:
            W.write(root, H.reference_obs(object="Game A", task_ratio=0.1, observed_at="2026-10-01T08:00:00+00:00"))
            W.write(root, H.reference_obs(object="game  a", task_ratio=0.3, observed_at="2026-10-16T08:00:00+00:00"))
            W.write(root, H.reference_obs(object="Game A", task="codes", task_ratio=0.5))
            lib = QR.load_library(root)
            self.assertEqual(sorted((x["task"], x["r"]) for x in lib), [("codes", 0.5), ("map", 0.3)])
            self.assertTrue(all(x["ref"].startswith("证据/_quick/") and x["observed_at"] for x in lib))

    def test_load_library_empty(self):
        with H.TmpRoot() as root:
            self.assertEqual(QR.load_library(root), [])

    def test_check_refs_refuses_mismatch(self):
        with H.TmpRoot() as root:
            refs = [W.write(root, H.reference_obs(object=f"Game {i}", task_ratio=r)) for i, r in enumerate((0.1, 0.2, 0.3))]
            got = QR.check_refs(root, refs, "map", "mmo_gacha", "category")
            self.assertEqual((got["r_p25"], got["r_median"], got["references"], got["scope"]), (0.15, 0.2, 3, "category"))
            self.assertEqual(got["reference_refs"], sorted(refs))
            for bad in (refs[:2], refs + [refs[0]]):
                with self.subTest(len(bad)), self.assertRaises(BenchError):
                    QR.check_refs(root, bad, "map", "mmo_gacha", "category")
            with self.assertRaises(BenchError):
                QR.check_refs(root, refs, "build", "mmo_gacha", "category")
            with self.assertRaises(BenchError):       # 类别不符:按 category 算不行,按 task_type 可以
                QR.check_refs(root, refs, "map", "roblox", "category")
            self.assertEqual(QR.check_refs(root, refs, "map", "roblox", "task_type")["scope"], "task_type")
            with self.assertRaises(BenchError):
                QR.check_refs(root, refs, "map", "mmo_gacha", "everything")

    def test_check_refs_refuses_non_reference_and_duplicate_object(self):
        with H.TmpRoot() as root:
            refs = [W.write(root, H.reference_obs(object=f"Game {i}", task_ratio=0.1 * (i + 1))) for i in range(3)]
            signal = W.write(root, H.quick_signal_obs())
            with self.assertRaises(BenchError):       # 不是参照观察
                QR.check_refs(root, refs[:2] + [signal], "map", "mmo_gacha", "category")
            with self.assertRaises(BenchError):       # 路径不存在
                QR.check_refs(root, refs[:2] + ["证据/_quick/not-there.json"], "map", "mmo_gacha", "category")
            dup = W.write(root, H.reference_obs(object="game  0", task_ratio=0.9))       # 同一对象换个写法
            with self.assertRaises(BenchError):
                QR.check_refs(root, refs + [dup], "map", "mmo_gacha", "category")


class CliTest(unittest.TestCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = QR.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_time_range(self):
        code, out, _ = self.run_cli(["time-range", "--playable-at", "2026-07-01", "--on", "2026-10-16"])
        self.assertEqual((code, out.strip()), (0, "2026-06-22 2026-08-29"))
        code, _, err = self.run_cli(["time-range", "--playable-at", "2026-13-01"])
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("拒收:"))

    def test_build_dry_run_summary_and_refusal(self):
        with H.TmpRoot() as root:
            src, quick_dir = root / "payload.json", root / "证据" / "_quick"
            src.write_text(json.dumps(payload(), ensure_ascii=False), encoding="utf-8")
            # build --dry-run:返回 0、不写文件、输出里有 r
            code, out, _ = self.run_cli(["--data-root", str(root), "build", "--input", str(src), "--dry-run"])
            self.assertEqual(code, 0)
            self.assertEqual(list(quick_dir.glob("*")), [])
            self.assertEqual(json.loads(out)["readings"]["r"], 0.1)
            # summary 在空库上返回 0、打印空列表
            code, out, _ = self.run_cli(["--data-root", str(root), "summary"])
            self.assertEqual((code, json.loads(out)), (0, []))
            # 缺 task 的 payload 拒收:退出码 1、stderr 以"拒收:"开头、不写文件
            bad = {k: v for k, v in payload().items() if k != "task"}
            src.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            code, _, err = self.run_cli(["--data-root", str(root), "build", "--input", str(src)])
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("拒收:"))
            self.assertEqual(list(quick_dir.glob("*")), [])
            # 不是对象的 JSON 也按拒收处理
            src.write_text("[]", encoding="utf-8")
            code, _, err = self.run_cli(["--data-root", str(root), "build", "--input", str(src)])
            self.assertEqual(code, 1)

    def test_build_writes_then_summary_lists(self):
        with H.TmpRoot() as root:
            src = root / "payload.json"
            for i in range(3):
                p = payload(object=f"Game {i}", task_term=f"game {i} map")
                p["object_series"]["terms"][0] = f"Game {i}"
                p["task_series"]["terms"][0] = f"game {i} map"
                src.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
                code, out, _ = self.run_cli(["--data-root", str(root), "build", "--input", str(src)])
                self.assertEqual(code, 0)
                got = json.loads(out)
                self.assertEqual((got["r"], got["任务词窗口"], got["满 60 天"]), (0.1, ["2026-07-01", "2026-07-14"], True))
                self.assertTrue(got["写入"].startswith("证据/_quick/"))
                self.assertTrue((root / got["写入"]).is_file())
            code, out, _ = self.run_cli(["--data-root", str(root), "summary", "--task", "map"])
            rows = json.loads(out)
            self.assertEqual((code, len(rows)), (0, 1))
            self.assertEqual((rows[0]["任务类型"], rows[0]["类别"], rows[0]["条数"], rows[0]["下四分位"], rows[0]["中位数"]),
                             ("map", "mmo_gacha", 3, 0.1, 0.1))
            code, out, _ = self.run_cli(["--data-root", str(root), "summary", "--category", "roblox"])
            self.assertEqual((code, json.loads(out)), (0, []))


if __name__ == "__main__":
    unittest.main()
