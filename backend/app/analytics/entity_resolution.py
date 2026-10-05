"""Light entity resolution: normalisation + blocking keys + fuzzy match within a block.

Blocking avoids O(n^2) comparisons: a query is only compared against registry entries that
share its block key (first significant token), which keeps lookups fast at 100k+ firms.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

LEGAL_FORMS = {"ltd", "sa", "llc", "co", "group", "sarl", "inc", "plc", "gmbh", "srl", "limited", "company", "sas"}
STOP = {"the", "and", "&", "de", "la", "el", "of"}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_name(name: str) -> str:
    s = strip_accents(name).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = [t for t in s.split() if t not in LEGAL_FORMS]
    return " ".join(toks)


def block_key(name: str) -> str:
    toks = [t for t in normalize_name(name).split() if t not in STOP]
    return toks[0][:5] if toks else ""


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def normalize_address(addr: str) -> str:
    s = strip_accents(addr or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    for a, b in (("road", "rd"), ("avenue", "ave"), ("street", "st"), ("boulevard", "blvd"),
                 ("lane", "ln"), ("drive", "dr"), ("square", "sq")):
        s = re.sub(rf"\b{a}\b", b, s)
    return " ".join(s.split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


class NameIndex:
    """Blocked fuzzy index over registry names."""

    def __init__(self, names: dict[str, str]):  # id -> name
        self.names = names
        self.exact: dict[str, str] = {}
        self.blocks: dict[str, list[str]] = {}
        for cid, n in names.items():
            self.exact.setdefault(normalize_name(n), cid)
            self.blocks.setdefault(block_key(n), []).append(cid)

    def lookup(self, query: str, min_score: float = 0.82) -> list[tuple[str, float]]:
        q = normalize_name(query)
        if q in self.exact:
            return [(self.exact[q], 1.0)]
        cands = self.blocks.get(block_key(query), [])
        scored = sorted(((cid, similarity(query, self.names[cid])) for cid in cands), key=lambda x: -x[1])
        return [(c, round(s, 3)) for c, s in scored if s >= min_score][:5]
