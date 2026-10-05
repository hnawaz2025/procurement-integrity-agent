PY ?= python3.12
VENV = .venv
BIN = $(VENV)/bin

.PHONY: setup data dev api ui build test lint eval eval-mock bench docker clean-audit

setup:            ## create venv, install backend + frontend deps, generate demo corpus
	$(PY) -m venv $(VENV) && $(BIN)/pip install -q -r requirements-dev.txt
	cd frontend && npm install
	$(BIN)/python data/generate.py

data:             ## regenerate demo + scale corpora
	$(BIN)/python data/generate.py
	$(BIN)/python data/generate.py --tenders 10000

api:              ## backend on :8000
	$(BIN)/uvicorn backend.app.main:app --reload --port 8000

ui:               ## frontend dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

dev:              ## backend + frontend together
	$(MAKE) -j2 api ui

build:            ## production frontend build (served by FastAPI at :8000)
	cd frontend && npm run build

test:
	$(BIN)/python -m pytest -q

lint:
	$(BIN)/ruff check backend evals tests data

eval:             ## Claude mode if ANTHROPIC_API_KEY is set, else mock
	$(BIN)/python evals/run_eval.py

eval-mock:
	FORCE_MOCK=1 $(BIN)/python evals/run_eval.py

bench:            ## screening at 1k / 10k / 100k tenders
	$(BIN)/python evals/bench.py

docker:
	docker build -t procurement-integrity-agent .

clean-audit:
	rm -f audit/audit_log.jsonl
