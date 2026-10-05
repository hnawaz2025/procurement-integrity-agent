"""Agent tools. All read-only over data; the only writes are to the per-review context
(signals, retrieved chunks, flags, dismissals). Inputs are Pydantic-validated; validation errors
are returned to the model as tool errors so it can self-correct.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..analytics.corpus import Corpus, load_corpus
from ..analytics.graph import EntityGraph, build_graph
from ..analytics.rules import find_line, run_rules
from ..analytics.screening import screen_cached
from ..audit.log import get_audit
from ..config import settings
from ..rag.hybrid_index import get_index
from ..schemas import (
    Category,
    Dismissal,
    GuardrailEvent,
    NetworkFinding,
    ProcurementFacts,
    RiskFlag,
    Signal,
    TraceStep,
    Usage,
)
from ..telemetry import tracer
from .extract import EXTRACTION_PROMPT, extract_rule_based


@dataclass
class ReviewContext:
    review_id: str
    doc: str                                   # redacted document
    llm: Any = None                            # Claude client or None (mock)
    emit: Callable[[dict], None] = lambda e: None
    facts: ProcurementFacts | None = None
    signals: dict[str, Signal] = field(default_factory=dict)
    retrieved: dict[str, dict] = field(default_factory=dict)
    flags: list[RiskFlag] = field(default_factory=list)
    dismissals: list[Dismissal] = field(default_factory=list)
    graph_paths: list[list[str]] = field(default_factory=list)
    network_entities: set[str] = field(default_factory=set)
    findings: list[NetworkFinding] = field(default_factory=list)
    guardrail_events: list[GuardrailEvent] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)
    tools_used: set[str] = field(default_factory=set)
    usage: Usage = field(default_factory=Usage)
    summary: str = ""
    questions: list[str] = field(default_factory=list)
    done: bool = False
    raw_model_outputs: list[dict] = field(default_factory=list)

    @property
    def corpus(self) -> Corpus:
        return load_corpus(str(settings.corpus_dir))

    @property
    def graph(self) -> EntityGraph:
        return build_graph(self.corpus)

    def add_signal(self, s: Signal) -> Signal:
        # de-duplicate on (code, entities, evidence) so repeated tool calls don't inflate the baseline
        key = (s.code, tuple(sorted(s.entities)), s.evidence_quote, tuple(s.graph_path or []))
        for existing in self.signals.values():
            if (existing.code, tuple(sorted(existing.entities)), existing.evidence_quote,
                    tuple(existing.graph_path or [])) == key:
                return existing
        s.signal_id = f"S{len(self.signals) + 1}"
        self.signals[s.signal_id] = s
        return s

    def step(self, agent: str, kind: str, name: str, inp: dict | None = None, out: str = "", ms: int = 0):
        t = TraceStep(step=len(self.trace) + 1, agent=agent, kind=kind, name=name, input=inp or {},
                      output_summary=out[:600], duration_ms=ms)
        self.trace.append(t)
        self.emit({"type": "step", "step": t.model_dump()})


# ---------------- input models ----------------
class NoArgs(BaseModel):
    pass


class SearchIn(BaseModel):
    query: str = Field(..., min_length=3, description="Natural-language query, any language")
    k: int = Field(4, ge=1, le=8)


class LookupIn(BaseModel):
    name: str = Field(..., min_length=2, description="Company or procuring-entity name as written")


class HistoryIn(BaseModel):
    company: str | None = Field(None, description="Company name or id")
    entity: str | None = Field(None, description="Procuring entity name or id")


class ConnectionsIn(BaseModel):
    entities: list[str] = Field(..., min_length=2, max_length=8, description="Company names or ids")
    max_hops: int = Field(4, ge=1, le=6)


class PatternsIn(BaseModel):
    companies: list[str] = Field(default_factory=list, description="Company names or ids")
    entity: str | None = Field(None, description="Procuring entity name or id")


class DelegateIn(BaseModel):
    entities: list[str] = Field(..., min_length=1, max_length=8)
    question: str = Field(..., min_length=5)


class DismissIn(BaseModel):
    signal_id: str
    reason: str = Field(..., min_length=15, description="Specific, evidence-based reason")


class FinishIn(BaseModel):
    summary: str = Field(..., min_length=40, description="Cited summary using [KB-xx] markers")
    review_questions: list[str] = Field(..., min_length=1, max_length=8)


class ReportIn(BaseModel):
    findings: list[NetworkFinding]


# ---------------- helpers ----------------
def _resolve_company(c: Corpus, name: str) -> tuple[str, float] | None:
    if name in c.company_name:
        return name, 1.0
    hits = c.name_index.lookup(name)
    return hits[0] if hits else None


def _resolve_entity(c: Corpus, name: str) -> str | None:
    if name in c.entity_name:
        return name
    hits = c.entity_index.lookup(name, min_score=0.75)
    return hits[0][0] if hits else None


def _doc_line(ctx: ReviewContext, names: list[str]) -> str | None:
    """Anchor a corpus-level signal to the document line that names one of its parties."""
    for n in names:
        ln = find_line(ctx.doc, n)
        if ln:
            return ln
    return None


# ---------------- tool implementations ----------------
def t_extract(ctx: ReviewContext, _: NoArgs) -> dict:
    if ctx.facts is None:
        if ctx.llm is not None:
            try:
                ctx.facts = ctx.llm.extract(EXTRACTION_PROMPT.format(doc=ctx.doc), ctx.usage)
            except Exception as e:  # degrade gracefully to the deterministic parser
                ctx.guardrail_events.append(GuardrailEvent(kind="extraction_fallback", detail=str(e)[:200]))
                ctx.facts = extract_rule_based(ctx.doc)
        else:
            ctx.facts = extract_rule_based(ctx.doc)
    return ctx.facts.model_dump()


def t_rules(ctx: ReviewContext, _: NoArgs) -> dict:
    if ctx.facts is None:
        t_extract(ctx, NoArgs())
    sigs = [ctx.add_signal(s) for s in run_rules(ctx.facts, ctx.doc)]
    return {"signals": [s.model_dump(exclude={"stats"}) for s in sigs],
            "note": "Each signal must be addressed: record_flag (with signal_refs) or dismiss_signal."}


def t_search(ctx: ReviewContext, a: SearchIn) -> dict:
    hits = get_index().search(a.query, a.k)
    for h in hits:
        prev = ctx.retrieved.get(h["id"])
        if not prev or (h["cosine"] or 0) > (prev.get("cosine") or 0):
            ctx.retrieved[h["id"]] = {**h, "query": a.query}
    return {"results": [{"id": h["id"], "title": h["title"], "text": h["text"], "score": h["rrf"]} for h in hits]}


def t_lookup(ctx: ReviewContext, a: LookupIn) -> dict:
    c = ctx.corpus
    out = []
    for cid, score in c.name_index.lookup(a.name):
        row = c.companies[c.companies.company_id == cid].iloc[0]
        dirs = c.directors[c.directors.company_id == cid].person_id.map(c.person_name).tolist()
        nb = c.bids_x[c.bids_x.company_id == cid]
        ctx.network_entities.add(cid)
        out.append({"type": "company", "id": cid, "name": row["name"], "match": score, "sector": row.sector,
                    "registered": row.registered.date().isoformat(), "is_shell_flag": bool(row.is_shell),
                    "directors": dirs, "tenders_bid": int(nb.tender_id.nunique()), "wins": int(nb.is_winner.sum())})
    eid = _resolve_entity(c, a.name)
    if eid:
        n = int((c.tenders.entity_id == eid).sum())
        out.append({"type": "procuring_entity", "id": eid, "name": c.entity_name[eid], "tenders": n})
    return {"matches": out} if out else {"matches": [], "note": "No registry match. A firm with no registry "
                                                                 "record can itself be a warning sign [KB-12]."}


def t_history(ctx: ReviewContext, a: HistoryIn) -> dict:
    c = ctx.corpus
    res: dict[str, Any] = {}
    if a.company:
        r = _resolve_company(c, a.company)
        if not r:
            return {"error": f"company '{a.company}' not found in registry"}
        cid = r[0]
        ctx.network_entities.add(cid)
        b = c.bids_x[c.bids_x.company_id == cid]
        tids = b.tender_id.unique()
        co = c.bids_x[c.bids_x.tender_id.isin(tids) & (c.bids_x.company_id != cid)]
        top_co = co.company_id.value_counts().head(5)
        t = c.tenders[c.tenders.tender_id.isin(tids)].sort_values("published", ascending=False)
        res["company"] = {
            "id": cid, "name": c.company_name[cid], "tenders_bid": len(tids), "wins": int(b.is_winner.sum()),
            "frequent_co_bidders": [{"id": k, "name": c.company_name[k], "times": int(v)} for k, v in top_co.items()],
            "recent": [{"tender_id": r.tender_id, "date": r.published.date().isoformat(), "entity": c.entity_name.get(r.entity_id),
                        "winner": c.company_name.get(r.winner_id), "value": r.contract_value} for r in t.head(8).itertuples()],
            "prior_reviews": get_audit().prior_cases(c.company_name[cid]),
        }
    if a.entity:
        eid = _resolve_entity(c, a.entity)
        if not eid:
            return {**res, "entity_error": f"entity '{a.entity}' not found"}
        t = c.tenders[c.tenders.entity_id == eid]
        top = t.winner_id.value_counts().head(5)
        res["entity"] = {"id": eid, "name": c.entity_name[eid], "tenders": len(t),
                         "median_window_days": float(t.window_days.median()) if len(t) else None,
                         "top_winners": [{"name": c.company_name[k], "wins": int(v)} for k, v in top.items()]}
    return res or {"error": "provide company and/or entity"}


def t_connections(ctx: ReviewContext, a: ConnectionsIn) -> dict:
    c, g = ctx.corpus, ctx.graph
    ids, unresolved = [], []
    for n in a.entities:
        r = _resolve_company(c, n)
        (ids.append(r[0]) if r else unresolved.append(n))
    ctx.network_entities.update(ids)
    links = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            p = g.path(ids[i], ids[j], a.max_hops)
            if p:
                desc = g.describe_path(p)
                ctx.graph_paths.append(desc)
                links.append({"between": [c.company_name[ids[i]], c.company_name[ids[j]]], "path": desc,
                              "hops": len(p) - 1})
                via_shell = any(s.startswith("shell company") for s in desc)
                ctx.add_signal(Signal(
                    signal_id="", code="P-LINK", category=Category.hidden_ownership_link, severity="high",
                    title="Competing bidders linked through shared identity attributes",
                    detail=f"{c.company_name[ids[i]]} and {c.company_name[ids[j]]} are connected in the registry "
                           f"graph ({len(p) - 1} hops{', via a shell company' if via_shell else ''}).",
                    graph_path=desc, entities=[c.company_name[ids[i]], c.company_name[ids[j]]],
                    stats={"hops": len(p) - 1, "via_shell": via_shell}))
    return {"links": links, "unresolved": unresolved,
            "note": "No links found between resolved firms." if not links else
            "Shared attributes can have innocent explanations; corroborate with bidding history [KB-23]."}


def t_patterns(ctx: ReviewContext, a: PatternsIn) -> dict:
    c = ctx.corpus
    _, pr, _ = screen_cached(str(settings.corpus_dir))
    ids = [r[0] for n in a.companies if (r := _resolve_company(c, n))]
    ctx.network_entities.update(ids)
    eid = _resolve_entity(c, a.entity) if a.entity else None
    found = []
    for grp in pr.rotation_groups:
        if set(ids) & set(grp["members"]):
            names = [c.company_name[m] for m in grp["members"]]
            strong = grp["rotating"] and grp["stable_cover"]
            found.append({"pattern": "bid_rotation", "members": names, **{k: grp[k] for k in (
                "n_ring_tenders", "distinct_winners", "max_win_share", "ring_capture", "cover_ratio_mean",
                "cover_ratio_std", "rotating", "stable_cover")}})
            ctx.add_signal(Signal(
                signal_id="", code="P-ROT", category=Category.bid_rotation, severity="high" if strong else "low",
                title="Bid-rotation pattern in procurement history" if strong else
                "Recurring co-bidding group (thin-market pattern)",
                detail=f"{len(names)} firms co-bid on {grp['n_ring_tenders']} tenders; {grp['distinct_winners']} "
                       f"different winners (max share {grp['max_win_share']:.0%}); losing bids "
                       f"{(grp['cover_ratio_mean'] - 1):.1%} above winner on average (std {grp['cover_ratio_std']:.3f}).",
                entities=names, evidence_quote=_doc_line(ctx, names),
                stats={k: grp[k] for k in ("n_ring_tenders", "cover_ratio_std", "stable_cover")}))
    for x in pr.concentration:
        if x["supplier"] in ids or (eid and x["entity_id"] == eid and x["supplier"] in ids):
            name = c.company_name[x["supplier"]]
            found.append({"pattern": "supplier_concentration", "supplier": name, "entity": c.entity_name[x["entity_id"]],
                          **{k: x[k] for k in ("wins", "entity_awards", "share", "lift", "median_window_supplier",
                                               "median_window_entity")}})
            ctx.add_signal(Signal(
                signal_id="", code="P-CONC", category=Category.supplier_concentration, severity="medium",
                title="Supplier wins an outsized share of this entity's contracts",
                detail=f"{name} won {x['wins']} of {x['entity_awards']} {x['sector']} awards at {c.entity_name[x['entity_id']]} "
                       f"({x['lift']}x the expected share); median bidding window on those awards "
                       f"{x['median_window_supplier']:.0f} days vs {x['median_window_entity']:.0f} for the entity.",
                entities=[name, c.entity_name[x["entity_id"]]], evidence_quote=_doc_line(ctx, [name]),
                stats={"share": x["share"], "lift": x["lift"]}))
    for x in pr.splitting:
        if x["supplier"] in ids:
            name = c.company_name[x["supplier"]]
            found.append({"pattern": "split_purchases", "supplier": name, "entity": c.entity_name[x["entity_id"]],
                          **{k: x[k] for k in ("n_contracts", "total_value", "threshold", "first", "last")}})
            ctx.add_signal(Signal(
                signal_id="", code="P-SPLIT", category=Category.split_purchases, severity="high",
                title="Series of awards just under the review threshold",
                detail=f"{name} received {x['n_contracts']} awards from {c.entity_name[x['entity_id']]} between "
                       f"{x['first']} and {x['last']}, each just below the {x['threshold']:,.0f} threshold "
                       f"(combined {x['total_value']:,.0f}).",
                entities=[name], evidence_quote=_doc_line(ctx, [name]),
                stats={"n": x["n_contracts"], "total": x["total_value"]}))
    nf = pr.new_firms[pr.new_firms.company_id.isin(ids)]
    for r in nf.drop_duplicates("company_id").itertuples(index=False):
        name = c.company_name[r.company_id]
        found.append({"pattern": "new_firm", "company": name, "age_days_at_bid": int(r.age_days), "tender": r.tender_id})
        ctx.add_signal(Signal(
            signal_id="", code="P-NEW", category=Category.new_or_shell_bidder, severity="medium",
            title="Recently registered firm bidding",
            detail=f"{name} bid on {r.tender_id} {r.age_days} days after registration.", entities=[name],
            evidence_quote=_doc_line(ctx, [name]),
            stats={"age_days": int(r.age_days)}))
    return {"patterns": found, "resolved_ids": ids,
            "note": "No corpus-level patterns for these parties." if not found else ""}


def has_corpus_evidence(ctx: ReviewContext, f: RiskFlag) -> bool:
    return any(ctx.signals[r].code.startswith(("P-", "G-")) for r in f.signal_refs if r in ctx.signals)


def t_dismiss(ctx: ReviewContext, a: DismissIn) -> dict:
    if a.signal_id not in ctx.signals:
        return {"error": f"unknown signal_id {a.signal_id}; known: {sorted(ctx.signals)}"}
    ctx.dismissals.append(Dismissal(signal_id=a.signal_id, reason=a.reason))
    return {"ok": True, "note": "Dismissal recorded and shown to the human reviewer."}


def t_record_flag(ctx: ReviewContext, a: RiskFlag) -> dict:
    a.id = f"F{len(ctx.flags) + 1}"
    unknown = [s for s in a.signal_refs if s not in ctx.signals]
    if unknown:
        return {"error": f"unknown signal_refs {unknown}; known: {sorted(ctx.signals)}"}
    if not a.evidence_quote and not a.graph_path and not has_corpus_evidence(ctx, a):
        return {"error": "a flag needs evidence_quote (verbatim from the document), graph_path (from "
                         "find_connections), or a signal_ref to a corpus-pattern signal (P-*)"}
    if not a.citations:
        return {"error": "cite at least one knowledge-base chunk retrieved via search_guidance"}
    ctx.flags.append(a)
    return {"ok": True, "flag_id": a.id, "note": "Recorded; the verifier will check quotes, paths and citations."}


def t_finish(ctx: ReviewContext, a: FinishIn) -> dict:
    ctx.summary, ctx.questions, ctx.done = a.summary, a.review_questions, True
    return {"ok": True}


TOOLS: dict[str, tuple[type[BaseModel], Callable, str]] = {
    "extract_procurement_facts": (NoArgs, t_extract,
        "Extract structured procurement facts (method, dates, bids, award, amendments, specification excerpts) "
        "from the submitted document. Works for any language. Call first."),
    "run_red_flag_rules": (NoArgs, t_rules,
        "Run deterministic single-document red-flag rules (bid clustering, shared bidder details, threshold "
        "proximity, short window, unjustified direct contracting, large amendments, award not to lowest). "
        "Returns signals with ids; every signal must later be flagged or explicitly dismissed."),
    "search_guidance": (SearchIn, t_search,
        "Hybrid search over the integrity knowledge base (World Bank public guidance + reviewer guidance). "
        "Only chunk ids returned here may be cited."),
    "lookup_entity": (LookupIn, t_lookup,
        "Resolve a company or procuring entity against the registry: id, registration date, directors, activity."),
    "get_bidding_history": (HistoryIn, t_history,
        "Procurement history for a company (tenders, wins, frequent co-bidders, prior reviews and reviewer "
        "decisions) and/or a procuring entity (award concentration, typical bidding windows)."),
    "find_connections": (ConnectionsIn, t_connections,
        "Find hidden links between companies in the registry graph (shared directors, addresses, phones, bank "
        "accounts, shell companies). Returns explicit paths usable as graph_path evidence."),
    "check_patterns": (PatternsIn, t_patterns,
        "Check corpus-wide screening results for these parties: bid rotation rings, supplier concentration, "
        "split purchases, newly registered firms."),
    "delegate_network_investigation": (DelegateIn, None,
        "Delegate an in-depth network question to the Network Analyst subagent (fresh context, graph and "
        "history tools only). Use when several parties or multi-hop relationships need investigating."),
    "record_flag": (RiskFlag, t_record_flag,
        "Record one risk signal for human review. Requires evidence_quote (verbatim from the document) or "
        "graph_path (from find_connections), KB citations, and signal_refs for any deterministic signals it covers. "
        "Use non-accusatory language: indicators, not conclusions."),
    "dismiss_signal": (DismissIn, t_dismiss,
        "Explicitly dismiss a deterministic signal with a specific, evidence-based reason (shown to reviewers)."),
    "finish": (FinishIn, t_finish,
        "End the review with a short cited summary ([KB-xx] markers) and 3-6 questions for the human reviewer."),
}
SUBAGENT_TOOLS = ["lookup_entity", "get_bidding_history", "find_connections", "check_patterns"]


def tool_specs(names: list[str], extra: dict | None = None) -> list[dict]:
    specs = []
    for n in names:
        model, _, desc = TOOLS[n] if n in TOOLS else extra[n]
        schema = model.model_json_schema()
        specs.append({"name": n, "description": desc, "input_schema": schema})
    return specs


def execute(ctx: ReviewContext, name: str, raw: dict, agent: str = "orchestrator",
            delegate: Callable | None = None) -> tuple[str, bool]:
    """Validate + run a tool; returns (json result, is_error). Every call is traced."""
    t0 = time.perf_counter()
    span = tracer.start_span(f"tool.{name}", attributes={"agent": agent, "review.id": ctx.review_id})
    if name not in TOOLS and name != "report_findings":
        out, err = {"error": f"unknown tool {name}"}, True
    else:
        model = ReportIn if name == "report_findings" else TOOLS[name][0]
        try:
            args = model.model_validate(raw or {})
            if name == "delegate_network_investigation":
                out = delegate(ctx, args)
            elif name == "report_findings":
                out = {"ok": True}
            else:
                out = TOOLS[name][1](ctx, args)
            err = "error" in out
        except ValidationError as e:
            out, err = {"error": "invalid arguments", "details": json.loads(e.json(include_url=False))[:5]}, True
        except Exception as e:  # tool bug -> visible error, never a silent failure
            out, err = {"error": f"tool failed: {type(e).__name__}: {e}"}, True
    ctx.tools_used.add(name)
    ms = int((time.perf_counter() - t0) * 1000)
    span.set_attribute("tool.error", err)
    span.end()
    summ = json.dumps(out, default=str)
    ctx.step(agent, "tool_call", name, raw or {}, ("ERROR " if err else "") + summ, ms)
    return summ, err
