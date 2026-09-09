import helpers
import unittest
import qualification as Q
import narrative as N
import ledger as L
from helpers import TmpRoot, verified_candidate, VERIFY_OBS


class NarrativeTest(unittest.TestCase):
    def test_coverage_and_estimate_are_explicit(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            rec = L.load(root)['candidates'][slug]
            text = N.build_groups(rec, [VERIFY_OBS])
            self.assertIn('500,000', text)
            self.assertIn('100,000 未计入收入', text)
            self.assertIn('$210.00', text)
            self.assertIn('不是排名保证', text)
            self.assertNotIn('打得过。', text)
            self.assertNotIn('点击完整留在自然结果', text)

    def test_verdicts_are_short_and_visible(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            text = N.build_groups(L.load(root)['candidates'][slug], [VERIFY_OBS])
            for heading in ('有人在搜吗','Google 会不会自己答完','打得过吗','能赚多少','最大的风险'):
                first = text.split('### ' + heading)[1].strip().splitlines()[0]
                self.assertTrue(first.startswith('**') and first.endswith('**'))
                self.assertLess(len(first), 100)

    def test_unknown_strength_is_not_zero(self):
        strong, unknown = Q.strong_results({'serp_top10': [{'completes_task': True, 'dr': None}]})
        self.assertEqual(len(strong), 0)
        self.assertEqual(len(unknown), 1)

    def test_old_or_wrong_format_is_not_strong(self):
        rows = [dict(completes_task=True, dr=80, fresh=False, format_match=True),
                dict(completes_task=True, dr=80, fresh=True, format_match=False),
                dict(completes_task=True, dr=80, fresh=True, format_match=True)]
        strong, unknown = Q.strong_results({'serp_top10': rows})
        self.assertEqual((len(strong), len(unknown)), (1, 0))
