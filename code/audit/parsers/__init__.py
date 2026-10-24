"""Load every evidence file listed in evidence_files.csv into one fact table."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..model import Activity, Coverage, Fact
from ..util import parse_ts, read_csv
from .activity import activity_facts, catalog_aliases, load_activities
from .documents import parse_document
from .flat import parse_flat_text
from .jsonfiles import parse_json
from .logs import parse_log
from .sql import parse_sql


@dataclass
class EvidenceStore:
    facts: list[Fact]
    coverage: list[Coverage]
    activities: list[Activity]
    manifest: dict[str, dict]                       # file_id -> manifest row (+ parsed captured_at)
    by_resource: dict[str, list[Fact]] = field(default_factory=dict)
    by_key: dict[tuple, set] = field(default_factory=dict)   # identifier -> resource ids
    parse_stats: dict[str, int] = field(default_factory=dict)

    def index(self) -> "EvidenceStore":
        by_res, by_key = defaultdict(list), defaultdict(set)
        for f in self.facts:
            by_res[f.resource_id].append(f)
            for k in f.keys:
                by_key[k].add(f.resource_id)
        for fs in by_res.values():
            fs.sort(key=lambda f: (f.observed_at, f.evidence_id))
        self.by_resource, self.by_key = dict(by_res), dict(by_key)
        return self


def load_evidence(dataset_dir: Path) -> EvidenceStore:
    activities = load_activities(dataset_dir / "system_activity.csv")
    aliases = catalog_aliases(activities)
    facts: list[Fact] = []
    coverage: list[Coverage] = []
    manifest = {}
    stats = defaultdict(int)
    for row in read_csv(dataset_dir / "evidence_files.csv"):
        fid, path = row["file_id"], dataset_dir / row["file_path"]
        cite_at = parse_ts(row["captured_at"])
        manifest[fid] = {**row, "captured": cite_at}
        suffix = path.suffix.lower()
        fs, cov = [], []
        if suffix == ".sql":
            fs, cov = parse_sql(path.read_text(encoding="utf-8"), fid, cite_at)
        elif suffix == ".json":
            fs, cov = parse_json(path.read_text(encoding="utf-8"), fid, cite_at)
        elif suffix == ".log":
            fs = parse_log(path.read_text(encoding="utf-8"), fid, cite_at)
        elif suffix == ".txt":
            fs = parse_flat_text(path.read_text(encoding="utf-8"), fid, cite_at)
        elif suffix in (".pdf", ".png", ".jpg", ".jpeg"):
            fs = parse_document(path, fid, cite_at, aliases)
        stats[suffix] += len(fs)
        facts += fs
        coverage += cov
    act = activity_facts(activities)
    stats["activity"] = len(act)
    return EvidenceStore(facts + act, coverage, activities, manifest, parse_stats=dict(stats)).index()
