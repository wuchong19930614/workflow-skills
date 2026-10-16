import contextlib
import copy
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import helpers as H
import ledger as L
import quick_forecast as QF
import quick_model as QM
import settle
import trends_volume as TV
import validate_ledger
import write_observation as W
from _common import BenchError, load_ledger, save_ledger
from helpers import task_volume

AT = "2026-10-13T08:00:00+00:00"
OBJECT = "Monster Hunter Outlanders"
SLUG = "mho-map"
TERMS = [{"term": "mho map", "source": "autocomplete", "first_seen": "2026-10-12"}]
OBJ = {"name": OBJECT, "type": "game", "first_public": "2026-10-29", "date_source": "https://example.org/mho"}


def register_variant(root, obj_type="game", first_public="2026-10-29", terms=None, object_us=600000, with_screen=False,
                     with_forecast=True):
    """按 cases 的键各改一处,其余同 setup_forecast,然后调 register_quick。"""
    forecast_ref, _ = H.write_forecast(root, SLUG, object_us)
    screen_ref = W.write(root, H.quick_screen_obs(SLUG, term="mho map")) if with_screen else None
    obj = dict(OBJ, type=obj_type, first_public=first_public)
    return L.register_quick(root, SLUG, "怪物猎人新作地图", "tool", obj, terms or TERMS, screen_ref, "预判过线",
                            forecast_ref=forecast_ref if with_forecast else None)


def forecast_with_volume_ref(root, vref):
    """一份预判观察,只把 object_volume_ref 换成 vref(观察校验只看路径在 证据/ 下,登记时才读它)。"""
    real = W.write(root, H.quick_volume_obs(SLUG, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0, term=OBJECT))
    obs = QF.build_observation(root, H.forecast_payload(volume_ref=real), at=AT)
    obs["readings"]["object_volume_ref"] = vref
    return W.write(root, obs)


