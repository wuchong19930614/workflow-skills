import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = ROOT.parent


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class DocumentationContractsTest(unittest.TestCase):
    """锁定跨文档的行为边界，避免摘述重新偏离核心契约。"""

    def test_continuous_run_has_one_executor_per_round(self):
        run = read("xinci-run/SKILL.md")
        self.assertIn("每一轮只派一个轮次子代理", run)
        self.assertIn("同一轮不得按阶段更换子代理", run)
        self.assertNotIn("每个阶段动作(一次扫描轮、一个候选的复查/认定/决策)派一个子代理", run)

    def test_reopen_owners_match_lane_contract(self):
        common = read("xinci-core/通用约定.md")
        lifecycle = read("xinci-core/生命周期契约.md")
        track = read("xinci-track/SKILL.md")
        mature = read("xinci-mature/SKILL.md")
        self.assertIn("到期 SERP 型 rejected 的复核与 reopen", common)
        self.assertIn("new 道由 xinci-track 复核", lifecycle)
        self.assertIn("--by xinci-track", track)
        self.assertIn("--by xinci-mature", mature)

    def test_ymyl_prescreen_is_not_named_g3(self):
        mature = read("xinci-mature/SKILL.md")
        guide = read("xinci-core/数据采集指南.md")
        self.assertIn('"stage":"prescreen"', mature)
        self.assertIn('"reason_code":"ymyl_high_competition"', mature)
        self.assertNotIn('"gate":"G3","reason":"[YMYL]', mature)
        self.assertIn("不是 G3 exact-task completion 结论", guide)

    def test_new_trap_category_requires_contract_authorization(self):
        lifecycle = read("xinci-core/生命周期契约.md")
        run = read("xinci-run/SKILL.md")
        track = read("xinci-track/SKILL.md")
        self.assertIn("不包含在 xinci-run 的标准授权里", lifecycle)
        self.assertIn("不在启动 xinci-run 的标准授权内", run)
        self.assertIn("新增通用判据属于契约变更,须用户确认", track)
        self.assertIn("用户确认后", lifecycle)

    def test_root_readme_does_not_define_a_default_data_root(self):
        root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("用户配置的数据区", root_readme)
        self.assertIn("不是规范默认值", root_readme)
        self.assertIn("默认是用户逐步确认的单步模式", root_readme)


if __name__ == "__main__":
    unittest.main()
