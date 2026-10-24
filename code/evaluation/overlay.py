"""Overlay datasets: a temporary copy of dataset/ plus synthetic rows/files. dataset/ is never modified."""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
from pathlib import Path

from audit.config import DATASET_DIR


def _append(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, encoding="utf-8", newline="") as fh:
        fields = next(csv.reader(fh))
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def build_overlay(identities=(), audit_log=(), activities=(), evidence=(), requests=(), base: Path = DATASET_DIR) -> Path:
    """evidence: dicts with file_id, file_path (relative to dataset), captured_at, content (str or dict)."""
    tmp = Path(tempfile.mkdtemp(prefix="audit_overlay_"))
    shutil.copytree(base, tmp / "dataset")
    root = tmp / "dataset"
    _append(root / "user_identities.csv", list(identities))
    _append(root / "user_audit_log.csv", list(audit_log))
    _append(root / "system_activity.csv", list(activities))
    _append(root / "deletion_requests.csv", list(requests))
    manifest = []
    for e in evidence:
        p = root / e["file_path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        content = e["content"]
        p.write_text(content if isinstance(content, str) else json.dumps(content, indent=1), encoding="utf-8")
        manifest.append({"file_id": e["file_id"], "file_path": e["file_path"], "origin": e.get("origin", "custom"),
                         "captured_at": e["captured_at"]})
    _append(root / "evidence_files.csv", manifest)
    return root


def cleanup(root: Path) -> None:
    shutil.rmtree(root.parent, ignore_errors=True)


def bundle(captured_at: str, *snapshots) -> dict:
    """Snapshot-bundle JSON in the dataset's own format: snapshots=(data_store, collection, records)."""
    return {"exported_at": captured_at, "source": "custom_eval",
            "snapshots": [{"captured_at": captured_at, "data_store": s, "collection": c, "records": r}
                          for s, c, r in snapshots]}
