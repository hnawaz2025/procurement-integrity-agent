"""Non-accusatory language policy: outputs are risk signals, never findings of misconduct."""
from __future__ import annotations

import re

BANNED = [
    r"\b(?:is|are|was|were) (?:guilty|corrupt|fraudulent|criminals?)\b",
    r"\bcommitted (?:fraud|corruption|collusion|a crime)\b",
    r"\b(?:proves?|proven|confirms?|confirmed) (?:that )?(?:fraud|corruption|collusion|bid[- ]rigging)\b",
    r"\b(?:definitely|certainly|clearly) (?:fraud|corrupt|collud)",
    r"\bbribed\b",
]
RX = [re.compile(p, re.IGNORECASE) for p in BANNED]


def violations(text: str) -> list[str]:
    return [m.group(0) for rx in RX for m in rx.finditer(text or "")]
