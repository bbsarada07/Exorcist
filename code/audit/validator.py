"""ValidatorAgent: strict checks of the output.csv contract. Fails loudly (raises) on any error."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import OPERATION_ORDER, OPERATION_STATE, PHASES
from .util import case_sort_key, parse_ts, read_csv

HEADER = ["case_id", "deletion_status", "steps_json"]
STEP_KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}


class ValidationError(Exception):
    pass


def known_evidence_ids(dataset_dir: Path) -> dict[str, str | None]:
    ids = {r["file_id"]: r["captured_at"] for r in read_csv(dataset_dir / "evidence_files.csv")}
    ids.update({r["activity_id"]: r["event_time"] for r in read_csv(dataset_dir / "system_activity.csv")})
    ids.update({r["audit_id"]: r["event_time"] for r in read_csv(dataset_dir / "user_audit_log.csv")})
    return ids


def validate_rows(rows: list[dict], requests: list[dict], evidence_ids: dict) -> list[str]:
    errors = []
    req = {r["case_id"]: r for r in requests}
    ids = [r["case_id"] for r in rows]
    if len(rows) != len(requests):
        errors.append(f"expected {len(requests)} rows, got {len(rows)}")
    if set(ids) != set(req):
        errors.append(f"case ids differ: missing={sorted(set(req) - set(ids))[:5]} extra={sorted(set(ids) - set(req))[:5]}")
    if len(set(ids)) != len(ids):
        errors.append("duplicate case ids")
    if ids != sorted(ids, key=case_sort_key):
        errors.append("rows not sorted by case_id")
    for r in rows:
        cid, status = r["case_id"], r["deletion_status"]
        where = f"{cid}:"
        if status not in STATUSES:
            errors.append(f"{where} bad status {status}")
            continue
        try:
            steps = json.loads(r["steps_json"])
        except json.JSONDecodeError as e:
            errors.append(f"{where} invalid JSON ({e})")
            continue
        if not isinstance(steps, list):
            errors.append(f"{where} steps_json is not an array")
            continue
        if status == "NOT_APPLICABLE":
            if steps:
                errors.append(f"{where} NOT_APPLICABLE must have []")
            continue
        if not steps:
            errors.append(f"{where} {status} with no steps")
        audit = parse_ts(req[cid]["audit_at"]) if cid in req else None
        prev_key = None
        for i, s in enumerate(steps, 1):
            if set(s) != STEP_KEYS:
                errors.append(f"{where} step {i} keys {sorted(s)}")
                continue
            if s["step_no"] != i:
                errors.append(f"{where} step_no {s['step_no']} != {i}")
            if s["phase"] not in PHASES or s["operation"] not in OPERATION_ORDER.get(s["phase"], []):
                errors.append(f"{where} step {i} {s['phase']}/{s['operation']} not allowed")
                continue
            if OPERATION_STATE[s["operation"]] != s["state"]:
                errors.append(f"{where} step {i} state {s['state']} wrong for {s['operation']}")
            key = (PHASES.index(s["phase"]), OPERATION_ORDER[s["phase"]].index(s["operation"]),
                   s["system_id"], s["resource_id"])
            if prev_key is not None and key < prev_key:
                errors.append(f"{where} step {i} out of order")
            if prev_key == key:
                errors.append(f"{where} step {i} duplicate")
            prev_key = key
            ev = s["evidence_id"]
            cited = status == "COMPLETE" or s["phase"] == "FINDING"
            if status == "COMPLETE" and s["phase"] != "VERIFICATION":
                errors.append(f"{where} COMPLETE case contains {s['phase']}")
            if cited:
                if ev not in evidence_ids:
                    errors.append(f"{where} step {i} cites unknown evidence '{ev}'")
                elif audit and evidence_ids[ev] and parse_ts(evidence_ids[ev]) > audit:
                    errors.append(f"{where} step {i} cites {ev} captured after audit_at")
            elif ev != "":
                errors.append(f"{where} step {i} future work must have empty evidence_id")
        if status == "INCOMPLETE" and not any(s.get("phase") == "FINDING" for s in steps):
            errors.append(f"{where} INCOMPLETE without findings")
    return errors


def validate_file(output_csv: Path, dataset_dir: Path, requests_csv: Path | None = None) -> list[str]:
    with open(output_csv, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if header != HEADER:
            raise ValidationError(f"bad header {header}")
    rows = read_csv(output_csv)
    requests = read_csv(requests_csv or dataset_dir / "deletion_requests.csv")
    return validate_rows(rows, requests, known_evidence_ids(dataset_dir))
