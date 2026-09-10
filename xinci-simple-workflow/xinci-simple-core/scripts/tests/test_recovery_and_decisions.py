import helpers
import copy
import json
import unittest
from unittest.mock import patch

import ledger as L
import qualification as Q
import run_log as R
import settle_candidate as S
import build_report as B
from helpers import TmpRoot, register_candidate, write_obs, VERIFY_OBS, plan_candidate


class RecoveryTest(unittest.TestCase):
    def log(self, root, run='a', stage='scan', outcome='completed', step='verify', rnd=1, budget=2):
        return R.record(root, date='2026-09-10', skill='xinci-simple-'+stage,
                        sources_opened=[], candidates_touched=[], billable_calls=0, notes=[],
                        progress={'run_id':run, 'round':rnd, 'max_rounds':budget,'source_kind':'root',
                                  'seed_value':'Generator','outcome':outcome,'next_step':step})

    def test_backlog_plan_is_executable(self):
        with TmpRoot() as root:
            for n in range(5):
                register_candidate(root, 'candidate-'+str(n))
            self.log(root)
            self.log(root, stage='verify', step='scan')
            plan = R.plan(root)
            self.assertEqual((plan['action'], plan['scan_outcome'], plan['resume']['round']), ('scan','skipped',2))
            self.log(root, stage=plan['action'], outcome=plan['scan_outcome'], rnd=2)
            self.log(root, stage='verify', step='done', rnd=2)
            self.assertIsNone(R.plan(root)['resume'])

    def test_unfinished_run_blocks_new_id(self):
        with TmpRoot() as root:
            self.log(root)
            with self.assertRaisesRegex(R.RunLogError, '未完成'):
                self.log(root, run='b')

    def test_legacy_newer_finished_run_does_not_hide_pending(self):
        with TmpRoot() as root:
            first = self.log(root)
            row = json.loads(first.read_text())
            row['recorded_at'] = '2099-01-01T00:00:00+00:00'
            row['progress'].update(run_id='newer', max_rounds=1, next_step='done')
            row['skill'] = 'xinci-simple-verify'
            (root/'运行'/'legacy-newer.json').write_text(json.dumps(row))
            self.assertEqual(R.plan(root)['resume']['run_id'], 'a')

    def test_multiple_pending_runs_are_explicit(self):
        with TmpRoot() as root:
            first = self.log(root)
            row = json.loads(first.read_text())
            row['progress']['run_id'] = 'historical-b'
            (root/'运行'/'legacy-b.json').write_text(json.dumps(row))
            plan = R.plan(root)
            self.assertTrue(plan['conflict'])
            self.assertIsNone(plan['action'])
            self.assertEqual(len(plan['active_run_ids']), 2)
            self.assertEqual(R.plan(root, 'a')['resume']['run_id'], 'a')

    def test_finish_infers_fields_and_rejects_double_billing(self):
        with TmpRoot() as root:
            self.log(root, outcome='started', step='scan')
            result = R.finish(root, run_id='a', billable_calls=2)
            row = json.loads(result.read_text())
            self.assertEqual(row['progress']['next_step'], 'verify')
            self.assertEqual(row['billable_calls'], 2)
            with self.assertRaises(R.RunLogError):
                R.finish(root, run_id='a', billable_calls=2)


