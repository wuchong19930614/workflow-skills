import helpers
import copy
import json
import unittest
from datetime import date

from helpers import TmpRoot, register_candidate, verified_candidate, write_obs, CLUSTER, SEED, PROXY, VERIFY_OBS
from test_investment import plan
import ledger as L
import qualification as Q
import opportunity as O
import investment as I
import build_report as B
import report_status as S
import validate_ledger as V


def funded_plan(**changes):
    p = plan()
    p['monetization'] = {'status': 'supported', 'channel': 'ads', 'basis': '测试广告渠道与主题适用；并非实测 RPM',
                         'key_assumption': '模型 RPM 仍待真实收入验证', 'validation_step': '上线后测每千访问广告收入',
                         'checked_at': date.today().isoformat(), 'source_urls': ['https://example.com/ad-terms']}
    p.update(changes)
    return p


class OpportunityTests(unittest.TestCase):
    def test_new_candidate_cannot_skip_entry_check(self):
        with TmpRoot() as root:
            ev = write_obs(root, 'new', 'scan.json')
            L.register(root, slug='new', primary_keyword='heic to jpg', cluster=CLUSTER,
                       seed=SEED, proxy=PROXY, evidence=[ev], by='t', reason='x')
            task = {'core_reason': '转换', 'groups': [{'id': 'convert', 'role': 'core', 'keywords': ['heic to jpg']}]}
            with self.assertRaisesRegex(ValueError, '进入优势'):
                L.set_task_plan(root, 'new', plan=task, by='t', reason='x')
            self.assertNotIn('task_plan', L.load(root)['candidates']['new'])

    def test_unknown_can_be_completed_before_freeze_and_retries_are_idempotent(self):
        with TmpRoot() as root:
            slug = register_candidate(root, plan=False)
            rec = L.load(root)['candidates'][slug]
            entry = dict(rec['entry_plan']['plan'], status='unknown')
            L.set_entry_plan(root, slug, plan=entry, by='t', reason='交付缺依据')
            task = {'core_reason': '转换', 'groups': [{'id': 'convert', 'role': 'core', 'keywords': ['heic to jpg converter']}]}
            with self.assertRaisesRegex(ValueError, '未明确'):
                L.set_task_plan(root, slug, plan=task, by='t', reason='x')
            entry['status'] = 'ready'
            L.set_entry_plan(root, slug, plan=entry, by='t', reason='补齐')
            rec = L.set_task_plan(root, slug, plan=task, by='t', reason='冻结')
            self.assertEqual(rec, L.set_entry_plan(root, slug, plan=entry, by='t', reason='重试'))
            with self.assertRaisesRegex(ValueError, '已冻结'):
                L.set_entry_plan(root, slug, plan=dict(entry, solution='另一方案'), by='t', reason='更改')

    def test_entry_tamper_is_detected_even_if_rehashed(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            data = L.load(root)
            entry = data['candidates'][slug]['entry_plan']
            entry['plan']['solution'] = '事后改变'
            entry['sha256'] = O.digest({k:v for k,v in entry.items() if k != 'sha256'})
            L.save(root, data)
            with self.assertRaisesRegex(ValueError, '进入预检已变化'):
                Q.check_bound(root, data['candidates'][slug])

    def test_changed_entry_evidence_is_not_accepted(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            rec = L.load(root)['candidates'][slug]
            path = root / rec['entry_plan']['plan']['evidence_refs'][0]
            data = json.loads(path.read_text()); data['points'] = ['不同现场']
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, '证据摘要变化'): O.check_entry(root, rec)

    def test_missing_money_or_channel_never_pilot(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            rec = L.load(root)['candidates'][slug]
            self.assertEqual(O.recommendation(rec)['status'], 'needs_evidence')
            rec = L.set_investment(root, slug, plan=plan(), by='t')
            self.assertEqual(O.recommendation(rec)['status'], 'needs_evidence')
            p = funded_plan(hourly_rate_usd=None, unknowns={'hourly_rate_usd': '未知'})
            self.assertEqual(O.recommendation(dict(rec, investment=I.baseline(rec, p, 't')))['status'], 'needs_evidence')

    def test_time_cost_and_unavailable_channel_defer(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            rec = L.load(root)['candidates'][slug]
            for p in (funded_plan(build_hours=1000), funded_plan()):
                if p['build_hours'] != 1000: p['monetization']['status'] = 'unavailable'
                self.assertEqual(O.recommendation(dict(rec, investment=I.baseline(rec,p,'t')))['status'], 'defer')

    def test_good_plan_surfaces_in_report_status_and_cli(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            rec = L.set_investment(root, slug, plan=funded_plan(), by='t')
            self.assertEqual(O.recommendation(rec)['status'], 'pilot')
            md = B.build(root, slug)
            self.assertIn('值得小规模试做', md.read_text())
            self.assertIn('值得小规模试做', md.with_suffix('.html').read_text())
            self.assertEqual(S.build_report(root)['verified'][0]['investment_recommendation']['status'], 'pilot')
            self.assertEqual(V.validate(root)[0], [])
            from unittest.mock import patch
            with patch('builtins.print'):
                self.assertEqual(I.main(['recommend','--data-root',str(root),'--slug',slug]), 0)

    def test_rejected_and_changed_research_do_not_reuse_pilot(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            rec = L.set_investment(root, slug, plan=funded_plan(), by='t')
            self.assertEqual(O.recommendation(dict(rec, state='rejected'))['status'], 'defer')
            changed = copy.deepcopy(rec); changed['revenue']['base'] += 1
            self.assertEqual(O.recommendation(changed)['status'], 'needs_evidence')

    def test_channel_must_match_model_and_supported_needs_sources(self):
        with TmpRoot() as root:
            slug = verified_candidate(root); rec = L.load(root)['candidates'][slug]
            p = funded_plan(); p['monetization']['channel'] = 'affiliate'
            self.assertEqual(O.recommendation(dict(rec, investment=I.baseline(rec,p,'t')))['status'], 'needs_evidence')
            p['monetization']['source_urls'] = []
            with self.assertRaises(ValueError): I.validate_plan(p)

    def test_legacy_qualification_stays_readable_but_not_pilot(self):
        with TmpRoot() as root:
            slug = verified_candidate(root); data = L.load(root); rec=data['candidates'][slug]
            del rec['workflow_version']; del rec['entry_plan']; del rec['qualification']['entry_plan_sha256']
            L.save(root,data)
            Q.check_bound(root,rec)
            B.build(root,slug)
            self.assertEqual(V.validate(root)[0],[])
            self.assertEqual(O.recommendation(rec)['status'],'needs_evidence')


class EntryCliTests(unittest.TestCase):
    def test_register_entry_task_qualify_report_cli(self):
        import subprocess
        import sys
        from pathlib import Path
        scripts = Path(__file__).resolve().parents[1]
        with TmpRoot() as root:
            ref = write_obs(root, 'cli', 'scan.json')
            L.register(root, slug='cli', primary_keyword='heic to jpg converter', cluster=CLUSTER,
                       seed=SEED, proxy=PROXY, evidence=[ref], by='t', reason='测试')
            entry = {'status':'ready','user_gap':'重复操作','solution':'批量转换','advantage':'减少步骤',
                     'delivery_basis':'样例测试','biggest_unknown':'大文件','evidence_refs':[ref]}
            payload=root/'entry.json';payload.write_text(json.dumps(entry))
            def run(script,*args):
                r=subprocess.run([sys.executable,str(scripts/script),'--data-root',str(root),*args],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                return r.stdout
            run('ledger.py','set-entry-plan','--slug','cli','--plan-file',str(payload),'--by','t','--reason','测试')
            payload.write_text(json.dumps({'core_reason':'转换','groups':[{'id':'convert','role':'core','keywords':['heic to jpg','heic to jpg converter']}]}))
            run('ledger.py','set-task-plan','--slug','cli','--plan-file',str(payload),'--by','t','--reason','测试')
            ev=write_obs(root,'cli','verify.json',**VERIFY_OBS)
            run('settle_candidate.py','--slug','cli','--evidence',ev,'--by','t','--reason','测试')
            self.assertEqual(json.loads(run('investment.py','recommend','--slug','cli'))['status'],'needs_evidence')
            run('validate_ledger.py')
