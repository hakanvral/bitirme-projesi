"""Build the configured LLM clients (settings.yaml ``llm`` section + .env overrides)."""

from __future__ import annotations

import os

from pusula.config import get_secrets, get_settings
from pusula.llm.base import LLMClient
from pusula.llm.cache import ResponseCache
from pusula.llm.ratelimit import RateLimiter

_LIMITER: RateLimiter | None = None
_CACHE: ResponseCache | None = None


def shared_limiter() -> RateLimiter:
    """One limiter per process: all clients share the account's request budget."""
    global _LIMITER
    if _LIMITER is None:
        _LIMITER = RateLimiter(get_settings().llm.rpm)
    return _LIMITER


def shared_cache() -> ResponseCache:
    global _CACHE
    if _CACHE is None:
        _CACHE = ResponseCache(get_settings().llm.cache_path)
    return _CACHE


def provider_info() -> dict:
    cfg, sec = get_settings().llm, get_secrets()
    return {
        "provider": sec.llm_provider or cfg.provider,
        "base_url": sec.llm_base_url or cfg.base_url,
        "model": sec.llm_model or cfg.model,
        "model_light": sec.llm_model_light or cfg.model_light,
        "rpm": cfg.rpm,
        "max_concurrency": cfg.max_concurrency,
    }


def _api_key() -> str | None:
    cfg, sec = get_settings().llm, get_secrets()
    for k in (sec.nvidia_api_key if cfg.api_key_env == "NVIDIA_API_KEY" else None, sec.llm_api_key):
        if k is not None and k.get_secret_value():
            return k.get_secret_value()
    return os.environ.get(cfg.api_key_env) or None


def get_client(light: bool = False, lean: bool = False) -> LLMClient:
    """``lean=True`` adds ``llm.extra_body_lean`` (e.g. reasoning off) for E4's lean calls."""
    cfg = get_settings().llm
    info = provider_info()
    model = info["model_light"] if light else info["model"]
    common = {"cache": shared_cache(), "max_json_retries": cfg.max_json_retries,
              "temperature": cfg.temperature, "max_tokens": cfg.max_tokens}  # fmt: skip
    if info["provider"] == "openai_compatible":
        from pusula.llm.openai_compat import OpenAICompatibleClient

        return OpenAICompatibleClient(
            model,
            info["base_url"],
            _api_key(),
            limiter=shared_limiter(),
            timeout_s=cfg.timeout_s,
            json_mode=cfg.json_mode,
            max_backoff_retries=cfg.max_backoff_retries,
            extra_body={**cfg.extra_body, **(cfg.extra_body_lean if lean else {})},
            **common,
        )
    if info["provider"] == "anthropic":
        from pusula.llm.anthropic_client import AnthropicClient

        sec = get_secrets()
        if not sec.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        name = sec.anthropic_model_light if light else sec.anthropic_model
        return AnthropicClient(name, sec.anthropic_api_key.get_secret_value(), **common)
    raise RuntimeError(f"Unknown LLM provider {info['provider']!r}")
