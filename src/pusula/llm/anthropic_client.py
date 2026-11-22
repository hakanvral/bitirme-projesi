"""Optional Anthropic provider (not the default; needs ``pip install anthropic`` and
ANTHROPIC_API_KEY). Kept so a paid provider can be compared later (D-054)."""

from __future__ import annotations

import time

from pusula.llm.base import Completion, LLMClient
from pusula.llm.ratelimit import RateLimiter


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, model: str, api_key: str, limiter: RateLimiter | None = None, **kw) -> None:
        super().__init__(model, **kw)
        import anthropic  # lazy: optional dependency

        self._client = anthropic.Anthropic(api_key=api_key)
        self.limiter = limiter or RateLimiter(50)

    def complete(self, messages: list[dict], json_mode: bool) -> Completion:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        chat = [m for m in messages if m["role"] != "system"]
        self.limiter.acquire()
        t0 = time.perf_counter()
        r = self._client.messages.create(model=self.model, system=system, messages=chat,
                                         max_tokens=self.max_tokens)  # fmt: skip
        text = "".join(getattr(b, "text", "") for b in r.content)
        return Completion(text, r.usage.input_tokens, r.usage.output_tokens,
                          time.perf_counter() - t0)  # fmt: skip
