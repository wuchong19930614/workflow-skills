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


if __name__ == "__main__":
    unittest.main()
