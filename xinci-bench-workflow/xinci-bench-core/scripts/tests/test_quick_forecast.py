import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import helpers as H
import quick_forecast as QF
import quick_model as QM
import trends_volume as TV
import write_observation as W
from _common import BenchError

AT = "2026-10-13T08:00:00+00:00"
OBJECT = "Monster Hunter Outlanders"
SLUG = "mho-map"


def setup(root, term=OBJECT, slug=SLUG, **volume):
    """写三条参照(map、mmo_gacha、倍数 0.1/0.2/0.3)与对象名量级观察(美国 600000),返回量级观察路径。"""
    H.write_references(root)
    return W.write(root, H.quick_volume_obs(slug, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0, term=term,
                                            **volume))


class BuildForecastTest(unittest.TestCase):
    def test_go_forecast(self):
        with H.TmpRoot() as root:
            vref = setup(root)
            obs = QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT)
            W.validate(obs)
            r = obs["readings"]
            self.assertEqual((r["forecast_p25"], r["forecast_median"], r["suggestion"]), (90000, 120000, "go"))
            t = r["tasks"][0]
            self.assertEqual((t["r_p25"], t["r_median"], t["references"], t["scope"]), (0.15, 0.2, 3, "category"))
            self.assertEqual((r["object_volume_pre"], r["skipped_geos"]), ({"US": 600000}, []))

    def test_observation_shape_and_rates_come_straight_from_library(self):
        with H.TmpRoot() as root:
            vref = setup(root)
            decoys = [W.write(root, H.reference_obs(object=f"Roblox Game {i}", category="roblox", task_ratio=0.9))
                      for i in range(3)]                                                    # 别的类别的参照,不该混进来
            obs = QF.build_observation(root, H.forecast_payload(volume_ref=vref, tasks=[
                {"task": "map", "terms": ["mho map", "mho interactive map"]}]), at=AT)
            self.assertEqual((obs["kind"], obs["stage"], obs["slug"], obs["observed_at"]), ("quick_forecast", "quick", SLUG, AT))
            r, t = obs["readings"], obs["readings"]["tasks"][0]
            self.assertEqual(sorted(t), ["r_median", "r_p25", "reference_refs", "references", "scope", "task", "terms"])
            self.assertEqual(t["terms"], ["mho map", "mho interactive map"])
            self.assertEqual((len(t["reference_refs"]), t["r_p25"]), (3, 0.15))
            self.assertFalse(set(t["reference_refs"]) & set(decoys))
            self.assertTrue(all(p.startswith("证据/_quick/") and p.endswith("-quick_reference.json") for p in t["reference_refs"]))
            self.assertEqual(t["reference_refs"], sorted(t["reference_refs"]))
            self.assertEqual((r["object"], r["category"], r["playable_at"], r["date_source"], r["object_volume_ref"]),
                             (OBJECT, "mmo_gacha", "2026-10-29", "https://example.org/mho", vref))
            self.assertEqual(list(r["checks"]), ["P1", "P2", "P3", "P4", "P5", "P6"])
            self.assertTrue(r["checks"]["P3"]["pass"] and r["checks"]["P3"]["basis"])
            self.assertEqual(obs["browser_preflight"], H.PREFLIGHT)
            self.assertEqual((obs["semrush_calls"], obs["source_urls"]), (0, ["https://example.org/mho"]))
            self.assertTrue(obs["points"])

    def test_task_type_scope_when_category_short(self):
        with H.TmpRoot() as root:
            H.write_references(root, category="roblox")
            vref = W.write(root, H.quick_volume_obs(SLUG, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0, term=OBJECT))
            obs = QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT)
            W.validate(obs)
            t = obs["readings"]["tasks"][0]
            self.assertEqual((t["scope"], t["references"], t["r_p25"]), ("task_type", 3, 0.15))

    def test_several_tasks_add_up(self):
        with H.TmpRoot() as root:
            vref = setup(root)
            H.write_references(root, rs=(0.02, 0.04, 0.06), task="tier_list")
            tasks = [{"task": "map", "terms": ["mho map"]}, {"task": "tier_list", "terms": ["mho tier list"]}]
            obs = QF.build_observation(root, H.forecast_payload(volume_ref=vref, tasks=tasks), at=AT)
            W.validate(obs)
            r = obs["readings"]
            # 600000 × (0.15 + 0.03) = 108000;600000 × (0.2 + 0.04) = 144000
            self.assertEqual((r["forecast_p25"], r["forecast_median"], r["suggestion"]), (108000, 144000, "go"))
            self.assertEqual([t["task"] for t in r["tasks"]], ["map", "tier_list"])

    def test_references_short_fails_p3(self):
        with H.TmpRoot() as root:
            vref = setup(root)
            p = H.forecast_payload(volume_ref=vref, tasks=[{"task": "calculator", "terms": ["mho calculator"]}])
            obs = QF.build_observation(root, p, at=AT)
            W.validate(obs)
            r = obs["readings"]
            self.assertEqual((r["checks"]["P3"]["pass"], r["suggestion"], r["forecast_p25"]), (False, "skip", None))
            self.assertIn("参照不足", r["checks"]["P3"]["basis"])
            self.assertIn("calculator", r["checks"]["P3"]["basis"])
            self.assertEqual((r["forecast_median"], r["object_volume_pre"]), (None, None))
            t = r["tasks"][0]
            self.assertEqual((t["task"], t["terms"], t["r_p25"], t["r_median"], t["references"], t["reference_refs"], t["scope"]),
                             ("calculator", ["mho calculator"], None, None, None, [], None))

    def test_one_short_task_fails_p3_for_all(self):
        with H.TmpRoot() as root:
            vref = setup(root)
            tasks = [{"task": "map", "terms": ["mho map"]}, {"task": "calculator", "terms": ["mho calculator"]}]
            r = QF.build_observation(root, H.forecast_payload(volume_ref=vref, tasks=tasks), at=AT)["readings"]
            self.assertEqual((r["checks"]["P3"]["pass"], r["suggestion"], r["forecast_p25"]), (False, "skip", None))
            self.assertIn("calculator", r["checks"]["P3"]["basis"])
            self.assertTrue(all(t["r_p25"] is None and t["reference_refs"] == [] for t in r["tasks"]))

    def test_input_check_failure_nulls_numbers(self):
        with H.TmpRoot() as root:
            vref = setup(root)
            p = H.forecast_payload(volume_ref=vref)
            p["checks"]["P5"] = {"pass": False, "basis": "测试期已有专做本作的 wiki"}
            obs = QF.build_observation(root, p, at=AT)
            W.validate(obs)
            r = obs["readings"]
            self.assertEqual((r["checks"]["P5"]["pass"], r["checks"]["P3"]["pass"]), (False, True))
            self.assertEqual((r["suggestion"], r["forecast_p25"], r["forecast_median"], r["object_volume_pre"]),
                             ("skip", None, None, None))
            self.assertEqual((r["tasks"][0]["r_p25"], r["tasks"][0]["reference_refs"]), (None, []))
            self.assertTrue(any("P5" in x for x in obs["points"]))

    def test_unqueried_checks_stay_null_after_a_failure(self):
        with H.TmpRoot() as root:
            H.write_references(root)
            p = H.forecast_payload()
            p["checks"] = {"P1": {"pass": False, "basis": "开玩日还没公布"}, "P2": {"pass": None, "basis": "前项不过,没查"},
                           "P4": {"pass": None, "basis": "前项不过,没查"}, "P5": {"pass": None, "basis": "前项不过,没查"},
                           "P6": {"pass": None, "basis": "前项不过,没查"}}
            p["serp"] = []
            del p["browser_preflight"]
            obs = QF.build_observation(root, p, at=AT)
            r = obs["readings"]
            self.assertEqual((r["suggestion"], r["object_volume_ref"], r["object_volume_pre"], r["serp"]), ("skip", None, None, []))
            self.assertNotIn("browser_preflight", obs)

    def test_executor_p3_failure_is_kept(self):
        with H.TmpRoot() as root:
            vref = setup(root)
            p = H.forecast_payload(volume_ref=vref)
            p["checks"]["P3"] = {"pass": False, "basis": "这项任务是一次性的"}
            r = QF.build_observation(root, p, at=AT)["readings"]
            self.assertEqual((r["checks"]["P3"], r["suggestion"]), ({"pass": False, "basis": "这项任务是一次性的"}, "skip"))
            p["checks"]["P3"] = {"pass": True, "basis": "手填的依据不算数"}               # 手填通过不作数,由脚本按参照库重算
            r = QF.build_observation(root, p, at=AT)["readings"]
            self.assertNotEqual(r["checks"]["P3"]["basis"], "手填的依据不算数")
            self.assertEqual(r["suggestion"], "go")

    def test_skipped_geos_need_measure_rest(self):
        # 其他 5 国用 trends_volume 的"未查:"行 → complete=False → measure_rest
        with H.TmpRoot() as root:
            H.write_references(root)
            vol = H.quick_volume_obs(SLUG, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0, term=OBJECT)
            for c in vol["readings"]["countries"]:
                if not c["readable"]:
                    c["basis"] = f"{TV.SKIPPED_PREFIX}429 限流"
            vref = W.write(root, vol)
            obs = QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT)
            W.validate(obs)
            r = obs["readings"]
            self.assertEqual(r["skipped_geos"], ["GB", "CA", "AU", "NZ", "IE"])
            self.assertEqual(r["object_volume_pre"], {"US": 600000})
            self.assertEqual((r["forecast_p25"], r["forecast_median"], r["suggestion"]), (90000, 120000, "measure_rest"))

    def test_readable_and_skipped_and_unreadable_mixed(self):
        with H.TmpRoot() as root:
            H.write_references(root)
            vol = H.quick_volume_obs(SLUG, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0, term=OBJECT,
                                     others={"GB": (100000, 50.0, 50.0)})
            for c in vol["readings"]["countries"]:
                if c["geo"] == "AU":
                    c["basis"] = f"{TV.SKIPPED_PREFIX}429 限流"          # 其余读不出的(CA、NZ、IE)是 Trends 全为 0,不算没查
            vref = W.write(root, vol)
            r = QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT)["readings"]
            self.assertEqual((r["object_volume_pre"], r["skipped_geos"]), ({"US": 600000, "GB": 100000}, ["AU"]))
            # 700000 × 0.15 = 105000;700000 × 0.2 = 140000;没测完 → measure_rest
            self.assertEqual((r["forecast_p25"], r["forecast_median"], r["suggestion"]), (105000, 140000, "measure_rest"))

    def test_us_only_below_half_threshold_is_skip_with_numbers(self):
        # 只测了美国且中位数基准 < 1 万 × 50%:不再测其他 5 国,suggestion 为 skip,但六条都过、数字照留
        with H.TmpRoot() as root:
            H.write_references(root)
            vol = H.quick_volume_obs(SLUG, anchor_volume=100000, new_mean=50.0, anchor_mean=50.0, term=OBJECT)
            for c in vol["readings"]["countries"]:
                if not c["readable"]:
                    c["basis"] = f"{TV.SKIPPED_PREFIX}美国单国已不到门槛一半"
            vref = W.write(root, vol)
            obs = QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT)
            W.validate(obs)
            r = obs["readings"]
            self.assertTrue(all(c["pass"] is True for c in r["checks"].values()))
            self.assertEqual((r["forecast_p25"], r["forecast_median"], r["suggestion"]), (15000, 20000, "skip"))

    def test_watching_when_only_median_passes(self):
        with H.TmpRoot() as root:
            H.write_references(root)
            vref = W.write(root, H.quick_volume_obs(SLUG, anchor_volume=500000, new_mean=50.0, anchor_mean=50.0, term=OBJECT))
            r = QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT)["readings"]
            # 500000 × 0.15 = 75000 → 基准 9000 < 1 万;500000 × 0.2 = 100000 → 基准 12000 ≥ 1 万
            self.assertEqual((r["forecast_p25"], r["forecast_median"], r["suggestion"]), (75000, 100000, "watching"))

    def test_object_volume_term_normalized(self):
        # 量级观察 term="monster  hunter OUTLANDERS" 也认
        with H.TmpRoot() as root:
            vref = setup(root, term="monster  hunter OUTLANDERS")
            obs = QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT)
            W.validate(obs)
            self.assertEqual((obs["readings"]["suggestion"], obs["readings"]["object"]), ("go", OBJECT))

    def test_object_volume_other_object_refused(self):
        # 量级观察 term="Other Game" → BenchError;量级观察属于别的 slug → BenchError
        with H.TmpRoot() as root:
            other_term = setup(root, term="Other Game")
            with self.assertRaisesRegex(BenchError, "term"):
                QF.build_observation(root, H.forecast_payload(volume_ref=other_term), at=AT)
            other_slug = W.write(root, H.quick_volume_obs("other-game", anchor_volume=600000, new_mean=50.0,
                                                          anchor_mean=50.0, term=OBJECT))
            with self.assertRaisesRegex(BenchError, "slug|方向"):
                QF.build_observation(root, H.forecast_payload(volume_ref=other_slug), at=AT)

    def test_object_volume_without_term_or_wrong_kind_refused(self):
        with H.TmpRoot() as root:
            H.write_references(root)
            no_term = W.write(root, H.quick_volume_obs(SLUG, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0))
            with self.assertRaisesRegex(BenchError, "term"):
                QF.build_observation(root, H.forecast_payload(volume_ref=no_term), at=AT)
            screen = W.write(root, H.quick_screen_obs(SLUG))
            with self.assertRaisesRegex(BenchError, "quick_volume"):
                QF.build_observation(root, H.forecast_payload(volume_ref=screen), at=AT)
            with self.assertRaises(BenchError):
                QF.build_observation(root, H.forecast_payload(volume_ref=f"证据/{SLUG}/not-there.json"), at=AT)

    def test_object_volume_lag(self):
        # 对象名量须在预判当天或之前 forecast_volume_max_lag_days(2)天内测,按日期比;晚于预判也拒收
        lag = QM.QUICK_ASSUMPTIONS["forecast_volume_max_lag_days"]
        self.assertEqual(lag, 2)
        cases = (("2026-10-13T23:00:00+00:00", None), ("2026-10-11T08:00:00+00:00", None),
                 ("2026-10-10T08:00:00+00:00", "早 3 天"), ("2026-10-14T08:00:00+00:00", "晚于预判"))
        for observed_at, refusal in cases:
            with self.subTest(observed_at), H.TmpRoot() as root:
                vref = setup(root, observed_at=observed_at)
                if refusal is None:
                    obs = QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT)
                    self.assertEqual(obs["readings"]["suggestion"], "go")
                else:
                    with self.assertRaisesRegex(BenchError, refusal):
                        QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT)

    def test_all_pass_without_volume_ref_refused(self):
        with H.TmpRoot() as root:
            H.write_references(root)
            with self.assertRaisesRegex(BenchError, "object_volume_ref"):
                QF.build_observation(root, H.forecast_payload(volume_ref=None), at=AT)

    def test_bad_payload_refused(self):
        with H.TmpRoot() as root:
            vref = setup(root)
            p = H.forecast_payload(volume_ref=vref)
            del p["serp"]
            with self.assertRaisesRegex(BenchError, "serp"):
                QF.build_observation(root, p, at=AT)
            with self.assertRaises(BenchError):
                QF.build_observation(root, [], at=AT)
            p = H.forecast_payload(volume_ref=vref)
            del p["checks"]["P6"]
            with self.assertRaisesRegex(BenchError, "P6"):
                QF.build_observation(root, p, at=AT)
            with self.assertRaises(BenchError):          # 任务类型不合规
                QF.build_observation(root, H.forecast_payload(volume_ref=vref, tasks=[{"task": "Tier List", "terms": ["x"]}]), at=AT)
            with self.assertRaises(BenchError):          # 开玩日不在 3–21 天内,P1 却写了通过
                QF.build_observation(root, H.forecast_payload(volume_ref=vref, playable_at="2026-12-01"), at=AT)

    def test_default_time_is_now(self):
        with H.TmpRoot() as root:
            H.write_references(root)
            p = H.forecast_payload()
            p["checks"]["P1"] = {"pass": False, "basis": "开玩日还没公布"}
            obs = QF.build_observation(root, p)
            self.assertTrue(obs["observed_at"].startswith("20"))


