import helpers
import json
import subprocess
import sys
import unittest
from pathlib import Path
from helpers import TmpRoot, register_candidate, write_obs, VERIFY_OBS

SCRIPTS = Path(__file__).resolve().parents[1]


class CliFlowTest(unittest.TestCase):
    def test_qualification_file_transition_report_and_validate(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            ref = write_obs(root, slug, 'cli-verify.json', **VERIFY_OBS)
            def run(script, *args):
                result = subprocess.run([sys.executable, str(SCRIPTS / script), '--data-root', str(root), *args], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout
            income = root / 'income.json'
            income.write_text(run('qualification.py', '--slug', slug, '--evidence', ref))
            self.assertTrue(json.loads(income.read_text())['passes'])
            run('ledger.py', 'transition', '--slug', slug, '--to', 'verified', '--form', 'tool', '--revenue-file', str(income), '--evidence', ref, '--by', 'test', '--reason', '完整核验')
            run('build_report.py', '--slug', slug)
            self.assertIn('0 个错误', run('validate_ledger.py'))
            report = json.loads(run('report_status.py', '--json'))
            self.assertIsNone(report['verified'][0]['integrity_error'])

    def test_progress_cli_can_resume(self):
        with TmpRoot() as root:
            args = [sys.executable, str(SCRIPTS/'run_log.py'), '--data-root', str(root)]
            log = subprocess.run(args + ['--date','2026-09-09','--skill','xinci-simple-scan','--run-id','cli-run','--round','1','--max-rounds','2','--source-kind','root','--seed-value','Generator','--outcome','completed','--next-step','verify'],capture_output=True,text=True)
            self.assertEqual(log.returncode, 0, log.stderr)
            plan = subprocess.run(args + ['--plan'],capture_output=True,text=True)
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertEqual(json.loads(plan.stdout)['resume']['run_id'], 'cli-run')
