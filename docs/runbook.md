# Operational runbook

## Run locally
```bash
make setup          # venv (Python 3.11+), pip + npm install, generate demo corpus
make build && make api   # UI + API on http://localhost:8000
# or for development: make dev  (API :8000, Vite UI :5173 with hot reload)
```
- **Offline mode:** used whenever `ANTHROPIC_API_KEY` is unset, or when `FORCE_MOCK=1`.
- **Claude mode:** set the key in `.env`. The health badge then shows "Claude agent".
- **Deep links for demos:** `/?tab=review&sample=08_looks_clean_carretera_es&rtab=network`.

## Configuration (`.env`)
| Variable | Default | Purpose |
|---|---|---|
| `ORCHESTRATOR_MODEL` / `SUBAGENT_MODEL` / `WORKER_MODEL` | opus-5-5 / sonnet-5-5 / haiku-4-5 | Model tiering |
| `ORCHESTRATOR_EFFORT` | medium | Depth versus cost |
| `MAX_AGENT_STEPS`, `MAX_SUBAGENT_STEPS` | 15, 8 | Loop budgets |
| `MAX_REVIEW_COST_USD` | 1.50 | Per-review cost ceiling. The loop stops and the baseline completes the review |
| `CORPUS_DIR` | data/demo | Corpus to screen and query |
| `USE_EMBEDDINGS` | 1 | 0 means BM25-only (used in CI and air-gapped runs) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | (none) | Enables Azure Monitor export (`pip install -r requirements-azure.txt`) |

## Health and monitoring
- **`GET /api/health`** reports:
  - the mode and retrieval mode
  - corpus size
  - telemetry exporter
  - **audit-chain validity**
- **`GET /api/audit/verify`** re-hashes the full chain. Alert if `valid=false`.
- **Telemetry:** OpenTelemetry spans `review` and `tool.<name>`, with attributes for review id, mode, flag count, cost, escalation and tool errors.
- **Suggested Application Insights alerts:**
  - p95 review latency above 120 s
  - average cost per review above twice the baseline
  - verifier rejection rate above 20%
  - planner_error events
  - audit chain invalid

## Common incidents
| Symptom | Likely cause | Action |
|---|---|---|
| Reviews show `planner_failed`, scripted planner used | LLM outage, rate limit after SDK retries, or bad key | Check the provider status and key. Reviews remain valid (deterministic baseline). Re-run with "bypass cache" when the LLM is back |
| `extraction_fallback` guardrail events | Structured-output failure on the worker model | Inspect raw outputs in `/api/audit/{id}`. The rule-based parser was used |
| Many `baseline_guarantee` events | Agent not addressing deterministic signals (prompt regression) | Compare prompt versions in the audit log. Run `make eval` and inspect the agent-rule agreement score |
| Retrieval shows "BM25 only" | Embedding model not downloaded (offline) | Pre-download it (the Dockerfile does this) or accept lexical-only |
| Audit chain invalid | The log file was edited or truncated | Treat as a security incident. Restore from immutable storage and investigate |
| Batch items stuck at `running` | Worker pool saturated (3 workers) | Wait, or scale workers. In production, queue depth drives Container Apps scaling |

## Changing prompts, thresholds or models
1. Edit `agent/prompts.py` and bump `PROMPT_VERSION`, or edit `config.Thresholds`, or the model environment variables.
2. Run `make test` and `make eval-mock`. With a key, also run `make eval` to get real numbers, trajectories and cost.
3. Compare `evals/results/latest_*.md` with the previous run. Any drop in clean-document precision, injection resistance or citation validity blocks the release (the CI gate).
4. Record the change in the PR description. The audit log records the prompt version on every review.

## Data handling
- The audit log contains redacted documents and model outputs. Store it according to the case-file classification.
- Never load confidential data into the demo corpus. `data/generate.py` is the only data source in this repository.
