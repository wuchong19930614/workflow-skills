# validate_ledger:状态词汇、证据存在、history 末项==state、verified 有 form/revenue 且报告存在(警告)、孤儿证据目录(警告)。
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
import validate_ledger as V
from helpers import plan_candidate, revenue_for, VERIFY_OBS, TmpRoot, write_obs, CLUSTER, SEED, PROXY, REVENUE


def reg(root, slug):
    ev = write_obs(root, slug, "2026-09-10-scan.json")
    L.register(root, slug=slug, primary_keyword=slug, cluster=CLUSTER, seed=SEED, proxy=PROXY,
               evidence=[ev], by="t", reason="r")
    plan_candidate(root, slug)


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

    def test_verified_requires_both_md_and_html(self):
        """照 xinci 的规矩:go 态要求 md+html 双文件,且 html 内源 SHA 与当前 md 一致。"""
        import build_report as B
        import build_report_html as H
        with TmpRoot() as root:
            slug = "dual"
            ev = write_obs(root, slug, "2026-09-10-scan.json")
            L.register(root, slug=slug, primary_keyword="dual fmt", cluster=CLUSTER, seed=SEED,
                       proxy=PROXY, evidence=[ev], by="t", reason="r")
            plan_candidate(root, slug)
            from helpers import VERIFY_OBS
            vev = write_obs(root, slug, "2026-09-11-verify.json", **VERIFY_OBS)
            L.transition(root, slug, to="verified", evidence=[vev], by="t", reason="r",
                         form="tool", revenue=revenue_for(root, slug, [vev]))
            B.build(root, slug)
            self.assertEqual(V.validate(root), ([], []))
            # 删掉 html → 报错
            (root / "报告" / f"{slug}.html").unlink()
            errors, _ = V.validate(root)
            self.assertTrue(any("html" in e for e in errors))
            # html 回来但 md 变了 → SHA 不一致,报错
            H.build(root / "报告" / f"{slug}.md")
            md = root / "报告" / f"{slug}.md"
            md.write_text(md.read_text(encoding="utf-8") + "\n改了一个字\n", encoding="utf-8")
            errors, _ = V.validate(root)
            self.assertTrue(any("SHA" in e for e in errors))

    def test_verified_without_report_is_error(self):
        with TmpRoot() as root:
            reg(root, "v")
            ev = write_obs(root, "v", "2026-09-10-verify.json", **VERIFY_OBS)
            L.transition(root, "v", to="verified", evidence=[ev], by="t", reason="r",
                         form="tool", revenue=revenue_for(root, "v", [ev]))
            errors, warnings = V.validate(root)
            self.assertTrue(any("报告/v.md" in e for e in errors))

    def test_verified_missing_form_is_error(self):
        with TmpRoot() as root:
            reg(root, "v")
            ev = write_obs(root, "v", "2026-09-10-verify.json", **VERIFY_OBS)
            L.transition(root, "v", to="verified", evidence=[ev], by="t", reason="r",
                         form="tool", revenue=revenue_for(root, "v", [ev]))
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
