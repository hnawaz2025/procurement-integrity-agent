"""Runtime configuration (env-driven, 12-factor). Thresholds are illustrative prototype settings."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Thresholds:
    bid_spread_pct: float = 0.02          # R1: spread across >=3 bids
    under_threshold_band: float = 0.10    # R3: within 10% below review threshold
    min_window_open: int = 21             # R4
    min_window_rfq: int = 7               # R4
    amendment_pct: float = 0.15           # R6
    new_firm_days: int = 90               # P-NEW
    split_window_days: int = 30           # P-SPLIT
    lead_risk_min: float = 2.0            # screening: minimum risk weight to become a lead


@dataclass(frozen=True)
class Settings:
    corpus_dir: Path = Path(os.getenv("CORPUS_DIR", ROOT / "data" / "demo"))
    kb_dir: Path = ROOT / "knowledge_base"
    samples_dir: Path = ROOT / "samples"
    audit_path: Path = Path(os.getenv("AUDIT_PATH", ROOT / "audit" / "audit_log.jsonl"))
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    use_embeddings: bool = os.getenv("USE_EMBEDDINGS", "1") == "1"
    orchestrator_model: str = os.getenv("ORCHESTRATOR_MODEL", "claude-opus-5-5")
    worker_model: str = os.getenv("WORKER_MODEL", "claude-haiku-4-5")
    effort: str = os.getenv("ORCHESTRATOR_EFFORT", "medium")
    max_steps: int = int(os.getenv("MAX_AGENT_STEPS", "15"))
    max_subagent_steps: int = int(os.getenv("MAX_SUBAGENT_STEPS", "8"))
    max_cost_usd: float = float(os.getenv("MAX_REVIEW_COST_USD", "1.50"))
    max_doc_chars: int = int(os.getenv("MAX_DOC_CHARS", "40000"))
    force_mock: bool = os.getenv("FORCE_MOCK", "0") == "1"
    thresholds: Thresholds = field(default_factory=Thresholds)

    @property
    def llm_enabled(self) -> bool:
        return not self.force_mock and bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


settings = Settings()

# USD per 1M tokens (input, output) - from Anthropic's published price list; used for cost reporting.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
