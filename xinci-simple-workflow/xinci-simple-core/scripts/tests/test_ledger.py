# ledger:4 态合法表、证据存在、reason 非空、verified 需 form+revenue、history 只追加、原子写。
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledger as L
from helpers import TmpRoot, write_obs, CLUSTER, SEED, PROXY, REVENUE


def reg(root, slug="heic-to-jpg-converter"):
    ev = write_obs(root, slug, "2026-09-10-scan.json")
    L.register(root, slug=slug, primary_keyword=slug.replace("-", " "), cluster=CLUSTER,
               seed=SEED, proxy=PROXY, evidence=[ev], by="xinci-simple-scan", reason="准入:簇量 182K")
    return slug


class LedgerTest(unittest.TestCase):
    def test_register_creates_found(self):
        with TmpRoot() as root:
            slug = reg(root)
            rec = L.load(root)["candidates"][slug]
            self.assertEqual(rec["state"], "found")
            self.assertIsNone(rec["form"])
            self.assertIsNone(rec["revenue"])
            self.assertEqual(len(rec["history"]), 1)
            self.assertEqual(rec["history"][0]["to"], "found")
            self.assertIsNone(rec["history"][0]["from"])

    def test_register_requires_existing_evidence(self):
        with TmpRoot() as root:
            with self.assertRaises(L.LedgerError):
                L.register(root, slug="x", primary_keyword="x", cluster=CLUSTER, seed=SEED,
                           proxy=PROXY, evidence=["证据/x/none.json"], by="xinci-simple-scan", reason="r")

    def test_register_duplicate_rejected(self):
        with TmpRoot() as root:
            reg(root)
            with self.assertRaises(L.LedgerError):
                reg(root)

    def test_illegal_transition_rejected(self):
        with TmpRoot() as root:
            slug = reg(root)
            ev = write_obs(root, slug, "2026-09-10-verify.json", stage="verify")
            L.transition(root, slug, to="rejected", evidence=[ev], by="xinci-simple-verify", reason="G1 直答")
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="r",
                             form="tool", revenue=REVENUE)

    def test_reason_required(self):
        with TmpRoot() as root:
            slug = reg(root)
            ev = write_obs(root, slug, "2026-09-10-verify.json", stage="verify")
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to="rejected", evidence=[ev], by="x", reason="")

    def test_verified_requires_form_and_revenue(self):
        with TmpRoot() as root:
            slug = reg(root)
            ev = write_obs(root, slug, "2026-09-10-verify.json", stage="verify")
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="r")
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="r", form="tool")
            L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="base 640",
                         form="tool", revenue=REVENUE)
            rec = L.load(root)["candidates"][slug]
            self.assertEqual(rec["state"], "verified")
            self.assertEqual(rec["form"], "tool")
            self.assertEqual(rec["revenue"]["base"], 640)

    def test_parked_then_verified(self):
        with TmpRoot() as root:
            slug = reg(root)
            ev = write_obs(root, slug, "2026-09-10-verify.json", stage="verify")
            L.transition(root, slug, to="parked", evidence=[ev], by="x", reason="季节性")
            L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="r",
                         form="info", revenue=REVENUE)
            rec = L.load(root)["candidates"][slug]
            self.assertEqual([h["to"] for h in rec["history"]], ["found", "parked", "verified"])

    def test_invalid_form_rejected(self):
        with TmpRoot() as root:
            slug = reg(root)
            ev = write_obs(root, slug, "2026-09-10-verify.json", stage="verify")
            with self.assertRaises(L.LedgerError):
                L.transition(root, slug, to="verified", evidence=[ev], by="x", reason="r",
                             form="saas", revenue=REVENUE)

    def test_no_tmp_left_behind(self):
        with TmpRoot() as root:
            reg(root)
            self.assertEqual([p.name for p in (root / "账本").iterdir()], ["候选账本.json"])

    def test_list_by_state(self):
        with TmpRoot() as root:
            a = reg(root, "a-term")
            b = reg(root, "b-term")
            ev = write_obs(root, b, "2026-09-10-verify.json", stage="verify")
            L.transition(root, b, to="rejected", evidence=[ev], by="x", reason="G2")
            self.assertEqual([r["slug"] for r in L.list_candidates(root, state="found")], [a])
            self.assertEqual(len(L.list_candidates(root)), 2)


if __name__ == "__main__":
    unittest.main()
