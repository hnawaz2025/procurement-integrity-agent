"""Stage 3 of the funnel: one review = guardrails -> agent investigation -> verifier -> scoring -> audit."""
from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from ..audit.log import get_audit
from ..config import settings
from ..guardrails.injection import scan
from ..guardrails.pii import redact
from ..llm.anthropic_provider import SUBAGENT_MODEL
from ..rag.hybrid_index import get_index
from ..schemas import Category, GuardrailEvent, ReviewResult, Signal
from ..telemetry import tracer
from .planners import get_planner
from .prompts import PROMPT_VERSION
from .score import confidence, escalate
from .tools import ReviewContext
from .verify import verify


class InputRejected(ValueError):
    pass


def _client():
    if not settings.llm_enabled:
        return None
    from ..llm.anthropic_provider import Claude
    return Claude()


def run_review(document: str, emit: Callable[[dict], None] = lambda e: None, use_cache: bool = True) -> ReviewResult:
    mode = "claude" if settings.llm_enabled else "mock"
    if not document or len(document.strip()) < 50:
        raise InputRejected("document is empty or too short to review")
    if len(document) > settings.max_doc_chars:
        raise InputRejected(f"document exceeds {settings.max_doc_chars} characters; split it or raise MAX_DOC_CHARS")
    sha = hashlib.sha256(document.encode()).hexdigest()
    audit = get_audit()
    if use_cache and (hit := audit.find_review_by_input(sha, mode)):
        r = ReviewResult.model_validate({**hit, "cached": True})
        emit({"type": "step", "step": {"step": 0, "agent": "system", "kind": "guardrail", "name": "idempotency cache",
                                       "input": {}, "output_summary": f"identical document already reviewed "
                                       f"({r.review_id}); returning stored result", "duration_ms": 0}})
        return r

    with tracer.start_as_current_span("review") as span:
        review_id = f"R-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:6]}"
        span.set_attribute("review.id", review_id)
        span.set_attribute("review.mode", mode)
        t0 = time.perf_counter()
        redacted, pii = redact(document)
        ctx = ReviewContext(review_id=review_id, doc=redacted, llm=_client(), emit=emit)
        if pii:
            ctx.guardrail_events.append(GuardrailEvent(kind="pii_redaction",
                                                       detail="pseudonymised: " + ", ".join(f"{v} {k.lower()}" for k, v in pii.items())))
        ctx.step("system", "guardrail", "pii_redaction", out=f"pseudonymised identifiers: {pii or 'none'}",
                 ms=int((time.perf_counter() - t0) * 1000))
        inj = scan(redacted)
        if inj:
            ctx.guardrail_events.append(GuardrailEvent(kind="prompt_injection", severity="high",
                                                       detail=f"{len(inj)} embedded instruction(s) detected"))
            ctx.add_signal(Signal(signal_id="", code="G-INJ", category=Category.document_manipulation, severity="high",
                                  title="Document contains embedded instructions aimed at the reviewer",
                                  detail="Text in the document attempts to direct the review outcome; it was not "
                                         "followed and may indicate an attempt to manipulate the review.",
                                  evidence_quote=inj[0]))
        ctx.step("system", "guardrail", "prompt_injection_scan",
                 out=f"{len(inj)} suspicious instruction(s): {inj[:2]}" if inj else "no embedded instructions found")
        idx = get_index()
        ctx.step("system", "guardrail", "retrieval_ready", out=idx.mode)

        planner = get_planner(ctx.llm is not None)
        try:
            planner.run(ctx, inj)
        except Exception as e:  # LLM outage etc.: the deterministic baseline still produces a review
            ctx.step("system", "error", "planner_failed", out=f"{type(e).__name__}: {e}")
            ctx.guardrail_events.append(GuardrailEvent(kind="planner_error", severity="medium", detail=str(e)[:300]))
            from .planners import ScriptedPlanner
            if ctx.facts is None or not ctx.done:
                ScriptedPlanner().run(ctx, inj)

        tv = time.perf_counter()
        kept, rejected, n_base = verify(ctx)
        ctx.step("system", "verifier", "verify_flags",
                 out=f"{len(kept) - n_base} agent flag(s) verified, {len(rejected)} rejected, "
                     f"{n_base} baseline flag(s) added, {len(ctx.dismissals)} dismissal(s)",
                 ms=int((time.perf_counter() - tv) * 1000))
        conf = confidence(ctx, kept, len(rejected), n_base)
        overall, esc, reasons = escalate(kept, conf.score, bool(inj))
        ctx.step("system", "score", "confidence_and_escalation", out=f"confidence {conf.score:.2f}; {esc}; {reasons}")
        if not ctx.questions:
            from .prompts import QUESTIONS
            ctx.questions = [QUESTIONS[c] for c in dict.fromkeys(f.category.value for f in kept) if c in QUESTIONS][:5]
        if not ctx.summary:
            ctx.summary = f"{len(kept)} risk signal(s) identified for human review."
        models = {"orchestrator": settings.orchestrator_model, "subagent": SUBAGENT_MODEL,
                  "extraction": settings.worker_model} if ctx.llm else {"planner": "scripted", "extraction": "rule-based"}
        models.update({"embeddings": settings.embedding_model if idx.embedder else "none (BM25)",
                       "prompt_version": PROMPT_VERSION})
        result = ReviewResult(
            review_id=review_id, created_at=datetime.now(UTC).isoformat(), mode=mode, planner=planner.name,
            models=models, input_sha256=sha, redacted_document=redacted, summary=ctx.summary, flags=kept,
            rejected_flags=rejected, dismissals=ctx.dismissals, signals=list(ctx.signals.values()),
            overall_risk=overall, confidence=conf.score, confidence_breakdown=conf,
            human_review_questions=ctx.questions, escalation=esc, escalation_reasons=reasons,
            guardrail_events=ctx.guardrail_events,
            retrieved=sorted(ctx.retrieved.values(), key=lambda r: r["id"]), trace=ctx.trace,
            usage=ctx.usage.model_copy(update={"cost_usd": round(ctx.usage.cost_usd, 4)}),
            network_entities=sorted(ctx.network_entities))
        payload = result.model_dump(mode="json")
        payload["raw_model_outputs"] = ctx.raw_model_outputs
        result.audit_hash = audit.append("review", review_id, payload)
        span.set_attribute("review.flags", len(kept))
        span.set_attribute("review.cost_usd", result.usage.cost_usd)
        span.set_attribute("review.escalation", esc)
        emit({"type": "result", "result": result.model_dump(mode="json")})
        return result
