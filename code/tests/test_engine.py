"""Guardrail tests (stdlib unittest):  python -m unittest discover -s code/tests

* no-hardcode lint: no case ids, evidence/activity/audit ids, resource ids, dataset emails or
  evidence file names appear as literals in engine code;
* determinism: two runs (and different PYTHONHASHSEEDs) produce byte-identical output.csv;
* validator: rejects malformed rows (it must fail loudly, not pass silently).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE))

from audit.config import DATASET_DIR  # noqa: E402
from audit.util import EMAIL_RE, read_csv  # noqa: E402
from audit.validator import known_evidence_ids, validate_rows  # noqa: E402

ENGINE_DIRS = [CODE / "audit", CODE / "main.py"]
ID_LITERAL = re.compile(r"""["'](?:case|evidence|activity|audit|user)_\d+["']|"""
                        r"""["'](?:account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|"""
                        r"""legal_hold|marketing|object|cache|email_delivery)_\d+["']""")


def _py_files():
    for p in ENGINE_DIRS:
        yield from ([p] if p.is_file() else sorted(p.rglob("*.py")))


class NoHardcodeLint(unittest.TestCase):
    def test_no_id_literals(self):
        hits = [f"{p.name}:{i}: {line.strip()}" for p in _py_files()
                for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if ID_LITERAL.search(line)]
        self.assertEqual(hits, [], "hardcoded ids in engine code")

    def test_no_dataset_emails_or_file_names(self):
        emails = {e.lower() for r in read_csv(DATASET_DIR / "user_identities.csv") for e in [r["email"]]}
        files = {Path(r["file_path"]).name for r in read_csv(DATASET_DIR / "evidence_files.csv")}
        offenders = []
        for p in _py_files():
            text = p.read_text(encoding="utf-8")
            offenders += [f"{p.name}: {e}" for e in EMAIL_RE.findall(text) if e.lower() in emails]
            offenders += [f"{p.name}: {f}" for f in files if f in text]
        self.assertEqual(offenders, [])

    def test_answers_never_read_by_engine(self):
        for p in _py_files():
            self.assertNotIn("sample_output", p.read_text(encoding="utf-8"), f"{p} reads gold answers")


class Determinism(unittest.TestCase):
    def test_two_runs_identical(self):
        outs = []
        for seed in ("1", "12345"):
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / "out.csv"
                env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONIOENCODING": "utf-8"}
                subprocess.run([sys.executable, str(CODE / "main.py"), "--output", str(out), "--no-sidecars"],
                               check=True, env=env, capture_output=True)
                outs.append(out.read_bytes())
        self.assertEqual(outs[0], outs[1])


class ValidatorRejects(unittest.TestCase):
    def setUp(self):
        self.reqs = read_csv(DATASET_DIR / "deletion_requests.csv")
        self.ids = known_evidence_ids(DATASET_DIR)
        out = CODE.parent / "output.csv"
        self.rows = read_csv(out) if out.exists() else None

    def test_current_output_valid(self):
        if self.rows is None:
            self.skipTest("run main.py first")
        self.assertEqual(validate_rows(self.rows, self.reqs, self.ids), [])

    def test_detects_broken_rows(self):
        if self.rows is None:
            self.skipTest("run main.py first")
        bad = [dict(r) for r in self.rows]
        inc = next(r for r in bad if r["deletion_status"] == "INCOMPLETE")
        steps = json.loads(inc["steps_json"])
        steps[0]["evidence_id"] = "evidence_does_not_exist"
        steps[-1]["step_no"] = 99
        inc["steps_json"] = json.dumps(steps)
        bad[0], bad[1] = bad[1], bad[0]
        errs = validate_rows(bad, self.reqs, self.ids)
        self.assertTrue(any("unknown evidence" in e for e in errs))
        self.assertTrue(any("step_no" in e for e in errs))
        self.assertTrue(any("not sorted" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
