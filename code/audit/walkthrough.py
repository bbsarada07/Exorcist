"""Evidence-first case walkthrough + controlled mutations (live demo; sidecar only, never writes output.csv).

    python code/main.py investigate --case <case_id>
    python code/main.py investigate --random --seed 7
    python code/main.py investigate --case <case_id> --mutate add-active-flow
    python code/main.py investigate --random --seed 7 --mutate move-audit-before-resurrection
    python code/main.py investigate --random --seed 7 --mutate change-email-case

Mutations act on a copy of the case data (the request row or the in-memory evidence store), never on dataset/.
Each one states what the engine's logic predicts, re-runs the engine and checks the prediction.
"""
from __future__ import annotations

import argparse
import random
import re
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from .config import DATASET_DIR, STORE_TYPE
from .evidence_cards import CardBuilder
from .model import Fact
from .parsers import EvidenceStore
from .pipeline import AuditEngine
from .util import case_sort_key, iso, read_csv

GHOST_TYPES = ("leftover record", "exposed PII in a retained record", "active sync", "restore risk", "replica drift")


def mask_email(email: str) -> str:
    local, _, dom = email.partition("@")
    return f"{local[:3]}••@••••.{dom.rsplit('.', 1)[-1]}" if dom else "••••"


def ghost_type(a) -> str:
    """Classify one violation (a "ghost") by what kind of leftover it is."""
    if a.finding == "REPORT_EXPOSED_PII":
        return "exposed PII in a retained record"
    if a.finding == "REPORT_ACTIVE_DATA_FLOW":
        return "active sync"
    if a.finding == "REPORT_RESTORE_RISK":
        return "restore risk"
    return "replica drift" if a.drift else "leftover record"


def eval_ids(engine) -> list[str]:
    return sorted((r["case_id"] for r in read_csv(engine.dataset_dir / "deletion_requests.csv")), key=case_sort_key)


# ---------------------------------------------------------------- walkthrough
def walkthrough(engine, results, cid: str, builder: CardBuilder | None = None) -> list[str]:
    builder = builder or CardBuilder(engine)
    r = results[cid]
    c = r.case
    out = [f"{cid}: workflow reported {c.reported_status} at {iso(c.reported_at)}; audit cut {iso(c.audit_at)}; "
           f"reconstructed {r.status}"]
    out.append(f"1. Request ({iso(c.requested_at)}): {c.intent.reason} (intent confidence {c.intent.confidence:.2f}).")
    if c.user_id is None:
        out.append(f"   Email {mask_email(c.email)} resolves to no known subject ({c.resolution.match}); nothing can be audited.")
        return out
    out.append(f"   Email {mask_email(c.email)} resolves to {c.user_id} as its {c.resolution.match} address.")
    if r.status == "NOT_APPLICABLE":
        out.append("   The text does not authorise deletion, so the answer is NOT_APPLICABLE with no steps.")
        return out
    ids = Counter(f"{i.origin} {i.kind}" for i in engine.identity.subjects[c.user_id].identifiers if i.kind != "name")
    out.append("2. Identifiers searched in every store: " + ", ".join(f"{n} {k}" for k, n in sorted(ids.items())) + ".")
    modes = Counter(l.mode for l in r.links.resources.values())
    out.append(f"3. Resources tied to the subject: {len(r.links.resources)} ("
               + ", ".join(f"{n} by {m.replace('_', ' ')}" for m, n in sorted(modes.items())) + ")"
               + (f"; account delete event {r.links.account_event.activity_id} via {r.links.account_mode.replace('_', ' ')}"
                  if r.links.account_event else "; no account delete event found") + ".")
    findings = [s for s in r.steps if s.phase == "FINDING"]
    if not findings:
        out.append("4. No violation at audit_at. Evidence for the compliant end state:")
        for s in r.steps:
            out.append(f"   {s.operation} {s.system_id}/{s.resource_id} [{STORE_TYPE.get(s.system_id, s.system_id)}] "
                       f"cites {s.evidence_id}")
    else:
        out.append(f"4. Findings ({len(findings)}), evidence first:")
        for s in findings:
            card = builder.card(r, s)
            a = next(x for x in r.assessments if x.resource_id == s.resource_id)
            out.append(f"   F{s.step_no} {s.operation} {s.system_id}/{s.resource_id} [{card['where']['store_type']}]"
                       f"  ghost type: {ghost_type(a)}")
            why = [m for m in card["why"]["matches"] if m["kind"] != "chain"]
            if why:
                out.append("      why it is the subject's: " + "; ".join(
                    f"{m['identifier']} ({m['mode']}) in {', '.join(m['evidence']) or 'no pre-audit file'}"
                    + (f" (+ {', '.join(m['captured_after_audit'])} captured after audit_at)" if m.get("captured_after_audit") else "")
                    for m in why[:3]))
            if card["why"]["chain"] and card["why"]["chain"]["mode"] != "chain_pinned":
                ch = card["why"]["chain"]
                out.append(f"      chain link: {ch['mode']} via {', '.join(ch['worker_events'])} (margin {ch['margin']})")
            st = card["state_at_audit"]["cited"]
            if st:
                locs = [l for l in st["locations"] if l != s.system_id]
                where = f" in {', '.join(locs)}" if locs else ""
                gone = f", already absent in {', '.join(st['absent_in'])}" if st["absent_in"] else ""
                exposed = f", exposes {', '.join(st['exposed'])}" if st["exposed"] and "exposes" not in card["state_at_audit"]["verdict"] else ""
                verdict = re.sub(r"\[([^\]]*)\]", lambda m: m.group(1).replace("'", ""), card["state_at_audit"]["verdict"])
                out.append(f"      state at audit_at: {verdict}{where}{gone}{exposed} "
                           f"(fact time {st['observed_at']}, {st['evidence_id']} captured {st['file_captured_at']})")
            else:
                out.append(f"      state at audit_at: {card['state_at_audit']['verdict']} (no citable pre-audit file)")
            for p in card["could_recreate"][:3]:
                out.append(f"      could recreate: {p['path']}: {p['how']} [{p['link']}]")
            out.append(f"      confidence {card['confidence']}: " + "; ".join(card["confidence_factors"]))
        cited = {s.resource_id: s.evidence_id for s in findings}
        claims = [(w, a) for a in r.assessments if a.status == "violation" for w in r.links.worker_events
                  if w.resource_id == a.resource_id and w.reported_result == "SUCCESS"]
        for w, a in claims[:3]:
            out.append(f"   Claim vs evidence: {w.activity_id} ({iso(w.event_time)}) reported {w.event_type} SUCCESS on "
                       f"{a.resource_id}, but {cited.get(a.resource_id) or 'the evidence'} still shows it at audit_at ({a.reason}).")
        rem = [s for s in r.steps if s.phase == "REMEDIATION"]
        out.append("5. Plan: " + " -> ".join(f"{s.operation} {s.resource_id}" for s in rem) + ".")
        ver = [s for s in r.steps if s.phase == "VERIFICATION"]
        out.append(f"6. Then {len(ver)} checks must pass: " + ", ".join(f"{s.operation} {s.resource_id}" for s in ver) + ".")
    return out


