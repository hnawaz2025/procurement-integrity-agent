"""Cost model for the review funnel: 'agent on every contract' vs 'screen everything, agent on leads'.

Per-review LLM cost uses the measured average from the latest Claude-mode eval when available
(evals/results/latest.json); otherwise a clearly labelled estimate.
"""
from __future__ import annotations

import json

from ..config import PRICES, ROOT

# Estimate when no measured run exists: ~60k input tokens (40% cache reads) + ~6k output on the orchestrator,
# plus subagent and extraction calls. Replace by running `make eval` with ANTHROPIC_API_KEY set.
EST_ORCH_IN, EST_ORCH_OUT, EST_CACHE_SHARE = 60_000, 6_000, 0.4


def per_review_cost() -> tuple[float, str]:
    p = ROOT / "evals" / "results" / "latest.json"
    if p.exists():
        d = json.loads(p.read_text())
        if d.get("mode") == "claude" and d.get("agent", {}).get("avg_cost_usd"):
            return float(d["agent"]["avg_cost_usd"]), "measured (latest Claude-mode eval)"
    pin, pout = PRICES["claude-opus-5-5"]
    est = (EST_ORCH_IN * (1 - EST_CACHE_SHARE) * pin + EST_ORCH_IN * EST_CACHE_SHARE * pin * 0.1
           + EST_ORCH_OUT * pout) / 1e6 + 0.05  # + subagent/extraction allowance
    return round(est, 3), "estimate (no measured Claude run yet)"


def project(n_contracts: int, lead_rate: float, screening_seconds_per_100k: float,
            minutes_per_human_review: float = 45.0) -> dict:
    cost, basis = per_review_cost()
    leads = max(1, int(n_contracts * lead_rate))
    return {
        "contracts_per_year": n_contracts,
        "per_review_cost_usd": cost,
        "cost_basis": basis,
        "agent_on_everything": {"llm_reviews": n_contracts, "llm_cost_usd": round(n_contracts * cost),
                                "human_hours_if_all_reviewed": round(n_contracts * minutes_per_human_review / 60)},
        "funnel": {"screening_compute_seconds": round(n_contracts / 100_000 * screening_seconds_per_100k, 1),
                   "leads": leads, "lead_rate": round(lead_rate, 4), "llm_cost_usd": round(leads * cost),
                   "human_hours": round(leads * minutes_per_human_review / 60)},
        "assumptions": f"{minutes_per_human_review:.0f} reviewer-minutes per case; lead rate from the 100k-tender benchmark",
    }