class RegisterForecastTest(unittest.TestCase):
    def test_register_future_playable(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual((rec["basis"], rec["state"], rec["object"]["first_public"]), ("forecast", "found", "2026-10-29"))
            self.assertEqual(rec["evidence_refs"][:2], refs[:2])            # 预判观察、对象名量级
            self.assertEqual(len(refs), 3)                                  # 再加上简报素材
            self.assertEqual(rec["evidence_refs"], refs)                    # 简报素材经 update 补进引用
            self.assertEqual((rec["lane"], rec["terms"], rec["volume"], rec["model"]), ("quick", TERMS, None, None))
            self.assertEqual(W.read(root, refs[0])["kind"], "quick_forecast")
            self.assertEqual(W.read(root, refs[1])["kind"], "quick_volume")

    def test_evidence_refs_are_forecast_then_object_volume(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root, brief=False)
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual(rec["evidence_refs"], refs)
            self.assertEqual(len(refs), 2)
            self.assertEqual(W.read(root, refs[0])["readings"]["object_volume_ref"], refs[1])

    def test_watching_suggestion_can_register(self):
        with H.TmpRoot() as root:                                   # 对象名 50 万:只有中位数过线 → watching
            slug, refs = H.setup_forecast(root, object_us=500000, brief=False)
            self.assertEqual(W.read(root, refs[0])["readings"]["suggestion"], "watching")
            self.assertEqual(load_ledger(root)["directions"][slug]["basis"], "forecast")

    def test_refusals(self):
        cases = {
            "not_game": (dict(obj_type="other"), "game"),
            "date_mismatch": (dict(first_public="2026-10-30"), "first_public"),
            "term_not_in_tasks": (dict(terms=[{"term": "mho tier list", "source": "autocomplete",
                                               "first_seen": "2026-10-12"}]), "任务"),
            "skip_suggestion": (dict(object_us=100000), "suggestion"),       # 预判建议 skip 不登记
            "both_refs": (dict(with_screen=True), "恰好"),
            "neither_ref": (dict(with_forecast=False), "恰好"),
        }
        for name, (kw, msg) in cases.items():
            with self.subTest(name), H.TmpRoot() as root:
                with self.assertRaisesRegex(BenchError, msg):
                    register_variant(root, **kw)
                self.assertEqual(load_ledger(root)["directions"], {})        # 拒收不留半截记录

    def test_object_name_must_be_the_forecast_object(self):
        with H.TmpRoot() as root:
            fref, _ = H.write_forecast(root, SLUG)
            with self.assertRaisesRegex(BenchError, "Monster Hunter Wilds.*Monster Hunter Outlanders"):
                L.register_quick(root, SLUG, "t", "tool", dict(OBJ, name="Monster Hunter Wilds"), TERMS, None, "r",
                                 forecast_ref=fref)
            self.assertEqual(load_ledger(root)["directions"], {})
            rec = L.register_quick(root, SLUG, "t", "tool", dict(OBJ, name="monster hunter  OUTLANDERS"), TERMS, None, "r",
                                   forecast_ref=fref)                          # 大小写与空格不计
            self.assertEqual(rec["object"]["name"], "monster hunter  OUTLANDERS")

    def test_one_stray_term_is_enough_to_refuse(self):
        stray = TERMS + [{"term": "mho tier list", "source": "autocomplete", "first_seen": "2026-10-12"}]
        with H.TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "mho tier list"):
                register_variant(root, terms=stray)

    def test_term_match_ignores_case_and_spaces(self):
        loud = [{"term": "MHO   Map", "source": "autocomplete", "first_seen": "2026-10-12"}]
        with H.TmpRoot() as root:
            rec = register_variant(root, terms=loud)
            self.assertEqual(rec["terms"], loud)

    def test_measure_rest_suggestion_is_refused(self):
        with H.TmpRoot() as root:
            H.write_references(root)
            vol = H.quick_volume_obs(SLUG, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0, term=OBJECT)
            for c in vol["readings"]["countries"]:
                if not c["readable"]:
                    c["basis"] = f"{TV.SKIPPED_PREFIX}429 限流"
            vref = W.write(root, vol)
            fref = W.write(root, QF.build_observation(root, H.forecast_payload(volume_ref=vref), at=AT))
            self.assertEqual(W.read(root, fref)["readings"]["suggestion"], "measure_rest")
            with self.assertRaisesRegex(BenchError, "measure_rest"):
                L.register_quick(root, SLUG, "t", "tool", dict(OBJ), TERMS, None, "r", forecast_ref=fref)

    def test_failed_check_is_refused_with_its_name(self):
        with H.TmpRoot() as root:
            H.write_references(root)
            p = H.forecast_payload(slug=SLUG)                                   # P5 不过:只记观察、建议 skip
            p["checks"]["P5"] = {"pass": False, "basis": "测试期已有专做本作的 wiki"}
            fref = W.write(root, QF.build_observation(root, p, at=AT))
            with self.assertRaisesRegex(BenchError, "P5"):
                L.register_quick(root, SLUG, "t", "tool", dict(OBJ), TERMS, None, "r", forecast_ref=fref)

    def test_forecast_must_be_this_directions(self):
        with H.TmpRoot() as root:
            fref, _ = H.write_forecast(root, "other-map")
            with self.assertRaisesRegex(BenchError, "不是本方向的预判观察"):
                L.register_quick(root, SLUG, "t", "tool", dict(OBJ), TERMS, None, "r", forecast_ref=fref)
            screen = W.write(root, H.quick_screen_obs(SLUG, term="mho map"))          # 速判观察当预判用
            with self.assertRaisesRegex(BenchError, "不是本方向的预判观察"):
                L.register_quick(root, SLUG, "t", "tool", dict(OBJ), TERMS, None, "r", forecast_ref=screen)

    def test_object_volume_must_be_this_directions_quick_volume(self):
        with H.TmpRoot() as root:
            H.write_references(root)
            other = W.write(root, H.quick_volume_obs("other-map", anchor_volume=600000, new_mean=50.0, anchor_mean=50.0,
                                                     term=OBJECT))
            brief = W.write(root, H.quick_brief_obs(SLUG))
            for bad in (other, brief):
                with self.subTest(bad):
                    fref = forecast_with_volume_ref(root, bad)
                    with self.assertRaisesRegex(BenchError, "object_volume_ref"):
                        L.register_quick(root, SLUG, "t", "tool", dict(OBJ), TERMS, None, "r", forecast_ref=fref)
            self.assertEqual(load_ledger(root)["directions"], {})

    def test_still_checks_slug_title_and_term_clash(self):
        with H.TmpRoot() as root:
            H.setup_forecast(root, slug="mho-map", brief=False)
            fref, _ = H.write_forecast(root, "mho-map2")
            with self.assertRaisesRegex(BenchError, "已属于方向 mho-map"):         # 说法冲突沿用现有检查
                L.register_quick(root, "mho-map2", "t", "tool", dict(OBJ), TERMS, None, "r", forecast_ref=fref)
            with self.assertRaisesRegex(BenchError, "title"):
                L.register_quick(root, "mho-map2", " ", "tool", dict(OBJ), TERMS, None, "r", forecast_ref=fref)

    def test_register_consumes_pool_items(self):
        import quick_pool
        with H.TmpRoot() as root:
            item = {"source": "autocomplete", "object": OBJECT, "term": "mho map",
                    "url": "https://suggestqueries.google.com/x", "seen_at": "2026-10-13"}
            quick_pool.add_items(root, [item], "证据/_quick/x-quick_signal.json")
            H.setup_forecast(root, brief=False)
            self.assertEqual(quick_pool.pending(root), [])

    def test_register_consumes_the_games_calendar_item(self):
        import quick_pool
        calendar = {"source": "wikipedia", "object": OBJECT, "term": None, "url": "https://en.wikipedia.org/x",
                    "seen_at": "2026-10-12", "playable_at": "2026-10-29", "stage": "Release"}
        other = dict(calendar, object="Other Game", url="https://en.wikipedia.org/y", playable_at="2026-10-30")
        with H.TmpRoot() as root:
            quick_pool.add_items(root, [calendar, other], "证据/_quick/x-quick_signal.json")
            before = [r["object"] for r in quick_pool.upcoming(root, on="2026-10-13", days=21)]
            self.assertEqual(before, [OBJECT, "Other Game"])
            H.setup_forecast(root)
            after = [r["object"] for r in quick_pool.upcoming(root, on="2026-10-13", days=21)]
            self.assertEqual(after, ["Other Game"])                       # 登记过的游戏不再出现在即将开玩里
            self.assertEqual([r["status"] for r in quick_pool._read_pool(root) if r["object"] == OBJECT], ["used"])

    def test_screen_registration_leaves_the_calendar_item_alone(self):
        import quick_pool
        calendar = {"source": "wikipedia", "object": H.OBJ["name"], "term": None, "url": "https://en.wikipedia.org/x",
                    "seen_at": "2026-10-12", "playable_at": "2026-10-20", "stage": "Release"}
        with H.TmpRoot() as root:
            quick_pool.add_items(root, [calendar], "证据/_quick/x-quick_signal.json")
            H.setup_quick(root)                                           # 现行(速判)登记只消耗登记的说法
            self.assertEqual([r["object"] for r in quick_pool.upcoming(root, on="2026-10-13")], [H.OBJ["name"]])

    def test_current_registration_unchanged(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_quick(root)
            self.assertNotIn("basis", load_ledger(root)["directions"][slug])

    def test_current_registration_still_needs_the_screen(self):
        with H.TmpRoot() as root:
            with self.assertRaisesRegex(BenchError, "恰好"):
                L.register_quick(root, "q", "t", "tool", dict(H.OBJ), [{"term": "q term", "source": "autocomplete",
                                                                         "first_seen": "2026-10-13"}], None, "r")


class DeriveTest(unittest.TestCase):
    def test_derive_ignores_object_name_volume(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            rec = load_ledger(root)["directions"][slug]
            self.assertIsNone(L.derive_quick(root, rec)["volume"])        # 只有对象名的量,任务词还没测

    def test_derive_uses_the_latest_volume_of_a_registered_term(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            ours = W.write(root, H.quick_volume_obs(slug, anchor_volume=60000, new_mean=50.0, anchor_mean=60.0,
                                                    term="MHO  map"))                       # 规范化后是本方向的说法
            later = W.write(root, H.quick_volume_obs(slug, anchor_volume=900000, new_mean=50.0, anchor_mean=50.0,
                                                     term=OBJECT))
            L.update(root, slug, {}, [ours, later])
            rec = load_ledger(root)["directions"][slug]
            v = L.derive_quick(root, rec)["volume"]
            self.assertEqual(v["estimate_7d"], 50000)                    # 取任务词的量,不被后写的对象名量盖掉

    def test_derive_takes_the_newest_of_several(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            old = W.write(root, H.quick_volume_obs(slug, anchor_volume=60000, new_mean=30.0, anchor_mean=60.0,
                                                   term="mho map"))
            new = W.write(root, H.quick_volume_obs(slug, anchor_volume=60000, new_mean=50.0, anchor_mean=60.0,
                                                   term="mho map"))
            L.update(root, slug, {}, [old, new])
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual(L.derive_quick(root, rec)["volume"]["estimate_7d"], 50000)

    def test_derive_still_reads_volume_without_term(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_quick(root)                               # 现行方向:量级观察不写 term
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual(L.derive_quick(root, rec)["volume"]["estimate_7d"], 50000)

    def test_derive_ignores_volume_of_another_term_for_current_direction(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_quick(root)
            other = W.write(root, H.quick_volume_obs(slug, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0,
                                                     term="something else"))
            L.update(root, slug, {}, [other])
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual(L.derive_quick(root, rec)["volume"]["estimate_7d"], 50000)


def hand_forecast(root, slug, refs, observed_at="2026-10-13T09:00:00+00:00", r_p25=None, object_us=None,
                  playable_at=None, volume_ref=None):
    """在已登记方向的预判观察(refs[0])上手改几处:合计与建议按改后的数重算,所以观察本身合法、能写入。
    写入后补进方向引用(观察时间晚于原观察,成为最新),返回路径。"""
    obs = copy.deepcopy(W.read(root, refs[0]))
    r = obs["readings"]
    obs["observed_at"] = observed_at
    if r_p25 is not None:
        r["tasks"][0]["r_p25"] = r_p25
    if object_us is not None:
        r["object_volume_pre"] = {"US": object_us}
    if playable_at is not None:
        r["playable_at"] = playable_at
    if volume_ref is not None:
        r["object_volume_ref"] = volume_ref
    r["forecast_p25"], r["forecast_median"] = QM.forecast_totals(r["object_volume_pre"], r["tasks"])
    r["suggestion"] = QM.forecast_suggestion(r["forecast_p25"], r["forecast_median"], complete=True)
    ref = W.write(root, obs)
    L.update(root, slug, {}, [ref])
    return ref


class PregameSettleTest(unittest.TestCase):
    def test_pregame_go(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            rec = settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="倍数只有 3 个参照", on="2026-10-14")
            self.assertEqual((rec["state"], rec["follow_up"]["launch_by"], rec["forecast"]["review_at"]), ("go", "2026-10-28", "2026-11-05"))
            self.assertEqual((rec["model"]["basis"], rec["forecast"]["forecast_p25"], rec["volume"]), ("forecast", 90000, None))
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-10-14"), [])

    def test_pregame_go_writes_the_forecast_block(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            rec = settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="倍数只有 3 个参照", on="2026-10-14")
            self.assertEqual(rec["forecast"], {
                "ref": refs[0], "playable_at": "2026-10-29", "object_volume_pre": {"US": 600000},
                "tasks": [{"task": "map", "r_p25": 0.15, "r_median": 0.2}], "forecast_p25": 90000,
                "forecast_median": 120000, "review_at": "2026-11-05", "review": None, "slipped_days": 0})
            self.assertEqual((rec["serp"], rec["watch"]), (None, None))
            self.assertEqual((rec["follow_up"]["status"], rec["follow_up"]["go_at"]), ("pending", "2026-10-14"))
            self.assertEqual(rec["model"]["scenarios"]["base"]["visits"], 10800)

    def test_pregame_watching_expires_at_review(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000)        # 下四分位 8100 访问、中位数 10800
            rec = settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
            self.assertEqual(rec["watch"]["expires_at"], "2026-11-05")
            self.assertEqual((rec["watch"]["since"], rec["watch"]["checks"], rec["follow_up"]), ("2026-10-14", [], None))
            self.assertEqual((rec["forecast"]["review_at"], rec["volume"], rec["model"]["suggestion"]), ("2026-11-05", None, "watching"))
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-10-14"), [])

    def test_wrong_verdict_refused(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000)
            self.assertRaises(BenchError, settle.settle, root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")
            self.assertRaises(BenchError, settle.settle, root, slug, "rejected", gate="volume", reason="x",
                              biggest_unknown="y", on="2026-10-14")          # 开玩前不能否决
            settle.settle(root, slug, "parked", reason="先放着", biggest_unknown="y", on="2026-10-14")

    def test_go_suggestion_cannot_settle_as_watching(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)                                 # 下四分位就过线,建议 go
            with self.assertRaisesRegex(BenchError, "go"):
                settle.settle(root, slug, "watching", reason="x", biggest_unknown="y", on="2026-10-14")
            self.assertEqual(load_ledger(root)["directions"][slug]["state"], "found")

    def test_rejected_is_refused_before_launch_with_the_reason(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000)
            with self.assertRaisesRegex(BenchError, "开玩前只能结算 go、观察中或搁置"):
                settle.settle(root, slug, "rejected", gate="volume", reason="x", biggest_unknown="y", on="2026-10-14")
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual((rec["state"], rec["decision"], rec["bindings"]), ("found", None, None))

    def test_parked_only_tries_the_model(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000)
            rec = settle.settle(root, slug, "parked", reason="先放着", biggest_unknown="y", on="2026-10-14")
            self.assertEqual((rec["state"], rec["model"]["basis"], rec["watch"], rec["follow_up"], rec["volume"]),
                             ("parked", "forecast", None, None, None))
            self.assertNotIn("forecast", rec)                                # 搁置不写 forecast 块
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-10-14"), [])

    def test_parked_records_no_model_when_the_forecast_is_refused(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            hand_forecast(root, slug, refs, r_p25=0.12)                      # 倍数与参照库对不上
            rec = settle.settle(root, slug, "parked", reason="先放着", biggest_unknown="y", on="2026-10-14")
            self.assertEqual((rec["state"], rec["model"]), ("parked", None))
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-10-14"), [])

    def test_pregame_settle_outside_window_refused(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            self.assertRaises(BenchError, settle.settle, root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-27")

    def test_settle_window_is_3_to_21_days_before_playable(self):
        for on, ok in (("2026-10-07", False), ("2026-10-08", True), ("2026-10-26", True), ("2026-10-27", False),
                       ("2026-10-29", False), ("2026-10-30", False)):
            with self.subTest(on), H.TmpRoot() as root:
                slug, _ = H.setup_forecast(root)
                if ok:
                    self.assertEqual(settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on=on)["state"], "go")
                else:
                    with self.assertRaisesRegex(BenchError, "3–21 天"):
                        settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on=on)
                    self.assertEqual(load_ledger(root)["directions"][slug]["state"], "found")

    def test_go_needs_brief(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, brief=False)
            self.assertRaises(BenchError, settle.settle, root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")
            with self.assertRaisesRegex(BenchError, "quick_brief"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def test_go_needs_buildable_brief(self):
        for name, brief in {"no_data": H.quick_brief_obs(SLUG, data_available=False),
                            "too_long": H.quick_brief_obs(SLUG, build_days=4)}.items():
            with self.subTest(name), H.TmpRoot() as root:
                slug, _ = H.setup_forecast(root, brief=False)
                L.update(root, slug, {}, [W.write(root, brief)])
                with self.assertRaisesRegex(BenchError, "3 天内"):
                    settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def test_watching_does_not_need_brief(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000, brief=False)
            self.assertEqual(settle.settle(root, slug, "watching", reason="x", biggest_unknown="y", on="2026-10-14")["state"],
                             "watching")

    def test_tampered_reference_rate_refused(self):
        # 手写一份预判观察:reference_refs 仍是那三条参照,但 r_p25 写 0.12(合计按 0.12 重算,观察本身合法、能写入),
        # 它自己的建议是 watching;update 引用后结算 watching → 拒收,信息含"参照倍数与参照库重算不一致"
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            fake = hand_forecast(root, slug, refs, r_p25=0.12)
            obs = W.read(root, fake)["readings"]
            self.assertEqual((obs["forecast_p25"], obs["suggestion"]), (72000, "watching"))
            self.assertEqual(obs["tasks"][0]["reference_refs"], W.read(root, refs[0])["readings"]["tasks"][0]["reference_refs"])
            with self.assertRaisesRegex(BenchError, "参照倍数与参照库重算不一致"):
                settle.settle(root, slug, "watching", reason="x", biggest_unknown="y", on="2026-10-14")
            self.assertEqual(load_ledger(root)["directions"][slug]["state"], "found")      # 拒收不留半截

    def test_latest_forecast_is_the_one_settled_on(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root, object_us=450000)            # 原观察判 watching
            self.assertEqual(settle.settle(root, slug, "watching", reason="x", biggest_unknown="y", on="2026-10-14")["forecast"]["ref"],
                             refs[0])

    def test_forecast_with_other_playable_date_refused(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            hand_forecast(root, slug, refs, playable_at="2026-10-30")        # 方向的开玩日仍是 10-29
            with self.assertRaisesRegex(BenchError, "开玩日"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def test_object_volume_must_be_in_evidence_refs(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            other = W.write(root, H.quick_volume_obs(slug, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0,
                                                     term="Monster Hunter Outlanders"))
            hand_forecast(root, slug, refs, volume_ref=other)                # 量级观察存在,但没引用进方向
            with self.assertRaisesRegex(BenchError, "对象名量级观察.*不在方向引用里"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def test_object_volume_must_match_the_volume_observation(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            hand_forecast(root, slug, refs, object_us=900000)                # 观察里写 90 万,量级观察只有 60 万
            with self.assertRaisesRegex(BenchError, "对象名月量.*与量级观察.*不一致"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def test_object_volume_must_be_the_object_name_not_a_task_word(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            task_word = W.write(root, H.quick_volume_obs(slug, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0,
                                                         term="mho map"))             # 数对得上,但测的是任务词
            L.update(root, slug, {}, [task_word])
            hand_forecast(root, slug, refs, volume_ref=task_word)
            with self.assertRaisesRegex(BenchError, "不是对象名"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def test_object_volume_lag_is_checked_at_settle(self):
        # 预判观察比对象名量级观察晚 2 天还认,晚 3 天拒收;量级观察晚于预判观察也拒收(都按日期比)
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            hand_forecast(root, slug, refs, observed_at="2026-10-15T09:00:00+00:00")
            self.assertEqual(settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-15")["state"], "go")
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            hand_forecast(root, slug, refs, observed_at="2026-10-16T09:00:00+00:00")
            with self.assertRaisesRegex(BenchError, "早 3 天"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-16")
            self.assertEqual(load_ledger(root)["directions"][slug]["state"], "found")
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            later = W.write(root, H.quick_volume_obs(slug, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0, term=OBJECT,
                                                     observed_at="2026-10-14T08:00:00+00:00"))
            L.update(root, slug, {}, [later])
            hand_forecast(root, slug, refs, volume_ref=later)                 # 预判观察 10-13,量级观察 10-14
            with self.assertRaisesRegex(BenchError, "晚于预判"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def test_partial_geos_forecast_refused(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            obs = copy.deepcopy(W.read(root, refs[0]))
            obs["observed_at"] = "2026-10-13T09:00:00+00:00"
            obs["readings"]["skipped_geos"] = ["GB"]
            obs["readings"]["suggestion"] = QM.forecast_suggestion(90000, 120000, complete=False)      # measure_rest
            L.update(root, slug, {}, [W.write(root, obs)])
            with self.assertRaisesRegex(BenchError, "没测的国家"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def test_registered_terms_must_stay_covered_by_the_forecast_tasks(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            L.update(root, slug, {"terms": [{"term": "mho tier list", "source": "autocomplete", "first_seen": "2026-10-12"}]})
            with self.assertRaisesRegex(BenchError, "mho tier list"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def test_settle_is_resumable(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            first = settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="y", on="2026-10-14")
            again = settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="y", on="2026-10-14")
            self.assertEqual((again["state"], again["forecast"], again["history"]), (first["state"], first["forecast"], first["history"]))

    def test_transition_alone_rechecks_the_pregame_evidence(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")
            ledger = load_ledger(root)                                       # 回到结算前,但账本里留着新结算的产物
            rec = ledger["directions"][slug]
            rec["state"] = "found"
            rec["forecast"]["forecast_p25"] += 1                             # 预判块被改
            save_ledger(root, ledger)
            with self.assertRaisesRegex(BenchError, "预判块"):
                L.transition(root, slug, "go", None, "x", "t", "2026-10-14")

    def test_validate_catches_model_drift(self):
        # 结算后手改账本 rec["forecast"]["tasks"][0]["r_p25"] = 0.2 → check_direction 报"快道模型重算与账本不一致"
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            rec = settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")
            rec["forecast"]["tasks"][0]["r_p25"] = 0.2
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-10-14"),
                             [f"{slug}: 快道模型重算与账本不一致"])


class PregameValidateTest(unittest.TestCase):
    def settled(self, root, **kw):
        slug, _ = H.setup_forecast(root, **kw)
        return slug, settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-14")

    def check(self, root, slug, rec):
        return validate_ledger.check_direction(root, slug, rec, on="2026-10-14")

    def test_malformed_forecast_records_are_errors_not_crashes(self):
        def no_block(rec):
            rec["forecast"] = None

        def no_tasks(rec):
            del rec["forecast"]["tasks"]

        def no_volume(rec):
            del rec["forecast"]["object_volume_pre"]

        def task_without_rate(rec):
            del rec["forecast"]["tasks"][0]["r_median"]

        def not_a_dict(rec):
            rec["forecast"] = "x"

        for fn in (no_block, no_tasks, no_volume, task_without_rate, not_a_dict):
            with self.subTest(fn.__name__), H.TmpRoot() as root:
                slug, rec = self.settled(root)
                fn(rec)
                errs = self.check(root, slug, rec)
                self.assertTrue(errs)
                self.assertTrue(all(e.startswith(f"{slug}: ") for e in errs), errs)

    def test_forecast_block_keys_must_be_complete(self):
        with H.TmpRoot() as root:
            slug, rec = self.settled(root)
            del rec["forecast"]["review"]
            self.assertIn(f"{slug}: forecast 块缺字段 ['review']", self.check(root, slug, rec))

    def test_block_playable_must_equal_first_public(self):
        with H.TmpRoot() as root:
            slug, rec = self.settled(root)
            rec["forecast"]["playable_at"] = "2026-10-30"
            errs = self.check(root, slug, rec)
            self.assertTrue(any("playable_at" in e and "first_public" in e for e in errs), errs)

    def test_block_review_at_must_follow_playable(self):
        with H.TmpRoot() as root:
            slug, rec = self.settled(root)
            rec["forecast"]["review_at"] = "2026-11-06"
            errs = self.check(root, slug, rec)
            self.assertTrue(any("review_at" in e and "2026-11-05" in e for e in errs), errs)

    def test_basis_can_only_be_forecast(self):
        with H.TmpRoot() as root:
            slug, rec = self.settled(root)
            rec["basis"] = "current"
            self.assertTrue(any("basis" in e for e in self.check(root, slug, rec)))

    def test_current_directions_are_not_asked_for_a_forecast_block(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_quick(root)
            rec = settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-13")
            self.assertNotIn("basis", rec)
            self.assertNotIn("forecast", rec)
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-10-13"), [])


class SettleValidatesAsOfSettleDayTest(unittest.TestCase):
    """settle 结算后的自校验按结算日 on 算,不按真实今天:结算时观察还没到期,
    不能因为之后某天已过到期日,就把刚结算出的结果拒掉(用 today 往后拨到到期日之后来模拟)。"""
    LATER = "2026-11-20"                                  # 晚于预判观察的到期日 11-05 与下面现行观察的到期日 11-19

    def test_pregame_watching_is_valid_as_of_the_settle_day(self):
        with H.TmpRoot() as root, mock.patch.object(validate_ledger, "today", return_value=self.LATER):
            slug, _ = H.setup_forecast(root, object_us=450000)
            rec = settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
            self.assertEqual((rec["state"], rec["watch"]["expires_at"]), ("watching", "2026-11-05"))
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-10-14"), [])
            self.assertTrue(any("到期" in e for e in validate_ledger.check_direction(root, slug, rec)))   # 按"今天"看确已到期

    def test_current_watching_is_valid_as_of_the_settle_day(self):
        volume = H.quick_volume_obs("gag2-calculator", anchor_volume=9900, new_mean=50.0, anchor_mean=99.0)    # 约 5,000 → 观察中
        with H.TmpRoot() as root, mock.patch.object(validate_ledger, "today", return_value=self.LATER):
            slug, _ = H.setup_quick(root, volume=volume)
            rec = settle.settle(root, slug, "watching", reason="量还不够,在涨", biggest_unknown="能不能涨到 5 万", on="2026-10-20")
            self.assertEqual((rec["state"], rec["watch"]["expires_at"]), ("watching", "2026-11-19"))
            self.assertTrue(any("到期" in e for e in validate_ledger.check_direction(root, slug, rec)))


class RegisterQuickCliTest(unittest.TestCase):
    def run_cli(self, root, payload):
        path = root / "register.json"
        H.write_json(path, payload)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = L.main(["--data-root", str(root), "register-quick", "--input", str(path)])
        return code, out.getvalue(), err.getvalue()

    def payload(self, **over):
        d = {"slug": SLUG, "title": "怪物猎人新作地图", "site_type": "tool", "object": dict(OBJ), "terms": TERMS,
             "reason": "预判过线"}
        d.update(over)
        return d

    def test_forecast_key_replaces_screen(self):
        with H.TmpRoot() as root:
            fref, _ = H.write_forecast(root, SLUG)
            code, out, err = self.run_cli(root, self.payload(forecast=fref))
            self.assertEqual((code, err), (0, ""))
            self.assertIn('"basis": "forecast"', out)
            self.assertEqual(load_ledger(root)["directions"][SLUG]["basis"], "forecast")

    def test_screen_key_still_works(self):
        with H.TmpRoot() as root:
            ref = W.write(root, H.quick_screen_obs("gag2", term="gag2 term"))
            code, out, err = self.run_cli(root, self.payload(slug="gag2", screen=ref, object=dict(H.OBJ),
                                                             terms=[{"term": "gag2 term", "source": "autocomplete",
                                                                     "first_seen": "2026-10-13"}]))
            self.assertEqual((code, err), (0, ""))
            self.assertNotIn("basis", load_ledger(root)["directions"]["gag2"])

    def test_neither_or_both_is_refused(self):
        with H.TmpRoot() as root:
            fref, _ = H.write_forecast(root, SLUG)
            screen = W.write(root, H.quick_screen_obs(SLUG, term="mho map"))
            for name, kw in {"neither": {}, "both": dict(forecast=fref, screen=screen)}.items():
                with self.subTest(name):
                    code, out, err = self.run_cli(root, self.payload(**kw))
                    self.assertEqual(code, 1)
                    self.assertIn("拒收", err)
                    self.assertIn("恰好", err)
            self.assertEqual(load_ledger(root)["directions"], {})


def two_task_go(root):
    """两项任务(map、codes)的预判 go:预测下四分位 600000 × (0.15 + 0.15) = 180000,止损线 45000。"""
    H.write_references(root, task="map")
    H.write_references(root, task="codes")
    volume_ref = W.write(root, H.quick_volume_obs(SLUG, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0, term=OBJECT))
    tasks = [{"task": "map", "terms": ["mho map"]}, {"task": "codes", "terms": ["mho codes", "mho redeem codes"]}]
    forecast_ref = W.write(root, QF.build_observation(root, H.forecast_payload(slug=SLUG, object=OBJECT, volume_ref=volume_ref,
                                                                              tasks=tasks), at=AT))
    terms = TERMS + [{"term": "mho codes", "source": "autocomplete", "first_seen": "2026-10-12"}]
    L.register_quick(root, SLUG, "怪物猎人新作", "tool", dict(OBJ), terms, None, "预判过线", forecast_ref=forecast_ref)
    L.update(root, SLUG, {}, [W.write(root, H.quick_brief_obs(SLUG))])
    settle.settle(root, SLUG, "go", reason="开玩前预测过线", biggest_unknown="倍数", on="2026-10-14")
    return SLUG


class ReviewTest(unittest.TestCase):
    def go(self, root):
        slug, _ = H.setup_forecast(root)
        settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="倍数", on="2026-10-14")
        return slug

    def test_stop_below_quarter(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            out = L.review_forecast(root, slug, [W.write(root, task_volume(slug, 22499))], on="2026-11-05")
            self.assertEqual((out["actual"], out["stop"], out["message"]), (22499, True, "预判失准,建议停止追加投入"))

    def test_quarter_boundary_not_stop(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            self.assertFalse(L.review_forecast(root, slug, [W.write(root, task_volume(slug, 22500))], on="2026-11-05")["stop"])

    def test_review_refusals(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            early = W.write(root, task_volume(slug, 30000))
            self.assertRaises(BenchError, L.review_forecast, root, slug, [early], on="2026-11-04")       # 复核日未到
            pre = W.write(root, task_volume(slug, 30000, day="2026-10-20"))
            self.assertRaises(BenchError, L.review_forecast, root, slug, [pre], on="2026-11-05")        # 开玩前测的量
            other = W.write(root, task_volume(slug, 30000, term="mho codes"))
            self.assertRaises(BenchError, L.review_forecast, root, slug, [other], on="2026-11-05")      # 不是本方向的说法
            L.review_forecast(root, slug, [early], on="2026-11-05")
            self.assertRaises(BenchError, L.review_forecast, root, slug, [early], on="2026-11-06")      # 已复核

    def test_review_writes_the_block_and_adds_the_refs(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            ref = W.write(root, task_volume(slug, 30000))
            out = L.review_forecast(root, slug, [ref], on="2026-11-05")
            want = {"at": "2026-11-05", "actual": 30000, "forecast_p25": 90000, "ratio": 0.3333, "stop": False,
                    "by_task": [{"task": "map", "ref": ref, "estimate_7d": 30000}]}
            self.assertEqual({k: out[k] for k in want}, want)
            self.assertNotEqual(out["message"], "预判失准,建议停止追加投入")
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual(rec["forecast"]["review"], want)
            self.assertIn(ref, rec["evidence_refs"])
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-11-05"), [])

    def test_stop_is_recorded_in_the_block(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            L.review_forecast(root, slug, [W.write(root, task_volume(slug, 1000))], on="2026-11-05")
            review = load_ledger(root)["directions"][slug]["forecast"]["review"]
            self.assertEqual((review["stop"], review["ratio"]), (True, 0.0111))

    def test_review_takes_the_latest_volume_of_each_task_and_sums_the_tasks(self):
        with H.TmpRoot() as root:
            slug = two_task_go(root)                                           # 预测下四分位 180000,止损线 45000
            old = W.write(root, task_volume(slug, 99999, day="2026-11-02"))
            new = W.write(root, task_volume(slug, 30000, day="2026-11-05"))
            second = W.write(root, task_volume(slug, 15000, day="2026-11-05", term="Mho Redeem  Codes"))   # 任务的第二个说法
            out = L.review_forecast(root, slug, [new, old, second], on="2026-11-05")          # 引用顺序不决定谁最新
            self.assertEqual((out["actual"], out["stop"]), (45000, False))
            self.assertEqual([(t["task"], t["ref"], t["estimate_7d"]) for t in out["by_task"]],
                             [("map", new, 30000), ("codes", second, 15000)])

    def test_two_tasks_below_the_line_stop(self):
        with H.TmpRoot() as root:
            slug = two_task_go(root)
            refs = [W.write(root, task_volume(slug, 30000)), W.write(root, task_volume(slug, 14999, term="mho codes"))]
            self.assertTrue(L.review_forecast(root, slug, refs, on="2026-11-05")["stop"])           # 44999 < 45000

    def test_review_names_the_task_without_a_post_launch_volume(self):
        with H.TmpRoot() as root:
            slug = two_task_go(root)
            only_map = W.write(root, task_volume(slug, 30000))
            with self.assertRaisesRegex(BenchError, "codes"):
                L.review_forecast(root, slug, [only_map], on="2026-11-05")
            self.assertIsNone(load_ledger(root)["directions"][slug]["forecast"]["review"])

    def test_refused_review_leaves_the_ledger_untouched(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            before = load_ledger(root)
            ref = W.write(root, task_volume(slug, 30000))
            self.assertRaises(BenchError, L.review_forecast, root, slug, [ref], on="2026-11-04")
            self.assertEqual(load_ledger(root), before)

    def test_object_name_volume_does_not_count_as_a_task_reading(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            as_object = W.write(root, task_volume(slug, 30000, term=OBJECT))
            with self.assertRaisesRegex(BenchError, "map"):
                L.review_forecast(root, slug, [as_object], on="2026-11-05")

    def test_volume_without_term_does_not_count(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            bare = dict(task_volume(slug, 30000))
            bare["readings"] = {k: v for k, v in bare["readings"].items() if k != "term"}
            self.assertRaises(BenchError, L.review_forecast, root, slug, [W.write(root, bare)], on="2026-11-05")

    def test_only_a_pregame_go_can_be_reviewed(self):
        with H.TmpRoot() as root:
            found, _ = H.setup_forecast(root)
            self.assertRaises(BenchError, L.review_forecast, root, found, [], on="2026-11-05")          # 还没结算
            self.assertRaises(BenchError, L.review_forecast, root, "no-such", [], on="2026-11-05")
        with H.TmpRoot() as root:
            watching, _ = H.setup_forecast(root, object_us=450000)
            settle.settle(root, watching, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
            self.assertRaises(BenchError, L.review_forecast, root, watching, [], on="2026-11-05")       # 观察中走复查
        with H.TmpRoot() as root:
            current, _ = H.setup_quick(root)
            settle.settle(root, current, "go", reason="速判全过", biggest_unknown="热度", on="2026-10-14")
            self.assertRaises(BenchError, L.review_forecast, root, current, [], on="2026-11-05")        # 现行方向没有预测可比

    def test_watching_that_went_go_on_the_current_path_is_not_reviewed(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000)
            settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
            screen = dict(H.quick_screen_obs(slug, term="mho map"), observed_at="2026-11-05T08:00:00+00:00")
            volume = W.write(root, task_volume(slug, 60000))                      # 基准 60000 × 0.2 = 12000 访问,过现行门槛
            self.assertEqual(L.watch_check(root, slug, [W.write(root, screen), volume], on="2026-11-05")["suggestion"], "go")
            rec = settle.settle(root, slug, "go", reason="开玩后量够了", biggest_unknown="热度", on="2026-11-05")
            self.assertEqual((rec["state"], rec["basis"], rec["model"].get("basis"), rec["forecast"]["review"]),
                             ("go", "forecast", None, None))                       # 现行路径的模型,但 forecast 块还在
            before = load_ledger(root)
            with self.assertRaisesRegex(BenchError, "现行路径"):
                L.review_forecast(root, slug, [volume], on="2026-11-05")
            self.assertEqual(load_ledger(root), before)

    def test_partly_measured_volume_is_refused(self):
        # 只测了美国、其余 5 国"未查:"的量级不能拿来复核(预测是 6 国合计,只比美国会误报止损)
        with H.TmpRoot() as root:
            slug = self.go(root)
            us_only = task_volume(slug, 30000)
            for c in us_only["readings"]["countries"]:
                if not c["readable"]:
                    c["basis"] = f"{TV.SKIPPED_PREFIX}只测美国"
            before = load_ledger(root)
            with self.assertRaisesRegex(BenchError, "没测的国家.*GB"):
                L.review_forecast(root, slug, [W.write(root, us_only)], on="2026-11-05")
            self.assertEqual(load_ledger(root), before)

    def test_volume_before_the_review_day_is_refused(self):
        # 开玩当天、复核日前一天测的量,7 天窗口没全落在开玩后,不能拿来复核;复核日当天测的才算
        with H.TmpRoot() as root:
            slug = self.go(root)
            for day in ("2026-10-29", "2026-11-04"):
                with self.subTest(day):
                    early = W.write(root, task_volume(slug, 30000, day=day))
                    with self.assertRaisesRegex(BenchError, "复核日 2026-11-05 或之后"):
                        L.review_forecast(root, slug, [early], on="2026-11-06")
            out = L.review_forecast(root, slug, [W.write(root, task_volume(slug, 30000))], on="2026-11-06")
            self.assertEqual(out["actual"], 30000)

    def test_review_uses_the_settled_forecast(self):
        # go 之后再挂一份任务不同的新预判观察:复核仍按结算时那份(forecast.ref)的任务与说法
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="倍数", on="2026-10-14")
            newer = copy.deepcopy(W.read(root, refs[0]))
            newer["observed_at"] = "2026-10-15T09:00:00+00:00"
            r = newer["readings"]
            r["tasks"].append(dict(r["tasks"][0], task="codes", terms=["mho codes"]))
            r["forecast_p25"], r["forecast_median"] = QM.forecast_totals(r["object_volume_pre"], r["tasks"])
            r["suggestion"] = QM.forecast_suggestion(r["forecast_p25"], r["forecast_median"], complete=True)
            L.update(root, slug, {}, [W.write(root, newer)])
            out = L.review_forecast(root, slug, [W.write(root, task_volume(slug, 30000))], on="2026-11-05")
            self.assertEqual(([t["task"] for t in out["by_task"]], out["forecast_p25"]), (["map"], 90000))

    def test_review_cli(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            ref = W.write(root, task_volume(slug, 22499))
            for day, code in (("2026-11-04", 1), ("2026-11-05", 0)):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(L, "today", return_value=day), contextlib.redirect_stdout(out), \
                        contextlib.redirect_stderr(err):
                    got = L.main(["--data-root", str(root), "review-forecast", "--slug", slug, "--ref", ref])
                self.assertEqual(got, code)
                self.assertIn("拒收" if code else "预判失准,建议停止追加投入", err.getvalue() if code else out.getvalue())




class PregameWatchTest(unittest.TestCase):
    def watching(self, root):
        slug, _ = H.setup_forecast(root, object_us=450000)
        settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
        return slug

    def test_before_review_refused(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            self.assertRaises(BenchError, L.watch_check, root, slug, [], on="2026-11-04")

    def test_first_check_rebases_expiry(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            screen = dict(H.quick_screen_obs(slug, term="mho map"), observed_at="2026-11-05T08:00:00+00:00")
            refs = [W.write(root, screen), W.write(root, task_volume(slug, 30000))]
            out = L.watch_check(root, slug, refs, on="2026-11-05")
            self.assertEqual((out["suggestion"], out["expires_at"]), ("watching", "2026-12-05"))

    def test_pre_launch_screen_refused(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            refs = [W.write(root, H.quick_screen_obs(slug, term="mho map")), W.write(root, task_volume(slug, 30000))]
            self.assertRaises(BenchError, L.watch_check, root, slug, refs, on="2026-11-05")        # 速判是 10-13 开玩前看的

    def screen_and_volume(self, root, slug, estimate=30000, day="2026-11-05"):
        screen = dict(H.quick_screen_obs(slug, term="mho map"), observed_at=f"{day}T08:00:00+00:00")
        return [W.write(root, screen), W.write(root, task_volume(slug, estimate, day=day))]

    def test_the_check_is_recorded_and_the_expiry_persists(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            out = L.watch_check(root, slug, self.screen_and_volume(root, slug), on="2026-11-05")
            watch = load_ledger(root)["directions"][slug]["watch"]
            self.assertEqual(watch["expires_at"], "2026-12-05")
            self.assertEqual([(c["at"], c["estimate_7d"], c["suggestion"]) for c in watch["checks"]],
                             [("2026-11-05", 30000, out["suggestion"])])

    def test_second_check_does_not_rebase_again(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            L.watch_check(root, slug, self.screen_and_volume(root, slug), on="2026-11-05")
            out = L.watch_check(root, slug, self.screen_and_volume(root, slug, 31000, "2026-11-12"), on="2026-11-12")
            self.assertEqual(out["expires_at"], "2026-12-05")
            self.assertEqual(len(load_ledger(root)["directions"][slug]["watch"]["checks"]), 2)

    def test_refused_first_check_does_not_rebase(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            before = load_ledger(root)
            refs = [W.write(root, H.quick_screen_obs(slug, term="mho map")), W.write(root, task_volume(slug, 30000))]
            self.assertRaises(BenchError, L.watch_check, root, slug, refs, on="2026-11-05")
            self.assertEqual(load_ledger(root)["directions"][slug]["watch"], before["directions"][slug]["watch"])

    def test_pre_launch_task_volume_refused(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            screen = dict(H.quick_screen_obs(slug, term="mho map"), observed_at="2026-11-05T08:00:00+00:00")
            refs = [W.write(root, screen), W.write(root, task_volume(slug, 30000, day="2026-10-20"))]
            self.assertRaises(BenchError, L.watch_check, root, slug, refs, on="2026-11-05")

    def test_object_name_volume_is_not_the_reading(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            screen = dict(H.quick_screen_obs(slug, term="mho map"), observed_at="2026-11-05T08:00:00+00:00")
            as_object = task_volume(slug, 30000, term=OBJECT)             # 开玩后测的,但测的词是对象名,不是任务的说法
            with self.assertRaisesRegex(BenchError, "缺量级观察"):
                L.watch_check(root, slug, [W.write(root, screen), W.write(root, as_object)], on="2026-11-05")

    def test_missing_screen_is_refused_not_a_crash(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            with self.assertRaisesRegex(BenchError, "速判"):
                L.watch_check(root, slug, [W.write(root, task_volume(slug, 30000))], on="2026-11-05")

    def test_the_latest_screen_decides(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            refs = self.screen_and_volume(root, slug)
            refs.append(W.write(root, dict(H.quick_screen_obs(slug, term="mho map", fail={"Q5": False}, occupied_by="mho.wiki"),
                                           observed_at="2026-11-05T09:00:00+00:00")))
            self.assertEqual(L.watch_check(root, slug, refs, on="2026-11-05")["suggestion"], "rejected:occupied")

    def test_current_direction_keeps_its_expiry(self):
        volume = H.quick_volume_obs("gag2-calculator", anchor_volume=9900, new_mean=50.0, anchor_mean=99.0)     # 约 5,000
        with H.TmpRoot() as root:
            slug, _ = H.setup_quick(root, volume=volume)
            settle.settle(root, slug, "watching", reason="量还不够,在涨", biggest_unknown="能不能涨到 5 万", on="2026-10-20")
            out = L.watch_check(root, slug, on="2026-10-27")
            self.assertEqual((out["suggestion"], out["expires_at"]), ("watching", "2026-11-19"))




class PregameWatchSettleTest(unittest.TestCase):
    """预判观察中的方向开玩后结算(go、volume 与 oneoff 否决):复核日到了、复查过(watch-check),
    最新速判与任务说法的量级都是开玩日或之后看的,才按现行路径结算。"""

    def watching(self, root):
        slug, _ = H.setup_forecast(root, object_us=450000)               # 简报素材已在引用里
        settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
        return slug

    def observe(self, root, slug, estimate, day, series=None):
        """补挂一份速判与一份任务说法的量级观察(都在 day 当天看),不复查。"""
        screen = W.write(root, dict(H.quick_screen_obs(slug, term="mho map"), observed_at=f"{day}T08:00:00+00:00"))
        vol = task_volume(slug, estimate, day=day)
        if series is not None:
            vol["readings"]["series_30d"] = series
        L.update(root, slug, {}, [screen, W.write(root, vol)])

    def test_go_before_launch_is_refused(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            self.observe(root, slug, 60000, "2026-10-20")                  # 开玩前看的,量已够现行门槛
            with self.assertRaisesRegex(BenchError, "复核日 2026-11-05 未到"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-20")
            self.assertEqual(load_ledger(root)["directions"][slug]["state"], "watching")

    def test_volume_rejection_needs_a_watch_check_first(self):
        spike = [100] * 23 + [10] * 7                                      # 最近 7 天 < 峰值 × 30%:冲高回落
        for gate, series in (("volume", None), ("oneoff", spike)):
            with self.subTest(gate), H.TmpRoot() as root:
                slug = self.watching(root)
                self.observe(root, slug, 30000, "2026-11-05", series)
                with self.assertRaisesRegex(BenchError, "先跑 watch-check"):
                    settle.settle(root, slug, "rejected", gate=gate, reason="x", biggest_unknown="y", on="2026-11-06")
                self.assertEqual(load_ledger(root)["directions"][slug]["state"], "watching")

    def test_after_a_watch_check_the_current_path_settles(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            self.observe(root, slug, 30000, "2026-11-05")
            out = L.watch_check(root, slug, on="2026-11-05")
            self.assertEqual((out["suggestion"], out["expires_at"]), ("watching", "2026-12-05"))
            rec = settle.settle(root, slug, "rejected", gate="volume", reason="30 天没涨够", biggest_unknown="无", on="2026-12-05")
            self.assertEqual((rec["state"], rec["decision"]["gate"], rec["volume"]["estimate_7d"]), ("rejected", "volume", 30000))

    def test_latest_readings_must_be_after_launch(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            self.observe(root, slug, 60000, "2026-11-05")
            self.assertEqual(L.watch_check(root, slug, on="2026-11-05")["suggestion"], "go")
            L.update(root, slug, {}, [W.write(root, task_volume(slug, 60000, day="2026-10-20"))])   # 后补的开玩前量级成了最新
            with self.assertRaisesRegex(BenchError, "开玩日 2026-10-29 之前"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-11-05")
        with H.TmpRoot() as root:
            slug = self.watching(root)
            self.observe(root, slug, 60000, "2026-11-05")
            L.watch_check(root, slug, on="2026-11-05")
            L.update(root, slug, {}, [W.write(root, H.quick_screen_obs(slug, term="mho map"))])     # 后补的开玩前速判(10-13)
            with self.assertRaisesRegex(BenchError, "速判观察是 2026-10-13"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-11-05")

    def test_object_name_volume_is_not_taken_as_the_reading(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            self.observe(root, slug, 60000, "2026-11-05")
            L.watch_check(root, slug, on="2026-11-05")
            as_object = task_volume(slug, 900000, day="2026-11-05", term=OBJECT)        # 对象名的量,后补,曲线冲高回落
            as_object["readings"]["series_30d"] = [100] * 23 + [10] * 7
            L.update(root, slug, {}, [W.write(root, as_object)])
            rec = settle.settle(root, slug, "go", reason="开玩后量够了", biggest_unknown="热度", on="2026-11-05")
            self.assertEqual((rec["state"], rec["volume"]["estimate_7d"]), ("go", 60000))

    def test_validate_says_run_watch_check_before_the_first_check(self):
        with H.TmpRoot() as root:
            slug = self.watching(root)
            rec = load_ledger(root)["directions"][slug]
            errs = validate_ledger.check_direction(root, slug, rec, on="2026-11-06")
            self.assertTrue(any("到了复核日，先跑 watch-check" in e and "到期" in e for e in errs), errs)
            self.assertFalse(any("须按 go 或 volume 否决结算" in e for e in errs), errs)
            self.observe(root, slug, 30000, "2026-11-05")
            L.watch_check(root, slug, on="2026-11-06")
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-11-06"), [])
            errs = validate_ledger.check_direction(root, slug, rec, on="2026-12-07")
            self.assertTrue(any("须按 go 或 volume 否决结算" in e for e in errs), errs)


class SlipTest(unittest.TestCase):
    def test_slip_moves_dates(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="倍数", on="2026-10-14")
            rec = L.update(root, slug, {"object": {"first_public": "2026-11-12", "date_source": "https://example.org/delay"}},
                           on="2026-10-20")
            self.assertEqual((rec["follow_up"]["launch_by"], rec["forecast"]["review_at"], rec["forecast"]["slipped_days"]),
                             ("2026-11-11", "2026-11-19", 14))

    def test_slip_to_past_refused(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            for day in ("2026-10-20", "2026-10-19"):
                with self.subTest(day):
                    self.assertRaises(BenchError, L.update, root, slug,
                                      {"object": {"first_public": day, "date_source": "https://example.org/x"}}, on="2026-10-20")

    def test_slip_to_today_or_past_says_it_is_already_playable(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            for day in ("2026-10-20", "2026-10-19"):
                with self.subTest(day):
                    with self.assertRaisesRegex(BenchError, "说明已经开玩，按现行路径看首页"):
                        L.update(root, slug, {"object": {"first_public": day, "date_source": "https://example.org/x"}},
                                 on="2026-10-20")

    def test_current_direction_still_cannot_change_date(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_quick(root)
            self.assertRaises(BenchError, L.update, root, slug,
                              {"object": {"first_public": "2026-10-05", "date_source": "https://example.org/x"}})

    def go(self, root, **kw):
        slug, _ = H.setup_forecast(root, **kw)
        settle.settle(root, slug, "go", reason="开玩前预测过线", biggest_unknown="倍数", on="2026-10-14")
        return slug

    def slip(self, root, slug, day, on="2026-10-20"):
        return L.update(root, slug, {"object": {"first_public": day, "date_source": "https://example.org/delay"}}, on=on)

    def test_slipped_go_still_validates(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            rec = self.slip(root, slug, "2026-11-12")
            self.assertEqual(rec["object"]["first_public"], "2026-11-12")
            self.assertEqual((rec["forecast"]["playable_at"], rec["object"]["date_source"]),
                             ("2026-11-12", "https://example.org/delay"))
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-10-20"), [])
            self.assertEqual(load_ledger(root)["directions"][slug], rec)

    def test_slip_moves_a_watching_expiry_to_the_new_review_day(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000)
            settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
            rec = self.slip(root, slug, "2026-11-02")
            self.assertEqual((rec["watch"]["expires_at"], rec["forecast"]["review_at"], rec["forecast"]["slipped_days"]),
                             ("2026-11-09", "2026-11-09", 4))
            self.assertEqual(validate_ledger.check_direction(root, slug, rec, on="2026-10-20"), [])

    def test_slips_accumulate_and_can_be_pulled_in(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            self.assertEqual(self.slip(root, slug, "2026-11-05")["forecast"]["slipped_days"], 7)
            self.assertEqual(self.slip(root, slug, "2026-11-12")["forecast"]["slipped_days"], 14)
            rec = self.slip(root, slug, "2026-11-09")
            self.assertEqual((rec["forecast"]["slipped_days"], rec["follow_up"]["launch_by"]), (11, "2026-11-08"))

    def test_slip_leaves_a_started_follow_up_alone(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            L.follow_up(root, slug, "started", domain="mho-map.com", on="2026-10-15")
            rec = self.slip(root, slug, "2026-11-12")
            self.assertEqual((rec["follow_up"]["status"], rec["follow_up"]["launch_by"]), ("started", "2026-10-28"))
            self.assertEqual(rec["forecast"]["review_at"], "2026-11-19")

    def test_slip_on_found_changes_only_the_object_and_settle_asks_for_a_new_forecast(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root)
            rec = self.slip(root, slug, "2026-11-05", on="2026-10-22")
            self.assertEqual((rec["object"]["first_public"], rec.get("forecast")), ("2026-11-05", None))
            with self.assertRaisesRegex(BenchError, "update --ref"):
                settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-22")

    def test_found_slip_then_new_forecast_settles(self):
        with H.TmpRoot() as root:
            slug, refs = H.setup_forecast(root)
            self.slip(root, slug, "2026-11-05", on="2026-10-22")
            fresh = W.write(root, H.quick_volume_obs(slug, anchor_volume=600000, new_mean=50.0, anchor_mean=50.0, term=OBJECT,
                                                     observed_at="2026-10-22T08:00:00+00:00"))   # 重做预判要重测对象名的量
            L.update(root, slug, {}, [fresh])
            hand_forecast(root, slug, refs, playable_at="2026-11-05", observed_at="2026-10-22T09:00:00+00:00", volume_ref=fresh)
            rec = settle.settle(root, slug, "go", reason="x", biggest_unknown="y", on="2026-10-22")
            self.assertEqual((rec["forecast"]["playable_at"], rec["forecast"]["review_at"], rec["follow_up"]["launch_by"]),
                             ("2026-11-05", "2026-11-12", "2026-11-04"))

    def test_first_public_needs_a_date_source_and_a_real_date(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            for name, obj in {"no source": {"first_public": "2026-11-12"},
                              "blank source": {"first_public": "2026-11-12", "date_source": "  "},
                              "not a date": {"first_public": "soon", "date_source": "https://example.org/x"},
                              "no such day": {"first_public": "2026-02-30", "date_source": "https://example.org/x"},
                              "name": {"name": "Other", "date_source": "https://example.org/x"},
                              "type": {"type": "other", "date_source": "https://example.org/x"}}.items():
                with self.subTest(name):
                    self.assertRaises(BenchError, L.update, root, slug, {"object": obj}, on="2026-10-20")
            self.assertEqual(load_ledger(root)["directions"][slug]["object"]["first_public"], "2026-10-29")

    def test_date_source_alone_moves_nothing(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            rec = L.update(root, slug, {"object": {"date_source": "https://example.org/better"}}, on="2026-10-20")
            self.assertEqual((rec["object"]["date_source"], rec["forecast"]["review_at"], rec["forecast"]["slipped_days"]),
                             ("https://example.org/better", "2026-11-05", 0))

    def test_go_only_takes_the_object(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            self.assertRaises(BenchError, L.update, root, slug, {"title": "改名"}, on="2026-10-20")
            self.assertRaises(BenchError, L.update, root, slug, {"terms": TERMS}, on="2026-10-20")

    def test_slip_after_the_review_is_refused(self):
        with H.TmpRoot() as root:
            slug = self.go(root)
            L.review_forecast(root, slug, [W.write(root, task_volume(slug, 30000))], on="2026-11-05")
            with self.assertRaisesRegex(BenchError, "复核或复查过"):
                self.slip(root, slug, "2026-11-20", "2026-11-06")
            self.assertEqual(load_ledger(root)["directions"][slug]["object"]["first_public"], "2026-10-29")

    def test_slip_after_a_watch_check_is_refused(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_forecast(root, object_us=450000)
            settle.settle(root, slug, "watching", reason="中位数过线", biggest_unknown="开玩后量", on="2026-10-14")
            screen = dict(H.quick_screen_obs(slug, term="mho map"), observed_at="2026-11-05T08:00:00+00:00")
            L.watch_check(root, slug, [W.write(root, screen), W.write(root, task_volume(slug, 30000))], on="2026-11-05")
            with self.assertRaisesRegex(BenchError, "复核或复查过"):
                self.slip(root, slug, "2026-11-20", "2026-11-06")
            self.assertEqual(load_ledger(root)["directions"][slug]["object"]["first_public"], "2026-10-29")

    def test_current_go_still_cannot_be_updated(self):
        with H.TmpRoot() as root:
            slug, _ = H.setup_quick(root)
            settle.settle(root, slug, "go", reason="速判全过", biggest_unknown="热度", on="2026-10-14")
            self.assertRaises(BenchError, L.update, root, slug,
                              {"object": {"date_source": "https://example.org/x"}}, on="2026-10-20")




if __name__ == "__main__":
    unittest.main()
