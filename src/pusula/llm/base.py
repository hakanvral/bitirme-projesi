"""Provider-independent LLM interface.

Every provider implements one method, :meth:`LLMClient.complete` (one chat request -> text).
:meth:`LLMClient.generate` adds the parts that must behave identically for every provider:

1. disk cache keyed by (provider, model, prompt_version, input hash) -> reruns are free and
   batch runs can be resumed (cached items are skipped);
2. structured output: JSON mode when available, otherwise "answer with JSON"; the reply is
   extracted, validated with pydantic and, on failure, retried up to ``max_json_retries`` times
   with the validation error fed back (D-056);
3. a usage record (tokens, latency, attempts, JSON failures; cost = 0 on the free tier) that the
   caller logs to the ``llm_usage`` table.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from pusula.llm.cache import ResponseCache, cache_key
from pusula.llm.structured import JsonExtractionError, extract_json, feedback_message

T = TypeVar("T", bound=BaseModel)


@dataclass
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0


@dataclass
class CallRecord:
    """One logical generate() call (possibly several HTTP requests)."""

    call_id: str
    provider: str
    model: str
    agent: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    attempts: int = 0  # requests sent (1 + JSON retries)
    json_failures: int = 0  # replies that failed extraction / validation
    cached: bool = False
    cost_usd: float = 0.0  # 0 on the free tier; kept for comparison with paid providers
    error: str | None = None
    run_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class LLMError(RuntimeError):
    pass


class LLMClient(ABC):
    provider: str = "base"

    def __init__(self, model: str, cache: ResponseCache | None = None,
                 max_json_retries: int = 2, temperature: float = 0.2,
                 max_tokens: int = 4096) -> None:  # fmt: skip
        self.model = model
        self.cache = cache
        self.max_json_retries = max_json_retries
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def complete(self, messages: list[dict], json_mode: bool) -> Completion:
        """Send one chat request and return the assistant text."""

    def supports_json_mode(self) -> bool:
        return False

    # ------------------------------------------------------------------ structured
    def generate(self, system: str, user: str, schema: type[T], *, agent: str,
                 prompt_version: str, run_id: str | None = None,
                 use_cache: bool = True) -> tuple[T, CallRecord]:  # fmt: skip
        rec = CallRecord(str(uuid.uuid4()), self.provider, self.model, agent, prompt_version,
                         run_id=run_id)  # fmt: skip
        key = cache_key(self.provider, self.model, prompt_version, system, user, schema.__name__)
        if use_cache and self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                rec.cached = True
                rec.input_tokens, rec.output_tokens = hit["input_tokens"], hit["output_tokens"]
                return schema.model_validate(hit["data"]), rec

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        json_mode = self.supports_json_mode()
        last_err = ""
        t0 = time.perf_counter()
        for _ in range(1 + self.max_json_retries):
            comp = self.complete(messages, json_mode)
            rec.attempts += 1
            rec.input_tokens += comp.input_tokens
            rec.output_tokens += comp.output_tokens
            try:
                obj = schema.model_validate(extract_json(comp.text))
            except (JsonExtractionError, ValidationError) as exc:
                rec.json_failures += 1
                last_err = str(exc)[:1500]
                messages = [*messages, {"role": "assistant", "content": comp.text[:6000]},
                            {"role": "user", "content": feedback_message(last_err)}]  # fmt: skip
                continue
            rec.latency_s = time.perf_counter() - t0
            if self.cache is not None:
                self.cache.put(key, {"data": obj.model_dump(mode="json"),
                                     "input_tokens": rec.input_tokens,
                                     "output_tokens": rec.output_tokens})  # fmt: skip
            return obj, rec
        rec.latency_s = time.perf_counter() - t0
        rec.error = f"invalid JSON after {rec.attempts} attempts: {last_err[:300]}"
        raise LLMError(rec.error) from None