# ---------------------------------------------------------------- mutations
@dataclass
class MutationResult:
    case_id: str
    mutation: str
    change: str
    prediction: str
    before: tuple
    after: tuple
    held: bool

    def lines(self) -> list[str]:
        b_steps, a_steps = set(self.before[1]), set(self.after[1])
        out = [f"mutation {self.mutation} on {self.case_id}: {self.change}",
               f"prediction: {self.prediction}",
               f"before: {self.before[0]} with {len(self.before[1])} steps; after: {self.after[0]} with {len(self.after[1])} steps"]
        out += [f"  + {s}" for s in self.after[1] if s not in b_steps]
        out += [f"  - {s}" for s in self.before[1] if s not in a_steps]
        out.append("prediction held" if self.held else "PREDICTION FAILED")
        return out


def _summary(r) -> tuple:
    return r.status, tuple(f"{s.phase} {s.operation} {s.system_id}/{s.resource_id}" for s in r.steps)


def applicable(mutation: str, results, ids) -> list[str]:
    del_ids = [c for c in ids if results[c].status != "NOT_APPLICABLE"]
    if mutation == "move-audit-before-resurrection":
        return [c for c in del_ids if _resurrection(results[c]) is not None]
    return del_ids


def _resurrection(r):
    jobs = [j for a in r.assessments if a.status == "violation" for j in a.resurrected_by if j.event_time > r.case.requested_at]
    return min(jobs, key=lambda j: (j.event_time, j.activity_id)) if jobs else None


