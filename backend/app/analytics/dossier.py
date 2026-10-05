"""Render a corpus tender as a review document, so screening leads can be investigated by the agent."""
from __future__ import annotations

from .corpus import Corpus

METHOD = {"open": "Open competitive bidding", "rfq": "Request for quotations", "direct": "Direct contracting"}


def render_tender(c: Corpus, tender_id: str) -> str:
    t = c.tenders[c.tenders.tender_id == tender_id]
    if t.empty:
        raise KeyError(tender_id)
    t = t.iloc[0]
    bids = c.bids_x[c.bids_x.tender_id == tender_id].merge(
        c.companies[["company_id", "name", "address", "phone"]], on="company_id").sort_values("price")
    rows = "\n".join(f"| {b.name} | {b.address} | {b.phone} | {b.price:,.0f} |" for b in bids.itertuples())
    winner = c.company_name.get(t.winner_id, t.winner_id)
    amend = (f"- Amendment 1: contract value increase (+{t.amendment_pct:.0%} of the original contract value)."
             if t.amendment_pct > 0 else "None to date.")
    just = f"\n## Justification\n\n{t.justification or 'Not provided.'}\n" if t.method == "direct" else ""
    return f"""# Award Record: {t.title}

Tender reference: {t.tender_id}
Procuring entity: {c.entity_name.get(t.entity_id, t.entity_id)}
Procurement method: {METHOD.get(t.method, t.method)}
Currency: USD
Estimated contract value: USD {t.estimated_value:,.0f}
Review threshold: USD {t.review_threshold:,.0f}
Invitation published: {t.published.date().isoformat()}
Submission deadline: {t.deadline.date().isoformat()}

## Bids received

| Bidder | Address | Phone | Bid price (USD) |
|---|---|---|---|
{rows}

## Evaluation and award

Awarded to: {winner}
Contract value: USD {t.contract_value:,.0f}
Award rationale: {t.award_note or 'Not recorded.'}
{just}
## Contract amendments

{amend}
"""
