"""FastAPI service: review API (SSE), portfolio screening, batch investigation, graph, audit."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from . import telemetry
from .agent.orchestrator import InputRejected, run_review
from .analytics.corpus import load_corpus
from .analytics.cost import project
from .analytics.dossier import render_tender
from .analytics.graph import build_graph
from .analytics.screening import lead_records, screen_cached
from .audit.log import get_audit
from .config import ROOT, settings
from .rag.hybrid_index import get_index
from .schemas import ReviewerDecision

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")
app = FastAPI(title="Procurement Integrity Review Agent", version="0.3.0",
              description="AI-assisted integrity screening for procurement. Outputs are risk signals for human "
                          "review, never findings of misconduct. Synthetic data only.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
TELEMETRY = telemetry.setup()
POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="review")  # concurrency limit for LLM calls
BATCHES: dict[str, dict] = {}


class ReviewIn(BaseModel):
    document: str = Field(..., description="Procurement document text (Markdown or plain text)")
    use_cache: bool = True


class BatchIn(BaseModel):
    tender_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(0, ge=0, le=25)


@app.on_event("startup")
def warm():
    threading.Thread(target=lambda: (get_index(), screen_cached(str(settings.corpus_dir))), daemon=True).start()


@app.get("/api/health")
def health():
    idx = get_index()
    c = load_corpus(str(settings.corpus_dir))
    return {"status": "ok", "mode": "claude" if settings.llm_enabled else "mock",
            "planner": "claude-agent" if settings.llm_enabled else "scripted-offline",
            "models": {"orchestrator": settings.orchestrator_model, "extraction": settings.worker_model}
            if settings.llm_enabled else {}, "retrieval": idx.mode, "kb_chunks": len(idx.chunks),
            "corpus": {"dir": settings.corpus_dir.name, "tenders": c.n_tenders, "companies": len(c.companies)},
            "telemetry": TELEMETRY, "audit": get_audit().verify_chain()}


@app.get("/api/samples")
def samples():
    labels = json.loads((settings.samples_dir / "labels.json").read_text())
    return [{"id": p.stem, **labels.get(p.stem, {})} for p in sorted(settings.samples_dir.glob("*.md"))]


@app.get("/api/samples/{sid}")
def sample(sid: str):
    p = settings.samples_dir / f"{Path(sid).name}.md"
    if not p.exists():
        raise HTTPException(404, "sample not found")
    return {"id": sid, "document": p.read_text()}


@app.post("/api/review")
async def review(body: ReviewIn, request: Request):
    """Streams agent steps as Server-Sent Events, then the final ReviewResult (event: result)."""
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def emit(e: dict):
        loop.call_soon_threadsafe(q.put_nowait, e)

    def work():
        try:
            r = run_review(body.document, emit=emit, use_cache=body.use_cache)
            if r.cached:
                emit({"type": "result", "result": r.model_dump(mode="json")})
        except InputRejected as e:
            emit({"type": "error", "error": str(e)})
        except Exception as e:  # surfaced to the UI, logged with stack
            log.exception("review failed")
            emit({"type": "error", "error": f"{type(e).__name__}: {e}"})
        finally:
            emit({"type": "done"})

    POOL.submit(work)

    async def stream():
        while True:
            e = await q.get()
            if e["type"] == "done":
                break
            yield {"event": e["type"], "data": json.dumps(e, default=str)}

    return EventSourceResponse(stream())


@app.post("/api/review/sync")
def review_sync(body: ReviewIn):
    try:
        return run_review(body.document, use_cache=body.use_cache).model_dump(mode="json")
    except InputRejected as e:
        raise HTTPException(422, str(e))


@app.post("/api/screening/run")
def screening_run(top: int = 50):
    leads, pr, funnel = screen_cached(str(settings.corpus_dir))
    bench = ROOT / "evals" / "results" / "bench.json"
    sec_per_100k, lead_rate = funnel["timings"]["total_s"] * 100_000 / max(funnel["tenders_screened"], 1), \
        funnel["leads"] / funnel["tenders_screened"]
    if bench.exists():
        b = json.loads(bench.read_text())
        big = max(b["runs"], key=lambda r: r["tenders"])
        sec_per_100k = big["screen_s"] * 100_000 / big["tenders"]
        lead_rate = big["leads"] / big["tenders"]
    c = load_corpus(str(settings.corpus_dir))
    return {
        "funnel": {**funnel, "agent_queue": min(top, funnel["leads"])},
        "leads": lead_records(leads, top),
        "groups": {
            "rotation": [{**g, "members": [c.company_name[m] for m in g["members"]], "tenders": g["tenders"][:20]}
                         for g in pr.rotation_groups],
            "concentration": [{**x, "supplier": c.company_name[x["supplier"]], "entity": c.entity_name[x["entity_id"]]}
                              for x in pr.concentration],
            "splitting": [{**x, "supplier": c.company_name[x["supplier"]], "entity": c.entity_name[x["entity_id"]]}
                          for x in pr.splitting],
            "hidden_links": int(pr.hidden_links[["company_id_x", "company_id_y"]].drop_duplicates().shape[0]),
        },
        "cost_projection": project(100_000, lead_rate, sec_per_100k),
    }


@app.get("/api/leads/{tender_id}/document")
def lead_document(tender_id: str):
    try:
        return {"tender_id": tender_id, "document": render_tender(load_corpus(str(settings.corpus_dir)), tender_id)}
    except KeyError:
        raise HTTPException(404, "tender not found")


@app.post("/api/batch")
def batch(body: BatchIn):
    ids = list(body.tender_ids)
    if body.top_k:
        leads, _, _ = screen_cached(str(settings.corpus_dir))
        ids += [t for t in leads.tender_id.head(body.top_k) if t not in ids]
    if not ids:
        raise HTTPException(422, "provide tender_ids or top_k")
    bid = f"B-{uuid.uuid4().hex[:6]}"
    job = BATCHES[bid] = {"batch_id": bid, "items": {t: {"status": "queued"} for t in ids}}
    c = load_corpus(str(settings.corpus_dir))

    def one(tid: str):
        job["items"][tid] = {"status": "running"}
        try:
            r = run_review(render_tender(c, tid))
            job["items"][tid] = {"status": "done", "review_id": r.review_id, "overall_risk": r.overall_risk,
                                 "escalation": r.escalation, "flags": len(r.flags), "confidence": r.confidence,
                                 "cost_usd": r.usage.cost_usd, "cached": r.cached,
                                 "categories": sorted({f.category.value for f in r.flags})}
        except Exception as e:
            job["items"][tid] = {"status": "error", "error": str(e)[:200]}

    for t in ids:
        POOL.submit(one, t)
    return job


@app.get("/api/batch/{bid}")
def batch_status(bid: str):
    if bid not in BATCHES:
        raise HTTPException(404, "batch not found")
    return BATCHES[bid]


@app.get("/api/graph/subgraph")
def subgraph(entities: str):
    c = load_corpus(str(settings.corpus_dir))
    ids = [e for e in entities.split(",") if e in c.company_name]
    if not ids:
        raise HTTPException(422, "no known company ids")
    return build_graph(c).subgraph(ids)


@app.post("/api/reviews/{review_id}/decision")
def decision(review_id: str, d: ReviewerDecision):
    audit = get_audit()
    if not any(e["kind"] == "review" for e in audit.for_review(review_id)):
        raise HTTPException(404, "review not found")
    h = audit.append("decision", review_id, d.model_dump())
    return {"ok": True, "audit_hash": h}


@app.get("/api/audit/verify")
def audit_verify():
    return get_audit().verify_chain()


@app.get("/api/audit/{review_id}")
def audit_entries(review_id: str):
    entries = get_audit().for_review(review_id)
    if not entries:
        raise HTTPException(404, "no audit entries")
    return [{"kind": e["kind"], "ts": e["ts"], "hash": e["hash"], "prev_hash": e["prev_hash"],
             "payload": e["payload"] if e["kind"] == "decision" else {
                 k: e["payload"].get(k) for k in ("input_sha256", "mode", "planner", "models", "usage", "escalation",
                                                  "confidence", "retrieved", "raw_model_outputs")}} for e in entries]


@app.get("/api/kb/{chunk_id}")
def kb(chunk_id: str):
    c = get_index().by_id.get(chunk_id)
    if not c:
        raise HTTPException(404, "chunk not found")
    return c.__dict__


@app.get("/api/evals")
def evals():
    out = {}
    for n in ("latest", "bench"):
        p = ROOT / "evals" / "results" / f"{n}.json"
        out[n] = json.loads(p.read_text()) if p.exists() else None
    return out


DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
