import re
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = ROOT.parent


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class DocumentationContractsTest(unittest.TestCase):
    """锁定跨文档的行为边界，避免摘述重新偏离核心契约。"""

    def test_published_score_weights_match_runtime_schema(self):
        import qualification as Q
        # 校验对外契约表与运行中的同一组数值，避免改 Schema 后文档继续承诺旧分值。
        rows = re.findall(r"^\| ([^|]+) \| (\d+) \|", read("xinci-core/评分契约.md"), re.M)
        self.assertEqual([int(weight) for _, weight in rows], list(Q.WEIGHTS.values()))
        self.assertEqual(sum(Q.WEIGHTS.values()), 100)

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

    def test_documented_registrar_flags_exist_in_the_real_parser(self):
        """文档里写的 registrar 命令行参数必须真实存在。

        SKILL.md 与契约里手写的命令模板会和 CLI 漂移:2026-09-07 按 xinci-qualify 的
        模板给 disqualified 带上 --income-score,被 registrar 直接拒收——那份模板只
        覆盖了 qualified 那一条路径。这里把"文档提到的参数"与 argparse 实际接受的
        参数对住,改了 CLI 而忘记改文档(或反过来)就会红。
        """
        import registrar as R

        known = {cmd: {flag for flag, _ in params} for cmd, (_, params) in R.CLI_SPEC.items()}
        problems = []
        for doc in sorted(ROOT.glob("*/SKILL.md")) + sorted(ROOT.glob("xinci-core/*.md")):
            text = doc.read_text(encoding="utf-8")
            for match in re.finditer(r"registrar\.py\s+([a-z-]+)([^\n]*(?:\n\s+[^\n]*)*)", text):
                cmd, tail = match.group(1), match.group(2)
                if cmd == "--help":
                    continue
                if cmd not in known:
                    problems.append(f"{doc.parent.name}/{doc.name}: registrar.py 无子命令 {cmd}")
                    continue
                for flag in sorted(set(re.findall(r"(--[a-z][a-z0-9-]+)", tail))):
                    if flag not in known[cmd] and flag not in {"--data-root", "--help"}:
                        problems.append(f"{doc.parent.name}/{doc.name}: registrar.py {cmd} 无参数 {flag}")
        self.assertEqual(problems, [])

    def test_progressive_disclosure_keeps_history_out_of_runtime_read_set(self):
        run = read("xinci-run/SKILL.md")
        scan = read("xinci-scan/SKILL.md")
        calibration = read("xinci-core/闸门校准.md")
        quick_traps = read("xinci-core/陷阱速查.md")
        history = ROOT / "xinci-core/history/闸门校准历史.md"

        self.assertIn("不要在开局加载全部闸门", run)
        self.assertIn("疑似命中陷阱时才读取", scan)
        self.assertIn("不定义现行口径", calibration)
        self.assertIn("不能单独生成 G5 结论", quick_traps)
        self.assertTrue(history.is_file())


if __name__ == "__main__":
    unittest.main()
