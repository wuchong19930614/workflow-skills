import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _code_blocks(path):
    text = path.read_text(encoding="utf-8")
    return re.findall(r"```(?:bash)?\n(.*?)```", text, re.DOTALL)


class DocumentationContractsTest(unittest.TestCase):
    def test_xinci_run_begin_round_examples_declare_round_type(self):
        path = ROOT / "xinci-run" / "SKILL.md"
        blocks = [b for b in _code_blocks(path) if "run_controller.py begin-round" in b]
        self.assertTrue(blocks)
        for block in blocks:
            self.assertIn("--round-type", block)

    def test_xinci_run_record_round_example_reconciles_source_outcomes(self):
        path = ROOT / "xinci-run" / "SKILL.md"
        blocks = [b for b in _code_blocks(path)
                  if "run_controller.py record-round" in b]
        self.assertTrue(blocks)
        for block in blocks:
            outcomes_match = re.search(r"--source-family-outcomes '([^']+)'", block)
            funnel_match = re.search(r"--funnel '([^']+)'", block)
            self.assertIsNotNone(outcomes_match)
            self.assertIsNotNone(funnel_match)
            self.assertIn("--g1-checks", block)
            self.assertIn("--source-family-counts", block)
            outcomes = json.loads(outcomes_match.group(1))
            funnel = json.loads(funnel_match.group(1))
            self.assertEqual(sum(row["formal"] for row in outcomes.values()),
                             funnel["extracted"])
            self.assertEqual(sum(row["deep"] for row in outcomes.values()),
                             funnel["deep_audited"])

    def test_xinci_scan_register_examples_include_site_scope(self):
        path = ROOT / "xinci-scan" / "SKILL.md"
        blocks = [b for b in _code_blocks(path) if "registrar.py register" in b]
        self.assertTrue(blocks)
        for block in blocks:
            command = block.split("registrar.py transition", 1)[0]
            self.assertIn("--site-thesis", command)
            self.assertGreaterEqual(command.count("--task-family"), 2)

    def test_current_scan_does_not_use_subscription_as_global_veto(self):
        text = (ROOT / "xinci-scan" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("订阅线为 `tentative_veto` 时已无可用盈利线", text)
        self.assertNotIn("订阅线 `tentative_veto` 时没有可用盈利线", text)
        self.assertIn("只有所有适用线均暂定否决才按 G6 预筛出局", text)

    def test_g3_current_contract_names_traffic_and_nontraffic_lines(self):
        text = (ROOT / "xinci-core" / "闸门契约.md").read_text(encoding="utf-8")
        self.assertIn("当前通过线全部依赖自然流量", text)
        self.assertIn("subscription / lead_generation / transaction / paid_report", text)
        self.assertIn("affiliate / advertising", text)

    def test_mature_volume_threshold_does_not_veto_whole_candidate(self):
        text = (ROOT / "xinci-mature" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("两条都只筛流量线", text)
        self.assertIn("不得把 advertising 的量级门套给", text)
        self.assertNotIn("**簇内词总数 N** < 约 1,000 → 弃", text)

    def test_all_g1_stage_skills_require_cluster_counterfactual(self):
        for relative in ("xinci-scan/SKILL.md", "xinci-track/SKILL.md",
                         "xinci-mature/SKILL.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("cluster_counterfactual", text, relative)
            self.assertIn("atomic_only", text, relative)

    def test_readmes_expose_mature_and_forbid_manual_manifests(self):
        root_readme = (ROOT.parent / "README.md").read_text(encoding="utf-8")
        workflow_readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("xinci-mature", root_readme)
        self.assertIn("xinci-mature", workflow_readme)
        self.assertIn("两条赛道与六条盈利线", root_readme)
        self.assertNotIn("清单全靠手写", root_readme + workflow_readme)

    def test_scan_repeat_task_only_vetoes_subscription(self):
        gate = (ROOT / "xinci-core" / "闸门契约.md").read_text(encoding="utf-8")
        scan = (ROOT / "xinci-scan" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("只把 subscription 写成 `tentative_veto`", gate)
        self.assertIn("只先否决 subscription", scan)
        self.assertNotIn("没有被迫/重复任务(只值一周好奇)、或", scan)

    def test_global_self_serve_veto_requires_all_delivery_lines_to_fail(self):
        gate = (ROOT / "xinci-core" / "闸门契约.md").read_text(encoding="utf-8")
        schema = json.loads((ROOT / "xinci-core" / "数据结构" /
                             "observation.schema.json").read_text(encoding="utf-8"))
        self.assertIn("六条适用盈利线全部无法成立", gate)
        self.assertIn("不得使用全局入口否决", gate)
        self.assertNotIn("要,第③项就不成立,G6 出局", gate)
        description = schema["properties"]["g6_entry_veto"]["description"]
        self.assertIn("所有声称交付", description)
        self.assertIn("只影响部分盈利线时不得填写", description)

    def test_source_share_minimum_sample_is_documented(self):
        lifecycle = (ROOT / "xinci-core" / "生命周期契约.md").read_text(encoding="utf-8")
        run = (ROOT / "xinci-run" / "SKILL.md").read_text(encoding="utf-8")
        for text in (lifecycle, run):
            self.assertIn("达到 5 条", text)
            self.assertIn("5 条以前", text)

    def test_mature_tool_pattern_is_checked_at_g2_not_zero_cost(self):
        mature = (ROOT / "xinci-mature" / "SKILL.md").read_text(encoding="utf-8")
        zero_cost, g2 = mature.split("### 第 3 层", 1)[0], mature.split("### 第 6 层", 1)[1]
        self.assertNotIn("首页出现专做这件事的站", zero_cost)
        self.assertIn("需要 G2 现场证据", g2)

    def test_lifecycle_names_mature_and_all_nontraffic_g3_lines(self):
        lifecycle = (ROOT / "xinci-core" / "生命周期契约.md").read_text(encoding="utf-8")
        self.assertIn("五个有写入能力的阶段 skill", lifecycle)
        self.assertIn("xinci-scan / track / mature / qualify / decide", lifecycle)
        self.assertGreaterEqual(
            lifecycle.count("subscription / lead_generation / transaction / paid_report"), 2)

    def test_mature_guide_declares_existing_three_step_flow(self):
        guide = (ROOT / "xinci-core" / "数据采集指南.md").read_text(encoding="utf-8")
        self.assertIn("现行执行流程固定为三步", guide)
        self.assertIn("xinci-mature 已承接这第三步", guide)
        self.assertNotIn("现行的两步流程", guide)


if __name__ == "__main__":
    unittest.main()
