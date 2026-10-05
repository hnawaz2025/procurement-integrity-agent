"""Deterministic verifier + baseline guarantee. Runs after the agent loop; trusts nothing it says.

1. Every flag's evidence_quote must appear in the redacted document (whitespace-normalised, fuzzy >= 0.85).
2. Every graph_path must be one actually returned by find_connections.
3. Every citation must be a chunk actually retrieved in this review.
4. Title + rationale must pass the non-accusatory language policy.
5. Baseline guarantee: every deterministic signal is covered by a surviving flag or an explicit dismissal.
   Uncovered signals become baseline flags, so an agent (or an injected instruction) cannot silently drop evidence.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..guardrails.language_policy import violations
from ..rag.hybrid_index import get_index
from ..schemas import GuardrailEvent, RejectedFlag, RiskFlag, Signal
from .prompts import KB_QUERY
from .tools import ReviewContext, has_corpus_evidence

PRACTICE = {"bid_clustering": "collusive", "shared_bidder_details": "collusive", "bid_rotation": "collusive",
            "hidden_ownership_link": "collusive", "tailored_specifications": "collusive",
            "threshold_avoidance": "corrupt", "split_purchases": "corrupt", "short_bidding_window": "corrupt",
            "unjustified_direct_contracting": "corrupt", "large_amendment": "corrupt", "award_not_lowest": "corrupt",
            "supplier_concentration": "corrupt", "new_or_shell_bidder": "fraudulent",
            "document_manipulation": "obstructive"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def quote_in_doc(quote: str, doc: str) -> bool:
    q, d = _norm(quote).strip("\"'“”"), _norm(doc)
    if not q:
        return False
    if q in d:
        return True
    lines = [_norm(ln) for ln in doc.splitlines() if ln.strip()]
    return max((SequenceMatcher(None, q, ln).ratio() for ln in lines), default=0) >= 0.85


def check_flag(f: RiskFlag, ctx: ReviewContext) -> list[str]:
    reasons = []
    if f.evidence_quote and not quote_in_doc(f.evidence_quote, ctx.doc):
        reasons.append("evidence_quote not found in the submitted document")
    if f.graph_path and not any(f.graph_path in (p, p[::-1]) for p in ctx.graph_paths):
        reasons.append("graph_path was not returned by find_connections")
    if not f.evidence_quote and not f.graph_path and not has_corpus_evidence(ctx, f):
        reasons.append("no evidence")
    bad = [c for c in f.citations if c not in ctx.retrieved]
    if bad:
        reasons.append(f"citations not retrieved in this review: {bad}")
    if not f.citations:
        reasons.append("no citations")
    v = violations(f"{f.title} {f.rationale}")
    if v:
        reasons.append(f"accusatory language: {v}")
    return reasons


def baseline_flag(s: Signal, ctx: ReviewContext) -> RiskFlag:
    hits = get_index().search(KB_QUERY.get(s.category.value, s.title), 2)
    for h in hits:
        ctx.retrieved.setdefault(h["id"], {**h, "query": f"baseline:{s.signal_id}"})
    return RiskFlag(category=s.category, practice_hint=PRACTICE.get(s.category.value, "unclear"),
                    severity=s.severity, title=s.title,
                    rationale=f"{s.detail} (Added by the baseline guarantee: deterministic signal not addressed by the agent.)",
                    evidence_quote=s.evidence_quote, graph_path=s.graph_path, citations=[h["id"] for h in hits],
                    signal_refs=[s.signal_id], origin="pattern" if s.code.startswith(("P-", "G-")) else "rule")


def verify(ctx: ReviewContext) -> tuple[list[RiskFlag], list[RejectedFlag], int]:
    kept, rejected = [], []
    for f in ctx.flags:
        r = check_flag(f, ctx)
        (rejected.append(RejectedFlag(flag=f, reasons=r)) if r else kept.append(f))
    covered = {s for f in kept for s in f.signal_refs} | {d.signal_id for d in ctx.dismissals}
    added = 0
    for sid, s in ctx.signals.items():
        if sid not in covered:
            bf = baseline_flag(s, ctx)
            bf.id = f"F{len(ctx.flags) + added + 1}"
            kept.append(bf)
            added += 1
    if added:
        ctx.guardrail_events.append(GuardrailEvent(
            kind="baseline_guarantee", severity="medium",
            detail=f"{added} deterministic signal(s) were not addressed by the agent and were added as baseline flags."))
    for f in kept:  # origin bookkeeping: llm flags that rest on deterministic signals are 'both'
        if f.origin == "llm" and f.signal_refs:
            f.origin = "both"
    return kept, rejected, added