class ForecastValidationTest(unittest.TestCase):
    def test_valid_hand_written_observation(self):
        W.validate(H.forecast_obs())

    def test_playable_window_boundaries(self):
        for day, ok in (("2026-10-15", False), ("2026-10-16", True), ("2026-11-03", True), ("2026-11-04", False)):
            obs = H.forecast_obs(playable_at=day)        # 观察日 2026-10-13,P1 判过
            with self.subTest(day):
                if ok:
                    W.validate(obs)
                else:
                    self.assertRaises(BenchError, W.validate, obs)

    def test_window_not_checked_when_p1_fails(self):
        obs = H.forecast_obs(playable_at="2027-03-01")
        r = obs["readings"]
        r["checks"]["P1"] = {"pass": False, "basis": "开玩日太远"}
        r.update(suggestion="skip", forecast_p25=None, forecast_median=None, object_volume_pre=None, object_volume_ref=None)
        W.validate(obs)

    def test_refusals(self):
        bad = {
            "few_refs": lambda r: r["tasks"][0].update(references=2, reference_refs=r["tasks"][0]["reference_refs"][:2]),
            "p25_gt_median": lambda r: r["tasks"][0].update(r_p25=0.3),
            "total": lambda r: r.update(forecast_p25=95000),
            "suggestion": lambda r: r.update(suggestion="watching"),
            "p2_us_zero": lambda r: r.update(object_volume_pre={"US": 0, "GB": 600000}, forecast_p25=90000),
            "five_tasks": lambda r: r.update(tasks=r["tasks"] * 5),
            "no_wiki_serp": lambda r: r.update(serp=[{"query": "mho map", "top10": []}, {"query": "mho tier list", "top10": []}]),
            "fail_not_skip": lambda r: r["checks"].update(P5={"pass": False, "basis": "占位"}),   # 有不过项时 suggestion 须为 skip
        }
        for name, mutate in bad.items():
            obs = H.forecast_obs()
            mutate(obs["readings"])
            with self.subTest(name), self.assertRaises(BenchError):
                W.validate(obs)

    def test_refusal_reasons(self):
        # 同一批用例各自拒收的原因:不能靠别的毛病蒙混过关
        bad = {
            "few_refs": (lambda r: r["tasks"][0].update(references=2, reference_refs=r["tasks"][0]["reference_refs"][:2]), "参照"),
            "refs_count_mismatch": (lambda r: r["tasks"][0].update(references=4), "reference_refs"),
            "duplicate_refs": (lambda r: r["tasks"][0].update(reference_refs=r["tasks"][0]["reference_refs"][:1] * 3), "重复"),
            "p25_gt_median": (lambda r: r["tasks"][0].update(r_p25=0.3), "r_p25"),
            "negative_rate": (lambda r: r["tasks"][0].update(r_p25=-0.1), "r_p25"),
            "bad_scope": (lambda r: r["tasks"][0].update(scope="everything"), "scope"),
            "total": (lambda r: r.update(forecast_p25=95000), "forecast_p25"),
            "median_total": (lambda r: r.update(forecast_median=130000), "forecast_median"),
            "suggestion": (lambda r: r.update(suggestion="watching"), "suggestion"),
            "unknown_suggestion": (lambda r: r.update(suggestion="maybe"), "suggestion"),
            "p2_us_zero": (lambda r: r.update(object_volume_pre={"US": 0, "GB": 600000}, forecast_p25=90000), "美国"),
            "no_us": (lambda r: r.update(object_volume_pre={"GB": 600000}), "美国"),
            "non_en_geo": (lambda r: r.update(object_volume_pre={"US": 600000, "DE": 1}), "英文区"),
            "volume_ref": (lambda r: r.update(object_volume_ref=None), "object_volume_ref"),
            "skipped_has_us": (lambda r: r.update(skipped_geos=["US"]), "skipped_geos"),
            "skipped_overlaps": (lambda r: r.update(object_volume_pre={"US": 500000, "GB": 100000}, skipped_geos=["GB"]), "skipped_geos"),
            "skipped_not_en": (lambda r: r.update(skipped_geos=["DE"]), "skipped_geos"),
            "five_tasks": (lambda r: r.update(tasks=r["tasks"] * 5), "1–4"),
            "no_tasks": (lambda r: r.update(tasks=[]), "1–4"),
            "duplicate_task": (lambda r: r.update(tasks=r["tasks"] * 2), "重复"),
            "bad_task_type": (lambda r: r["tasks"][0].update(task="Tier List"), "task"),
            "empty_terms": (lambda r: r["tasks"][0].update(terms=[]), "terms"),
            "no_wiki_serp": (lambda r: r.update(serp=[{"query": "mho map", "top10": []}, {"query": "mho tier list", "top10": []}]), "wiki"),
            "one_serp": (lambda r: r.update(serp=r["serp"][1:]), "两条"),
            "serp_no_top10": (lambda r: r["serp"][0].pop("top10"), "top10"),
            "fail_not_skip": (lambda r: r["checks"].update(P5={"pass": False, "basis": "占位"}), "skip"),
            "bad_category": (lambda r: r.update(category="puzzle"), "category"),
            "bad_date": (lambda r: r.update(playable_at="2026-13-01"), "playable_at"),
            "no_date_source": (lambda r: r.update(date_source=" "), "date_source"),
            "null_without_failure": (lambda r: r["checks"].update(P6={"pass": None, "basis": "没查"}), "null"),
            "missing_check": (lambda r: r["checks"].pop("P3"), "checks"),
        }
        for name, (mutate, needle) in bad.items():
            obs = H.forecast_obs()
            mutate(obs["readings"])
            with self.subTest(name), self.assertRaisesRegex(BenchError, needle):
                W.validate(obs)

    def test_failed_check_allows_nulls(self):
        obs = H.forecast_obs()
        obs["readings"].update(checks={**obs["readings"]["checks"], "P5": {"pass": False, "basis": "已有 wiki"}},
                               object_volume_pre=None, object_volume_ref=None, forecast_p25=None,
                               forecast_median=None, suggestion="skip")
        W.validate(obs)

    def test_failed_check_needs_skip_even_with_nulls(self):
        obs = H.forecast_obs()
        obs["readings"].update(checks={**obs["readings"]["checks"], "P3": {"pass": False, "basis": "参照不足"}},
                               object_volume_pre=None, object_volume_ref=None, forecast_p25=None,
                               forecast_median=None, suggestion="go")
        self.assertRaises(BenchError, W.validate, obs)

    def test_p5_needs_preflight(self):
        obs = H.forecast_obs()
        del obs["browser_preflight"]
        self.assertRaises(BenchError, W.validate, obs)

    def test_p5_without_conclusion_needs_no_preflight_or_serp(self):
        obs = H.forecast_obs()
        r = obs["readings"]
        del obs["browser_preflight"]
        r["checks"].update(P2={"pass": False, "basis": "对象名开玩前读不出"}, P5={"pass": None, "basis": "前项不过,没查"},
                           P6={"pass": None, "basis": "前项不过,没查"})
        r.update(serp=[], suggestion="skip", forecast_p25=None, forecast_median=None, object_volume_pre=None,
                 object_volume_ref=None)
        W.validate(obs)

    def test_failed_preflight_refused(self):
        obs = H.forecast_obs()
        obs["browser_preflight"]["logged_out"] = False
        self.assertRaises(BenchError, W.validate, obs)

    def test_slug_must_be_real_and_kind_is_per_direction(self):
        obs = H.forecast_obs()
        obs["slug"] = None
        self.assertRaises(BenchError, W.validate, obs)
        self.assertIn("quick_forecast", W.QUICK_KINDS)
        self.assertEqual(W.FORECAST_CHECKS, ("P1", "P2", "P3", "P4", "P5", "P6"))

    def test_written_under_slug_folder(self):
        with H.TmpRoot() as root:
            ref = W.write(root, H.forecast_obs())
            self.assertTrue(ref.startswith(f"证据/{SLUG}/") and ref.endswith("-quick_forecast.json"))
            self.assertEqual(W.read(root, ref)["readings"]["suggestion"], "go")


