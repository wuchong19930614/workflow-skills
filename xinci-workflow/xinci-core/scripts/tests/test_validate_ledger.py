# validate_ledger 不变式测试:registrar 之外的改动(手工编辑损坏)必须被校验捕获。
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import registrar as R
import validate_ledger as V
from test_registrar import mk_evidence, mk_decision, GATES_SCREEN, GATES_678


class ValidateLedgerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # ---- 辅助 ----

    def build_chain(self, slug="demo-term", until="tracking", window="weeks"):
        ev = mk_evidence(self.root, slug, "2026-08-17-scan.json")
        R.register(self.root, slug=slug, term="demo term", source_url="https://e.com",
                   task="t", evidence=[ev])
        if until == "captured":
            return slug
        R.transition(self.root, slug, to="screened", by="xinci-scan",
                     gates=dict(GATES_SCREEN), window_estimate=window,
                     evidence=[mk_evidence(self.root, slug, "2026-08-17b-scan.json")])
        if until == "screened":
            return slug
        if until == "fast_grab_ready":
            ref = mk_decision(self.root, slug)
            R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                         decision_ref=ref, expiry="2026-08-25", play="fast_grab")
            return slug
        R.transition(self.root, slug, to="tracking", by="xinci-scan",
                     expiry="2026-09-30", invalidation=["官方工具上线"],
                     evidence=[mk_evidence(self.root, slug, "2026-08-17c-scan.json")])
        if until == "tracking":
            return slug
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-27-track.json")])
        R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                     gates={"G1": "pass"},
                     evidence=[mk_evidence(self.root, slug, "2026-09-03-track.json")])
        if until == "formation_confirmed":
            return slug
        R.transition(self.root, slug, to="qualified", by="xinci-qualify", score=85,
                     gates=dict(GATES_678),
                     evidence=[mk_evidence(self.root, slug, "2026-09-10-qualify.json")])
        if until == "qualified":
            return slug
        ref = mk_decision(self.root, slug)
        R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                     decision_ref=ref, play="single_domain")
        return slug

    def corrupt(self, slug, **fields):
        p = self.root / "账本" / "候选账本.json"
        ledger = json.loads(p.read_text(encoding="utf-8"))
        ledger["candidates"][slug].update(fields)
        p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    def errors(self):
        errs, _ = V.validate(self.root)
        return errs

    # ---- 用例 ----

    def test_clean_full_chain_passes(self):
        self.build_chain(until="build_ready")
        self.build_chain(slug="fast-one", until="fast_grab_ready", window="days")
        self.assertEqual(self.errors(), [])

    def test_detects_missing_window_on_screened(self):
        slug = self.build_chain(until="screened")
        self.corrupt(slug, window_estimate=None)
        self.assertTrue(any("window_estimate" in e for e in self.errors()))

    def test_detects_missing_expiry_on_tracking(self):
        slug = self.build_chain(until="tracking")
        self.corrupt(slug, expiry=None)
        self.assertTrue(any("expiry" in e for e in self.errors()))

    def test_detects_fast_grab_invariants(self):
        slug = self.build_chain(until="fast_grab_ready", window="days")
        self.corrupt(slug, expiry=None, play="single_domain", score=90)
        errs = self.errors()
        self.assertTrue(any("expiry" in e for e in errs))
        self.assertTrue(any("play" in e for e in errs))
        self.assertTrue(any("score" in e for e in errs))

    def test_detects_fast_grab_window_not_days(self):
        slug = self.build_chain(until="fast_grab_ready", window="days")
        self.corrupt(slug, window_estimate="weeks")
        self.assertTrue(any("window_estimate=days" in e for e in self.errors()))

    def test_detects_screen_gate_veto(self):
        slug = self.build_chain(until="screened")
        ledger_gates = dict(GATES_SCREEN)
        ledger_gates["G3"] = "veto"
        self.corrupt(slug, gates=ledger_gates)
        self.assertTrue(any("G0–G5 全 pass" in e and "G3" in e for e in self.errors()))

    def test_detects_qualify_gate_missing(self):
        slug = self.build_chain(until="qualified")
        gates = {**GATES_SCREEN, "G6": "pass", "G8": "pass"}  # 缺 G7
        self.corrupt(slug, gates=gates)
        self.assertTrue(any("G6–G8 全 pass" in e and "G7" in e for e in self.errors()))

    def test_detects_missing_track_observations(self):
        slug = self.build_chain(until="formation_confirmed")
        p = self.root / "账本" / "候选账本.json"
        ledger = json.loads(p.read_text(encoding="utf-8"))
        rec = ledger["candidates"][slug]
        rec["evidence_refs"] = [r for r in rec["evidence_refs"] if not r.endswith("-track.json")]
        p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertTrue(any("≥2 个 -track 观察" in e for e in self.errors()))

    def test_detects_track_span_too_short(self):
        slug = self.build_chain(until="formation_confirmed")
        # 把 -track 观察替换为同一天的两份:跨度 0 天,应报错
        p = self.root / "账本" / "候选账本.json"
        ledger = json.loads(p.read_text(encoding="utf-8"))
        rec = ledger["candidates"][slug]
        rec["evidence_refs"] = [r for r in rec["evidence_refs"] if not r.endswith("-track.json")]
        rec["evidence_refs"] += [mk_evidence(self.root, slug, "2026-09-03-track.json"),
                                 mk_evidence(self.root, slug, "2026-09-03b-track.json")]
        p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertTrue(any("跨度" in e for e in self.errors()))

    def test_detects_low_score_on_qualified(self):
        slug = self.build_chain(until="qualified")
        self.corrupt(slug, score=79)
        self.assertTrue(any("score" in e for e in self.errors()))

    def test_detects_bad_play_on_build_ready(self):
        slug = self.build_chain(until="build_ready")
        self.corrupt(slug, play="fast_grab")
        self.assertTrue(any("play" in e for e in self.errors()))

    def test_detects_broken_history_chain(self):
        slug = self.build_chain(until="tracking")
        p = self.root / "账本" / "候选账本.json"
        ledger = json.loads(p.read_text(encoding="utf-8"))
        ledger["candidates"][slug]["history"][1]["from"] = "tracking"  # 应为 captured
        p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertTrue(any("history" in e and "断链" in e for e in self.errors()))

    def test_detects_evidence_path_escape(self):
        slug = self.build_chain(until="captured")
        self.corrupt(slug, evidence_refs=["../外部文件.json"])
        self.assertTrue(any("相对路径" in e for e in self.errors()))


    # ---- G3 快道豁免(veto_window_bet)的封锁 ----

    def build_window_bet(self, slug="bet-term", until="screened"):
        ev = mk_evidence(self.root, slug, "2026-08-17-scan.json")
        R.register(self.root, slug=slug, term="bet term", source_url="https://e.com",
                   task="t", evidence=[ev])
        R.transition(self.root, slug, to="screened", by="xinci-scan",
                     gates=dict(GATES_SCREEN, G3=R.G3_WINDOW_BET), window_estimate="days",
                     reason="临时空位:数到的免费实现均因对象太新未被收录",
                     evidence=[mk_evidence(self.root, slug, "2026-08-17b-scan.json")])
        if until == "screened":
            return slug
        R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                     decision_ref=mk_decision(self.root, slug), expiry="2026-08-31")
        if until == "fast_grab_ready":
            return slug
        R.transition(self.root, slug, to="built", by="user")
        return slug

    def test_window_bet_on_allowed_states_is_valid(self):
        self.build_window_bet(until="fast_grab_ready")
        self.assertEqual(self.errors(), [])

    def test_window_bet_at_built_is_valid(self):
        self.build_window_bet(until="built")
        self.assertEqual(self.errors(), [])

    def test_window_bet_smuggled_into_tracking_is_caught(self):
        # 手工把豁免候选改成 tracking = 绕过 G3 走向全站
        slug = self.build_window_bet()
        self.corrupt(slug, state="tracking", expiry="2026-09-30")
        self.assertTrue(any("绕过了 G3" in e for e in self.errors()), self.errors())

    def test_window_bet_must_stay_days(self):
        slug = self.build_window_bet()
        self.corrupt(slug, window_estimate="weeks")
        self.assertTrue(any("要求 window_estimate=days" in e for e in self.errors()), self.errors())

    def test_plain_g3_veto_at_screened_is_caught(self):
        # 真否决被手工塞进 screened:三分里只有 pass / veto_window_bet 放行
        slug = self.build_window_bet()
        self.corrupt(slug, gates=dict(GATES_SCREEN, G3="veto"))
        self.assertTrue(any("未满足: ['G3']" in e for e in self.errors()), self.errors())