class RejectionTest(unittest.TestCase):
    def test_pass_observation_cannot_be_rejected_for_any_gate(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            ref = write_obs(root, slug, 'pass-verify.json', **VERIFY_OBS)
            for gate in ('G1','G2','G3','scope','revenue'):
                with self.subTest(gate=gate), self.assertRaises(Q.QualificationError):
                    L.transition(root, slug, to='rejected', evidence=[ref], by='t', reason='错误拒绝', gate=gate)
            self.assertEqual(L.load(root)['candidates'][slug]['state'], 'found')

    def test_early_g1_does_not_require_later_gates(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            obs = copy.deepcopy(VERIFY_OBS)
            obs['ai_overview']['completes_task'] = True
            for key in ('serp_top10','trends','scope_recheck','serp_structure'):
                del obs[key]
            ref = write_obs(root, slug, 'early-verify.json', **obs)
            self.assertEqual(S.settle(root, slug, evidence=[ref], by='t', reason='首屏完成', gate='G1')['state'], 'rejected')

    def test_three_confirmed_strong_results_allow_g3_rejection(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            obs = copy.deepcopy(VERIFY_OBS)
            for row in obs['serp_top10'][:3]:
                row.update(dr=80, completes_task=True, fresh=True, format_match=True)
            obs.pop('trends')
            ref = write_obs(root, slug, 'g3-verify.json', **obs)
            self.assertEqual(S.settle(root, slug, evidence=[ref], by='t', reason='三个强对手', gate='G3')['state'], 'rejected')


class TaskManifestTest(unittest.TestCase):
    def setup_candidate(self, root):
        slug = register_candidate(root, plan=False)
        plan_candidate(root, slug, [
            {'id':'core','role':'core','keywords':['heic to jpg converter']},
            {'id':'support','role':'support','keywords':['heic to jpg']}])
        core, support = copy.deepcopy(VERIFY_OBS), copy.deepcopy(VERIFY_OBS)
        core['task_group'].update(id='core', keywords=['heic to jpg converter'])
        support['task_group'].update(id='support', keywords=['heic to jpg'], representative_keyword='heic to jpg')
        support['query_url'] = support['query_url'].replace('heic+to+jpg+converter','heic+to+jpg')
        support['ai_overview']['present'] = False  # support alone would previously pass at $210
        return slug, core, support

    def test_omitting_failed_core_cannot_pass(self):
        with TmpRoot() as root:
            slug, core, support = self.setup_candidate(root)
            core['ai_overview']['completes_task'] = True
            write_obs(root, slug, 'core-failed-verify.json', **core)
            ref = write_obs(root, slug, 'support-verify.json', **support)
            with self.assertRaisesRegex(Q.QualificationError, '不完整'):
                S.settle(root, slug, evidence=[ref], by='t', reason='只提交通过组')
            self.assertEqual(L.load(root)['candidates'][slug]['state'], 'found')

    def test_core_cannot_be_excluded_or_changed(self):
        with TmpRoot() as root:
            slug, core, support = self.setup_candidate(root)
            core['task_group']['exclusion_reason'] = '核心组失败后剔除'
            refs = [write_obs(root, slug, 'core-verify.json', **core), write_obs(root, slug, 'support-verify.json', **support)]
            with self.assertRaisesRegex(Q.QualificationError, '核心组'):
                S.settle(root, slug, evidence=refs, by='t', reason='缩小')
            with self.assertRaisesRegex(Q.QualificationError, '冻结'):
                plan_candidate(root, slug, [{'id':'new','role':'core','keywords':['heic to jpg','heic to jpg converter']}])

    def test_support_exclusion_is_bound_disclosed_and_not_counted(self):
        with TmpRoot() as root:
            slug, core, support = self.setup_candidate(root)
            core['ai_overview']['present'] = False
            core['task_group']['niche'] = 'home'  # $252 on 200K core volume
            support['task_group']['exclusion_reason'] = '支撑组直答风险不同，本次不计入'
            refs = [write_obs(root, slug, 'core-verify.json', **core), write_obs(root, slug, 'support-verify.json', **support)]
            result = S.settle(root, slug, evidence=refs, by='t', reason='核心通过，明确剔除支撑组')
            self.assertEqual(result['state'], 'verified')
            rec = L.load(root)['candidates'][slug]
            self.assertEqual(rec['revenue']['inputs']['cluster_volume'], 200000)
            self.assertEqual(rec['revenue']['base'], 252)
            self.assertEqual(len(rec['qualification']['bindings']), 3)
            self.assertIn('未计入的支撑组 support', (root/result['report']).read_text())

    def test_missing_plan_rejected(self):
        with TmpRoot() as root:
            slug = register_candidate(root, plan=False)
            ref = write_obs(root, slug, 'v-verify.json', **VERIFY_OBS)
            with self.assertRaises(Q.QualificationError):
                S.settle(root, slug, evidence=[ref], by='t', reason='未登记计划')


class SettlementTest(unittest.TestCase):
    def test_report_failure_can_resume_without_second_transition(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            ref = write_obs(root, slug, 'v-verify.json', **VERIFY_OBS)
            with patch.object(B, 'build', side_effect=OSError('模拟报告写入失败')):
                with self.assertRaisesRegex(Q.QualificationError, '相同结算命令恢复'):
                    S.settle(root, slug, evidence=[ref], by='t', reason='完整核验')
            history = L.load(root)['candidates'][slug]['history']
            S.settle(root, slug, evidence=[ref], by='t', reason='完整核验')
            self.assertEqual(L.load(root)['candidates'][slug]['history'], history)
            self.assertTrue((root/'报告'/f'{slug}.html').is_file())
