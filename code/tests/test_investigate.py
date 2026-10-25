"""Tests for the evidence cards, the walkthrough and the investigate mutations:
    python -m unittest discover -s code/tests

Cases are drawn with a seeded RNG from the cases each mutation applies to (no hardcoded case ids).
"""
from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE))

from audit.config import DATASET_DIR  # noqa: E402
from audit.evidence_cards import CardBuilder  # noqa: E402
from audit.pipeline import AuditEngine  # noqa: E402
from audit.walkthrough import applicable, eval_ids, mutate, walkthrough  # noqa: E402

SEEDS = (3, 11)


class InvestigateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = AuditEngine(DATASET_DIR)
        cls.results = cls.engine.run()
        cls.ids = eval_ids(cls.engine)

    def pick(self, mutation, seed):
        return random.Random(seed).choice(applicable(mutation, self.results, self.ids))

    def test_add_active_flow_adds_finding_remediation_verification(self):
        for seed in SEEDS:
            cid = self.pick("add-active-flow", seed)
            m = mutate(self.engine, self.results, cid, "add-active-flow")
            self.assertTrue(m.held, "\n".join(m.lines()))
            self.assertEqual(m.after[0], "INCOMPLETE")
            added = set(m.after[1]) - set(m.before[1])
            self.assertEqual(len(added), 3, added)   # the new flow's finding, remediation and verification
            if m.before[0] == "INCOMPLETE":           # an already-incomplete plan only grows
                self.assertTrue(set(m.before[1]) <= set(m.after[1]))

    def test_move_audit_before_resurrection_removes_it(self):
        for seed in SEEDS:
            cid = self.pick("move-audit-before-resurrection", seed)
            m = mutate(self.engine, self.results, cid, "move-audit-before-resurrection")
            self.assertTrue(m.held, "\n".join(m.lines()))
            self.assertNotEqual(m.before, m.after)

    def test_change_email_case_changes_nothing(self):
        for seed in SEEDS:
            cid = self.pick("change-email-case", seed)
            m = mutate(self.engine, self.results, cid, "change-email-case")
            self.assertTrue(m.held, "\n".join(m.lines()))
            self.assertEqual(m.before, m.after)

    def test_one_card_per_finding_and_deterministic(self):
        a = CardBuilder(self.engine).cards(self.results, self.ids)
        n_findings = sum(1 for c in self.ids for s in self.results[c].steps if s.phase == "FINDING")
        self.assertEqual(len(a), n_findings)
        engine2 = AuditEngine(DATASET_DIR)
        b = CardBuilder(engine2).cards(engine2.run(), self.ids)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        for card in a:
            self.assertGreater(card["confidence"], 0)
            self.assertLessEqual(card["confidence"], 0.99)
            cited = card["state_at_audit"]["cited"]
            if cited:   # never cite a file captured after the audit cut
                self.assertLessEqual(cited["file_captured_at"], card["state_at_audit"]["audit_at"])

    def test_investigator_agrees_and_trace_is_deterministic(self):
        from exorcist.investigator import crosscheck
        a = crosscheck.run(self.engine, self.results, None, verbose=False)
        engine2 = AuditEngine(DATASET_DIR)
        b = crosscheck.run(engine2, engine2.run(), None, verbose=False)
        self.assertEqual(a["trace_sha256"], b["trace_sha256"])
        self.assertTrue(a["steps"]["frontier_exhausted_all"])
        self.assertEqual(a["agreement"]["all_deletion_cases"]["status_agreement"], 1.0)
        self.assertEqual(a["material_disagreement_cases_evaluation"], 0)

    def test_investigator_trace_independent_of_hash_seed(self):
        import os
        import subprocess
        code = ("import sys; sys.path.insert(0, %r); from audit.config import DATASET_DIR; "
                "from audit.pipeline import AuditEngine; from exorcist.investigator import crosscheck; "
                "e = AuditEngine(DATASET_DIR); print(crosscheck.run(e, e.run(), None, verbose=False)['trace_sha256'])") % str(CODE)
        outs = {subprocess.run([sys.executable, "-c", code], env={**os.environ, "PYTHONHASHSEED": seed},
                               capture_output=True, text=True, check=True).stdout.strip() for seed in ("1", "999")}
        self.assertEqual(len(outs), 1, outs)

    def test_walkthrough_is_deterministic_and_masked(self):
        cid = random.Random(5).choice(self.ids)
        one = walkthrough(self.engine, self.results, cid)
        self.assertEqual(one, walkthrough(self.engine, self.results, cid))
        self.assertNotIn(self.results[cid].case.email.lower(), "\n".join(one).lower())


if __name__ == "__main__":
    unittest.main()
