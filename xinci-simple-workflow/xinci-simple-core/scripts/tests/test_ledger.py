import helpers  # initializes script import path
import copy
import unittest
import ledger as L
import qualification as Q
from helpers import TmpRoot, write_obs, VERIFY_OBS, revenue_for, register_candidate, verified_candidate


class LedgerTest(unittest.TestCase):
    def test_register_and_duplicate(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            self.assertEqual(L.load(root)['candidates'][slug]['state'], 'found')
            with self.assertRaises(L.LedgerError):
                register_candidate(root)

    def test_pass_binds_and_recomputes(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            rec = L.load(root)['candidates'][slug]
            self.assertEqual(rec['revenue']['base'], 210)
            self.assertEqual(rec['qualification']['qualified_volume'], 500000)
            self.assertEqual(len(rec['qualification']['bindings']), 2)
            Q.check_bound(root, rec)
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to='found', evidence=rec['evidence_refs'], by='t', reason='x')

    def test_tampered_income_and_incomplete_evidence_refused(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            ev = write_obs(root, slug, 'v-verify.json', **VERIFY_OBS)
            revenue = revenue_for(root, slug, [ev])
            for patch in ({'base': 9999}, {'threshold': 1}, {'assumptions_version': 'old'}):
                with self.subTest(patch=patch), self.assertRaises(L.LedgerError):
                    L.transition(root, slug, to='verified', evidence=[ev], by='t', reason='x', form='tool', revenue=dict(revenue, **patch))
            broken = copy.deepcopy(VERIFY_OBS)
            broken['trends']['status'] = 'unknown'
            bad = write_obs(root, slug, 'bad-verify.json', **broken)
            with self.assertRaisesRegex(L.LedgerError, '季节性'):
                L.transition(root, slug, to='verified', evidence=[bad], by='t', reason='x', form='tool', revenue=revenue)
            self.assertEqual(L.load(root)['candidates'][slug]['state'], 'found')

    def test_parked_can_be_completed(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            ev = write_obs(root, slug, 'v-verify.json', **VERIFY_OBS)
            L.transition(root, slug, to='parked', evidence=[ev], by='t', reason='待补采')
            L.transition(root, slug, to='verified', evidence=[ev], by='t', reason='完整', form='tool', revenue=revenue_for(root, slug, [ev]))
            self.assertEqual([h['to'] for h in L.load(root)['candidates'][slug]['history']], ['found','found','found','parked','verified'])

    def test_requalify_requires_eligible_rejection_and_change(self):
        for gate in ('revenue', 'G1', 'G2', 'G3'):
            with self.subTest(gate=gate), TmpRoot() as root:
                slug = register_candidate(root)
                ev = write_obs(root, slug, 'v-verify.json', **VERIFY_OBS)
                # Historical records may predate strict rejection validation.
                data = L.load(root)
                data['candidates'][slug]['state'] = 'rejected'
                data['candidates'][slug]['history'].append({'at':'2026-09-09T00:00:00+00:00','from':'found','to':'rejected','by':'old','reason':'旧裁决','gate':gate})
                L.save(root, data)
                kwargs = dict(evidence=[ev], by='t', reason='重审', form='tool', revenue=revenue_for(root, slug, [ev]))
                with self.assertRaises(L.LedgerError):
                    L.requalify(root, slug, **kwargs)
                if gate == 'revenue':
                    rec = L.requalify(root, slug, **kwargs, change_basis='用户批准门槛变更')
                    self.assertEqual(rec['state'], 'verified')
                else:
                    with self.assertRaises(L.LedgerError):
                        L.requalify(root, slug, **kwargs, change_basis='降低收入门槛')

    def test_reopen_only_competition_gate_with_audit_and_change(self):
        for gate in ('G3', 'revenue', 'scope'):
            with self.subTest(gate=gate), TmpRoot() as root:
                slug = register_candidate(root)
                plan = L.load(root)['candidates'][slug].get('task_plan')
                ev = write_obs(root, slug, 'v-verify.json', **VERIFY_OBS)
                audit = write_obs(root, slug, 'a-verify.json', **VERIFY_OBS, audit_basis='沿用原观察,按用户批准口径改判')
                data = L.load(root)
                data['candidates'][slug]['state'] = 'rejected'
                data['candidates'][slug]['history'].append({'at':'2026-09-09T00:00:00+00:00','from':'found','to':'rejected','by':'old','reason':'旧裁决','gate':gate})
                L.save(root, data)
                if gate != 'G3':
                    with self.assertRaises(L.LedgerError):
                        L.reopen(root, slug, evidence=[audit], by='t', reason='重开', change_basis='用户批准')
                    continue
                with self.assertRaises(L.LedgerError):
                    L.reopen(root, slug, evidence=[audit], by='t', reason='重开')
                with self.assertRaises(L.LedgerError):
                    L.reopen(root, slug, evidence=[ev], by='t', reason='重开', change_basis='用户批准')
                rec = L.reopen(root, slug, evidence=[audit], by='t', reason='重开', change_basis='用户批准')
                self.assertEqual(rec['state'], 'found')
                self.assertEqual(rec['history'][-1]['reopened_gate'], 'G3')
                self.assertEqual(rec.get('task_plan'), plan)
                L.transition(root, slug, to='verified', evidence=[ev], by='t', reason='完整', form='tool', revenue=revenue_for(root, slug, [ev]))
                self.assertEqual(L.load(root)['candidates'][slug]['state'], 'verified')

    def test_rejection_requires_gate_reason_and_verify(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            ev = write_obs(root, slug, 'v-verify.json', **VERIFY_OBS)
            for extra in ({'reason': '', 'gate':'G1'}, {'reason':'x'}):
                with self.assertRaises(L.LedgerError):
                    L.transition(root, slug, to='rejected', evidence=[ev], by='t', **extra)
            fail = copy.deepcopy(VERIFY_OBS)
            fail['ai_overview']['completes_task'] = True
            ev = write_obs(root, slug, 'failed-verify.json', **fail)
            L.transition(root, slug, to='rejected', evidence=[ev], by='t', reason='G1 实测直答', gate='G1')
            self.assertEqual(L.list_candidates(root, 'rejected')[0]['slug'], slug)

class AuditTest(unittest.TestCase):
    def test_invalidate_preserves_history_and_archives_report(self):
        import build_report as B
        with TmpRoot() as root:
            slug = verified_candidate(root)
            md = B.build(root, slug)
            original = md.read_bytes()
            before = L.load(root)['candidates'][slug]['history']
            ev = write_obs(root, slug, 'audit-verify.json', stage='verify', audit_basis='基于旧材料重审范围', scope_recheck={'ymyl':True})
            rec = L.invalidate(root, slug, to='rejected', evidence=[ev], gate='scope', by='t', reason='任务涉及人身安全')
            self.assertEqual(rec['history'][:-1], before)
            self.assertEqual(rec['state'], 'rejected')
            self.assertFalse(md.exists())
            archived = rec['history'][-1]['archived_reports']
            self.assertEqual(len(archived), 2)
            self.assertEqual((root / archived[0]).read_bytes(), original)

    def test_invalidate_refuses_unsubstantiated_scope_claim(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            ev = write_obs(root, slug, 'audit-verify.json', stage='verify', audit_basis='audit')
            with self.assertRaises(L.LedgerError):
                L.invalidate(root, slug, to='rejected', evidence=[ev], gate='scope', by='t', reason='x')
            self.assertEqual(L.load(root)['candidates'][slug]['state'], 'verified')

    def test_refresh_adds_evidence_and_preserves_old_cluster(self):
        from helpers import CLUSTER
        with TmpRoot() as root:
            slug = register_candidate(root)
            ev = write_obs(root, slug, 'new-scan.json')
            rec = L.refresh_cluster(root, slug, cluster=dict(CLUSTER, total_volume=700000), evidence=[ev], by='t', reason='补采')
            self.assertEqual(rec['history'][-1]['previous_cluster']['total_volume'], 600000)
            self.assertEqual(rec['cluster']['total_volume'], 700000)
            self.assertEqual(rec['state'], 'found')

    def test_prescreen_cannot_fake_income_or_use_qualified_subset(self):
        import revenue_model as M
        with TmpRoot() as root:
            slug = register_candidate(root)
            ev = write_obs(root, slug, 'pre-verify.json', stage='verify', prescreen={'basis':'tool tech', 'result':M.upper_bound(1000, ['tool'], ['tech'])})
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to='rejected', evidence=[ev], gate='revenue_prescreen', by='t', reason='不足')


class RebaseTest(unittest.TestCase):
    """假设表改版后,既有 verified 按已绑定观察重算。"""

    def test_rebase_updates_version_and_keeps_unaffected_income(self):
        from unittest import mock
        import revenue_model as M
        with TmpRoot() as root:
            with mock.patch.object(M, 'VERSION', '2026-09-09.2'):
                slug = verified_candidate(root)
            before = L.load(root)['candidates'][slug]
            with self.assertRaises(Q.QualificationError):
                Q.check_bound(root, before)  # 旧版本收入在新假设表下不能直接通过校验
            rec = L.rebase(root, slug, by='t', reason='假设表升版', change_basis='用户批准 near me ×0.2')
            self.assertEqual(rec['state'], 'verified')
            self.assertEqual(rec['revenue']['assumptions_version'], M.VERSION)
            self.assertEqual(rec['revenue']['base'], before['revenue']['base'])
            self.assertEqual(rec['history'][:-1], before['history'])
            last = rec['history'][-1]
            self.assertEqual((last['action'], last['to']), ('rebase', 'verified'))
            self.assertEqual(last['previous_revenue']['assumptions_version'], '2026-09-09.2')
            Q.check_bound(root, rec)
            with self.assertRaisesRegex(Q.QualificationError, '无需 rebase'):
                L.rebase(root, slug, by='t', reason='重复', change_basis='同上')

    def test_rebase_rejects_near_me_candidate_and_archives_report(self):
        from unittest import mock
        import revenue_model as M
        import build_report as B
        from test_qualification import near_me_candidate, near_me_observations
        with TmpRoot() as root:
            with mock.patch.object(M, 'VERSION', '2026-09-09.2'), mock.patch.object(M, 'HAIRCUT_NEAR_ME', 1.0):
                slug = near_me_candidate(root)
                refs = near_me_observations(root, slug, groups=('nearme',))
                plan = {'core_reason': '找狗公园', 'groups': [{'id': 'nearme', 'role': 'core', 'keywords': ['dog park near me']}]}
                data = L.load(root); data['candidates'][slug]['task_plan'] = plan; L.save(root, data)
                rec = L.load(root)['candidates'][slug]
                form, revenue, _ = Q.assess(root, rec, refs)
                self.assertEqual(revenue['base'], 210)
                L.transition(root, slug, to='verified', evidence=refs, by='t', reason='旧假设通过', form=form, revenue=revenue)
                B.build(root, slug)
            rec = L.rebase(root, slug, by='t', reason='near me 折减后重算', change_basis='用户批准 near me ×0.2')
            self.assertEqual(rec['state'], 'rejected')
            self.assertEqual(rec['history'][-1]['gate'], 'revenue')
            self.assertEqual(rec['revenue']['base'], 42)
            self.assertFalse((root / '报告' / f'{slug}.md').exists())
            self.assertEqual(len(rec['history'][-1]['archived_reports']), 2)
            Q.check_rejection(root, rec, refs, 'revenue')

    def test_rebase_refuses_non_verified_and_missing_basis(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            with self.assertRaisesRegex(Q.QualificationError, '只用于既有 verified'):
                L.rebase(root, slug, by='t', reason='x', change_basis='y')
            slug = verified_candidate(root, 'other-slug')
            with self.assertRaisesRegex(Q.QualificationError, 'change-basis'):
                L.rebase(root, slug, by='t', reason='x', change_basis=' ')

