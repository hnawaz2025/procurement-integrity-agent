"""Hybrid retrieval over the knowledge base: BM25 (lexical) + multilingual embeddings (semantic),
fused with Reciprocal Rank Fusion. Falls back to BM25-only if embeddings are unavailable.

Production equivalent: Azure AI Search hybrid query (BM25 + vector, RRF) with semantic ranker.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from ..config import settings

log = logging.getLogger(__name__)


@dataclass
class Chunk:
    id: str
    title: str
    category: str
    practice: str
    source: str
    url: str
    text: str


def load_kb(kb_dir: Path) -> list[Chunk]:
    chunks = []
    for p in sorted(kb_dir.glob("KB-*.md")):
        raw = p.read_text()
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
        meta = dict(re.findall(r'^(\w+):\s*"?(.*?)"?\s*$', m.group(1), re.MULTILINE))
        chunks.append(Chunk(id=meta["id"], title=meta["title"], category=meta["category"],
                            practice=meta["practice"], source=meta["source"], url=meta.get("url", ""),
                            text=m.group(2).strip()))
    return chunks


def _tok(s: str) -> list[str]:
    return re.findall(r"[a-záéíóúñçàèêëîïôûü0-9]+", s.lower())


class HybridIndex:
    def __init__(self, chunks: list[Chunk], use_embeddings: bool = True):
        self.chunks = chunks
        self.by_id = {c.id: c for c in chunks}
        self.bm25 = BM25Okapi([_tok(f"{c.title} {c.text}") for c in chunks])
        self.embedder = None
        self.vecs = None
        if use_embeddings:
            try:
                from fastembed import TextEmbedding
                self.embedder = TextEmbedding(settings.embedding_model)
                v = np.array(list(self.embedder.embed([f"{c.title}. {c.text}" for c in chunks])))
                self.vecs = v / np.linalg.norm(v, axis=1, keepdims=True)
            except Exception as e:  # offline / model unavailable -> lexical only
                log.warning("embeddings unavailable, using BM25 only: %s", e)
                self.embedder = None

    @property
    def mode(self) -> str:
        return "hybrid (BM25 + multilingual embeddings, RRF)" if self.embedder else "BM25 only"

    def search(self, query: str, k: int = 4, rrf_k: int = 60) -> list[dict]:
        bm = self.bm25.get_scores(_tok(query))
        ranks: dict[int, float] = {}
        for r, i in enumerate(np.argsort(-bm)[:20]):
            ranks[i] = ranks.get(i, 0) + 1 / (rrf_k + r + 1)
        cos = None
        if self.embedder is not None:
            q = np.array(list(self.embedder.embed([query])))[0]
            cos = self.vecs @ (q / np.linalg.norm(q))
            for r, i in enumerate(np.argsort(-cos)[:20]):
                ranks[i] = ranks.get(i, 0) + 1 / (rrf_k + r + 1)
        top = sorted(ranks.items(), key=lambda x: -x[1])[:k]
        out = []
        for i, s in top:
            c = self.chunks[i]
            out.append({"id": c.id, "title": c.title, "source": c.source, "url": c.url, "text": c.text,
                        "rrf": round(s, 4), "bm25": round(float(bm[i]), 3),
                        "cosine": round(float(cos[i]), 3) if cos is not None else None})
        return out


@lru_cache(maxsize=1)
def get_index() -> HybridIndex:
    return HybridIndex(load_kb(settings.kb_dir), settings.use_embeddings)
