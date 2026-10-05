"""Corpus-level pattern detectors. All vectorised (pandas group-bys / self-joins bounded by tender size).

Each detector returns a DataFrame keyed by tender_id (so screening can score tenders) plus
explainable per-group details. Thresholds are illustrative and documented in the model card.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd

from ..config import settings
from .corpus import Corpus
from .graph import EntityGraph

T = settings.thresholds


@dataclass
class PatternResults:
    rotation_groups: list[dict]
    hidden_links: pd.DataFrame        # tender_id, company_id_x, company_id_y
    concentration: list[dict]
    splitting: list[dict]
    new_firms: pd.DataFrame           # tender_id, company_id, age_days
    tender_signals: pd.DataFrame      # tender_id, signal, weight, detail


# ---------- co-bidding & rotation ----------
def cobid_pairs(c: Corpus) -> pd.DataFrame:
    b = c.bids_x[["tender_id", "company_id"]]
    p = b.merge(b, on="tender_id")
    p = p[p.company_id_x < p.company_id_y]
    cnt = p.groupby(["company_id_x", "company_id_y"]).size().rename("n").reset_index()
    nb = b.groupby("company_id").size()
    cnt["n_min"] = np.minimum(cnt.company_id_x.map(nb), cnt.company_id_y.map(nb))
    cnt["ratio"] = cnt.n / cnt.n_min
    return cnt


def rotation_groups(c: Corpus, min_cobids: int = 5, min_ratio: float = 0.6) -> list[dict]:
    pairs = cobid_pairs(c)
    strong = pairs[(pairs.n >= min_cobids) & (pairs.ratio >= min_ratio)]
    g = nx.Graph()
    g.add_edges_from(zip(strong.company_id_x, strong.company_id_y))
    bx = c.bids_x
    out = []
    for members in nx.connected_components(g):
        if len(members) < 3:
            continue
        m = bx[bx.company_id.isin(members)]
        per_t = m.groupby("tender_id").company_id.nunique()
        ring_t = per_t[per_t >= 3].index
        if len(ring_t) < 5:
            continue
        rt = c.tenders[c.tenders.tender_id.isin(ring_t)]
        ring_wins = rt[rt.winner_id.isin(members)]
        win_share = ring_wins.winner_id.value_counts(normalize=True)
        captured = len(ring_wins) / len(rt)
        # cover-bid ratio: losing member bids relative to the winning price, per ring tender
        mb = m[m.tender_id.isin(ring_t)].merge(rt[["tender_id", "winner_id"]], on="tender_id")
        losers = mb[mb.company_id != mb.winner_id]
        ratios = losers.price / losers.contract_value
        rotating = win_share.size >= 3 and win_share.max() <= 0.5 and captured >= 0.8
        stable_cover = len(ratios) >= 5 and 1.0 < ratios.mean() < 1.12 and ratios.std() < 0.03
        if rotating or stable_cover:
            out.append({
                "members": sorted(members), "tenders": sorted(ring_t.tolist()),
                "n_ring_tenders": len(ring_t), "distinct_winners": int(win_share.size),
                "max_win_share": round(float(win_share.max()), 2), "ring_capture": round(captured, 2),
                "cover_ratio_mean": round(float(ratios.mean()), 3), "cover_ratio_std": round(float(ratios.std()), 3),
                "rotating": bool(rotating), "stable_cover": bool(stable_cover),
            })
    return out


# ---------- concentration ----------
def concentration(c: Corpus, min_wins: int = 6, min_lift: float = 2.5, window_ratio: float = 0.6) -> list[dict]:
    t = c.tenders
    grp = t.groupby(["entity_id", "sector"])
    stats = grp.agg(n=("tender_id", "size"), med_window=("window_days", "median")).reset_index()
    suppliers = c.bids_x.groupby(["entity_id", "sector"]).company_id.nunique().rename("n_sup").reset_index()
    wins = t.groupby(["entity_id", "sector", "winner_id"]).agg(
        wins=("tender_id", "size"), win_window=("window_days", "median")).reset_index()
    w = wins.merge(stats, on=["entity_id", "sector"]).merge(suppliers, on=["entity_id", "sector"])
    w["share"] = w.wins / w.n
    w["lift"] = w.share * w.n_sup
    hit = w[(w.wins >= min_wins) & (w.lift >= min_lift) & (w.win_window <= window_ratio * w.med_window)]
    out = []
    for r in hit.itertuples(index=False):
        tids = t[(t.entity_id == r.entity_id) & (t.sector == r.sector) & (t.winner_id == r.winner_id)].tender_id
        out.append({"entity_id": r.entity_id, "sector": r.sector, "supplier": r.winner_id, "wins": int(r.wins),
                    "entity_awards": int(r.n), "share": round(r.share, 2), "lift": round(r.lift, 1),
                    "median_window_supplier": float(r.win_window), "median_window_entity": float(r.med_window),
                    "tenders": tids.tolist()})
    return out


# ---------- splitting ----------
def splitting(c: Corpus, min_series: int = 3) -> list[dict]:
    t = c.tenders
    near = t[(t.contract_value < t.review_threshold) &
             (t.contract_value >= (1 - T.under_threshold_band) * t.review_threshold)]
    near = near.sort_values(["entity_id", "winner_id", "published"])
    g = near.groupby(["entity_id", "winner_id"])
    near = near.assign(ahead=g.published.shift(-(min_series - 1)))
    starts = near[(near.ahead - near.published).dt.days <= T.split_window_days]
    out = []
    for (eid, sup), _ in starts.groupby(["entity_id", "winner_id"]):
        series = near[(near.entity_id == eid) & (near.winner_id == sup)]
        out.append({"entity_id": eid, "supplier": sup, "n_contracts": len(series),
                    "total_value": round(float(series.contract_value.sum()), 2),
                    "threshold": float(series.review_threshold.iloc[0]),
                    "first": series.published.min().date().isoformat(),
                    "last": series.published.max().date().isoformat(), "tenders": series.tender_id.tolist()})
    return out


# ---------- new firms ----------
def new_firms(c: Corpus) -> pd.DataFrame:
    b = c.bids_x
    age = (b.published - b.registered).dt.days
    return b.assign(age_days=age)[(age >= 0) & (age < T.new_firm_days)][["tender_id", "company_id", "age_days"]]


# ---------- single-tender rules, vectorised over the corpus ----------
def tender_rules(c: Corpus) -> pd.DataFrame:
    t = c.tenders
    b = c.bids_x
    rows = []
    spread = b.groupby("tender_id").price.agg(["min", "max", "size"])
    clustered = spread[(spread["size"] >= 3) & ((spread["max"] - spread["min"]) / spread["min"] < T.bid_spread_pct)]
    rows += [(tid, "bid_clustering", 1.5, "bid spread < 2%") for tid in clustered.index]
    short = t[((t.method == "open") & (t.window_days < T.min_window_open)) |
              ((t.method == "rfq") & (t.window_days < T.min_window_rfq))]
    rows += [(tid, "short_bidding_window", 1.0, f"{w}-day window") for tid, w in zip(short.tender_id, short.window_days)]
    direct = t[(t.method == "direct") & (t.justification.str.strip() == "")]
    rows += [(tid, "unjustified_direct_contracting", 1.5, "direct award, no justification") for tid in direct.tender_id]
    amend = t[t.amendment_pct > T.amendment_pct]
    rows += [(tid, "large_amendment", 1.0, f"+{p:.0%} amendment") for tid, p in zip(amend.tender_id, amend.amendment_pct)]
    under = t[(t.contract_value < t.review_threshold) &
              (t.contract_value >= (1 - T.under_threshold_band) * t.review_threshold)]
    rows += [(tid, "threshold_avoidance", 0.5, "value just under review threshold") for tid in under.tender_id]
    return pd.DataFrame(rows, columns=["tender_id", "signal", "weight", "detail"])


def run_all(c: Corpus, g: EntityGraph) -> PatternResults:
    rot = rotation_groups(c)
    links = g.linked_cobidder_pairs()
    conc = concentration(c)
    split = splitting(c)
    newf = new_firms(c)
    sig = [tender_rules(c)]
    rows = []
    for grp in rot:
        # rotation AND stable cover margins is a strong signal; either alone is common in thin markets
        w = 3.0 if grp["rotating"] and grp["stable_cover"] else 1.5
        rows += [(tid, "bid_rotation", w, f"ring of {len(grp['members'])} firms") for tid in grp["tenders"]]
    for r in links.drop_duplicates("tender_id").itertuples(index=False):
        rows.append((r.tender_id, "hidden_ownership_link", 3.0, "co-bidders share identity attributes"))
    for x in conc:
        rows += [(tid, "supplier_concentration", 2.0, f"{x['share']:.0%} of awards at entity") for tid in x["tenders"]]
    for x in split:
        rows += [(tid, "split_purchases", 2.5, f"{x['n_contracts']} awards under threshold") for tid in x["tenders"]]
    for r in newf.drop_duplicates("tender_id").itertuples(index=False):
        rows.append((r.tender_id, "new_or_shell_bidder", 1.5, f"bidder registered {r.age_days} days before"))
    sig.append(pd.DataFrame(rows, columns=["tender_id", "signal", "weight", "detail"]))
    ts = pd.concat(sig, ignore_index=True)
    # split-purchase tenders also trip the weak threshold rule; keep the stronger explanation only
    return PatternResults(rot, links, conc, split, newf, ts)
