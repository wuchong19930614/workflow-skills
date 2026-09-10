import helpers
import unittest
from unittest.mock import patch
from helpers import TmpRoot, register_candidate, verified_candidate, write_obs
import ledger as L
import build_report as B
import discovery_feedback as D
import run_log as R


def log(source, run, touched=(), outcome='completed', calls=1):
    return {'skill':'xinci-simple-scan', 'candidates_touched':list(touched), 'billable_calls':calls,
            'progress':{'run_id':run,'round':1,'source_kind':source,'outcome':outcome,'seed_value':'seed'}}


class DiscoveryFeedbackTests(unittest.TestCase):
    def test_duplicate_touches_do_not_inflate_yield_and_incomplete_reports_excluded(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            rows=[log('root','a',[slug],outcome='started',calls=2),log('root','a',[slug],calls=3)]
            self.assertEqual(D.summarize(root,rows)['sources']['root']['cohort_verified'],0)
            B.build(root,slug)
            stat=D.summarize(root,rows)['sources']['root']
            self.assertEqual(stat['cohort_verified'],1)
            self.assertEqual(stat['scan_calls'],5)
            self.assertEqual(stat['scan_calls_per_verified'],5)

    def test_legacy_no_cost_attribution_and_rejected_historical_unknown_not_training(self):
        with TmpRoot() as root:
            slug=register_candidate(root)
            data=L.load(root);rec=data['candidates'][slug];rec['state']='rejected';rec['history'].append({'to':'rejected','reason':'历史'})
            L.save(root,data)
            rows=[{'skill':'xinci-simple-scan','billable_calls':99},log('root','a',[slug])]
            result=D.summarize(root,rows)
            self.assertEqual(result['sources']['root']['rejected'],1)
            self.assertEqual(result['sources']['root']['resolved'],0)
            self.assertEqual(result['sources']['root']['scan_calls'],1)
            self.assertEqual(result['legacy_logs_excluded'],1)

    def test_history_changes_priority_with_exploration_and_no_mutation(self):
        with TmpRoot() as root:
            rows=[]
            for source in ('root','forum'):
                slugs=[]
                for i in range(3):
                    slug=verified_candidate(root,f'{source}-{i}')
                    data=L.load(root);data['candidates'][slug]['seed']['type']=source;L.save(root,data)
                    B.build(root,slug);slugs.append(slug)
                rows += [log(source,source+'1',slugs,calls=1 if source=='forum' else 10), log(source,source+'2',slugs,calls=1)]
            before=L.ledger_path(root).read_bytes()
            result=D.summarize(root,rows)
            self.assertEqual(result['next_source'],'forum')
            rows += [log('forum','extra'+str(i)) for i in range(3)]
            self.assertEqual(D.summarize(root,rows)['next_source'],'small_site')
            self.assertEqual(before,L.ledger_path(root).read_bytes())

    def test_resume_retains_source_even_if_advisor_changes(self):
        with TmpRoot() as root:
            R.record(root,date='2026-09-10',skill='xinci-simple-scan',sources_opened=[],candidates_touched=[],billable_calls=0,notes=[],progress={
                'run_id':'a','round':1,'max_rounds':3,'source_kind':'forum','seed_value':'topic','outcome':'started','next_step':'scan'})
            with patch('discovery_feedback.summarize',return_value={'next_source':'root','selection_reason':'new'}):
                result=R.plan(root)
            self.assertEqual(result['next_source'],'forum')
            self.assertEqual(result['resume']['seed_value'],'topic')

    def test_replay_does_not_turn_missing_samples_into_success(self):
        with TmpRoot() as root:
            register_candidate(root)
            before=L.ledger_path(root).read_bytes()
            result=D.replay(root)
            self.assertEqual(result['sample_count'],1)
            self.assertEqual(result['decision'],'retain_current_thresholds')
            self.assertEqual(before,L.ledger_path(root).read_bytes())


    def test_verified_rejections_lower_seed_priority_but_pending_does_not(self):
        import copy
        from helpers import VERIFY_OBS
        with TmpRoot() as root:
            slugs=[]
            for i in range(3):
                slug=register_candidate(root,f'failed-{i}')
                obs=copy.deepcopy(VERIFY_OBS);obs['ai_overview']['completes_task']=True
                ref=write_obs(root,slug,'fail.json',**obs)
                L.transition(root,slug,to='rejected',gate='G1',evidence=[ref],by='t',reason='首屏完成')
                slugs.append(slug)
            pending=register_candidate(root,'pending');slugs.append(pending)
            result=D.summarize(root,[log('root','one',slugs),log('root','two',slugs)])
            self.assertEqual(result['sources']['root']['resolved'],3)
            self.assertEqual(result['sources']['root']['pending'],1)
            self.assertTrue(result['directions'][0]['lower_priority'])
            self.assertEqual(result['sources']['root']['gates']['G1'],3)

    def test_skipped_scan_never_advances_rotation_or_attributes_candidates(self):
        with TmpRoot() as root:
            slug=verified_candidate(root);B.build(root,slug)
            result=D.summarize(root,[log('root','skip',[slug],outcome='skipped',calls=0)])
            self.assertEqual(result['sources']['root']['completed_scans'],0)
            self.assertEqual(result['sources']['root']['cohort_verified'],0)
            self.assertEqual(result['next_source'],'root')
