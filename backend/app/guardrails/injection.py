"""Prompt-injection screening for untrusted documents (defence in depth, not a guarantee).

Layer 1 (here): multilingual heuristic patterns -> guardrail event + escalation.
Layer 2 (prompts): documents are wrapped in <untrusted_document> tags and the system prompt
states that document text is evidence, never instructions.
Layer 3 (verifier): the agent cannot drop deterministic signals without an explicit reason,
so an injected "rate this low risk" cannot silently suppress rule findings.
Production: add Azure AI Content Safety Prompt Shields as an additional classifier.
"""
from __future__ import annotations

import re

PATTERNS = [
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier) (?:instructions|prompts?)",
    r"disregard (?:all |any )?(?:the )?(?:previous|prior|above) ",
    r"system (?:note|prompt|message|instruction)s? (?:to|for) (?:the )?(?:ai|assistant|model|reviewer)",
    r"\byou are now\b",
    r"rate (?:it|this|the tender)[^.\n]{0,30}low[ -]risk",
    r"do not (?:create|raise|add|report) (?:any )?flags?",
    r"do not mention this",
    r"</?(?:system|assistant|instructions?)>",
    r"ignora(?:r)? (?:todas )?las instrucciones",
    r"ignorez (?:toutes )?les instructions",
]
RX = [re.compile(p, re.IGNORECASE) for p in PATTERNS]


def scan(text: str) -> list[str]:
    hits = []
    for rx in RX:
        for m in rx.finditer(text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            hits.append(text[line_start: line_end if line_end != -1 else None].strip())
    return list(dict.fromkeys(hits))