class ForecastParamsTest(unittest.TestCase):
    def test_forecast_written_with_current_params(self):
        r = H.forecast_obs()["readings"]
        self.assertEqual(r["params"], {"forecast_days": [3, 21], "min_references": 3, "threshold_visits": 10000,
                                       "share_base": 0.2, "aio_factor": 0.6, "us_only_cutoff": 0.5})
        self.assertEqual(r["params"], QM.forecast_params())
        self.assertEqual(r["assumptions_version"], QM.QUICK_ASSUMPTIONS["version"])
        with H.TmpRoot() as root:
            vref = setup(root)
            failing = dict(H.forecast_payload(volume_ref=None),                            # 有不过项,只记观察
                           checks={**H.forecast_payload()["checks"], "P4": {"pass": False, "basis": "x"}})
            for payload in (H.forecast_payload(volume_ref=vref), failing):                 # 六条全过 / 只记观察
                r = QF.build_observation(root, payload, at=AT)["readings"]
                self.assertEqual(r["params"], QM.forecast_params())
                self.assertEqual(r["assumptions_version"], QM.QUICK_ASSUMPTIONS["version"])

    def test_write_refuses_made_up_params(self):
        for key, value in (("min_references", 2), ("threshold_visits", 5000), ("us_only_cutoff", 0.4),
                           ("forecast_days", [1, 30])):
            obs = H.forecast_obs()
            obs["readings"]["params"][key] = value
            with self.subTest(key), self.assertRaisesRegex(BenchError, "口径"):
                W.validate(obs)

    def test_read_forecast_after_threshold_change(self):
        with H.TmpRoot() as root:
            ref = W.write(root, H.forecast_obs())
            with mock.patch.dict(QM.QUICK_ASSUMPTIONS, {"threshold_visits": 5000}):
                self.assertEqual(W.read(root, ref)["readings"]["suggestion"], "go")

    def test_read_checks_suggestion_by_own_params(self):
        # 现行门槛抬到 2 万:这份 go 按新门槛是 skip,但读回按它自己写的 1 万校验,照样读得进来;现在再写同样的观察就拒收
        with H.TmpRoot() as root:
            obs = H.forecast_obs()
            ref = W.write(root, obs)
            with mock.patch.dict(QM.QUICK_ASSUMPTIONS, {"threshold_visits": 20000}):
                self.assertEqual(W.read(root, ref)["readings"]["suggestion"], "go")
                with self.assertRaisesRegex(BenchError, "口径与当前假设表不一致"):
                    W.write(root, obs)

    def test_read_checks_reference_count_and_lead_by_own_params(self):
        with H.TmpRoot() as root:
            ref = W.write(root, H.forecast_obs())                      # 观察日 10-13,开玩日 10-29:提前 16 天、参照 3 条
            with mock.patch.dict(QM.QUICK_ASSUMPTIONS, {"min_references": 4, "forecast_days": (3, 10)}):
                self.assertEqual(W.read(root, ref)["readings"]["tasks"][0]["references"], 3)

    def test_params_survive_json_roundtrip(self):
        with H.TmpRoot() as root:
            ref = W.write(root, H.forecast_obs())
            self.assertEqual(W.read(root, ref)["readings"]["params"], QM.forecast_params())

    def test_validate_current_flag(self):
        obs = H.forecast_obs()
        task = obs["readings"]["tasks"][0]
        obs["readings"]["params"]["min_references"] = 2
        obs["readings"]["assumptions_version"] = "2026-09-01.old"
        task.update(references=2, reference_refs=task["reference_refs"][:2])
        W.validate(obs, current=False)
        with self.assertRaisesRegex(BenchError, "口径与当前假设表不一致"):
            W.validate(obs)

    def test_params_shape_refused(self):
        bad = {
            "missing_params": (lambda r: r.pop("params"), "缺字段"),
            "missing_version": (lambda r: r.pop("assumptions_version"), "缺字段"),
            "blank_version": (lambda r: r.update(assumptions_version=""), "assumptions_version"),
            "params_not_dict": (lambda r: r.update(params=None), "params"),
            "missing_key": (lambda r: r["params"].pop("aio_factor"), "params"),
            "extra_key": (lambda r: r["params"].update(task_days=14), "params"),
            "days_one_item": (lambda r: r["params"].update(forecast_days=[3]), "forecast_days"),
            "days_not_int": (lambda r: r["params"].update(forecast_days=[3, "21"]), "forecast_days"),
            "min_refs_zero": (lambda r: r["params"].update(min_references=0), "min_references"),
            "min_refs_bool": (lambda r: r["params"].update(min_references=True), "min_references"),
            "threshold_zero": (lambda r: r["params"].update(threshold_visits=0), "threshold_visits"),
            "threshold_text": (lambda r: r["params"].update(threshold_visits="10000"), "threshold_visits"),
            "share_over_one": (lambda r: r["params"].update(share_base=1.5), "share_base"),
            "aio_negative": (lambda r: r["params"].update(aio_factor=-0.1), "aio_factor"),
            "cutoff_over_one": (lambda r: r["params"].update(us_only_cutoff=2), "us_only_cutoff"),
            "cutoff_bool": (lambda r: r["params"].update(us_only_cutoff=True), "us_only_cutoff"),
        }
        for name, (mutate, reason) in bad.items():
            for current in (True, False):
                obs = H.forecast_obs()
                mutate(obs["readings"])
                with self.subTest(name, current=current), self.assertRaisesRegex(BenchError, reason):
                    W.validate(obs, current=current)

    def test_reference_with_changed_params_is_unusable(self):
        # 参照库里另一套口径的参照不混着算:跳过,写进"参照不可用"与观察的 points,倍数只按现行口径的 3 条算
        with H.TmpRoot() as root:
            vref = setup(root)
            old = H.write_stale_reference(root, object="Old Game", task_ratio=0.9)
            unusable = []
            obs = QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT, unusable=unusable)
            t = obs["readings"]["tasks"][0]
            self.assertEqual((t["r_p25"], t["r_median"], t["references"]), (0.15, 0.2, 3))
            self.assertNotIn(old, t["reference_refs"])
            self.assertEqual(unusable, [{"ref": old, "reason": "口径已变,需重测(写于 2026-09-01.old)"}])
            self.assertTrue(any("口径已变" in x and old in x for x in obs["points"]))