def mutate(engine: AuditEngine, results, cid: str, mutation: str) -> MutationResult:
    r = results[cid]
    before = _summary(r)
    if mutation == "change-email-case":
        new_email = r.case.email.upper() if r.case.email != r.case.email.upper() else r.case.email.lower()

        def transform(row):
            return {**row, "email": new_email} if row["case_id"] == cid else row
        after = engine.run(transform=transform)[cid]
        return MutationResult(cid, mutation, f"request email case changed to {mask_email(new_email)}",
                              "identities are matched after normalisation, so status and steps do not change",
                              before, _summary(after), _summary(after) == before)

    if mutation == "move-audit-before-resurrection":
        job = _resurrection(r)
        if job is None:
            raise ValueError(f"{cid} has no resurrection after its request; try --random with this mutation")
        new_audit = job.event_time - timedelta(minutes=1)
        victims = sorted({a.resource_id for a in r.assessments for j in a.resurrected_by if j.activity_id == job.activity_id})

        def transform(row):
            return {**row, "audit_at": iso(new_audit)} if row["case_id"] == cid else row
        mutated = engine.run(transform=transform)[cid]
        after = _summary(mutated)
        still = [a.resource_id for a in mutated.assessments if a.resource_id in victims and
                 any(j.activity_id == job.activity_id for j in a.resurrected_by)]
        return MutationResult(cid, mutation, f"audit_at moved to {iso(new_audit)}, one minute before {job.activity_id} "
                              f"({job.event_type}) repopulated {', '.join(victims)}",
                              f"the resurrection is invisible at the new audit cut, so it no longer explains {', '.join(victims)}",
                              before, after, not still)

    if mutation == "add-active-flow":
        if r.case.user_id is None or r.status == "NOT_APPLICABLE":
            raise ValueError(f"{cid} is not a deletion case")
        subject = engine.identity.subjects[r.case.user_id]
        email = next(i.value for i in subject.identifiers if i.kind == "email" and i.origin == "current")
        nums = [int(rid.rsplit("_", 1)[1]) for rid in engine.ev.by_resource if rid.startswith("data_flow_")]
        rid = f"data_flow_{max(nums, default=0) + 1}"
        t = r.case.audit_at - timedelta(hours=1)
        fact = Fact("mutation_injected", t, t, rid, "integration_service", exists=True, category="DATA_FLOW",
                    exposed=frozenset({"email"}), keys=frozenset({("email", email), ("user", subject.user_id)}),
                    attrs={"enabled": True}, source="mutation", note="injected enabled connector")
        ev = EvidenceStore(engine.ev.facts + [fact], engine.ev.coverage, engine.ev.activities, engine.ev.manifest).index()
        mutated = AuditEngine(engine.dataset_dir, llm=engine.llm, evidence=ev).run()[cid]
        after = _summary(mutated)
        want = {f"FINDING REPORT_ACTIVE_DATA_FLOW integration_service/{rid}",
                f"REMEDIATION DISABLE_DATA_FLOW integration_service/{rid}",
                f"VERIFICATION VERIFY_DATA_FLOW_DISABLED integration_service/{rid}"}
        if before[0] == "INCOMPLETE":
            prediction = f"exactly three steps are added (finding, DISABLE_DATA_FLOW, verification for {rid}); nothing else changes"
            held = after[0] == "INCOMPLETE" and set(after[1]) == set(before[1]) | want
        else:  # COMPLETE -> INCOMPLETE: by convention only account + retained-record verifications survive (planner.py)
            prediction = (f"status flips to INCOMPLETE with a finding, a DISABLE_DATA_FLOW and a verification for {rid}; "
                          "of the old verifications only account and retained-record checks remain (planner convention)")
            kept = {x for x in before[1] if x.split()[1] in ("VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT")
                    and x.split()[2].split("/")[0] in ("account_service", "security_service", "legal_service")}
            held = after[0] == "INCOMPLETE" and want <= set(after[1]) and set(after[1]) - want <= kept
        return MutationResult(cid, mutation, f"injected an enabled connector {rid} carrying the subject's current email, "
                              f"observed one hour before audit_at", prediction, before, after, held)
    raise ValueError(f"unknown mutation {mutation}")


# ---------------------------------------------------------------- CLI
MUTATIONS = ("add-active-flow", "move-audit-before-resurrection", "change-email-case")


def cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="main.py investigate")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--case")
    g.add_argument("--random", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mutate", choices=MUTATIONS)
    args = ap.parse_args(argv)
    engine = AuditEngine(DATASET_DIR)
    results = engine.run()
    ids = eval_ids(engine)
    if args.random:
        pool = applicable(args.mutate, results, ids) if args.mutate else ids
        cid = random.Random(args.seed).choice(pool)
        print(f"random pick with seed {args.seed} from {len(pool)} eligible evaluation cases: {cid}\n")
    else:
        cid = args.case
        if cid not in results:
            print(f"unknown case {cid}")
            return 2
    print("\n".join(walkthrough(engine, results, cid)))
    if args.mutate:
        print()
        try:
            print("\n".join(mutate(engine, results, cid, args.mutate).lines()))
        except ValueError as e:
            print(f"mutation not applicable: {e}")
            return 2
    return 0
