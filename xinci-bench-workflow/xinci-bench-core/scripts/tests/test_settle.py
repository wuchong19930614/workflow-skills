import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import settle as S
import validate_ledger as V
import write_observation as W
from _common import BenchError, load_ledger, sha256_file
from helpers import (TmpRoot, benchmark_record, cluster_record, delivery_obs, demand_obs, serp_obs,
                     setup_direction)

ON = "2026-10-20"


class SettleTest(unittest.TestCase):
    def test_go_builds_doc_with_brief_and_validates(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            rec = S.settle(root, slug, "go", None, "标杆 9 个月到 2 万", "Journey 实际 RPM", on=ON)
            self.assertEqual(rec["state"], "go")
            self.assertEqual(len(rec["bindings"]["files"]), len(refs))
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn("## 第二部分 建站简报", md)
            self.assertIn("第 6 个月 Search Console 点击低于", md)
            self.assertEqual(V.check_all(root), [])

    def test_revenue_reject_has_no_brief(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root, us_organic_m12=5400)
            with self.assertRaisesRegex(BenchError, "模型结论"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            rec = S.settle(root, slug, "rejected", "revenue", "基准只有 $10.80", "标杆是否还会涨", on=ON)
            self.assertEqual(rec["state"], "rejected")
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            self.assertNotIn("建站简报", md)
            self.assertIn("收入不足", md)

    def test_go_refuses_stale_clusters(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root, stale=True)
            with self.assertRaisesRegex(BenchError, "90 天"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            self.assertEqual(load_ledger(root)["directions"][slug]["state"], "found")

    def test_answered_requires_all_clusters_and_serp(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "所有簇"):
                S.settle(root, slug, "rejected", "answered", "r", "u", on=ON)
            ref = W.write(root, serp_obs(slug, answered=True))
            L.update(root, slug, {"clusters": [cluster_record(answered=True)]}, [ref])
            rec = S.settle(root, slug, "rejected", "answered", "AI 概览直接给县名", "定位后是否仍答", on=ON)
            self.assertEqual(rec["state"], "rejected")

    def test_scope_needs_hit(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            with self.assertRaisesRegex(BenchError, "命中项"):
                S.settle(root, slug, "rejected", "scope", "r", "u", on=ON)
            rec = S.settle(root, slug, "rejected", "scope", "克隆受版权游戏", "无", scope_hit="infringement", on=ON)
            self.assertEqual(rec["decision"]["scope_hit"], "infringement")

    def test_recovery_rebuilds_docs_without_new_history(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            (root / "文档" / f"{slug}.html").unlink()
            n = len(load_ledger(root)["directions"][slug]["history"])
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            self.assertEqual(len(load_ledger(root)["directions"][slug]["history"]), n)
            self.assertTrue((root / "文档" / f"{slug}.html").is_file())
            with self.assertRaisesRegex(BenchError, "不一致"):
                S.settle(root, slug, "go", "revenue", "r", "u", on=ON)

    def test_parked_then_go_archives_old_doc(self):
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            S.settle(root, slug, "parked", None, "曲线读不出", "Semrush 域名模块恢复后的读数", on=ON)
            S.settle(root, slug, "go", None, "补到曲线后过线", "Journey RPM", on=ON)
            self.assertEqual(len(list((root / "文档" / "历史").glob(f"{slug}-*.md"))), 1)
            self.assertEqual(V.check_all(root), [])


    def test_deleted_observation_gives_clear_refusal(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            (root / refs[3]).unlink()
            with self.assertRaisesRegex(BenchError, "观察不存在"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)


    def test_parked_then_rejected_go_restores_parked(self):
        # 审查 C1:parked 改判 go 被拒后,状态、结论、决策书都要保持 parked 原样,不能卡死
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            S.settle(root, slug, "parked", None, "曲线读不出", "u", on=ON)
            md = (root / "文档" / f"{slug}.md").read_text(encoding="utf-8")
            ref = W.write(root, delivery_obs(slug, feasible=False))
            L.update(root, slug, {}, [ref])
            with self.assertRaisesRegex(BenchError, "交付依据不成立"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual((rec["state"], rec["decision"]["verdict"]), ("parked", "parked"))
            self.assertEqual((root / "文档" / f"{slug}.md").read_text(encoding="utf-8"), md)
            self.assertEqual(list((root / "文档" / "历史").iterdir()), [])
            self.assertEqual(V.check_all(root), [])
            S.settle(root, slug, "rejected", "benchmark", "改判", "u", on=ON)

    def test_go_missing_brief_is_clean_refusal(self):
        # 审查 I1:缺 brief 观察时给"go 缺观察",账本不留 decision/bindings
        with TmpRoot() as root:
            slug, _ = setup_direction(root, with_brief=False)
            with self.assertRaisesRegex(BenchError, "go 缺观察"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)
            rec = load_ledger(root)["directions"][slug]
            self.assertEqual((rec["decision"], rec["bindings"], rec["model"]), (None, None, None))
            self.assertFalse((root / "文档" / f"{slug}.md").exists())

    def test_go_refuses_ledger_numbers_not_in_observation(self):
        # 审查 I3:账本里的标杆读数必须等于绑定的 benchmark 观察
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            dom = f"{slug}.example.com"
            L.update(root, slug, {"benchmarks": [benchmark_record(dom, us_organic_m12=200000)]})
            with self.assertRaisesRegex(BenchError, "us_organic_m12"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)

    def test_go_refuses_covered_demand_below_benchmark_clusters(self):
        # 审查 I3:标杆覆盖需求不能小于"标杆已做"的簇量合计(分母变小会抬高份额率)
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            dom = f"{slug}.example.com"
            L.update(root, slug, {"benchmarks": [benchmark_record(dom, us_organic_m12=20000, covered_demand=50000)]})
            with self.assertRaisesRegex(BenchError, "covered_demand"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)

    def test_go_requires_serp_for_every_counted_cluster(self):
        # 审查 I4:每个计入需求的簇都要有 serp 观察
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            d = demand_obs(slug, clusters=[
                {"id": "core", "seed_term": "what county am i in", "volume": 100000, "measured_at": "2026-10-13",
                 "coverage": "benchmark", "near_me": False},
                {"id": "extra", "seed_term": "school district", "volume": 1000000, "measured_at": "2026-10-13",
                 "coverage": "ours", "near_me": False}])
            ref = W.write(root, d)
            L.update(root, slug, {"clusters": [cluster_record(), cluster_record(id="extra", seed_term="school district",
                                                                                volume=1000000, coverage="ours")]}, [ref])
            with self.assertRaisesRegex(BenchError, "serp"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)

    def test_go_refuses_counted_cluster_answered_in_serp(self):
        # 审查 I4:serp 观察说某簇已被首屏答完,账本就不能把它计入需求
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            ref = W.write(root, serp_obs(slug, answered=True))
            L.update(root, slug, {}, [ref])
            with self.assertRaisesRegex(BenchError, "答完"):
                S.settle(root, slug, "go", None, "r", "u", on=ON)


class ValidateTest(unittest.TestCase):
    def test_detects_tampering(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            md = root / "文档" / f"{slug}.md"
            md.write_text(md.read_text(encoding="utf-8") + "手改\n", encoding="utf-8")
            self.assertTrue(any("md/html" in e for e in V.check_all(root)))

    def test_detects_md_rewritten_with_regenerated_html(self):
        # 审查 I2:手改 md 再重生成 html,也要被抓到
        import build_doc_html
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            md = root / "文档" / f"{slug}.md"
            md.write_text(md.read_text(encoding="utf-8").replace("$160.00", "$999.00"), encoding="utf-8")
            build_doc_html.build(md)
            self.assertTrue(any("与账本不一致" in e for e in V.check_all(root)))

    def test_found_with_leftover_decision_flagged(self):
        # 审查 I1:found 带着 decision/bindings 说明结算没走完
        from _common import save_ledger
        with TmpRoot() as root:
            slug, _ = setup_direction(root)
            ledger = load_ledger(root)
            ledger["directions"][slug]["decision"] = {"verdict": "go"}
            save_ledger(root, ledger)
            self.assertTrue(any("结算未完成" in e for e in V.check_all(root)))

    def test_detects_changed_observation(self):
        with TmpRoot() as root:
            slug, refs = setup_direction(root)
            S.settle(root, slug, "go", None, "r", "u", on=ON)
            p = root / refs[2]
            p.write_text(p.read_text(encoding="utf-8").replace("Organic Research", "Organic  Research"), encoding="utf-8")
            self.assertTrue(any("绑定观察已变动" in e for e in V.check_all(root)))

    def test_detects_bad_recheck(self):
        with TmpRoot() as root:
            import json
            from _common import REJECTS_REL
            (root / REJECTS_REL).write_text(json.dumps({"schema_version": 1, "domains": {
                "a.com": {"failed": ["B2"], "readings": "x", "at": "2026-10-13", "recheck_after": "2027-01-11",
                          "observation": "证据/_scan/x.json"}}}), encoding="utf-8")
            self.assertTrue(any("复查" in e for e in V.check_all(root)))


if __name__ == "__main__":
    unittest.main()
