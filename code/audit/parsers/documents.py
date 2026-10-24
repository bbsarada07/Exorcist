"""PDFs and screenshots -> text (pdftotext / Tesseract, cached by content hash) -> facts.

Screenshots and PDFs are business artifacts, not verdicts. We only extract which resources they
show and which identifiers appear next to them:
  * a resource id on an OCR/PDF line inherits the identifiers on that same line;
  * a catalog alias (e.g. a statement number or file name from LINK_RESOURCE_IDENTITY) found in the
    text means the document shows that resource;
  * PDFs are single-subject documents, so alias hits inherit every identifier in the PDF.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from ..config import CACHE_DIR
from ..model import Fact, resources_in, system_of
from ..util import identifier_of, identifiers_in_text

DISABLED_WORDS = ("disabled", "paused", "stopped", "inactive")


def extract_text(path: Path) -> str:
    """Text of a PDF/PNG; cached so repeated runs are fast and offline once warmed."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()[:24]
    cache = CACHE_DIR / "text" / f"{digest}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    text = ""
    if path.suffix.lower() == ".pdf" and shutil.which("pdftotext"):
        text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace").stdout
    elif path.suffix.lower() in (".png", ".jpg", ".jpeg") and shutil.which("tesseract"):
        text = subprocess.run(["tesseract", str(path), "stdout"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace").stdout
    if text:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
    return text


def parse_document(path: Path, evidence_id: str, cite_at: datetime, aliases: dict[str, str]) -> list[Fact]:
    text = extract_text(path)
    if not text:
        return []
    is_pdf = path.suffix.lower() == ".pdf"
    lines = [l for l in text.splitlines() if l.strip()]
    whole_keys = identifiers_in_text(text)
    hits: dict[str, dict] = {}

    def add(rid: str, keys: set, line: str):
        h = hits.setdefault(rid, {"keys": set(), "lines": []})
        h["keys"] |= keys
        h["lines"].append(line.strip())

    for line in lines:
        line_keys = identifiers_in_text(line)
        for rid in resources_in(line):
            add(rid, whole_keys if is_pdf else line_keys, line)
        for alias, rid in aliases.items():
            if alias == rid or alias not in line:
                continue
            # an alias that is itself a person key (e.g. "user_17") only names the page when it is the title line
            if identifier_of(alias) and line.strip() != alias:
                continue
            add(rid, whole_keys if is_pdf else line_keys, line)

    facts = []
    for rid, h in sorted(hits.items()):
        system = system_of(rid)
        if not system:
            continue
        attrs = {"text": " | ".join(h["lines"])[:600]}
        if system == "integration_service":
            attrs["enabled"] = not any(w in attrs["text"].lower() for w in DISABLED_WORDS)
        category = "SUPPORT_ATTACHMENT" if (is_pdf and system == "support_platform") else None
        exposed = {k if k != "user" else "user_ref" for k, _ in h["keys"]}
        facts.append(Fact(evidence_id=evidence_id, observed_at=cite_at, cite_at=cite_at, resource_id=rid,
                          system_id=system, location="document", exists=True, category=category,
                          exposed=frozenset(exposed), keys=frozenset(h["keys"]), attrs=attrs,
                          kind="record", source="pdf" if is_pdf else "ocr", note=path.name))
    return facts