class CliTest(unittest.TestCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = QF.main(argv)
        return code, out.getvalue(), err.getvalue()

    def write_payload(self, root, payload):
        src = root / "payload.json"
        src.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return str(src)

    def dated_payload(self, root, **kw):
        """命令行的预判观察时间由脚本取 now(),所以日期都跟着今天走:对象名量级观察记在今天,
        开玩日 = 今天 + 10 天(在 3–21 天窗口内),哪天跑都不过期。"""
        day = QF.now()[:10]
        vref = setup(root, observed_at=f"{day}T00:00:00+00:00")
        return H.forecast_payload(volume_ref=vref, playable_at=QM.add_days(day, 10), **kw)

    def test_writes_and_prints_summary(self):
        with H.TmpRoot() as root:
            src = self.write_payload(root, self.dated_payload(root))
            code, out, _ = self.run_cli(["--data-root", str(root), "--input", src])
            self.assertEqual(code, 0)
            got = json.loads(out)
            self.assertTrue(got["写入"].startswith(f"证据/{SLUG}/") and got["写入"].endswith("-quick_forecast.json"))
            self.assertEqual((got["suggestion"], got["forecast_p25"], got["forecast_median"], got["下四分位基准访问"]),
                             ("go", 90000, 120000, 10800))
            obs = W.read(root, got["写入"])
            self.assertEqual(obs["readings"]["forecast_p25"], 90000)

    def test_dry_run_writes_nothing(self):
        with H.TmpRoot() as root:
            src = self.write_payload(root, self.dated_payload(root))
            before = sorted(p.name for p in (root / "证据" / SLUG).glob("*"))
            code, out, _ = self.run_cli(["--data-root", str(root), "--input", src, "--dry-run"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["readings"]["suggestion"], "go")
            self.assertEqual(sorted(p.name for p in (root / "证据" / SLUG).glob("*")), before)

    def test_failed_forecast_prints_nulls(self):
        with H.TmpRoot() as root:
            p = self.dated_payload(root, tasks=[{"task": "calculator", "terms": ["mho calculator"]}])
            code, out, _ = self.run_cli(["--data-root", str(root), "--input", self.write_payload(root, p)])
            got = json.loads(out)
            self.assertEqual((code, got["suggestion"], got["forecast_p25"], got["下四分位基准访问"]), (0, "skip", None, None))

    def test_bad_reference_is_skipped_and_reported(self):
        # 参照库里一条坏了:跳过它照常预判,输出的"参照不可用"与观察的 points 都写明跳过了哪条
        with H.TmpRoot() as root:
            src = self.write_payload(root, self.dated_payload(root))
            bad = W.write(root, H.reference_obs(object="Broken"))
            (root / bad).write_text("{not json", encoding="utf-8")
            code, out, _ = self.run_cli(["--data-root", str(root), "--input", src])
            self.assertEqual(code, 0)
            got = json.loads(out)
            self.assertEqual(([x["ref"] for x in got["参照不可用"]], got["suggestion"]), ([bad], "go"))
            self.assertTrue(any(bad in p for p in W.read(root, got["写入"])["points"]))
            code, out, _ = self.run_cli(["--data-root", str(root), "--input", src, "--dry-run"])
            self.assertTrue(any(bad in p for p in json.loads(out)["points"]))

    def test_no_bad_reference_reports_an_empty_list(self):
        with H.TmpRoot() as root:
            code, out, _ = self.run_cli(["--data-root", str(root), "--input", self.write_payload(root, self.dated_payload(root))])
            self.assertEqual((code, json.loads(out)["参照不可用"]), (0, []))

    def test_refusal_exits_1_and_writes_nothing(self):
        with H.TmpRoot() as root:
            vref = setup(root, term="Other Game")
            before = sorted((root / "证据").rglob("*.json"))
            src = self.write_payload(root, H.forecast_payload(volume_ref=vref))
            code, _, err = self.run_cli(["--data-root", str(root), "--input", src])
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("拒收:"))
            self.assertEqual(sorted((root / "证据").rglob("*.json")), before)
            src = self.write_payload(root, ["not", "an", "object"])
            code, _, err = self.run_cli(["--data-root", str(root), "--input", src])
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("拒收:"))


