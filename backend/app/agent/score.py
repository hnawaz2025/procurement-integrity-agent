"""Computed confidence + escalation. Confidence is NOT the model's self-assessment: it is derived
from verifiable properties of the review (documented in docs/model_card.md)."""
from __future__ import annotations

from ..schemas import ConfidenceBreakdown, RiskFlag
from .tools import ReviewContext

W = {"grounding": 0.30, "citation_validity": 0.20, "retrieval_strength": 0.15, "signal_agreement": 0.20,
     "coverage": 0.15}
NETWORK = {"hidden_ownership_link", "bid_rotation"}


def confidence(ctx: ReviewContext, kept: list[RiskFlag], n_rejected: int, n_baseline: int) -> ConfidenceBreakdown:
    proposed = len(ctx.flags)
    grounding = 1.0 if proposed == 0 else (proposed - n_rejected) / proposed
    cites = [c for f in kept for c in f.citations]
    citation_validity = 1.0 if not cites else sum(c in ctx.retrieved for c in cites) / len(cites)
    cos = [r["cosine"] for r in ctx.retrieved.values() if r.get("cosine") is not None]
    retrieval_strength = min(1.0, max(0.0, (sum(cos) / len(cos) - 0.1) / 0.5)) if cos else 0.5
    n_sig = len(ctx.signals)
    signal_agreement = 1.0 if n_sig == 0 else (n_sig - n_baseline) / n_sig
    has_parties = bool(ctx.facts and len(ctx.facts.bids) >= 1)
    steps = ["extract_procurement_facts", "run_red_flag_rules", "search_guidance"]
    if has_parties:
        steps.append("network")
    used = ctx.tools_used | ({"network"} if ctx.tools_used & {"find_connections", "check_patterns",
                                                               "delegate_network_investigation"} else set())
    coverage = sum(s in used for s in steps) / len(steps)
    parts = dict(grounding=grounding, citation_validity=citation_validity, retrieval_strength=retrieval_strength,
                 signal_agreement=signal_agreement, coverage=coverage)
    score = sum(W[k] * v for k, v in parts.items())
    return ConfidenceBreakdown(**{k: round(v, 3) for k, v in parts.items()}, score=round(score, 3))


def escalate(kept: list[RiskFlag], conf: float, injection: bool) -> tuple[str, str, list[str]]:
    reasons = []
    if any(f.severity == "high" for f in kept):
        reasons.append("high-severity signal present")
    if any(f.category.value in NETWORK for f in kept):
        reasons.append("network-level signal (hidden link or rotation) present")
    if injection:
        reasons.append("embedded instructions detected in document")
    if conf < 0.5:
        reasons.append(f"low analysis confidence ({conf:.2f})")
    sev = "high" if any(f.severity == "high" for f in kept) else "medium" if any(
        f.severity == "medium" for f in kept) else "low"
    return sev, ("priority_review" if reasons else "standard_review"), reasons
