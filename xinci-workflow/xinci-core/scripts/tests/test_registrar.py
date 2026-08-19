# registrar 契约测试:断言与实现计划附录 A(合法转移表)、附录 B(证据要求)一一对应。
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import registrar as R


def mk_evidence(root: Path, cand_slug: str, name: str, **overrides) -> str:
    """写一份满足观察 schema 最小要求的证据文件;stage 由文件名后缀推导,
    observed_at 由文件名日期前缀推导(推导不出时用固定值)。"""
    d = root / "证据" / cand_slug
    d.mkdir(parents=True, exist_ok=True)
    stage = Path(name).stem.rsplit("-", 1)[-1]
    try:
        observed_at = f"{date.fromisoformat(name[:10]).isoformat()}T00:00:00+00:00"
    except ValueError:
        observed_at = "2026-08-17T00:00:00+00:00"
    obs = {
        "slug": cand_slug,
        "observed_at": observed_at,
        "stage": stage,
        "points": ["测试观察要点"],
    }
    obs.update(overrides)
    (d / name).write_text(json.dumps(obs, ensure_ascii=False), encoding="utf-8")
    return f"证据/{cand_slug}/{name}"


def mk_decision(root: Path, slug: str, with_html: bool = True) -> str:
    d = root / "决策书"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text("# 决策书", encoding="utf-8")
    if with_html:
        (d / f"{slug}.html").write_text("<html></html>", encoding="utf-8")
    return f"决策书/{slug}.md"


GATES_SCREEN = {"G0": "pass", "G1": "pass", "G2": "pass", "G3": "pass", "G4": "pass", "G5": "pass"}
GATES_678 = {"G6": "pass", "G7": "pass", "G8": "pass"}


class RegistrarTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # ---- 流程推进辅助 ----

    def register(self, slug="demo-term"):
        ev = mk_evidence(self.root, slug, "2026-08-17-scan.json")
        R.register(self.root, slug=slug, term="demo term", source_url="https://example.com/t",
                   task="complete demo task", evidence=[ev])
        return slug

    def to_screened(self, slug, window="weeks"):
        ev = mk_evidence(self.root, slug, "2026-08-17b-scan.json")
        R.transition(self.root, slug, to="screened", by="xinci-scan",
                     gates=dict(GATES_SCREEN), window_estimate=window, evidence=[ev])

    def to_tracking(self, slug):
        ev = mk_evidence(self.root, slug, "2026-08-17c-scan.json")
        R.transition(self.root, slug, to="tracking", by="xinci-scan",
                     expiry="2026-09-30", invalidation=["官方工具上线"], evidence=[ev])

    def to_formation(self, slug):
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-27-track.json")])
        ev = mk_evidence(self.root, slug, "2026-09-03-track.json")
        R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                     gates={"G1": "pass"}, evidence=[ev])

    def to_qualified(self, slug):
        ev = mk_evidence(self.root, slug, "2026-09-10-qualify.json")
        R.transition(self.root, slug, to="qualified", by="xinci-qualify",
                     score=80, gates=dict(GATES_678), evidence=[ev])

    def load(self, slug):
        ledger = json.loads((self.root / "账本" / "候选账本.json").read_text(encoding="utf-8"))
        return ledger["candidates"][slug]

    # ---- 用例 ----

    def test_register_creates_captured(self):
        slug = self.register()
        rec = self.load(slug)
        self.assertEqual(rec["state"], "captured")
        self.assertEqual(len(rec["history"]), 1)
        self.assertEqual(rec["history"][0]["to"], "captured")
        self.assertEqual(len(rec["evidence_refs"]), 1)

    def test_register_requires_evidence_file(self):
        with self.assertRaises(R.RegistrarError):
            R.register(self.root, slug="x", term="x", source_url="https://e.com",
                       task="t", evidence=["证据/x/不存在.json"])

    def test_illegal_jump_rejected(self):
        slug = self.register()
        mk_decision(self.root, slug)
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                         decision_ref=f"决策书/{slug}.md", play="single_domain")

    def test_screened_requires_all_six_gates(self):
        slug = self.register()
        gates = dict(GATES_SCREEN)
        del gates["G5"]
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="screened", by="xinci-scan",
                         gates=gates, window_estimate="weeks", evidence=[ev])
        self.to_screened(slug)
        self.assertEqual(self.load(slug)["state"], "screened")

    def test_tracking_requires_expiry_and_invalidation(self):
        slug = self.register()
        self.to_screened(slug)
        ev = mk_evidence(self.root, slug, "2026-08-19-scan.json")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="tracking", by="xinci-scan", evidence=[ev])
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="tracking", by="xinci-scan",
                         expiry="2026-09-30", invalidation=[], evidence=[ev])
        self.to_tracking(slug)
        self.assertEqual(self.load(slug)["state"], "tracking")

    def test_formation_needs_two_track_observations(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        ev = mk_evidence(self.root, slug, "2026-08-20-track.json")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                         gates={"G1": "pass"}, evidence=[ev])

    def test_formation_needs_seven_day_track_span(self):
        # 形成期以周计:同一天凑出的两个 -track 观察不得进 formation_confirmed
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])
        same_day = mk_evidence(self.root, slug, "2026-08-20b-track.json")
        with self.assertRaisesRegex(R.RegistrarError, "跨度"):
            R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                         gates={"G1": "pass"}, evidence=[same_day])
        # 六天也不够
        six_days = mk_evidence(self.root, slug, "2026-08-26-track.json")
        with self.assertRaisesRegex(R.RegistrarError, "跨度"):
            R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                         gates={"G1": "pass"}, evidence=[six_days])
        # 满 7 天通过
        ok = mk_evidence(self.root, slug, "2026-08-27-track.json")
        R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                     gates={"G1": "pass"}, evidence=[ok])
        self.assertEqual(self.load(slug)["state"], "formation_confirmed")

    def test_qualified_requires_score_80(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        ev = mk_evidence(self.root, slug, "2026-09-10-qualify.json")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="qualified", by="xinci-qualify",
                         score=79, gates=dict(GATES_678), evidence=[ev])
        self.to_qualified(slug)
        self.assertEqual(self.load(slug)["state"], "qualified")

    def test_build_ready_requires_dual_format(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        self.to_qualified(slug)
        ref = mk_decision(self.root, slug, with_html=False)
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                         decision_ref=ref, play="single_domain")
        mk_decision(self.root, slug, with_html=True)
        R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                     decision_ref=ref, play="single_domain")
        self.assertEqual(self.load(slug)["state"], "build_ready")

    def test_no_site_forbids_decision_ref(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        self.to_qualified(slug)
        ref = mk_decision(self.root, slug)
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="no_site", by="xinci-decide",
                         reason="簇撑不起独立站", decision_ref=ref)
        R.transition(self.root, slug, to="no_site", by="xinci-decide", reason="簇撑不起独立站")
        self.assertEqual(self.load(slug)["state"], "no_site")

    def test_fast_grab_only_from_screened(self):
        slug = self.register()
        ref = mk_decision(self.root, slug)
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                         decision_ref=ref, expiry="2026-08-25", play="fast_grab")
        self.to_screened(slug, window="days")
        R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                     decision_ref=ref, expiry="2026-08-25", play="fast_grab")
        self.assertEqual(self.load(slug)["state"], "fast_grab_ready")

    def test_fast_grab_requires_days_window(self):
        # 快道只收 window_estimate=days 的 screened 候选(xinci-decide 硬规则,registrar 强制)
        slug = self.register()
        self.to_screened(slug, window="weeks")
        ref = mk_decision(self.root, slug)
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                         decision_ref=ref, expiry="2026-08-25", play="fast_grab")

    def test_terminal_states_have_no_exit(self):
        slug = self.register()
        R.transition(self.root, slug, to="rejected", by="xinci-scan", reason="G1 否决:原生组件直接完成任务")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="tracking", by="xinci-scan",
                         expiry="2026-09-30", invalidation=["x"])

    def test_superseded_requires_existing_slug(self):
        slug = self.register()
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="superseded", by="xinci-scan", superseded_by="ghost")
        other = "better-wording"
        ev = mk_evidence(self.root, other, "2026-08-17-scan.json")
        R.register(self.root, slug=other, term="better wording", source_url="https://e.com",
                   task="same task", evidence=[ev])
        R.transition(self.root, slug, to="superseded", by="xinci-scan", superseded_by=other)
        rec = self.load(slug)
        self.assertEqual(rec["state"], "superseded")
        self.assertEqual(rec["superseded_by"], other)

    def test_superseded_allowed_from_decision_finals(self):
        # 生命周期契约:disqualified / no_site 是决策终局,除 superseded 外无出边——即 superseded 必须可达
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        R.transition(self.root, slug, to="disqualified", by="xinci-qualify",
                     reason="竞争维度差 12 分")
        other = "better-wording"
        ev = mk_evidence(self.root, other, "2026-08-17-scan.json")
        R.register(self.root, slug=other, term="better wording", source_url="https://e.com",
                   task="same task", evidence=[ev])
        R.transition(self.root, slug, to="superseded", by="xinci-scan", superseded_by=other)
        self.assertEqual(self.load(slug)["state"], "superseded")
        # 其余终态(rejected 等)仍无出边
        other2 = self.register("plain-rejected")
        R.transition(self.root, other2, to="rejected", by="xinci-scan", reason="G1 否决")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, other2, to="superseded", by="xinci-scan", superseded_by=other)

    def test_built_to_tracking_upgrade_path(self):
        # 快道 built 的词被证明耐久后,用户可发起转回 tracking 走完整认定
        slug = self.register()
        self.to_screened(slug, window="days")
        ref = mk_decision(self.root, slug)
        R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                     decision_ref=ref, expiry="2026-08-25", play="fast_grab")
        R.transition(self.root, slug, to="built", by="xinci-decide", reason="用户已建站")
        with self.assertRaises(R.RegistrarError):  # 缺 reason
            R.transition(self.root, slug, to="tracking", by="xinci-track", expiry="2026-12-31")
        with self.assertRaises(R.RegistrarError):  # 缺 expiry
            R.transition(self.root, slug, to="tracking", by="xinci-track", reason="词耐久,升级完整认定")
        R.transition(self.root, slug, to="tracking", by="xinci-track",
                     reason="词耐久,升级完整认定", expiry="2026-12-31")
        self.assertEqual(self.load(slug)["state"], "tracking")

    def test_hold_to_disqualified(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        self.to_qualified(slug)
        R.transition(self.root, slug, to="hold", by="xinci-decide", reason="窗口判断存疑,搁置重审")
        with self.assertRaises(R.RegistrarError):  # 缺 reason
            R.transition(self.root, slug, to="disqualified", by="xinci-qualify")
        R.transition(self.root, slug, to="disqualified", by="xinci-qualify",
                     reason="重审后耐久性缺口:官方答案已上线")
        self.assertEqual(self.load(slug)["state"], "disqualified")

    def test_checked_allowed_on_any_nonterminal_state(self):
        # 设计意图锁定:checked 是"登记新观察",适用于任何非终态(如 qualified 等待决策期间);终态拒绝
        slug = self.register()
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-19-track.json")])
        self.assertEqual(self.load(slug)["state"], "captured")
        R.transition(self.root, slug, to="rejected", by="xinci-scan", reason="G1 否决")
        with self.assertRaises(R.RegistrarError):
            R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])

    def test_checked_updates_last_checked_at_without_state_change(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        before = self.load(slug)
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])
        after = self.load(slug)
        self.assertEqual(after["state"], "tracking")
        self.assertGreaterEqual(after["last_checked_at"], before["last_checked_at"])
        self.assertIn(f"证据/{slug}/2026-08-20-track.json", after["evidence_refs"])

    def test_register_carries_gates_for_queued_candidate(self):
        # 扫描漏斗第 3/4 层:本轮没走完深审的存活候选注册成 captured 排队,
        # 带上已得闸门结论,下轮按 gates 补跑缺的门再进深审
        slug = "queued-term"
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json")
        gates = {"G0": "pass", "G4": "pass", "G5": "pass", "G1": "pass"}
        R.register(self.root, slug=slug, term="queued term", source_url="https://e.com",
                   task="t", evidence=[ev], gates=gates, expiry="2026-08-25")
        rec = self.load(slug)
        self.assertEqual(rec["state"], "captured")
        self.assertEqual(rec["gates"], gates)
        self.assertEqual(rec["expiry"], "2026-08-25")
        # 快照进 history,便于回答"注册时已过哪些门、当时给的排队 expiry 是哪天"
        self.assertEqual(rec["history"][0]["gates"], gates)
        self.assertEqual(rec["history"][0]["expiry"], "2026-08-25")

    def test_queued_register_requires_expiry(self):
        # 排队位每轮进多出少;没有 expiry 就没有过期出口,方向会在队列里无声腐烂
        slug = "queued-no-expiry"
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json")
        with self.assertRaises(R.RegistrarError):
            R.register(self.root, slug=slug, term="q", source_url="https://e.com",
                       task="t", evidence=[ev],
                       gates={"G0": "pass", "G4": "pass", "G5": "pass", "G1": "pass"})

    def test_register_rejects_bad_expiry(self):
        slug = "queued-bad-expiry"
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json")
        with self.assertRaises(R.RegistrarError):
            R.register(self.root, slug=slug, term="q", source_url="https://e.com",
                       task="t", evidence=[ev], expiry="2026/08/25")

    def test_queued_candidate_can_expire(self):
        # captured→expired:排队窗口过了要有干净出口,不必硬塞成 rejected(它没有失败的闸门)
        slug = "queued-term"
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json")
        R.register(self.root, slug=slug, term="queued term", source_url="https://e.com",
                   task="t", evidence=[ev], expiry="2026-08-25",
                   gates={"G0": "pass", "G4": "pass", "G5": "pass", "G1": "pass"})
        R.transition(self.root, slug, to="expired", by="xinci-scan",
                     reason="排队 expiry 已过,经用户确认不再深审")
        self.assertEqual(self.load(slug)["state"], "expired")

    def test_expired_requires_reason(self):
        slug = "queued-term"
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json")
        R.register(self.root, slug=slug, term="q", source_url="https://e.com",
                   task="t", evidence=[ev], expiry="2026-08-25",
                   gates={"G1": "pass"})
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="expired", by="xinci-scan")

    def test_queued_without_g1_cannot_reach_screened(self):
        # 决策 2:超 G1 配额未搜的方向也排队,但 gates 不含 G1;
        # registrar 是最后一道防线——缺 G1 的排队候选不许进 screened
        slug = "unsearched-term"
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json")
        R.register(self.root, slug=slug, term="unsearched term", source_url="https://e.com",
                   task="t", evidence=[ev], expiry="2026-08-25",
                   gates={"G0": "pass", "G4": "pass", "G5": "pass"})
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="screened", by="xinci-scan",
                         gates={"G2": "pass", "G3": "pass"}, window_estimate="weeks",
                         evidence=[mk_evidence(self.root, slug, "2026-08-19-scan.json")])

    def test_register_without_gates_stays_empty(self):
        slug = self.register()
        self.assertEqual(self.load(slug)["gates"], {})
        self.assertNotIn("gates", self.load(slug)["history"][0])

    def test_queued_candidate_can_finish_screening_next_round(self):
        # 排队候选下轮补完 G2/G3 后正常进 screened
        slug = "queued-term"
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json")
        R.register(self.root, slug=slug, term="queued term", source_url="https://e.com",
                   task="t", evidence=[ev], expiry="2026-08-25",
                   gates={"G0": "pass", "G4": "pass", "G5": "pass", "G1": "pass"})
        R.transition(self.root, slug, to="screened", by="xinci-scan",
                     gates={"G2": "pass", "G3": "pass"}, window_estimate="weeks",
                     evidence=[mk_evidence(self.root, slug, "2026-08-19-scan.json")])
        rec = self.load(slug)
        self.assertEqual(rec["state"], "screened")
        # G0/G4/G5/G1 来自注册,G2/G3 来自本次转移,合并后 G0–G5 齐全
        self.assertEqual({g: rec["gates"][g] for g in R.SCREEN_GATES},
                         {g: "pass" for g in R.SCREEN_GATES})

    # ---- G3 快道豁免(veto_window_bet):闸门契约 G3「唯一的降级出口」 ----

    def to_screened_window_bet(self, slug, window="days", by="xinci-scan", reason="默认豁免依据"):
        """G3 判定为临时空位(免费实现只因对象太新还没被收录)的降级路径。"""
        gates = dict(GATES_SCREEN, G3=R.G3_WINDOW_BET)
        R.transition(self.root, slug, to="screened", by=by, gates=gates,
                     window_estimate=window, reason=reason,
                     evidence=[mk_evidence(self.root, slug, "2026-08-17b-scan.json")])

    def test_window_bet_enters_screened(self):
        slug = self.register()
        self.to_screened_window_bet(slug, reason="数到 8 个免费计算器,均因模型太新未收录")
        rec = self.load(slug)
        self.assertEqual(rec["state"], "screened")
        self.assertEqual(rec["gates"]["G3"], R.G3_WINDOW_BET)
        # 豁免依据必须留在 history 里可审计
        self.assertIn("未收录", rec["history"][-1]["reason"])

    def test_window_bet_can_take_fast_lane(self):
        slug = self.register()
        self.to_screened_window_bet(slug, reason="临时空位")
        R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                     decision_ref=mk_decision(self.root, slug), expiry="2026-08-31")
        self.assertEqual(self.load(slug)["state"], "fast_grab_ready")

    def test_window_bet_requires_days_window(self):
        # 临时空位寿命以天计;窗口以周/月计说明判断自相矛盾
        slug = self.register()
        with self.assertRaises(R.RegistrarError):
            self.to_screened_window_bet(slug, window="weeks", reason="理由")

    def test_window_bet_requires_reason(self):
        slug = self.register()
        with self.assertRaises(R.RegistrarError):
            self.to_screened_window_bet(slug, reason=None)

    def test_window_bet_forbidden_in_continuous_mode(self):
        # 软化闸门的决定不在连续运行的标准授权内(闸门契约 G3)
        slug = self.register()
        with self.assertRaises(R.RegistrarError):
            self.to_screened_window_bet(slug, by="xinci-run", reason="理由")

    def test_window_bet_cannot_enter_tracking(self):
        # 放它进追踪等于让它绕过 G3 一路走到全站
        slug = self.register()
        self.to_screened_window_bet(slug, reason="临时空位")
        with self.assertRaises(R.RegistrarError):
            self.to_tracking(slug)

    def test_plain_g3_veto_cannot_enter_screened(self):
        # 三分里只有 pass 与 veto_window_bet 放行;真否决仍然出局
        slug = self.register()
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="screened", by="xinci-scan",
                         gates=dict(GATES_SCREEN, G3="veto"), window_estimate="days",
                         reason="理由",
                         evidence=[mk_evidence(self.root, slug, "2026-08-17b-scan.json")])

    def test_window_bet_upgrade_requires_real_g3_pass(self):
        # built→tracking 升级通路:豁免只在快道这一次有效
        slug = self.register()
        self.to_screened_window_bet(slug, reason="临时空位")
        R.transition(self.root, slug, to="fast_grab_ready", by="xinci-decide",
                     decision_ref=mk_decision(self.root, slug), expiry="2026-08-31")
        R.transition(self.root, slug, to="built", by="user")
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="tracking", by="user",
                         reason="词看起来耐久", expiry="2026-10-31")
        # 重跑 G3 并取得真 pass 后放行
        R.transition(self.root, slug, to="tracking", by="user", gates={"G3": "pass"},
                     reason="重跑 G3:通用工具始终未收录,空位判定为持久", expiry="2026-10-31")
        rec = self.load(slug)
        self.assertEqual(rec["state"], "tracking")
        self.assertEqual(rec["gates"]["G3"], "pass")

    def test_checked_records_history_entry_with_by(self):
        # by 是连续运行的授权印记(by=xinci-run 即"标准授权、未经逐条确认");
        # 不写 history 则复查的执行者与次数都无从追溯,只能靠证据文件名反推
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        depth = len(self.load(slug)["history"])
        ref = mk_evidence(self.root, slug, "2026-08-20-track.json")
        R.checked(self.root, slug, evidence=[ref], by="xinci-run")
        hist = self.load(slug)["history"]
        self.assertEqual(len(hist), depth + 1)
        entry = hist[-1]
        self.assertEqual(entry["by"], "xinci-run")
        self.assertEqual(entry["checked"], [ref])
        # from==to,history 链保持连续(与 amend 同构)
        self.assertEqual(entry["from"], "tracking")
        self.assertEqual(entry["to"], "tracking")

    def test_checked_history_keeps_ledger_valid(self):
        # checked 条目不得破坏 validate_ledger 的链连续性与末项一致性
        import validate_ledger as V
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])
        errors, _ = V.validate(self.root)
        self.assertEqual(errors, [])

    def test_history_records_param_snapshots(self):
        # gates/score 等顶层字段会被后续转移覆盖,history 必须留有当次快照
        slug = self.register()
        self.to_screened(slug)
        rec = self.load(slug)
        self.assertEqual(rec["history"][-1]["gates"], GATES_SCREEN)
        self.assertEqual(rec["history"][-1]["window_estimate"], "weeks")
        self.to_tracking(slug)
        rec = self.load(slug)
        self.assertEqual(rec["history"][-1]["expiry"], "2026-09-30")
        self.assertEqual(rec["history"][-1]["invalidation"], ["官方工具上线"])
        self.to_formation(slug)
        self.to_qualified(slug)
        rec = self.load(slug)
        self.assertEqual(rec["history"][-1]["score"], 80)
        self.assertEqual(rec["history"][-1]["gates"], GATES_678)
        R.amend(self.root, slug, by="xinci-track", expiry="2026-12-31",
                add_aliases=["nickname"], reason="用户确认续期")
        last = self.load(slug)["history"][-1]
        self.assertEqual(last["expiry"], "2026-12-31")
        self.assertEqual(last["add_aliases"], ["nickname"])

    def test_history_append_only(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        rec = self.load(slug)
        self.assertEqual([h["to"] for h in rec["history"]], ["captured", "screened", "tracking"])
        self.assertEqual(rec["history"][1]["from"], "captured")
        for h in rec["history"]:
            self.assertIn("at", h)
            self.assertIn("by", h)

    # ---- amend:观察性字段修订(续期/别名/失效条件) ----

    def test_amend_updates_expiry_with_reason(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        R.amend(self.root, slug, by="xinci-track", expiry="2026-10-31",
                reason="形成信号仍在增长,用户确认续期")
        rec = self.load(slug)
        self.assertEqual(rec["expiry"], "2026-10-31")
        self.assertEqual(rec["state"], "tracking")
        last = rec["history"][-1]
        self.assertEqual(last["from"], "tracking")
        self.assertEqual(last["to"], "tracking")
        self.assertIn("expiry", last["amend"])

    def test_amend_appends_aliases_and_invalidation(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        R.amend(self.root, slug, by="xinci-track", add_aliases=["community-nickname"],
                add_invalidation=["竞品完整题库上线"], reason="复查观察到命名分裂与新竞品信号")
        rec = self.load(slug)
        self.assertIn("community-nickname", rec["aliases"])
        self.assertIn("竞品完整题库上线", rec["invalidation"])

    def test_amend_requires_reason_and_fields(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        with self.assertRaises(R.RegistrarError):
            R.amend(self.root, slug, by="xinci-track", expiry="2026-10-31", reason="")
        with self.assertRaises(R.RegistrarError):
            R.amend(self.root, slug, by="xinci-track", reason="没有任何字段可改")

    def test_amend_rejects_terminal_states(self):
        slug = self.register()
        R.transition(self.root, slug, to="rejected", by="xinci-scan", reason="G1 否决")
        with self.assertRaises(R.RegistrarError):
            R.amend(self.root, slug, by="xinci-track", expiry="2026-10-31", reason="不该成功")

    # ---- 证据内容校验 ----

    def test_evidence_content_validated(self):
        slug = "content-check"
        d = self.root / "证据" / slug
        d.mkdir(parents=True)
        # 空对象:缺必填字段
        (d / "2026-08-17-scan.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(R.RegistrarError):
            R.register(self.root, slug=slug, term="t", source_url="https://e.com",
                       task="t", evidence=[f"证据/{slug}/2026-08-17-scan.json"])
        # slug 与候选不一致
        bad = mk_evidence(self.root, slug, "2026-08-18-scan.json", slug="someone-else")
        with self.assertRaises(R.RegistrarError):
            R.register(self.root, slug=slug, term="t", source_url="https://e.com",
                       task="t", evidence=[bad])
        # stage 与文件名不一致
        bad2 = mk_evidence(self.root, slug, "2026-08-19-scan.json", stage="track")
        with self.assertRaises(R.RegistrarError):
            R.register(self.root, slug=slug, term="t", source_url="https://e.com",
                       task="t", evidence=[bad2])
        # points 为空
        bad3 = mk_evidence(self.root, slug, "2026-08-20-scan.json", points=[])
        with self.assertRaises(R.RegistrarError):
            R.register(self.root, slug=slug, term="t", source_url="https://e.com",
                       task="t", evidence=[bad3])
        # schema 外字段(与 observation.schema.json 的 additionalProperties:false 对齐)
        bad4 = mk_evidence(self.root, slug, "2026-08-22-scan.json", verdict="looks good")
        with self.assertRaisesRegex(R.RegistrarError, "schema 外字段"):
            R.register(self.root, slug=slug, term="t", source_url="https://e.com",
                       task="t", evidence=[bad4])
        # observed_at 不是 ISO 8601
        bad5 = mk_evidence(self.root, slug, "2026-08-23-scan.json", observed_at="昨天")
        with self.assertRaisesRegex(R.RegistrarError, "ISO 8601"):
            R.register(self.root, slug=slug, term="t", source_url="https://e.com",
                       task="t", evidence=[bad5])
        # source_urls 类型错误
        bad6 = mk_evidence(self.root, slug, "2026-08-24-scan.json", source_urls="https://e.com")
        with self.assertRaisesRegex(R.RegistrarError, "source_urls"):
            R.register(self.root, slug=slug, term="t", source_url="https://e.com",
                       task="t", evidence=[bad6])
        # 合法观察(含可选字段)通过
        ok = mk_evidence(self.root, slug, "2026-08-21-scan.json",
                         source_urls=["https://e.com/thread"], gates={"G1": "pass"})
        R.register(self.root, slug=slug, term="t", source_url="https://e.com",
                   task="t", evidence=[ok])
        self.assertEqual(self.load(slug)["state"], "captured")

    def test_evidence_path_escape_rejected(self):
        slug = "path-check"
        outside = self.root.parent / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        for bad in [str(outside), f"证据/{slug}/../../outside.json"]:
            with self.assertRaises(R.RegistrarError):
                R.register(self.root, slug=slug, term="t", source_url="https://e.com",
                           task="t", evidence=[bad])


if __name__ == "__main__":
    unittest.main()
