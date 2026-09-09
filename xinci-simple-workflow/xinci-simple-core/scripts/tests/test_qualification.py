import helpers
import copy
import unittest
import ledger as L
import qualification as Q
from helpers import TmpRoot, register_candidate, write_obs, VERIFY_OBS


class QualificationTest(unittest.TestCase):
    def assess(self, root, slug, obs):
        ref = write_obs(root, slug, 'test-verify.json', **obs)
        return Q.assess(root, L.load(root)['candidates'][slug], [ref])

    def test_missing_or_failed_gates_block(self):
        patches = [
            ('browser_preflight', {'logged_out': False}), ('ai_overview', {'completes_task': True}),
            ('direct_answer', {'native_widget_completes_task': True}), ('serp_structure', {'blocked': True}),
            ('trends', {'status':'unknown'}), ('scope_recheck', {'ymyl': True}),
        ]
        with TmpRoot() as root:
            slug = register_candidate(root)
            for key, patch in patches:
                obs = copy.deepcopy(VERIFY_OBS)
                obs[key].update(patch)
                with self.subTest(key=key), self.assertRaises(Q.QualificationError):
                    self.assess(root, slug, obs)
            for key in ('browser_preflight','ai_overview','direct_answer','serp_top10','trends','scope_recheck','task_group'):
                obs = copy.deepcopy(VERIFY_OBS)
                del obs[key]
                with self.subTest(missing=key), self.assertRaises(Q.QualificationError):
                    self.assess(root, slug, obs)

    def test_top_results_require_complete_read(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            obs = copy.deepcopy(VERIFY_OBS)
            obs['serp_top10'] = obs['serp_top10'][:8]
            with self.assertRaisesRegex(Q.QualificationError, '不足 10'):
                self.assess(root, slug, obs)
            obs.update(natural_results_exhausted=True, exhaustion_evidence='完整首页只有八条自然结果')
            self.assess(root, slug, obs)

    def test_duplicate_keywords_and_query_mismatch_block(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            obs = copy.deepcopy(VERIFY_OBS)
            obs['task_group']['keywords'] *= 2
            with self.assertRaisesRegex(Q.QualificationError, '重复'):
                self.assess(root, slug, obs)
            obs = copy.deepcopy(VERIFY_OBS)
            obs['query_url'] = obs['query_url'].replace('heic+to+jpg+converter', 'unrelated')
            with self.assertRaisesRegex(Q.QualificationError, '代表|representative'):
                self.assess(root, slug, obs)

    def test_multiple_forms_sum_and_do_not_double_count(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            a, b = copy.deepcopy(VERIFY_OBS), copy.deepcopy(VERIFY_OBS)
            a['task_group']['keywords'] = ['heic to jpg converter']
            b['task_group'].update(id='lookup', keywords=['heic to jpg'], representative_keyword='heic to jpg', form='lookup')
            b['query_url'] = b['query_url'].replace('heic+to+jpg+converter','heic+to+jpg')
            refs = [write_obs(root, slug, 'a-verify.json', **a), write_obs(root, slug, 'b-verify.json', **b)]
            form, rev, _ = Q.assess(root, L.load(root)['candidates'][slug], refs)
            self.assertEqual(form, 'mixed')
            self.assertEqual(rev['inputs']['cluster_volume'], 500000)
            self.assertEqual(rev['base'], 172.2)
            b['task_group']['keywords'].append('heic to jpg converter')
            write_obs(root, slug, 'b-verify.json', **b)
            with self.assertRaisesRegex(Q.QualificationError, '重复'):
                Q.assess(root, L.load(root)['candidates'][slug], refs)

    def test_strong_three_or_unknown_blocks(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            for dr in (None, 80):
                obs = copy.deepcopy(VERIFY_OBS)
                for row in obs['serp_top10'][:3]:
                    row.update(completes_task=True, dr=dr, fresh=True, format_match=True)
                with self.subTest(dr=dr), self.assertRaisesRegex(Q.QualificationError, 'G3'):
                    self.assess(root, slug, obs)
