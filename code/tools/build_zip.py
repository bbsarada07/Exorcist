"""Build <repo>/code.zip from code/ only and verify it carries no secrets, caches or nested archives.

    python code/tools/build_zip.py
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent
REPO = CODE.parent
EXCLUDE_DIRS = {"__pycache__", "cache", "node_modules", ".venv", "venv", "dist", "data", "dataset", ".git",
                ".vite", "test-results", "playwright-report", "coverage"}
EXCLUDE_FILES = {".env"}
EXCLUDE_SUFFIX = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".pyc", ".tsbuildinfo", ".mp4", ".mov", ".webm"}
SECRET = re.compile(r"(sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")


def included(p: Path) -> bool:
    rel = p.relative_to(CODE)
    parts = set(rel.parts)
    # code/ui/public/data is the UI's committed static export (it must ship); any other "data" dir is excluded
    if "data" in parts and rel.parts[:3] == ("ui", "public", "data"):
        parts.discard("data")
    return not (parts & EXCLUDE_DIRS or p.name in EXCLUDE_FILES or p.suffix.lower() in EXCLUDE_SUFFIX)


def main() -> int:
    out = REPO / "code.zip"
    files = sorted(p for p in CODE.rglob("*") if p.is_file() and included(p))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, Path("code") / p.relative_to(CODE))
    problems = []
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        for n in names:
            if n.lower().endswith(tuple(EXCLUDE_SUFFIX)):
                problems.append(f"nested archive {n}")
            data = z.read(n)
            if SECRET.search(data.decode("utf-8", errors="ignore")):
                problems.append(f"possible secret in {n}")
        required = ["code/README.md", "code/main.py", "code/evaluation/evaluation_report.md", "code/evaluation/usage_report.md"]
        problems += [f"missing {r}" for r in required if r not in names]
    print(f"{out} files={len(names)} size={out.stat().st_size / 1e6:.2f} MB")
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
