"""Claude provider (Anthropic Python SDK).

Model tiering:
  orchestrator  -> ORCHESTRATOR_MODEL (default claude-opus-5-5): planning + judgement
  subagent      -> SUBAGENT_MODEL     (default claude-sonnet-5-5): focused network investigation
  extraction    -> WORKER_MODEL       (default claude-haiku-4-5): schema extraction at volume

Production notes: Claude is also available through Microsoft Foundry (anthropic.AnthropicFoundry),
which keeps traffic and billing inside an Azure tenancy.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import anthropic
from pydantic import ValidationError

from ..config import PRICES, settings
from ..schemas import ProcurementFacts, Usage

log = logging.getLogger(__name__)

SUBAGENT_MODEL = os.getenv("SUBAGENT_MODEL", "claude-sonnet-5-5")
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-opus-5"}


def add_usage(total: Usage, model: str, u: Any) -> None:
    if u is None:
        return
    pin, pout = PRICES.get(model, (4.0, 20.0))
    inp = getattr(u, "input_tokens", 0) or 0
    out = getattr(u, "output_tokens", 0) or 0
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    cw = getattr(u, "cache_creation_input_tokens", 0) or 0
    total.input_tokens += inp
    total.output_tokens += out
    total.cache_read_tokens += cr
    total.cache_write_tokens += cw
    total.cost_usd += (inp * pin + out * pout + cr * pin * 0.1 + cw * pin * 1.25) / 1_000_000


class Claude:
    def __init__(self):
        self.client = anthropic.Anthropic(max_retries=3, timeout=180.0)

    def extract(self, prompt: str, usage: Usage) -> ProcurementFacts:
        """JSON Schema in the prompt + Pydantic validation, one corrective retry.
        (Constrained decoding via messages.parse stalled >90s on this many-optional-field schema;
        prompt + validate returns in ~4s with the same guarantees after validation.)"""
        client = self.client.with_options(timeout=45.0, max_retries=1)
        messages = [{"role": "user", "content": prompt + "\n\nReturn only a JSON object conforming to this "
                     "JSON Schema:\n" + json.dumps(ProcurementFacts.model_json_schema())}]
        for attempt in range(2):
            resp = client.messages.create(model=settings.worker_model, max_tokens=4096, messages=messages)
            add_usage(usage, settings.worker_model, resp.usage)
            if resp.stop_reason == "refusal":
                raise RuntimeError("extraction refused")
            text = "".join(b.text for b in resp.content if b.type == "text")
            m = re.search(r"\{.*\}", text, re.S)
            try:
                return ProcurementFacts.model_validate_json(m.group(0) if m else text)
            except ValidationError as e:
                if attempt:
                    raise RuntimeError(f"extraction output failed validation: {e.errors()[:3]}") from e
                messages += [{"role": "assistant", "content": text},
                             {"role": "user", "content": f"That JSON failed validation: {e.errors()[:5]}. "
                                                         "Return only the corrected JSON object."}]
        raise RuntimeError("unreachable")

    def turn(self, *, model: str, system: str, messages: list, tools: list[dict], effort: str,
             usage: Usage):
        """One agent turn. Append-only history; tool definitions + system prompt are a stable,
        cacheable prefix (top-level automatic prompt caching)."""
        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=16000,
            system=system,
            messages=messages,
            tools=tools,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": effort},
            cache_control={"type": "ephemeral"},
        )
        if model in FALLBACK_MODELS:
            # server-side refusal fallback: routes a policy decline to a suitable model in the same call
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        # SDK retries 408/409/429/5xx with backoff (max_retries=3); other errors propagate to the
        # orchestrator, which records them and falls back to the deterministic baseline.
        resp = self.client.beta.messages.create(**kwargs)
        add_usage(usage, model, resp.usage)
        return resp