def h(observed, suggestion="skip", failed=None, playable="2026-10-29", tasks=("map",)):
    """一条预判历史条目(看板从预判观察整理出来的样子)。"""
    return {"observed_at": observed, "playable_at": playable, "suggestion": suggestion, "failed": failed,
            "tasks": list(tasks), "category": "mmo_gacha"}


def refs_lib(tasks=("map",), category="mmo_gacha", rs=(0.1, 0.2, 0.3)):
    """参照库(QR.load_library 返回的样子):每个任务 len(rs) 款不同游戏的参照。"""
    return [dict(H.reference_obs(object=f"G{i}", task=t, task_ratio=r, category=category)["readings"],
                 ref=f"证据/_quick/{t}-{i}.json", observed_at="2026-10-16T08:00:00+00:00")
            for t in tasks for i, r in enumerate(rs)]


class ReforecastTest(unittest.TestCase):
    def st(self, history, on, playable="2026-10-29", library=()):
        return QF.reforecast_status(history, playable, on, list(library))["reforecast"]

    def test_new_and_volume_skip_timeline(self):
        self.assertEqual(self.st([], "2026-10-14"), "new")
        early = [h("2026-10-13")]                                   # 开玩前 16 天做的,量不够
        self.assertEqual(self.st(early, "2026-10-19"), "wait")      # 开玩前 10 天
        self.assertEqual(self.st(early, "2026-10-20"), "due")       # 开玩前 9 天
        self.assertEqual(self.st(early, "2026-10-26"), "due")       # 开玩前 3 天
        self.assertEqual(self.st([h("2026-10-21")], "2026-10-22"), "no")    # 上次已在 9–3 天里做过

    def test_last_made_on_the_window_edges_counts_as_in_the_window(self):
        self.assertEqual(self.st([h("2026-10-20")], "2026-10-22"), "no")      # 开玩前 9 天做的:在窗口里
        self.assertEqual(self.st([h("2026-10-26")], "2026-10-26"), "no")      # 开玩前 3 天做的:在窗口里
        self.assertEqual(self.st([h("2026-10-19")], "2026-10-20"), "due")     # 开玩前 10 天做的:不在窗口里

    def test_past_the_window_is_no(self):
        # 开玩前不到 3 天:对象名窗口已经过了,再做也不是窗口里的量
        self.assertEqual(self.st([h("2026-10-13")], "2026-10-27"), "no")

    def test_max_two(self):
        # 两次都在 9–3 天窗口之外做的;没有上限的话这里会是 due
        self.assertEqual(self.st([h("2026-10-12"), h("2026-10-13")], "2026-10-20"), "no")

    def test_max_comes_from_the_assumptions(self):
        two = [h("2026-10-12"), h("2026-10-13")]
        looser = dict(QM.QUICK_ASSUMPTIONS, forecast_max_per_object=3)
        self.assertEqual(QF.reforecast_status(two, "2026-10-29", "2026-10-20", [], looser)["reforecast"], "due")
        self.assertEqual(QM.QUICK_ASSUMPTIONS["forecast_max_per_object"], 2)

    def test_measure_rest_not_counted(self):
        self.assertEqual(self.st([h("2026-10-13", "measure_rest")], "2026-10-13"), "due")
        self.assertEqual(self.st([h("2026-10-13", "measure_rest"), h("2026-10-13")], "2026-10-20"), "due")

    def test_measure_rest_is_due_at_once_whatever_the_window(self):
        self.assertEqual(self.st([h("2026-10-13", "measure_rest")], "2026-10-13"), "due")      # 开玩前 16 天,不等窗口
        self.assertEqual(self.st([h("2026-10-20", "measure_rest")], "2026-10-21"), "due")      # 上次在窗口里也照补

    def test_permanent_failures(self):
        for p in ("P4", "P5", "P6"):
            self.assertEqual(self.st([h("2026-10-13", failed=p)], "2026-10-20"), "no")
        self.assertEqual(self.st([h("2026-10-13", "go")], "2026-10-20"), "no")
        self.assertEqual(self.st([h("2026-10-13", "watching")], "2026-10-20"), "no")

    def test_p1_only_after_date_change(self):
        last = [h("2026-10-13", failed="P1")]
        self.assertEqual(self.st(last, "2026-10-20"), "no")
        self.assertEqual(self.st(last, "2026-10-20", playable="2026-11-05"), "due")

    def test_p3_waits_for_references(self):
        last = [h("2026-10-13", failed="P3")]
        self.assertEqual(self.st(last, "2026-10-14"), "wait")
        self.assertEqual(self.st(last, "2026-10-14", library=refs_lib()), "due")

    def test_p3_needs_every_task_to_have_rates(self):
        two_tasks = [h("2026-10-13", failed="P3", tasks=("map", "tier_list"))]
        self.assertEqual(self.st(two_tasks, "2026-10-14", library=refs_lib(("map",))), "wait")          # 库里只有 map
        self.assertEqual(self.st(two_tasks, "2026-10-14", library=refs_lib(("map", "tier_list"))), "due")

    def test_p3_falls_back_to_the_task_type_across_categories(self):
        # 同类别不够 3 条、同任务类型全部类别够 3 条,也算取得到倍数
        lib = refs_lib(rs=(0.1,), category="roblox") + refs_lib(rs=(0.2, 0.3), category="sports_racing_party")
        lib = [dict(x, object=f"G{i}") for i, x in enumerate(lib)]
        self.assertEqual(self.st([h("2026-10-13", failed="P3")], "2026-10-14", library=lib), "due")

    def test_p2_like_volume(self):
        self.assertEqual(self.st([h("2026-10-13", failed="P2")], "2026-10-20"), "due")
        self.assertEqual(self.st([h("2026-10-13", failed="P2")], "2026-10-19"), "wait")
        self.assertEqual(self.st([h("2026-10-21", failed="P2")], "2026-10-22"), "no")

    def test_only_the_last_one_decides(self):
        # 历史升序,最后一条是"上次":早先的原因不影响最后一次的结论(放宽次数上限,免得先撞上"已预判满")
        looser = dict(QM.QUICK_ASSUMPTIONS, forecast_max_per_object=5)
        def state(history):
            return QF.reforecast_status(history, "2026-10-29", "2026-10-20", [], looser)["reforecast"]
        self.assertEqual(state([h("2026-10-10", failed="P5"), h("2026-10-13")]), "due")
        self.assertEqual(state([h("2026-10-10"), h("2026-10-13", failed="P5")]), "no")
        self.assertEqual(state([h("2026-10-10", "go"), h("2026-10-13")]), "due")

    def test_reason_keywords(self):
        def reason(history, on, playable="2026-10-29", library=()):
            return QF.reforecast_status(history, playable, on, list(library))["reason"]
        self.assertIn("没预判过", reason([], "2026-10-14"))
        self.assertIn("已预判 2 次", reason([h("2026-10-12"), h("2026-10-13")], "2026-10-20"))
        self.assertIn("已登记", reason([h("2026-10-13", "go")], "2026-10-20"))
        self.assertIn("已登记", reason([h("2026-10-13", "watching")], "2026-10-20"))
        for p in ("P4", "P5", "P6"):
            self.assertIn(f"上次 {p} 不过", reason([h("2026-10-13", failed=p)], "2026-10-20"))
        self.assertIn("开玩日", reason([h("2026-10-13", failed="P1")], "2026-10-20"))
        self.assertNotIn("开玩日改了", reason([h("2026-10-13", failed="P1")], "2026-10-20"))
        self.assertIn("开玩日改了", reason([h("2026-10-13", failed="P1")], "2026-10-20", playable="2026-11-05"))
        self.assertIn("参照不足", reason([h("2026-10-13", failed="P3")], "2026-10-14"))
        self.assertIn("参照不足", reason([h("2026-10-13", failed="P3")], "2026-10-14", library=refs_lib()))
        for history, on in (([h("2026-10-13")], "2026-10-19"),                  # wait
                            ([h("2026-10-13")], "2026-10-20"),                  # due
                            ([h("2026-10-21")], "2026-10-22"),                  # no
                            ([h("2026-10-13", failed="P2")], "2026-10-20")):
            self.assertIn("开玩前 9–3 天", reason(history, on))
        self.assertIn("补测其余 5 国", reason([h("2026-10-13", "measure_rest")], "2026-10-13"))

    def test_result_shape(self):
        got = QF.reforecast_status([h("2026-10-13")], "2026-10-29", "2026-10-20", [])
        self.assertEqual(sorted(got), ["reason", "reforecast"])
        self.assertIn(got["reforecast"], ("new", "due", "wait", "no"))
        self.assertIsInstance(got["reason"], str)


class CliClockTest(CliTest):
    """同 CliTest,把 quick_forecast 的时钟拨到 2026-10-27 再跑一遍:日期写死的夹具到了那天开玩日就不在 3–21 天窗口里。"""
    CLOCK = "2026-10-27T08:00:00+00:00"

    def setUp(self):
        patcher = mock.patch.object(QF, "now", return_value=self.CLOCK)
        patcher.start()
        self.addCleanup(patcher.stop)


class CliLaterClockTest(CliClockTest):
    """同上,时钟拨到 2026-11-20(写死的开玩日早已过去)。"""
    CLOCK = "2026-11-20T08:00:00+00:00"


if __name__ == "__main__":
    unittest.main()
