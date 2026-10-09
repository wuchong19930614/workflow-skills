import helpers
import copy
import unittest
import ledger as L
import qualification as Q
from helpers import plan_candidate, TmpRoot, register_candidate, write_obs, VERIFY_OBS


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
            slug = register_candidate(root, plan=False)
            plan_candidate(root, slug, [{'id':'convert','role':'core','keywords':['heic to jpg converter']}, {'id':'lookup','role':'support','keywords':['heic to jpg']}])
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


class NearMeQualificationTest(unittest.TestCase):
    def test_near_me_group_detected_from_representative_query(self):
        with TmpRoot() as root:
            slug = near_me_candidate(root)
            refs = near_me_observations(root, slug)
            _, rev, _ = Q.assess(root, L.load(root)['candidates'][slug], refs)
            groups = {g['id']: g['revenue'] for g in rev['inputs']['groups']}
            self.assertTrue(groups['nearme']['inputs']['near_me'])
            self.assertFalse(groups['generic']['inputs']['near_me'])
            # 两组同为 tool/tech、AIO 未完成、K=1;near me 组再乘 0.2
            self.assertEqual(groups['nearme']['base'], round(500000 * 0.10 / 1000 * 10 * 0.6 * 0.7 * 0.2, 2))
            self.assertEqual(groups['generic']['base'], round(100000 * 0.10 / 1000 * 10 * 0.6 * 0.7, 2))


def near_me_candidate(root, slug='dog-park-near-me'):
    from helpers import SEED, PROXY, entry_candidate
    ev = write_obs(root, slug, 'scan.json')
    L.register(root, slug=slug, primary_keyword='dog park near me',
               cluster={'total_volume': 900000, 'keywords': [{'term': 'dog park near me', 'volume': 500000, 'kd': 40},
                                                            {'term': 'dog park', 'volume': 100000, 'kd': 30}]},
               seed=SEED, proxy=PROXY, evidence=[ev], by='test', reason='准入')
    entry_candidate(root, slug)
    plan_candidate(root, slug, [{'id': 'nearme', 'role': 'core', 'keywords': ['dog park near me']},
                                {'id': 'generic', 'role': 'support', 'keywords': ['dog park']}])
    return slug


def near_me_observations(root, slug, groups=('nearme', 'generic')):
    refs = []
    for gid, term in (('nearme', 'dog park near me'), ('generic', 'dog park')):
        if gid not in groups:
            continue
        obs = copy.deepcopy(VERIFY_OBS)
        obs['task_group'].update(id=gid, keywords=[term], representative_keyword=term,
                                 coverage_reason='同一找狗公园任务')
        obs['query_url'] = 'https://www.google.com/search?q=' + term.replace(' ', '+') + '&gl=us&hl=en&pws=0'
        refs.append(write_obs(root, slug, f'{gid}-verify.json', **obs))
    return refs

