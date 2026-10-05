"""Stage 1-2 of the review funnel: deterministic screening of ALL tenders -> ranked lead queue.

lead_score = risk_weight x exposure, where exposure = log10(contract value).
Ranking by risk x exposure points scarce reviewer time at high-risk, high-value contracts.
"""
from __future__ import annotations

import time
from functools import lru_cache

import numpy as np
import pandas as pd

from ..config import settings
from .corpus import Corpus, load_corpus
from .graph import build_graph
from .patterns import PatternResults, run_all


def screen(c: Corpus) -> tuple[pd.DataFrame, PatternResults, dict]:
    t0 = time.perf_counter()
    g = build_graph(c)
    t_graph = time.perf_counter() - t0
    pr = run_all(c, g)
    t_patterns = time.perf_counter() - t0 - t_graph
    sig = pr.tender_signals.drop_duplicates(["tender_id", "signal"])
    agg = sig.groupby("tender_id").agg(
        risk=("weight", "sum"), signals=("signal", lambda s: sorted(set(s))),
        details=("detail", list)).reset_index()
    leads = agg.merge(c.tenders[["tender_id", "entity_id", "sector", "title", "winner_id", "contract_value",
                                 "published"]], on="tender_id")
    leads["exposure"] = np.log10(leads.contract_value.clip(lower=1000))
    leads["lead_score"] = (leads.risk * leads.exposure).round(2)
    leads["winner"] = leads.winner_id.map(c.company_name)
    leads["entity"] = leads.entity_id.map(c.entity_name)
    leads = leads[leads.risk >= settings.thresholds.lead_risk_min].sort_values("lead_score", ascending=False)
    timings = {"graph_s": round(t_graph, 3), "patterns_s": round(t_patterns, 3),
               "total_s": round(time.perf_counter() - t0, 3)}
    funnel = {
        "tenders_screened": int(c.n_tenders),
        "with_any_signal": int(agg.tender_id.nunique()),
        "leads": len(leads),
        "timings": timings,
    }
    return leads.reset_index(drop=True), pr, funnel


@lru_cache(maxsize=4)
def screen_cached(corpus_dir: str):
    return screen(load_corpus(corpus_dir))


def lead_records(leads: pd.DataFrame, limit: int = 100) -> list[dict]:
    out = []
    for r in leads.head(limit).itertuples(index=False):
        out.append({"tender_id": r.tender_id, "title": r.title, "entity": r.entity, "sector": r.sector,
                    "winner": r.winner, "winner_id": r.winner_id, "contract_value": float(r.contract_value),
                    "published": r.published.date().isoformat(), "risk": float(r.risk),
                    "lead_score": float(r.lead_score), "signals": r.signals, "details": r.details})
    return out
