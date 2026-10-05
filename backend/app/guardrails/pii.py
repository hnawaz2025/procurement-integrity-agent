"""PII pseudonymisation before any text reaches an LLM.

Identifiers are replaced with *consistent* tokens ([PHONE_1], [EMAIL_2]...), so analysis that
depends on equality (two bidders sharing a phone) still works on redacted text, while the raw
values never leave the trust boundary. Company names are business identifiers and are kept.
Known limitation: untitled personal names are not detected (would need an NER model, e.g.
Azure AI Language PII detection, in production).
"""
from __future__ import annotations

import re

PATTERNS = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("ACCOUNT", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b|\bVL\d{10}\b")),
    ("PHONE", re.compile(r"\+\d{1,3}(?:[ \-]?\d{2,4}){2,5}")),
    ("ID", re.compile(r"\b(?:passport|national id|id no\.?|nid)[:\s#]*[A-Z0-9-]{6,}\b", re.IGNORECASE)),
    ("PERSON", re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Eng|Sr|Sra|M\.|Mme)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?")),
]


def redact(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for kind, rx in PATTERNS:
        mapping: dict[str, str] = {}

        def sub(m: re.Match, kind=kind, mapping=mapping) -> str:
            v = m.group(0)
            if v not in mapping:
                mapping[v] = f"[{kind}_{len(mapping) + 1}]"
            return mapping[v]

        text = rx.sub(sub, text)
        if mapping:
            counts[kind] = len(mapping)
    return text, counts