class ValidateRunsTest(unittest.TestCase):
    """运行清单校验:清单不经 registrar 写入,格式漂移只能靠本校验捕获。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "运行").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def mk_run(self, name="2026-08-17-xinci-scan.json", **fields):
        body = {"date": "2026-08-17", "skill": "xinci-scan"}
        body.update(fields)
        (self.root / "运行" / name).write_text(
            json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return body

    def assertErrorMatching(self, needle):
        errors = V.validate_runs(self.root)
        self.assertTrue(any(needle in e for e in errors),
                        f"未捕获 {needle!r},实际: {errors}")

    def test_minimal_and_full_manifests_pass(self):
        self.mk_run(sources_opened=["https://news.ycombinator.com"],
                    sources_blocked=["https://reddit.com/r/all/rising(策略拦截)"],
                    candidates_touched=[], billable_calls=0, notes=["零候选"])
        self.mk_run("2026-08-18-0930-xinci-run.json", date="2026-08-18", skill="xinci-run",
                    billable_calls=2,
                    rounds=[{"round": 1, "sources_opened": ["https://producthunt.com"],
                             "candidates_touched": ["demo-term"], "billable_calls": 2}])
        self.assertEqual(V.validate_runs(self.root), [])

    def test_real_world_drift_is_caught(self):
        # 首份真实清单的实际漂移:metered_calls / candidates_registered 都在 schema 外
        self.mk_run(metered_calls=0, candidates_registered=0)
        self.assertErrorMatching("schema 外字段")

    def test_missing_required_fields(self):
        (self.root / "运行" / "2026-08-17-xinci-scan.json").write_text(
            json.dumps({"date": "2026-08-17"}, ensure_ascii=False), encoding="utf-8")
        self.assertErrorMatching("缺必填字段 skill")

    def test_unknown_skill_rejected(self):
        self.mk_run("2026-08-17-xinci-bogus.json", skill="xinci-bogus")
        self.assertErrorMatching("skill 必须属于")

    def test_date_must_match_filename(self):
        self.mk_run(date="2026-08-20")
        self.assertErrorMatching("与文件名日期")

    def test_skill_must_match_filename(self):
        self.mk_run("2026-08-17-xinci-track.json", skill="xinci-scan")
        self.assertErrorMatching("与文件名")

    def test_filename_convention(self):
        self.mk_run("scan-notes.json")
        self.assertErrorMatching("文件名不合约定")

    def test_rounds_only_for_run(self):
        self.mk_run(rounds=[{"round": 1}])
        self.assertErrorMatching("rounds 是 xinci-run 专用字段")

    def test_round_entry_structure(self):
        self.mk_run("2026-08-17-xinci-run.json", skill="xinci-run",
                    rounds=[{"sources_opened": ["https://e.com"], "notes_extra": 1}])
        errors = V.validate_runs(self.root)
        self.assertTrue(any("缺必填字段 round" in e for e in errors), errors)
        self.assertTrue(any("schema 外字段" in e for e in errors), errors)

    def test_type_checks(self):
        self.mk_run(billable_calls="零", sources_opened="https://e.com")
        errors = V.validate_runs(self.root)
        self.assertTrue(any("billable_calls 必须是整数" in e for e in errors), errors)
        self.assertTrue(any("sources_opened 必须是非空字符串数组" in e for e in errors), errors)

    def test_malformed_json(self):
        (self.root / "运行" / "2026-08-17-xinci-scan.json").write_text("{坏", encoding="utf-8")
        self.assertErrorMatching("不是合法 JSON")

    # ---- 扫描漏斗自洽性:留痕纪律的可校验形式 ----

    FUNNEL_OK = {"extracted": 22, "rejected_zero_cost": 14, "rejected_g1": 4,
                 "deep_audited": 3, "queued": 1}

    def test_balanced_funnel_passes(self):
        self.mk_run(funnel=dict(self.FUNNEL_OK))
        self.assertEqual(V.validate_runs(self.root), [])

    def test_silently_dropped_directions_are_caught(self):
        # 2026-08-18 的真实缺陷:提取 5+ 条只有 1 条走到 G1,其余无声丢弃
        self.mk_run(funnel={"extracted": 5, "rejected_zero_cost": 0, "rejected_g1": 0,
                            "deep_audited": 1, "queued": 0})
        self.assertErrorMatching("不许无声丢弃")

    def test_funnel_missing_field(self):
        f = dict(self.FUNNEL_OK); f.pop("queued")
        self.mk_run(funnel=f)
        self.assertErrorMatching("funnel 缺字段")

    def test_funnel_rejects_unknown_field(self):
        self.mk_run(funnel=dict(self.FUNNEL_OK, maybe_list=3))
        self.assertErrorMatching("funnel 含 schema 外字段")

    def test_funnel_rejects_negative_and_nonint(self):
        self.mk_run(funnel=dict(self.FUNNEL_OK, queued=-1))
        self.assertErrorMatching("非负整数")

    def test_funnel_checked_inside_rounds(self):
        self.mk_run("2026-08-17-xinci-run.json", skill="xinci-run",
                    rounds=[{"round": 1, "funnel": {"extracted": 9, "rejected_zero_cost": 2,
                                                    "rejected_g1": 1, "deep_audited": 1,
                                                    "queued": 0}}])
        self.assertErrorMatching("rounds[0] funnel 去向加总")

    def test_funnel_optional(self):
        # 非扫描类清单(如纯复查轮)不带 funnel 是合法的
        self.mk_run()
        self.assertEqual(V.validate_runs(self.root), [])

    def test_missing_run_dir_is_not_an_error(self):
        empty = Path(self._tmp.name) / "空数据区"
        empty.mkdir()
        self.assertEqual(V.validate_runs(empty), [])


if __name__ == "__main__":
    unittest.main()
