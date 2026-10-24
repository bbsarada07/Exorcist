"""Optional LLM layer. Off by default; the deterministic engine never needs it.

Enable with AUDIT_LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY (read from the environment only).
Used solely as a fallback for low-confidence intent classification; it can never override evidence.
Every call is cached by content hash (temperature 0, JSON output) and logged to a token ledger that
evaluation/usage_report.md is generated from.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .config import CACHE_DIR, OUT_DIR

INTENT_PROMPT = (
    "You classify customer privacy requests. Answer with JSON {\"deletion\": true|false}. "
    "true only if the person asks to delete/erase/close their account or personal data; "
    "access, export, correction, marketing opt-out and help requests are false.\n\nRequest:\n"
)
# USD per million tokens, used only for the cost estimate in the usage report
PRICES = {"claude-haiku-5-5": (1.0, 5.0), "claude-sonnet-5-5": (3.0, 15.0)}


class LLMClient:
    def __init__(self, provider: str, model: str):
        self.provider, self.model = provider, model
        self.cache_dir = CACHE_DIR / "llm"
        self.ledger = OUT_DIR / "llm_ledger.jsonl"
        self._client = None

    def _call(self, prompt: str, case_hint: str = "") -> str | None:
        key = hashlib.sha256(f"{self.model}\n{prompt}".encode()).hexdigest()
        cached = self.cache_dir / f"{key}.json"
        if cached.exists():
            data = json.loads(cached.read_text(encoding="utf-8"))
            self._log(data["usage"], case_hint, cached=True)
            return data["text"]
        if self._client is None:
            import anthropic  # optional dependency
            self._client = anthropic.Anthropic()
        resp = self._client.messages.create(model=self.model, max_tokens=50, temperature=0,
                                            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"text": text, "usage": usage}), encoding="utf-8")
        self._log(usage, case_hint, cached=False)
        return text

    def _log(self, usage: dict, case_hint: str, cached: bool) -> None:
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "provider": self.provider, "model": self.model,
                                 "case": case_hint, "cached": cached, **usage}) + "\n")

    def classify_intent(self, text: str) -> bool | None:
        out = self._call(INTENT_PROMPT + text, case_hint="intent")
        try:
            return bool(json.loads(out)["deletion"])
        except Exception:
            return None


def build_llm() -> LLMClient | None:
    provider = os.environ.get("AUDIT_LLM_PROVIDER", "").strip().lower()
    if provider != "anthropic" or not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return LLMClient(provider, os.environ.get("AUDIT_LLM_MODEL", "claude-haiku-5-5"))


def reset_ledger() -> None:
    p = OUT_DIR / "llm_ledger.jsonl"
    if p.exists():
        p.unlink()


def read_ledger(path: Path | None = None) -> list[dict]:
    p = path or OUT_DIR / "llm_ledger.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
