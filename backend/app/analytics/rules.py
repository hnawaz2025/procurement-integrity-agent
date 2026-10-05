"""Single-document red-flag rules R1-R7 over extracted ProcurementFacts.

Deterministic, explainable, and each emits a verbatim evidence line from the (redacted) document.
These form the agent's *baseline*: the agent may add judgement but may not silently drop them.
"""
from __future__ import annotations

from datetime import date

from ..config import settings
from ..schemas import Category, ProcurementFacts, Signal
from .entity_resolution import normalize_address, normalize_name, normalize_phone

T = settings.thresholds
JUSTIFY_KEYWORDS = ("non-responsive", "non responsive", "technical", "disqualif", "rejected", "failed",
                    "no conforme", "non conforme", "rechaz", "écart", "rejet")


def find_label_line(doc: str, *labels: str) -> str | None:
    for lab in labels:
        for ln in doc.splitlines():
            if ln.strip().lower().startswith(lab.lower()):
                return ln.strip()
    return None


def find_line(doc: str, *needles: str) -> str | None:
    for n in needles:
        if not n:
            continue
        for ln in doc.splitlines():
            if n.lower() in ln.lower():
                return ln.strip()
    return None


def _d(s: str | None) -> date | None:
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except ValueError:
        return None


def run_rules(f: ProcurementFacts, doc: str) -> list[Signal]:
    out: list[Signal] = []

    def add(code, cat, sev, title, detail, quote, entities=(), **stats):
        out.append(Signal(signal_id="", code=code, category=cat, severity=sev, title=title, detail=detail,
                          evidence_quote=quote, entities=list(entities), stats=stats))

    priced = [b for b in f.bids if b.price]
    # R1 clustered bids
    if len(priced) >= 3:
        lo, hi = min(b.price for b in priced), max(b.price for b in priced)
        spread = (hi - lo) / lo
        if spread < T.bid_spread_pct:
            top = max(priced, key=lambda b: b.price)
            add("R1", Category.bid_clustering, "medium", "Bid prices tightly clustered",
                f"{len(priced)} bids within {spread:.2%} of each other (threshold {T.bid_spread_pct:.0%}).",
                find_line(doc, top.bidder), [b.bidder for b in priced], spread=round(spread, 4))
    # R2 shared contact details
    for key, norm in (("address", normalize_address), ("phone", normalize_phone)):
        seen: dict[str, str] = {}
        for b in f.bids:
            v = getattr(b, key)
            if not v:
                continue
            k = norm(v)
            if k and k in seen and normalize_name(seen[k]) != normalize_name(b.bidder):
                add("R2", Category.shared_bidder_details, "high", f"Competing bidders share the same {key}",
                    f"{seen[k]} and {b.bidder} list the same {key}.", find_line(doc, b.bidder),
                    [seen[k], b.bidder], attribute=key)
            seen.setdefault(k, b.bidder)
    # R3 just under threshold
    v = f.contract_value or f.estimated_value
    if v and f.review_threshold and (1 - T.under_threshold_band) * f.review_threshold <= v < f.review_threshold:
        add("R3", Category.threshold_avoidance, "medium" if f.procurement_method == "rfq" else "low",
            "Contract value just below review threshold",
            f"Value {v:,.0f} is {1 - v / f.review_threshold:.1%} below the {f.review_threshold:,.0f} threshold.",
            find_label_line(doc, "Contract value", "Valor del contrato", "Valeur du marché", "Estimated contract value"),
            ratio=round(v / f.review_threshold, 3))
    # R4 short window
    p, d = _d(f.published), _d(f.deadline)
    if p and d:
        days = (d - p).days
        minimum = T.min_window_open if f.procurement_method == "open" else T.min_window_rfq
        if 0 <= days < minimum:
            add("R4", Category.short_bidding_window, "medium", "Unusually short bidding window",
                f"{days}-day window for a '{f.procurement_method}' procedure (prototype minimum {minimum}).",
                find_line(doc, f.deadline), window_days=days, minimum=minimum)
    # R5 direct contracting without justification
    if f.procurement_method == "direct" and not f.justification:
        big = bool(v and f.review_threshold and v >= f.review_threshold)
        add("R5", Category.unjustified_direct_contracting, "high" if big else "medium",
            "Direct contracting without stated justification",
            "Single-source award with no documented justification" + (" above the review threshold." if big else "."),
            find_label_line(doc, "Procurement method", "Método de adquisición", "Méthode de passation"))
    # R6 large amendments
    for a in f.amendments:
        if a.pct and a.pct > T.amendment_pct:
            add("R6", Category.large_amendment, "high" if a.pct >= 0.3 else "medium",
                "Large post-award amendment", f"Amendment of +{a.pct:.0%} (threshold {T.amendment_pct:.0%}).",
                find_line(doc, a.description[:40]), pct=a.pct)
    # R7 award not to lowest bid without rationale
    if f.awarded_to and len(priced) >= 2:
        lowest = min(priced, key=lambda b: b.price)
        if normalize_name(lowest.bidder) != normalize_name(f.awarded_to):
            rationale = (f.award_rationale or "").lower()
            if not any(k in rationale for k in JUSTIFY_KEYWORDS):
                add("R7", Category.award_not_lowest, "medium", "Award not made to the lowest bid",
                    f"Lowest bid was {lowest.bidder} ({lowest.price:,.0f}); award to {f.awarded_to} "
                    "without a documented reason.", find_label_line(doc, "Awarded to", "Adjudicado a", "Attribué à"),
                    [lowest.bidder, f.awarded_to])
    return out
