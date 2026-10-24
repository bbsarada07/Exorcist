"""IntentAgent: does request_text authorise deletion?

Rules first (multilingual deletion cues, explicit negations, non-deletion intents). The optional LLM
hook is only consulted when the rules are not confident, and it can never override a rule verdict
that has an explicit negation or an explicit deletion request.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DELETION_CUES = [
    r"\b(delete|deleted|deleting|deletion|erase|erased|erasure)\b",
    r"\bclose (my|this|the) account\b", r"\bclose the account\b", r"\bclose this account\b",
    r"\bremov(e|ed|al)\b",                       # "remove that search result", "have been removed"
    r"\b(is|was|are) (gone|removed)\b",          # follow-ups on an earlier deletion
    r"\b(account|personal)[- ]data deletion\b",
    r"exclus[ãa]o|excluir|apagar",              # pt
    r"eliminaci[óo]n|eliminar|borrar",          # es
    r"suppression|supprimer|effacer",           # fr
    r"削除",                                     # ja
    r"삭제",                                     # ko
]
NEGATIONS = [
    r"\bnot (asking|requesting) (for )?(deletion|to (delete|erase))\b",
    r"\bnot a request to (erase|delete)\b",
    r"\b(do not|don't|dont) (delete|close|erase|remove)\b",
    r"\bwithout removing\b",
    r"\b(keep|leave) (the|my) (account|profile)\b",
    r"\bleave the account active\b",
    r"\b(still|continue to) (need|want|use)\b", r"\bcontinue using\b",
    r"\bonly\.?$|\blists only\b",
]
NON_DELETION_INTENTS = {
    "correction": r"\b(out of date|replace it|misspelled|correct it|change the email)\b",
    "marketing_opt_out": r"\b(promotional emails|marketing lists)\b",
    "access_or_export": r"\b(like to download|portable format|send me a copy|copy of last|what personal information)\b",
    "account_help": r"\b(resetting the login|can't access)\b",
}


@dataclass
class IntentResult:
    authorises_deletion: bool
    confidence: float
    reason: str


def classify(text: str) -> IntentResult:
    t = " ".join(text.lower().split())
    cues = [p for p in DELETION_CUES if re.search(p, t)]
    negs = [p for p in NEGATIONS if re.search(p, t)]
    other = [k for k, p in NON_DELETION_INTENTS.items() if re.search(p, t)]
    if negs:
        return IntentResult(False, 0.95, f"explicit negation; intent={','.join(other) or 'non-deletion'}")
    if cues and not other:
        return IntentResult(True, 0.95, "explicit deletion request")
    if cues and other:
        return IntentResult(True, 0.6, f"deletion cue with other intent {other}")
    if other:
        return IntentResult(False, 0.9, f"non-deletion intent {other}")
    return IntentResult(False, 0.4, "no deletion cue")


def classify_with_fallback(text: str, llm=None) -> IntentResult:
    """Rules first; an optional LLM (see audit.llm) may only resolve low-confidence rule outputs."""
    res = classify(text)
    if res.confidence >= 0.8 or llm is None:
        return res
    verdict = llm.classify_intent(text)
    if verdict is None:
        return res
    return IntentResult(verdict, 0.7, f"llm fallback ({res.reason})")
