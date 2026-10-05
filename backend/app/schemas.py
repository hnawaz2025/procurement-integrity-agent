"""Pydantic schemas: the contract between tools, the agent, the verifier, the API and the UI."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Category(str, Enum):
    bid_clustering = "bid_clustering"
    shared_bidder_details = "shared_bidder_details"
    threshold_avoidance = "threshold_avoidance"
    split_purchases = "split_purchases"
    short_bidding_window = "short_bidding_window"
    unjustified_direct_contracting = "unjustified_direct_contracting"
    large_amendment = "large_amendment"
    award_not_lowest = "award_not_lowest"
    tailored_specifications = "tailored_specifications"
    bid_rotation = "bid_rotation"
    hidden_ownership_link = "hidden_ownership_link"
    supplier_concentration = "supplier_concentration"
    new_or_shell_bidder = "new_or_shell_bidder"
    document_manipulation = "document_manipulation"
    other = "other"


Practice = Literal["corrupt", "fraudulent", "collusive", "coercive", "obstructive", "unclear"]
Severity = Literal["low", "medium", "high"]


# ---------- extraction ----------
class BidRow(BaseModel):
    bidder: str
    address: str | None = None
    phone: str | None = None
    price: float | None = None


class Amendment(BaseModel):
    description: str
    pct: float | None = Field(None, description="Change as a fraction of original contract value, e.g. 0.38")


class ProcurementFacts(BaseModel):
    tender_reference: str | None = None
    title: str | None = None
    procuring_entity: str | None = None
    language: str = Field("en", description="ISO 639-1 code of the source document")
    procurement_method: Literal["open", "rfq", "direct", "unknown"] = "unknown"
    currency: str | None = None
    estimated_value: float | None = None
    review_threshold: float | None = None
    published: str | None = Field(None, description="YYYY-MM-DD")
    deadline: str | None = Field(None, description="YYYY-MM-DD")
    bids: list[BidRow] = []
    awarded_to: str | None = None
    contract_value: float | None = None
    award_rationale: str | None = None
    justification: str | None = Field(None, description="Stated justification for direct contracting, if any")
    amendments: list[Amendment] = []
    specification_excerpts: list[str] = Field(default_factory=list,
                                              description="Verbatim technical-specification sentences")


# ---------- deterministic signals ----------
class Signal(BaseModel):
    signal_id: str
    code: str  # R1..R7 (single-doc rules) or P-* (corpus patterns)
    category: Category
    severity: Severity
    title: str
    detail: str
    evidence_quote: str | None = None
    graph_path: list[str] | None = None
    entities: list[str] = []
    stats: dict[str, Any] = {}


# ---------- agent outputs ----------
class RiskFlag(BaseModel):
    id: str = ""
    category: Category
    practice_hint: Practice = "unclear"
    severity: Severity
    title: str
    rationale: str
    evidence_quote: str | None = Field(None, description="Verbatim quote from the submitted document")
    graph_path: list[str] | None = Field(None, description="Node labels of a graph path, from find_connections")
    citations: list[str] = Field(default_factory=list, description="Knowledge-base chunk ids, e.g. KB-10")
    signal_refs: list[str] = Field(default_factory=list, description="Deterministic signal ids this flag is based on")
    origin: Literal["rule", "pattern", "llm", "both"] = "llm"


class RejectedFlag(BaseModel):
    flag: RiskFlag
    reasons: list[str]


class Dismissal(BaseModel):
    signal_id: str
    reason: str


class NetworkFinding(BaseModel):
    kind: Literal["hidden_link", "rotation", "concentration", "splitting", "new_firm", "none"]
    summary: str
    entities: list[str] = []
    graph_path: list[str] | None = None
    stats: dict[str, Any] = {}


class GuardrailEvent(BaseModel):
    kind: str
    detail: str
    severity: Severity = "low"


class TraceStep(BaseModel):
    step: int
    agent: Literal["orchestrator", "network_analyst", "system"] = "orchestrator"
    kind: Literal["guardrail", "thought", "tool_call", "verifier", "score", "error", "final"]
    name: str
    input: dict[str, Any] = {}
    output_summary: str = ""
    duration_ms: int = 0


class ConfidenceBreakdown(BaseModel):
    grounding: float
    citation_validity: float
    retrieval_strength: float
    signal_agreement: float
    coverage: float
    score: float


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0


class ReviewResult(BaseModel):
    review_id: str
    created_at: str
    mode: Literal["claude", "mock"]
    planner: str
    models: dict[str, str]
    input_sha256: str
    redacted_document: str
    summary: str
    flags: list[RiskFlag]
    rejected_flags: list[RejectedFlag]
    dismissals: list[Dismissal]
    signals: list[Signal]
    overall_risk: Severity
    confidence: float
    confidence_breakdown: ConfidenceBreakdown
    human_review_questions: list[str]
    escalation: Literal["standard_review", "priority_review"]
    escalation_reasons: list[str]
    guardrail_events: list[GuardrailEvent]
    retrieved: list[dict[str, Any]]
    trace: list[TraceStep]
    usage: Usage
    network_entities: list[str] = []
    audit_hash: str = ""
    cached: bool = False


class ReviewerDecision(BaseModel):
    flag_id: str
    decision: Literal["accept", "reject", "needs_info"]
    note: str = ""
    reviewer: str = "demo-reviewer"
