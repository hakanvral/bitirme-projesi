"""OpenAI-compatible chat client (default provider, D-054).

Works with any endpoint that implements ``POST {base_url}/chat/completions``:
* NVIDIA NIM: ``https://integrate.api.nvidia.com/v1`` with ``Authorization: Bearer nvapi-...``
* Ollama: ``http://localhost:11434/v1`` (no key)
* other OpenAI-compatible providers.

JSON mode (``response_format = {"type": "json_object"}``) is used when ``json_mode`` is "auto"
or "on"; if an endpoint rejects it (HTTP 400/422 mentioning response_format), the client turns it
off for the rest of the session and relies on prompt-based JSON + validation. Reasoning models
may return their thinking in a separate field; only ``message.content`` is used.
"""

from __future__ import annotations

import logging
import time

import httpx

from pusula.llm.base import Completion, LLMClient, LLMError
from pusula.llm.ratelimit import RateLimiter, backoff_delay

log = logging.getLogger(__name__)
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


class OpenAICompatibleClient(LLMClient):
    provider = "openai_compatible"

    def __init__(self, model: str, base_url: str, api_key: str | None = None, *,
                 limiter: RateLimiter | None = None, timeout_s: float = 180,
                 json_mode: str = "auto", max_backoff_retries: int = 6,
                 http: httpx.Client | None = None, sleep=time.sleep,
                 extra_body: dict | None = None, **kw) -> None:  # fmt: skip
        super().__init__(model, **kw)
        self.base_url = base_url.rstrip("/")
        self.provider = "nvidia_nim" if "nvidia.com" in self.base_url else (
            "ollama" if ":11434" in self.base_url else "openai_compatible")  # fmt: skip
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._http = http or httpx.Client(timeout=timeout_s, headers=headers)
        if http is not None:
            self._http.headers.update(headers)
        self.limiter = limiter or RateLimiter(35)
        self._json_mode = json_mode in ("auto", "on")
        self.max_backoff_retries = max_backoff_retries
        self._sleep = sleep
        self.extra_body = dict(extra_body or {})  # provider-specific fields (e.g. thinking switch)

    def supports_json_mode(self) -> bool:
        return self._json_mode

    def complete(self, messages: list[dict], json_mode: bool) -> Completion:
        body = {"model": self.model, "messages": messages, "temperature": self.temperature,
                "max_tokens": self.max_tokens}  # fmt: skip
        body.update(self.extra_body)
        if json_mode and self._json_mode:
            body["response_format"] = {"type": "json_object"}
        attempt = 0
        while True:
            attempt += 1
            self.limiter.acquire()
            t0 = time.perf_counter()
            try:
                r = self._http.post(f"{self.base_url}/chat/completions", json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt > self.max_backoff_retries:
                    raise LLMError(f"request failed after {attempt} attempts: {exc}") from exc
                self._sleep(backoff_delay(attempt))
                continue
            latency = time.perf_counter() - t0
            if (
                r.status_code in (400, 422)
                and "response_format" in body
                and ("response_format" in r.text or "json" in r.text.lower())
            ):
                log.warning("%s rejected JSON mode; using prompt-based JSON", self.model)
                self._json_mode = False
                body.pop("response_format")
                continue
            if r.status_code in RETRY_STATUS:
                if attempt > self.max_backoff_retries:
                    raise LLMError(f"HTTP {r.status_code} after {attempt} attempts")
                ra = r.headers.get("retry-after")
                self._sleep(backoff_delay(attempt, retry_after=float(ra) if ra and ra.replace(
                    ".", "", 1).isdigit() else None))  # fmt: skip
                continue
            if r.status_code != 200:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            usage = data.get("usage") or {}
            return Completion(text=msg.get("content") or "",
                              input_tokens=int(usage.get("prompt_tokens") or 0),
                              output_tokens=int(usage.get("completion_tokens") or 0),
                              latency_s=latency,
                              finish_reason=choice.get("finish_reason"))  # fmt: skip
