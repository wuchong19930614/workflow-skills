import copy
import hashlib
import json
import unittest
from datetime import date, timedelta, datetime, timezone
from unittest.mock import patch

from helpers import TmpRoot, verified_candidate
import investment as I
import ledger as L
import build_report as B
import validate_ledger as V


def plan():
    return dict(minimum_product='只做一种文件的批量转换', entry_advantage='减少步骤；待用户测试验证',
                delivery_basis='开源库样例支持；大文件内存待测', biggest_unknown='用户能否独立完成转换',
                cost_basis='预估开发、数据、内容工时；现金含 API、托管、获客；持续时间含维护和推广',
                ramp_basis='示例：首月无收入，次月半量，后月稳态；非事实',
                initial_cash_usd=100, build_hours=8, data_hours=1, content_hours=1,
                monthly_cash_usd=10, monthly_hours=1, hourly_rate_usd=10,
                monthly_revenue_fraction=[0, .5, 1, 1], unknowns={},
                experiment=dict(type='usability', metric='completions/attempts', hypothesis='用户可独立完成任务',
                                sample_definition='目标用户首次任务尝试，不含机器人和重复尝试',
                                success_rule='无需指导产出有效文件', min_sample=10, min_successes=8, min_success_rate=.8,
                                window_days=30, max_cash_usd=100, max_hours=20,
                                stop_rule='达到上限暂停复核', extend_rule='仅样本不足且有新获客途径才另行批准延期'))


