import helpers  # initializes script import path
import unittest
import build_report as B
import ledger as L
from helpers import TmpRoot, write_obs, VERIFY_OBS, verified_candidate, register_candidate


class BuildReportTest(unittest.TestCase):
    def test_values_are_from_qualified_volume(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            text = B.build(root, slug).read_text()
            for value in ('600,000', '500,000', '100,000', '$210.00', 'cloudconvert.com', 'cluster_expansion'):
                self.assertIn(value, text)
            self.assertTrue((root / '报告' / f'{slug}.html').is_file())

    def test_new_observation_does_not_replace_bound_evidence(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            before = B.build(root, slug).read_bytes()
            write_obs(root, slug, '2099-12-31-verify.json', **dict(VERIFY_OBS, points=['新现场，不属于旧裁决']))
            self.assertEqual(B.build(root, slug).read_bytes(), before)

    def test_changed_bound_evidence_refused(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            write_obs(root, slug, '2026-09-11-verify.json', **dict(VERIFY_OBS, points=['篡改']))
            with self.assertRaisesRegex(B.ReportError, 'SHA'):
                B.build(root, slug)

    def test_non_verified_refused(self):
        with TmpRoot() as root:
            slug = register_candidate(root)
            with self.assertRaises(B.ReportError):
                B.build(root, slug)

    def test_legacy_verified_requires_recheck(self):
        with TmpRoot() as root:
            slug = verified_candidate(root)
            data = L.load(root)
            del data['candidates'][slug]['qualification']
            L.save(root, data)
            with self.assertRaisesRegex(B.ReportError, '历史 verified'):
                B.build(root, slug)
