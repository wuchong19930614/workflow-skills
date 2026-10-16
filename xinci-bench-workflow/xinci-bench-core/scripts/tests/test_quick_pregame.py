import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import helpers as H
import ledger as L
import quick_forecast as QF
import trends_volume as TV
import write_observation as W
from _common import BenchError, load_ledger

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


if __name__ == "__main__":
    unittest.main()