def feedback(root, slug):
    path = root / '证据' / slug / 'actual.txt'
    path.write_text('测试原始任务记录')
    start = datetime.now(timezone.utc).date() - timedelta(days=30)
    return dict(id='first', by='test', started_on=start.isoformat(), as_of=(start + timedelta(days=30)).isoformat(),
                channel='测试用户直接访问；不作为自然搜索证据', cash_spent_usd=50, hours_spent=12,
                revenue_usd=0, sample=10, successes=8, unknowns={}, learning='示例用户任务完成',
                realized_risks='大文件仍未覆盖', next_action='复核后另定下一试验', calibration_proposal='none',
                evidence=[{'ref':str(path.relative_to(root)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}])


class InvestmentTests(unittest.TestCase):
    def setUp(self):
        started = (date.today() - timedelta(days=60)).isoformat() + 'T00:00:00+00:00'
        patcher = patch('investment.now', return_value=started)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cash_and_time_payback_include_ramp(self):
        result = I.estimate(plan(), dict(downside=100, base=200, upside=300))['base']
        self.assertEqual(result['cash_break_even_month'], 3)
        self.assertEqual(result['economic_break_even_month'], 3)
        self.assertEqual(result['months'][0]['cumulative_cash_usd'], -110)
        self.assertEqual(result['months'][0]['cumulative_economic_usd'], -220)
        p = plan(); p['hourly_rate_usd'] = 100
        result = I.estimate(p, dict(downside=100, base=200, upside=300))['base']
        self.assertEqual(result['economic_status'], 'not_within_horizon')
        self.assertEqual(result['cash_status'], 'reached')

    def test_unknowns_do_not_become_zero(self):
        p = plan(); p['hourly_rate_usd'] = None
        with self.assertRaises(ValueError): I.validate_plan(p)
        p['unknowns']['hourly_rate_usd'] = '尚未设定'
        result = I.estimate(p, dict(downside=100, base=200, upside=300))['base']
        self.assertEqual(result['economic_status'], 'unknown')
        self.assertEqual(result['cash_status'], 'reached')
        p['monthly_revenue_fraction'][0] = None
        p['unknowns']['monthly_revenue_fraction'] = '首月未知'
        self.assertEqual(I.estimate(p, {'base':200})['base']['cash_status'], 'unknown')

    def test_nonfinite_and_mismatched_experiment_rejected(self):
        for value in (True, -1, float('nan'), float('inf')):
            p = plan(); p['initial_cash_usd'] = value
            with self.assertRaises(ValueError): I.validate_plan(p)
        p = plan(); p['experiment']['type'] = 'seo'
        with self.assertRaises(ValueError): I.validate_plan(p)

    def test_freeze_report_feedback_and_retry(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            before = L.load(root)['candidates'][slug]
            rec = L.set_investment(root, slug, plan=plan(), by='test')
            self.assertEqual(rec['history'], before['history'])
            self.assertEqual(rec['revenue'], before['revenue'])
            self.assertEqual(L.set_investment(root, slug, plan=plan(), by='test'), rec)
            changed = plan(); changed['build_hours'] = 1
            with self.assertRaises(ValueError): L.set_investment(root, slug, plan=changed, by='test')
            report = B.build(root, slug); original = report.read_bytes()
            row = feedback(root, slug)
            result = I.record_feedback(root, rec, row)
            self.assertEqual(result['signal'], 'criterion_met')
            self.assertEqual(result['actual_cash_balance_usd'], -50)
            self.assertEqual(result['actual_economic_balance_usd'], -170)
            self.assertEqual(I.record_feedback(root, rec, row), result)
            B.build(root, slug)
            self.assertEqual(report.read_bytes(), original)
            self.assertIn('投入与最小验证', original.decode())
            self.assertEqual(V.validate(root)[0], [])
            row['successes'] = 9
            with self.assertRaises(ValueError): I.record_feedback(root, rec, row)

    def test_sample_budget_and_expiry_are_separate(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            rec = L.set_investment(root, slug, plan=plan(), by='test')
            row = feedback(root, slug); row.update(sample=0, successes=0, cash_spent_usd=100)
            result = I.record_feedback(root, rec, row)
            self.assertEqual(result['signal'], 'insufficient_evidence')
            self.assertTrue(result['window_elapsed'])
            self.assertEqual(result['budget_caps_reached'], ['cash_spent_usd'])
            self.assertEqual(L.load(root)['candidates'][slug]['state'], 'verified')

    def test_feedback_integrity_and_monotonicity(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            rec = L.set_investment(root, slug, plan=plan(), by='test')
            row = feedback(root, slug)
            row['as_of'] = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
            I.record_feedback(root, rec, row)
            changed = copy.deepcopy(row); changed.update(id='second', as_of=datetime.now(timezone.utc).date().isoformat(), hours_spent=1)
            with self.assertRaises(ValueError): I.record_feedback(root, rec, changed)
            changed = copy.deepcopy(row); changed['id'] = 'second'
            with self.assertRaises(ValueError): I.record_feedback(root, rec, changed)
            (root / row['evidence'][0]['ref']).write_text('篡改')
            self.assertTrue(any('反馈' in e for e in V.validate(root)[0]))

    def test_missing_baseline_is_explicit_and_rejected_has_no_fabricated_income(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            self.assertIn('回本期未知', B.build(root, slug).read_text())
            result = I.estimate(plan(), None)
            self.assertEqual(result['base']['cash_status'], 'unknown')

    def test_cli_end_to_end(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            path = root / 'plan.json'; path.write_text(json.dumps(plan()))
            args = ['--data-root', str(root), '--slug', slug]
            with patch('builtins.print'):
                self.assertEqual(I.main(['plan', *args, '--file', str(path), '--by', 'test']), 0)
                self.assertEqual(I.main(['estimate', *args, '--file', str(path)]), 0)
                path.write_text(json.dumps(feedback(root, slug)))
                self.assertEqual(I.main(['feedback', *args, '--file', str(path)]), 0)
                self.assertEqual(I.main(['review', *args]), 0)
            self.assertEqual(V.validate(root)[0], [])

    def test_baseline_tamper_is_detected(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            L.set_investment(root, slug, plan=plan(), by='test')
            data = L.load(root)
            data['candidates'][slug]['investment']['estimate']['base']['cash_break_even_month'] = 1
            L.save(root, data)
            self.assertTrue(any('基线摘要' in e for e in V.validate(root)[0]))

    def test_report_failure_recovers_same_baseline(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            path = root / 'plan.json'; path.write_text(json.dumps(plan()))
            args = ['plan', '--data-root', str(root), '--slug', slug, '--file', str(path), '--by', 'test']
            with patch('builtins.print'), patch('build_report.build', side_effect=OSError('disk')):
                self.assertEqual(I.main(args), 1)
            frozen = L.load(root)['candidates'][slug]['investment']
            with patch('builtins.print'):
                self.assertEqual(I.main(args), 0)
            self.assertEqual(L.load(root)['candidates'][slug]['investment'], frozen)
            self.assertEqual(V.validate(root)[0], [])

    def test_feedback_cannot_escape_evidence_directory_or_precommit(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            rec = L.set_investment(root, slug, plan=plan(), by='test')
            row = feedback(root, slug)
            row['evidence'][0]['ref'] = '账本/候选账本.json'
            with self.assertRaises(ValueError): I.record_feedback(root, rec, row)
            row = feedback(root, slug); row['started_on'] = '2000-01-01'
            with self.assertRaises(ValueError): I.record_feedback(root, rec, row)
            row = feedback(root, slug); row['as_of'] = (date.today() + timedelta(days=3)).isoformat()
            with self.assertRaises(ValueError): I.record_feedback(root, rec, row)


if __name__ == '__main__': unittest.main()
