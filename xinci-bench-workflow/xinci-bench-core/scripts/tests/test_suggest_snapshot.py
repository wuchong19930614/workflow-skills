import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_model as Q
import suggest_snapshot as S
from helpers import TmpRoot


def fake(answers):
    calls = []

    def f(q):
        calls.append(q)
        return answers.pop(0)
    f.calls = calls
    return f


class SuggestSnapshotTest(unittest.TestCase):
    def test_first_snapshot_is_baseline(self):
        with TmpRoot() as root:
            out = S.snapshot(root, "grow a garden 2 ", fake([["a", "b"]]), at="2026-10-13T08:00:00+00:00")
            self.assertEqual((out["first_time"], out["new_suggestions"], out["gap_days"]), (True, [], None))
            self.assertTrue(S.snapshot_path(root, "grow a garden 2 ").is_file())

    def test_new_means_never_seen_before(self):
        with TmpRoot() as root:
            f = fake([["a", "b"], ["b", "c"], ["a", "c", "d"]])
            S.snapshot(root, "q", f, at="2026-10-01T00:00:00+00:00")
            S.snapshot(root, "q", f, at="2026-10-05T00:00:00+00:00")
            out = S.snapshot(root, "q", f, at="2026-10-13T00:00:00+00:00")
            self.assertEqual((out["new_suggestions"], out["gap_days"]), (["d"], 8))   # a 在第一次出现过,不算新

    def test_fetch_failure_writes_nothing(self):
        with TmpRoot() as root:
            def boom(q):
                raise OSError("HTTP 429")
            out = S.snapshot(root, "q", boom)
            self.assertIn("429", out["error"])
            self.assertFalse(S.snapshot_path(root, "q").exists())

    def test_expand_uses_task_words_and_interval(self):
        with TmpRoot() as root:
            f, slept = fake([["x"]] * 11), []
            out = S.expand(root, "Grow a Garden 2", f, sleeper=slept.append, interval=1.0)
            self.assertEqual(len(out), 1 + len(Q.TASK_WORDS))
            self.assertEqual(f.calls[0], "Grow a Garden 2 ")
            self.assertIn("Grow a Garden 2 tier list", f.calls)
            self.assertEqual(slept, [1.0] * len(Q.TASK_WORDS))

    def test_snapshot_path_stable_and_safe(self):
        with TmpRoot() as root:
            a = S.snapshot_path(root, "Grow  A Garden/2 ")
            self.assertEqual(a, S.snapshot_path(root, "grow a garden/2"))
            self.assertNotIn("/2", a.name)


if __name__ == "__main__":
    unittest.main()
