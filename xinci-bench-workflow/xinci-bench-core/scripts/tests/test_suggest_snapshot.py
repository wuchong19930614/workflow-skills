import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quick_model as Q
import suggest_snapshot as S
from _common import BenchError
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

    def test_derivative_queries_and_interval(self):
        # 飙升词里冒出陌生站名时查派生说法(用户 2026-10-19 定):<站名> alternative / like / unlimited
        with TmpRoot() as root:
            f, slept = fake([["neal.fun alternative sites"], ["neal.fun like websites"], []]), []
            out = S.derive(root, " neal.fun ", f, sleeper=slept.append, interval=1.0)
            self.assertEqual(Q.DERIVATIVE_WORDS, ("alternative", "like", "unlimited"))
            self.assertEqual(f.calls, ["neal.fun alternative", "neal.fun like", "neal.fun unlimited"])
            self.assertEqual(slept, [1.0, 1.0])
            self.assertEqual([r["suggestions"] for r in out], [["neal.fun alternative sites"], ["neal.fun like websites"], []])
            self.assertTrue(S.snapshot_path(root, "neal.fun like").is_file())       # 快照照常存,下次能比出新说法

    def test_derivative_needs_name(self):
        with TmpRoot() as root:
            with self.assertRaises(BenchError):
                S.derive(root, "  ", fake([]), sleeper=lambda s: None)

    def test_cli_derivative(self):
        with TmpRoot() as root:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = S.main(["--data-root", str(root), "--derivative", "neal.fun"], fetcher=fake([["a"], ["b"], ["c"]]),
                            sleeper=lambda s: None)
            self.assertEqual(rc, 0)
            self.assertEqual([r["query"] for r in json.loads(buf.getvalue())],
                             ["neal.fun alternative", "neal.fun like", "neal.fun unlimited"])

    def test_other_country_has_own_snapshot(self):
        with TmpRoot() as root:
            us, gb = S.snapshot_path(root, "q"), S.snapshot_path(root, "q", gl="gb")
            self.assertNotEqual(us, gb)
            self.assertEqual(us, S.snapshot_path(root, "q", gl="us"))      # 美国的旧快照不受影响
            url = S.url_for("grow a garden", "gb")
            self.assertIn("gl=gb", url)
            self.assertTrue(url.endswith("q=grow%20a%20garden"))
            S.snapshot(root, "q", fake([["a"]]), gl="gb")
            self.assertTrue(gb.is_file() and not us.exists())

    def test_snapshot_path_stable_and_safe(self):
        with TmpRoot() as root:
            a = S.snapshot_path(root, "Grow  A Garden/2 ")
            self.assertEqual(a, S.snapshot_path(root, "grow a garden/2"))
            self.assertNotIn("/2", a.name)


if __name__ == "__main__":
    unittest.main()
