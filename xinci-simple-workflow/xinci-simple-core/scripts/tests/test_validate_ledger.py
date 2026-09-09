# validate_ledger:状态词汇、证据存在、history 末项==state、verified 有 form/revenue 且报告存在(警告)、孤儿证据目录(警告)。
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import validate_ledger as V
from helpers import TmpRoot, write_obs, CLUSTER, SEED, PROXY, REVENUE


def reg(root, slug):
    ev = write_obs(root, slug, "2026-09-10-scan.json")
    L.register(root, slug=slug, primary_keyword=slug, cluster=CLUSTER, seed=SEED, proxy=PROXY,
               evidence=[ev], by="t", reason="r")


class ValidateLedgerTest(unittest.TestCase):
    def test_clean_ledger_zero_errors(self):
        with TmpRoot() as root:
            reg(root, "a")
            errors, warnings = V.validate(root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

    def test_catches_each_invariant(self):
        with TmpRoot() as root:
            reg(root, "a")
            reg(root, "b")
            ledger = L.load(root)
            ledger["candidates"]["a"]["state"] = "flying"
            ledger["candidates"]["b"]["evidence_refs"].append("证据/b/missing.json")
            ledger["candidates"]["b"]["history"][-1]["to"] = "parked"
            L.save(root, ledger)
            (root / "证据" / "orphan").mkdir()
            errors, warnings = V.validate(root)
            joined = "\n".join(errors)
            self.assertIn("flying", joined)
            self.assertIn("missing.json", joined)
            self.assertIn("history 末项", joined)
            self.assertTrue(any("orphan" in w for w in warnings))

    def test_verified_without_report_is_warning(self):
        with TmpRoot() as root:
            reg(root, "v")
            ev = write_obs(root, "v", "2026-09-10-verify.json", stage="verify")
            L.transition(root, "v", to="verified", evidence=[ev], by="t", reason="r",
                         form="tool", revenue=REVENUE)
            errors, warnings = V.validate(root)
            self.assertEqual(errors, [])
            self.assertTrue(any("报告/v.md" in w for w in warnings))

    def test_verified_missing_form_is_error(self):
        with TmpRoot() as root:
            reg(root, "v")
            ev = write_obs(root, "v", "2026-09-10-verify.json", stage="verify")
            L.transition(root, "v", to="verified", evidence=[ev], by="t", reason="r",
                         form="tool", revenue=REVENUE)
            ledger = L.load(root)
            ledger["candidates"]["v"]["form"] = None
            L.save(root, ledger)
            errors, _ = V.validate(root)
            self.assertTrue(any("form" in e for e in errors))

    def test_cli_exit_codes(self):
        with TmpRoot() as root:
            reg(root, "a")
            self.assertEqual(V.main(["--data-root", str(root)]), 0)
            ledger = L.load(root)
            ledger["candidates"]["a"]["state"] = "flying"
            L.save(root, ledger)
            self.assertEqual(V.main(["--data-root", str(root)]), 1)


if __name__ == "__main__":
    unittest.main()
