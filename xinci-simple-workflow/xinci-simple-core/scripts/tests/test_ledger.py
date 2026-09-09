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
            self.assertEqual([h['to'] for h in L.load(root)['candidates'][slug]['history']], ['found','parked','verified'])

    def test_requalify_requires_eligible_rejection_and_change(self):
        for gate in ('revenue', 'G1', 'G2', 'G3'):
            with self.subTest(gate=gate), TmpRoot() as root:
                slug = register_candidate(root)
                ev = write_obs(root, slug, 'v-verify.json', **VERIFY_OBS)
                L.transition(root, slug, to='rejected', evidence=[ev], by='t', reason='旧裁决', gate=gate)
                kwargs = dict(evidence=[ev], by='t', reason='重审', form='tool', revenue=revenue_for(root, slug, [ev]))
                with self.assertRaises(L.LedgerError):
                    L.requalify(root, slug, **kwargs)
                if gate == 'revenue':
                    rec = L.requalify(root, slug, **kwargs, change_basis='用户批准门槛变更')
                    self.assertEqual(rec['state'], 'verified')
                else:
                    with self.assertRaises(L.LedgerError):
                        L.requalify(root, slug, **kwargs, change_basis='降低收入门槛')

    def test_rejection_requires_gate_reason_and_verify(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            ev = write_obs(root, slug, 'v-verify.json', **VERIFY_OBS)
            for extra in ({'reason': '', 'gate':'G1'}, {'reason':'x'}):
                with self.assertRaises(L.LedgerError):
                    L.transition(root, slug, to='rejected', evidence=[ev], by='t', **extra)
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
