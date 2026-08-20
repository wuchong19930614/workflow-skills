# registrar 契约测试:断言与实现计划附录 A(合法转移表)、附录 B(证据要求)一一对应。
import json
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import registrar as R
import build_decision_html as BDH
import run_controller as RC
import transaction_journal as TJ
import dedup_decisions as DD


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
    if obs.get("gates"):
        obs.setdefault("source_urls", ["https://e.com/source"])
        if obs["gates"].get("G3") == R.G3_WINDOW_BET:
            if "window_bet" not in obs:
                obs["window_bet"] = {
                    "implementation_urls": ["https://e.com/free-tool"],
                    "lag_sample_url": "https://e.com/previous-object",
                    "lag_days": 4,
                    "rationale": "实现可索引但新对象尚未收录",
                }
            if obs["window_bet"]:
                obs["source_urls"] = list(dict.fromkeys(
                    obs["source_urls"] + obs["window_bet"]["implementation_urls"]
                    + [obs["window_bet"]["lag_sample_url"]]))
    (d / name).write_text(json.dumps(obs, ensure_ascii=False), encoding="utf-8")
    return f"证据/{cand_slug}/{name}"


def mk_decision(root: Path, slug: str, with_html: bool = True) -> str:
    d = root / "决策书"
    d.mkdir(parents=True, exist_ok=True)
    md = d / f"{slug}.md"
    md.write_text("# 决策书\n\n## 失效条件\n\n- 条件\n\n## 下一步人工动作清单\n\n- 动作\n", encoding="utf-8")
    if with_html:
        BDH.build(md)
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
        R.register(self.root, slug=slug, term=slug.replace("-", " "), source_url="https://example.com/t",
                   task="complete demo task", evidence=[ev])
        return slug

    def to_screened(self, slug, window="weeks"):
        ev = mk_evidence(self.root, slug, "2026-08-17b-scan.json", gates=dict(GATES_SCREEN))
        R.transition(self.root, slug, to="screened", by="xinci-scan",
                     gates=dict(GATES_SCREEN), window_estimate=window, expiry="2026-10-01",
                     evidence=[ev])

    def to_tracking(self, slug):
        ev = mk_evidence(self.root, slug, "2026-08-17c-scan.json")
        R.transition(self.root, slug, to="tracking", by="xinci-scan",
                     expiry="2026-09-30", invalidation=["官方工具上线"], evidence=[ev])

    def to_formation(self, slug):
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-27-track.json")])
        ev = mk_evidence(self.root, slug, "2026-09-03-track.json", gates={"G1": "pass"})
        R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                     gates={"G1": "pass"}, evidence=[ev])

    def to_qualified(self, slug):
        ev = mk_evidence(self.root, slug, "2026-09-10-qualify.json", gates=dict(GATES_678))
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

    def test_register_enforces_slug_and_gate_vocabulary(self):
        ev = mk_evidence(self.root, "Bad Slug", "2026-08-17-scan.json")
        with self.assertRaisesRegex(R.RegistrarError, "kebab-case"):
            R.register(self.root, slug="Bad Slug", term="x", source_url="https://e.com",
                       task="t", evidence=[ev])
        slug = "bad-gate"
        ev = mk_evidence(self.root, slug, "2026-08-17-scan.json")
        with self.assertRaisesRegex(R.RegistrarError, "未知闸门"):
            R.register(self.root, slug=slug, term="x", source_url="https://e.com",
                       task="t", evidence=[ev], gates={"G9": "pass"}, expiry="2026-09-01")

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
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json", gates=gates)
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
        ev = mk_evidence(self.root, slug, "2026-08-20-track.json", gates={"G1": "pass"})
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                         gates={"G1": "pass"}, evidence=[ev])

    def test_formation_needs_seven_day_track_span(self):
        # 形成期以周计:同一天凑出的两个 -track 观察不得进 formation_confirmed
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        R.checked(self.root, slug, evidence=[mk_evidence(self.root, slug, "2026-08-20-track.json")])
        same_day = mk_evidence(self.root, slug, "2026-08-20b-track.json", gates={"G1": "pass"})
        with self.assertRaisesRegex(R.RegistrarError, "跨度"):
            R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                         gates={"G1": "pass"}, evidence=[same_day])
        # 六天也不够
        six_days = mk_evidence(self.root, slug, "2026-08-26-track.json", gates={"G1": "pass"})
        with self.assertRaisesRegex(R.RegistrarError, "跨度"):
            R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                         gates={"G1": "pass"}, evidence=[six_days])
        # 满 7 天通过
        ok = mk_evidence(self.root, slug, "2026-08-27-track.json", gates={"G1": "pass"})
        R.transition(self.root, slug, to="formation_confirmed", by="xinci-track",
                     gates={"G1": "pass"}, evidence=[ok])
        self.assertEqual(self.load(slug)["state"], "formation_confirmed")

    def test_qualified_requires_score_80(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        ev = mk_evidence(self.root, slug, "2026-09-10-qualify.json", gates=dict(GATES_678))
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

    def test_decision_html_must_match_current_markdown(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        self.to_qualified(slug)
        ref = mk_decision(self.root, slug)
        (self.root / ref).write_text("# 被修改\n\n## 失效条件\n- x\n\n## 下一步人工动作清单\n- y\n",
                                     encoding="utf-8")
        with self.assertRaisesRegex(R.RegistrarError, "不是由当前 md 生成"):
            R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                         decision_ref=ref, play="single_domain")

    def test_decision_html_rejects_forged_matching_hash(self):
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        self.to_qualified(slug)
        ref = mk_decision(self.root, slug)
        md = self.root / ref
        digest = hashlib.sha256(md.read_bytes()).hexdigest()
        md.with_suffix(".html").write_text(
            f'<html><head><meta name="xinci-source-sha256" content="{digest}"></head>'
            '<body>伪造内容</body></html>', encoding="utf-8")
        with self.assertRaisesRegex(R.RegistrarError, "确定性渲染"):
            R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                         decision_ref=ref, play="single_domain")

    def test_decision_ref_must_stay_inside_data_root(self):
        """决策书路径与证据路径同规:数据区内的相对路径,禁绝对路径与 ..。

        decision_ref 此前只校验存在性,`../` 或绝对路径能让账本指向数据区之外的文件。
        """
        slug = self.register()
        self.to_screened(slug)
        self.to_tracking(slug)
        self.to_formation(slug)
        self.to_qualified(slug)
        mk_decision(self.root, slug)
        for bad in (f"../决策书/{slug}.md", str(self.root / "决策书" / f"{slug}.md")):
            with self.assertRaises(R.RegistrarError):
                R.transition(self.root, slug, to="build_ready", by="xinci-decide",
                             decision_ref=bad, play="single_domain")
        self.assertEqual(self.load(slug)["state"], "qualified")

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
        R.transition(self.root, slug, to="rejected", by="xinci-scan",
                     gates={"G1": "veto"}, reason="G1 否决:原生组件直接完成任务",
                     evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                           gates={"G1": "veto"})])
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="tracking", by="xinci-scan",
                         expiry="2026-09-30", invalidation=["x"])

    def test_serp_rejection_can_reopen_with_new_evidence(self):
        slug = self.register()
        R.transition(self.root, slug, to="rejected", by="xinci-scan",
                     gates={"G3": "veto"}, reason="两个免费结果稳定可见",
                     evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                           gates={"G3": "veto"})])
        self.assertIsNotNone(self.load(slug)["recheck_after"])
        new_ref = mk_evidence(self.root, slug, "2026-09-20-scan.json",
                              points=["两个竞品均已下线,SERP 重新出现任务空缺"],
                              gates={"G3": "pass"})
        R.reopen(self.root, slug, by="xinci-scan", reason="竞品下线导致 G3 事实变化",
                 evidence=[new_ref])
        rec = self.load(slug)
        self.assertEqual(rec["state"], "captured")
        self.assertEqual(rec["gates"], {})
        self.assertTrue(rec["history"][-1]["reopened"])

    def test_reopen_rejects_stale_or_non_flipping_evidence(self):
        slug = self.register()
        R.transition(self.root, slug, to="rejected", by="xinci-scan",
                     gates={"G2": "veto", "G3": "veto"}, reason="SERP 与商业路径均不成立",
                     evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                           gates={"G2": "veto", "G3": "veto"})])
        stale = mk_evidence(self.root, slug, "2020-01-01-scan.json",
                            gates={"G2": "pass", "G3": "pass"})
        with self.assertRaisesRegex(R.RegistrarError, "晚于最近拒绝时间"):
            R.reopen(self.root, slug, by="xinci-scan", reason="使用旧截图", evidence=[stale])
        partial = mk_evidence(self.root, slug, "2026-09-21-scan.json", gates={"G2": "pass"})
        with self.assertRaisesRegex(R.RegistrarError, "尚未翻转.*G3"):
            R.reopen(self.root, slug, by="xinci-scan", reason="只翻转一道门", evidence=[partial])

    def test_structural_rejection_cannot_reopen(self):
        slug = self.register()
        R.transition(self.root, slug, to="rejected", by="xinci-scan",
                     gates={"G4": "veto"}, reason="任务需要持照人员到场",
                     evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                           gates={"G4": "veto"})])
        new_ref = mk_evidence(self.root, slug, "2026-09-20-scan.json")
        with self.assertRaisesRegex(R.RegistrarError, "结构性否决"):
            R.reopen(self.root, slug, by="xinci-scan", reason="想重开", evidence=[new_ref])

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
        R.transition(self.root, other2, to="rejected", by="xinci-scan",
                     gates={"G1": "veto"}, reason="G1 否决",
                     evidence=[mk_evidence(self.root, other2, "2026-08-18-scan.json",
                                           gates={"G1": "veto"})])
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
        R.transition(self.root, slug, to="rejected", by="xinci-scan",
                     gates={"G1": "veto"}, reason="G1 否决",
                     evidence=[mk_evidence(self.root, slug, "2026-08-20-scan.json",
                                           gates={"G1": "veto"})])
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
        gates = {"G0": "pass", "G4": "pass", "G5": "pass", "G1": "pass"}
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json", gates=gates)
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
        gates = {"G0": "pass", "G4": "pass", "G5": "pass", "G1": "pass"}
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json", gates=gates)
        with self.assertRaises(R.RegistrarError):
            R.register(self.root, slug=slug, term="q", source_url="https://e.com",
                       task="t", evidence=[ev],
                       gates=gates)

    def test_register_rejects_bad_expiry(self):
        slug = "queued-bad-expiry"
        gates = {"G0": "pass", "G4": "pass", "G5": "pass", "G1": "pass"}
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json", gates=gates)
        with self.assertRaises(R.RegistrarError):
            R.register(self.root, slug=slug, term="q", source_url="https://e.com",
                       task="t", evidence=[ev], expiry="2026/08/25")

    def test_queued_candidate_can_expire(self):
        # captured→expired:排队窗口过了要有干净出口,不必硬塞成 rejected(它没有失败的闸门)
        slug = "queued-term"
        gates = {"G0": "pass", "G4": "pass", "G5": "pass", "G1": "pass"}
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json", gates=gates)
        R.register(self.root, slug=slug, term="queued term", source_url="https://e.com",
                   task="t", evidence=[ev], expiry="2026-08-25",
                   gates=gates)
        R.transition(self.root, slug, to="expired", by="xinci-scan",
                     reason="排队 expiry 已过,经用户确认不再深审")
        self.assertEqual(self.load(slug)["state"], "expired")

    def test_screened_can_expire(self):
        # screened→expired:出闸后窗口自己过期(始终没排上快道、也没入库)的干净出口。
        # 与 captured→expired 同一条理由——它没有失败的闸门,不该被硬塞进 rejected。
        slug = self.register()
        self.to_screened(slug)
        R.transition(self.root, slug, to="expired", by="xinci-scan",
                     reason="窗口以周计但始终没推进,expiry 已过经用户确认")
        self.assertEqual(self.load(slug)["state"], "expired")

    def test_expired_requires_reason(self):
        slug = "queued-term"
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json", gates={"G1": "pass"})
        R.register(self.root, slug=slug, term="q", source_url="https://e.com",
                   task="t", evidence=[ev], expiry="2026-08-25",
                   gates={"G1": "pass"})
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="expired", by="xinci-scan")

    def test_queued_without_g1_cannot_reach_screened(self):
        # 决策 2:超 G1 配额未搜的方向也排队,但 gates 不含 G1;
        # registrar 是最后一道防线——缺 G1 的排队候选不许进 screened
        slug = "unsearched-term"
        initial_gates = {"G0": "pass", "G4": "pass", "G5": "pass"}
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json", gates=initial_gates)
        R.register(self.root, slug=slug, term="unsearched term", source_url="https://e.com",
                   task="t", evidence=[ev], expiry="2026-08-25",
                   gates=initial_gates)
        with self.assertRaises(R.RegistrarError):
            R.transition(self.root, slug, to="screened", by="xinci-scan",
                         gates={"G2": "pass", "G3": "pass"}, window_estimate="weeks",
                         expiry="2026-10-01",
                         evidence=[mk_evidence(self.root, slug, "2026-08-19-scan.json",
                                               gates={"G2": "pass", "G3": "pass"})])

    def test_register_without_gates_stays_empty(self):
        slug = self.register()
        self.assertEqual(self.load(slug)["gates"], {})
        self.assertNotIn("gates", self.load(slug)["history"][0])

    def test_queued_candidate_can_finish_screening_next_round(self):
        # 排队候选下轮补完 G2/G3 后正常进 screened
        slug = "queued-term"
        initial_gates = {"G0": "pass", "G4": "pass", "G5": "pass", "G1": "pass"}
        ev = mk_evidence(self.root, slug, "2026-08-18-scan.json", gates=initial_gates)
        R.register(self.root, slug=slug, term="queued term", source_url="https://e.com",
                   task="t", evidence=[ev], expiry="2026-08-25",
                   gates=initial_gates)
        R.transition(self.root, slug, to="screened", by="xinci-scan",
                     gates={"G2": "pass", "G3": "pass"}, window_estimate="weeks",
                     expiry="2026-10-01",
                     evidence=[mk_evidence(self.root, slug, "2026-08-19-scan.json",
                                           gates={"G2": "pass", "G3": "pass"})])
        rec = self.load(slug)
        self.assertEqual(rec["state"], "screened")
        # G0/G4/G5/G1 来自注册,G2/G3 来自本次转移,合并后 G0–G5 齐全
        self.assertEqual({g: rec["gates"][g] for g in R.SCREEN_GATES},
                         {g: "pass" for g in R.SCREEN_GATES})

    # ---- G3 快道豁免(veto_window_bet):闸门契约 G3「唯一的降级出口」 ----

    def to_screened_window_bet(self, slug, window="days", by="xinci-scan", reason="默认豁免依据",
                               run_id=None):
        """G3 判定为临时空位(免费实现只因对象太新还没被收录)的降级路径。"""
        gates = dict(GATES_SCREEN, G3=R.G3_WINDOW_BET)
        R.transition(self.root, slug, to="screened", by=by, gates=gates,
                     window_estimate=window, expiry="2026-08-31", reason=reason, run_id=run_id,
                     evidence=[mk_evidence(self.root, slug, "2026-08-17b-scan.json", gates=gates)])

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
        # 接受额外窗口赌注风险不在连续运行的标准授权内(闸门契约 G3)
        slug = self.register()
        with self.assertRaises(R.RegistrarError):
            self.to_screened_window_bet(slug, by="xinci-run", reason="理由")

    def test_window_bet_continuous_mode_requires_recorded_confirmation(self):
        slug = self.register()
        session = RC.start(self.root)
        run_id = session["run_id"]
        RC.begin_round(self.root, run_id)
        with self.assertRaisesRegex(R.RegistrarError, "单步确认"):
            self.to_screened_window_bet(slug, by="xinci-run", reason="临时空位", run_id=run_id)
        R.amend(self.root, slug, by="xinci-run", run_id=run_id,
                reason="深审判定为窗口赌注,等待用户确认", expiry="2026-08-31",
                gates=dict(GATES_SCREEN, G3=R.G3_WINDOW_BET),
                evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                      gates=dict(GATES_SCREEN, G3=R.G3_WINDOW_BET))])
        RC.confirm_window_bet(self.root, run_id, slug)
        self.to_screened_window_bet(slug, by="xinci-run", reason="临时空位", run_id=run_id)
        confirmation = RC.load_session(self.root, run_id)["confirmations"][slug]
        self.assertIsNotNone(confirmation["consumed_at"])

    def test_window_confirmation_cannot_be_rearmed_after_transition(self):
        slug = self.register()
        session = RC.start(self.root)
        run_id = session["run_id"]
        RC.begin_round(self.root, run_id)
        R.amend(self.root, slug, by="xinci-run", run_id=run_id,
                reason="窗口赌注", expiry="2026-08-31",
                gates=dict(GATES_SCREEN, G3=R.G3_WINDOW_BET),
                evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                      gates=dict(GATES_SCREEN, G3=R.G3_WINDOW_BET))])
        RC.confirm_window_bet(self.root, run_id, slug)
        self.to_screened_window_bet(slug, by="xinci-run", reason="临时空位", run_id=run_id)
        with self.assertRaises(RC.RunControllerError):
            RC.confirm_window_bet(self.root, run_id, slug)

    def test_window_transaction_recovers_after_ledger_write_failure(self):
        slug = self.register()
        session = RC.start(self.root)
        run_id = session["run_id"]
        RC.begin_round(self.root, run_id)
        gates = dict(GATES_SCREEN, G3=R.G3_WINDOW_BET)
        R.amend(self.root, slug, by="xinci-run", run_id=run_id,
                reason="窗口赌注", expiry="2026-08-31", gates=gates,
                evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json", gates=gates)])
        RC.confirm_window_bet(self.root, run_id, slug)
        with patch.object(R, "_save", side_effect=OSError("模拟账本写入中断")):
            with self.assertRaisesRegex(R.RegistrarError, "pending journal"):
                self.to_screened_window_bet(slug, by="xinci-run", reason="临时空位",
                                             run_id=run_id)
        self.assertEqual(self.load(slug)["state"], "captured")
        self.assertEqual(len(TJ.list_pending(self.root)), 1)
        with self.assertRaisesRegex(R.RegistrarError, "未恢复事务"):
            R.checked(self.root, slug,
                      evidence=[mk_evidence(self.root, slug, "2026-08-19-track.json")],
                      by="xinci-run", run_id=run_id)
        recovered = RC.recover(self.root, run_id)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(self.load(slug)["state"], "screened")
        self.assertEqual(TJ.list_pending(self.root), [])

    def test_divergent_transaction_requires_explicit_reconciliation(self):
        slug = self.register()
        session = RC.start(self.root)
        run_id = session["run_id"]
        RC.begin_round(self.root, run_id)
        gates = dict(GATES_SCREEN, G3=R.G3_WINDOW_BET)
        R.amend(self.root, slug, by="xinci-run", run_id=run_id,
                reason="窗口赌注", expiry="2026-08-31", gates=gates,
                evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json", gates=gates)])
        RC.confirm_window_bet(self.root, run_id, slug)
        with patch.object(R, "_save", side_effect=OSError("模拟中断")):
            with self.assertRaises(R.RegistrarError):
                self.to_screened_window_bet(slug, by="xinci-run", reason="临时空位",
                                             run_id=run_id)
        tx = TJ.list_pending(self.root)[0]
        ledger_path = self.root / "账本" / "候选账本.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["candidates"][slug]["task"] = "人工修订后的任务"
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(RC.RunControllerError, "非预期变化"):
            RC.recover(self.root, run_id)
        result = RC.reconcile(self.root, tx["tx_id"], "keep_current", "保留人工复核后的候选",
                              "user", "user-message-42")
        self.assertEqual(result["status"], "reconciled")
        self.assertEqual(self.load(slug)["task"], "人工修订后的任务")
        self.assertEqual(TJ.list_pending(self.root), [])
        # keep_current 会作废已消费确认，但保留确认历史；用户可重新明确确认而不被永久卡死。
        RC.confirm_window_bet(self.root, run_id, slug)
        confirmation = RC.load_session(self.root, run_id)["confirmations"][slug]
        self.assertIsNone(confirmation["consumed_at"])
        self.assertEqual(len(confirmation["history"]), 1)

    def test_transaction_candidate_snapshot_tamper_fails_closed(self):
        slug = self.register()
        session = RC.start(self.root)
        run_id = session["run_id"]
        RC.begin_round(self.root, run_id)
        gates = dict(GATES_SCREEN, G3=R.G3_WINDOW_BET)
        R.amend(self.root, slug, by="xinci-run", run_id=run_id,
                reason="窗口赌注", expiry="2026-08-31", gates=gates,
                evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json", gates=gates)])
        RC.confirm_window_bet(self.root, run_id, slug)
        with patch.object(R, "_save", side_effect=OSError("模拟中断")):
            with self.assertRaises(R.RegistrarError):
                self.to_screened_window_bet(slug, by="xinci-run", reason="临时空位",
                                             run_id=run_id)
        tx = TJ.list_pending(self.root)[0]
        path = Path(tx["_path"])
        body = json.loads(path.read_text(encoding="utf-8"))
        body["candidate_after"]["task"] = "被篡改"
        path.write_text(json.dumps(body), encoding="utf-8")
        with self.assertRaisesRegex(TJ.TransactionError, "哈希不匹配"):
            TJ.list_pending(self.root)

    def test_term_normalization_keeps_cplusplus_and_csharp_distinct(self):
        first = "cplusplus-tool"
        R.register(self.root, slug=first, term="C++ migration tool", source_url="https://e.com/cpp",
                   task="migrate C++", evidence=[mk_evidence(self.root, first, "2026-08-17-scan.json")])
        second = "csharp-tool"
        R.register(self.root, slug=second, term="C# migration tool", source_url="https://e.com/cs",
                   task="migrate C#", evidence=[mk_evidence(self.root, second, "2026-08-17-scan.json")])
        self.assertEqual(self.load(second)["state"], "captured")

    def test_probable_duplicate_registration_requires_distinct_ruling(self):
        first = "qwen-base"
        R.register(self.root, slug=first, term="Qwen 3.8 27B vram quantization",
                   source_url="https://e.com/base", task="estimate vram",
                   evidence=[mk_evidence(self.root, first, "2026-08-17-scan.json")])
        second = "qwen-requirements"
        evidence = [mk_evidence(self.root, second, "2026-08-17-scan.json")]
        with self.assertRaisesRegex(R.RegistrarError, "疑似重复"):
            R.register(self.root, slug=second, term="qwen 3.8 27b vram requirements",
                       source_url="https://e.com/new", task="list hardware requirements",
                       evidence=evidence)
        DD.resolve(self.root, "qwen 3.8 27b vram requirements",
                   "Qwen 3.8 27B vram quantization", "distinct",
                   "一个列硬件要求,另一个计算量化显存", actor="user",
                   term_task="列出部署显存要求", matched_task="计算量化显存",
                   term_evidence_urls=["https://e.com/requirements"],
                   matched_evidence_urls=["https://e.com/quantization"])
        R.register(self.root, slug=second, term="qwen 3.8 27b vram requirements",
                   source_url="https://e.com/new", task="list hardware requirements",
                   evidence=evidence)
        self.assertEqual(self.load(second)["state"], "captured")

    def test_same_duplicate_ruling_blocks_registration(self):
        first = "qwen-base"
        R.register(self.root, slug=first, term="Qwen 3.8 27B vram quantization",
                   source_url="https://e.com/base", task="estimate vram",
                   evidence=[mk_evidence(self.root, first, "2026-08-17-scan.json")])
        DD.resolve(self.root, "qwen 3.8 27b vram requirements",
                   "Qwen 3.8 27B vram quantization", "same", "同一显存任务的措辞漂移",
                   actor="user", term_task="估算显存", matched_task="估算显存",
                   term_evidence_urls=["https://e.com/requirements"],
                   matched_evidence_urls=["https://e.com/quantization"])
        second = "qwen-copy"
        with self.assertRaisesRegex(R.RegistrarError, "same"):
            R.register(self.root, slug=second, term="qwen 3.8 27b vram requirements",
                       source_url="https://e.com/new", task="estimate vram",
                       evidence=[mk_evidence(self.root, second, "2026-08-17-scan.json")])

    def test_single_step_write_is_blocked_during_active_run(self):
        session = RC.start(self.root)
        RC.begin_round(self.root, session["run_id"])
        slug = "single-during-run"
        ev = mk_evidence(self.root, slug, "2026-08-17-scan.json")
        with self.assertRaisesRegex(R.RegistrarError, "存在活动连续运行"):
            R.register(self.root, slug=slug, term="x", source_url="https://e.com",
                       task="t", evidence=[ev], by="xinci-scan")

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
                         evidence=[mk_evidence(self.root, slug, "2026-08-17b-scan.json",
                                               gates=dict(GATES_SCREEN, G3="veto"))])

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
                     reason="重跑 G3:通用工具始终未收录,空位判定为持久", expiry="2026-10-31",
                     evidence=[mk_evidence(self.root, slug, "2026-09-01-scan.json",
                                           gates={"G3": "pass"})])
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
        session = RC.start(self.root)
        RC.begin_round(self.root, session["run_id"])
        R.checked(self.root, slug, evidence=[ref], by="xinci-run", run_id=session["run_id"])
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

    def test_amend_records_gates_on_captured(self):
        """captured 上补记闸门结论:排队位/挂起位在账本上唯一的 gates 写入口。

        上轮已注册的排队候选本轮才跑出结论(典型是还债深审判出 G3=veto_window_bet):
        captured→captured 不是转移,transition 写不了它,不补记就等于账本上看不见这个挂起。
        """
        slug = "queued-term"
        initial_gates = {"G0": "pass", "G4": "pass", "G5": "pass", "G1": "pass"}
        ev = mk_evidence(self.root, slug, "2026-08-17-scan.json", gates=initial_gates)
        R.register(self.root, slug=slug, term="queued term", source_url="https://e.com",
                   task="t", evidence=[ev],
                   gates=initial_gates,
                   expiry="2026-08-25")
        session = RC.start(self.root)
        RC.begin_round(self.root, session["run_id"])
        R.amend(self.root, slug, by="xinci-run", gates={"G3": R.G3_WINDOW_BET},
                reason="还债深审:数到 4 个免费实现,收录时差实测 4 天",
                evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                      gates={"G3": R.G3_WINDOW_BET})],
                run_id=session["run_id"])
        rec = self.load(slug)
        self.assertEqual(rec["gates"]["G3"], R.G3_WINDOW_BET)
        self.assertEqual(rec["gates"]["G1"], "pass")   # 已有结论不被覆盖
        self.assertEqual(rec["state"], "captured")
        last = rec["history"][-1]
        self.assertIn("gates", last["amend"])
        self.assertEqual(last["gates"], {"G3": R.G3_WINDOW_BET})

    def test_amend_gates_only_on_captured(self):
        """出闸之后的 gates 只能由 transition 校验着写,amend 不给它们留后门。"""
        slug = self.register()
        self.to_screened(slug)
        with self.assertRaises(R.RegistrarError):
            R.amend(self.root, slug, by="xinci-scan", gates={"G3": R.G3_WINDOW_BET},
                    reason="想绕过 transition 的校验")

    def test_amend_gates_requires_expiry(self):
        """captured 带闸门结论即排队位:没有过期出口的方向会在队列里无声腐烂。"""
        slug = self.register()   # 不带 gates 注册,因此也没有 expiry
        with self.assertRaises(R.RegistrarError):
            R.amend(self.root, slug, by="xinci-scan", gates={"G1": "pass"},
                    reason="缺 expiry,应被拒",
                    evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                          gates={"G1": "pass"})])
        R.amend(self.root, slug, by="xinci-scan", gates={"G1": "pass"},
                expiry="2026-08-25", reason="同批给出排队位 expiry",
                evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                      gates={"G1": "pass"})])
        self.assertEqual(self.load(slug)["gates"]["G1"], "pass")

    def test_amend_rejects_terminal_states(self):
        slug = self.register()
        R.transition(self.root, slug, to="rejected", by="xinci-scan",
                     gates={"G1": "veto"}, reason="G1 否决",
                     evidence=[mk_evidence(self.root, slug, "2026-08-18-scan.json",
                                           gates={"G1": "veto"})])
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

    def test_transition_gates_must_be_supported_by_current_observation(self):
        slug = self.register()
        mismatch = mk_evidence(self.root, slug, "2026-08-18-scan.json",
                               gates={"G1": "veto"})
        with self.assertRaisesRegex(R.RegistrarError, "冲突"):
            R.transition(self.root, slug, to="rejected", by="xinci-scan",
                         gates={"G1": "pass"}, reason="不一致", evidence=[mismatch])
        no_sources = mk_evidence(self.root, slug, "2026-08-19-scan.json",
                                 gates={"G1": "veto"}, source_urls=[])
        with self.assertRaisesRegex(R.RegistrarError, "source_urls"):
            R.transition(self.root, slug, to="rejected", by="xinci-scan",
                         gates={"G1": "veto"}, reason="无来源", evidence=[no_sources])

    def test_window_bet_requires_structured_lag_evidence(self):
        slug = self.register()
        gates = dict(GATES_SCREEN, G3=R.G3_WINDOW_BET)
        ref = mk_evidence(self.root, slug, "2026-08-18-scan.json",
                          gates=gates, window_bet=None)
        with self.assertRaisesRegex(R.RegistrarError, "结构化 window_bet"):
            R.transition(self.root, slug, to="screened", by="xinci-scan", gates=gates,
                         window_estimate="days", expiry="2026-08-31", reason="临时空位",
                         evidence=[ref])

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
