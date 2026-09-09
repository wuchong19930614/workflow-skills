import helpers
import unittest
import write_observation as W
from helpers import TmpRoot


class ObservationTest(unittest.TestCase):
    def test_append_never_overwrites(self):
        with TmpRoot() as root:
            obs = {'slug':'sample', 'stage':'verify','observed_at':'2026-09-09T12:00:00+00:00','source_urls':['https://example.com'],'points':[]}
            a, b = W.write(root, obs), W.write(root, obs)
            self.assertNotEqual(a, b)
            self.assertEqual((root/a).read_bytes(), (root/b).read_bytes())

    def test_invalid_input_does_not_leave_observation(self):
        with TmpRoot() as root:
            with self.assertRaises(ValueError):
                W.write(root, {'slug':'sample', 'stage':'verify'})
            self.assertEqual(list((root/'证据').rglob('*.json')), [])

    def test_path_traversal_refused(self):
        with TmpRoot() as root:
            with self.assertRaises(ValueError):
                W.write(root, {'slug':'../bad','stage':'verify'})
