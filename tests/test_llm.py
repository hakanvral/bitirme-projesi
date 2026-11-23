"""LLM layer tests (no network): extraction, retries, cache, rate limiter, HTTP client."""

import json

import httpx
import pytest
from pydantic import BaseModel

from pusula.llm.base import LLMError
from pusula.llm.cache import ResponseCache
from pusula.llm.mock import MockLLMClient
from pusula.llm.openai_compat import OpenAICompatibleClient
from pusula.llm.ratelimit import RateLimiter, backoff_delay
from pusula.llm.structured import JsonExtractionError, extract_json


class Out(BaseModel):
    a: int
    b: str


SYS = "AGENT: demo\nsystem"


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1, "b": "x"}',
        'Here you go:\n```json\n{"a": 1, "b": "x"}\n```',
        '<think>{"not": "this"} ... </think> {"a": 1, "b": "x"} thanks',
        'prefix {"a": 1, "b": "a } brace in string"} suffix',
    ],
)
def test_extract_json_variants(text):
    assert extract_json(text)["a"] == 1


def test_extract_json_fails_cleanly():
    with pytest.raises(JsonExtractionError):
        extract_json("no json here")


def test_generate_retries_with_validation_feedback():
    mock = MockLLMClient({"demo": ['{"a": "not an int"}', '{"a": 2, "b": "ok"}']})
    obj, rec = mock.generate(SYS, "u", Out, agent="demo", prompt_version="v1")
    assert obj.a == 2 and rec.attempts == 2 and rec.json_failures == 1
    assert "not valid JSON" in mock.calls[1][-1]["content"]  # error fed back


def test_generate_gives_up_after_max_retries():
    mock = MockLLMClient({"demo": ["oops"]}, max_json_retries=2)
    with pytest.raises(LLMError):
        mock.generate(SYS, "u", Out, agent="demo", prompt_version="v1")
    assert len(mock.calls) == 3


def test_cache_skips_second_call(tmp_path):
    cache = ResponseCache(tmp_path / "c.sqlite")
    mock = MockLLMClient({"demo": '{"a": 1, "b": "x"}'}, cache=cache)
    mock.generate(SYS, "u", Out, agent="demo", prompt_version="v1")
    obj, rec = mock.generate(SYS, "u", Out, agent="demo", prompt_version="v1")
    assert rec.cached and len(mock.calls) == 1 and obj.b == "x"
    mock.generate(SYS, "u", Out, agent="demo", prompt_version="v2")  # new prompt version
    assert len(mock.calls) == 2 and len(cache) == 2


def test_rate_limiter_waits_when_window_is_full():
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    rl = RateLimiter(2, clock=lambda: now[0], sleep=sleep)
    assert rl.acquire() == 0 and rl.acquire() == 0
    waited = rl.acquire()
    assert waited == pytest.approx(60.01) and now[0] == pytest.approx(60.01)


def test_backoff_honours_retry_after_and_grows():
    assert backoff_delay(1, retry_after=7) == 7
    assert backoff_delay(3) > backoff_delay(1) / 2


def _client(handler, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleClient(
        "m",
        "https://integrate.api.nvidia.com/v1",
        "nvapi-test",
        http=http,
        sleep=lambda s: None,
        limiter=RateLimiter(1000),
        **kw,
    )


def _ok(content, pt=10, ct=5):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content, "reasoning_content": "hidden"}}],
            "usage": {"prompt_tokens": pt, "completion_tokens": ct},
        },
    )


def test_openai_client_retries_on_429_and_parses_usage():
    seen = []

    def handler(req):
        seen.append(req)
        if len(seen) == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return _ok('{"a": 1, "b": "x"}')

    c = _client(handler)
    obj, rec = c.generate(SYS, "u", Out, agent="demo", prompt_version="v1", use_cache=False)
    assert obj.a == 1 and rec.input_tokens == 10 and rec.output_tokens == 5
    assert len(seen) == 2 and seen[0].headers["authorization"] == "Bearer nvapi-test"
    body = json.loads(seen[1].content)
    assert body["response_format"] == {"type": "json_object"} and c.provider == "nvidia_nim"


def test_openai_client_falls_back_when_json_mode_unsupported():
    bodies = []

    def handler(req):
        b = json.loads(req.content)
        bodies.append(b)
        if "response_format" in b:
            return httpx.Response(400, text="response_format is not supported")
        return _ok('answer: {"a": 3, "b": "y"}')

    c = _client(handler)
    obj, _ = c.generate(SYS, "u", Out, agent="demo", prompt_version="v1", use_cache=False)
    assert obj.a == 3 and "response_format" not in bodies[-1] and not c.supports_json_mode()


def test_openai_client_ollama_without_key():
    def handler(req):
        assert "authorization" not in req.headers
        return _ok('{"a": 1, "b": "x"}')

    http = httpx.Client(transport=httpx.MockTransport(handler))
    c = OpenAICompatibleClient(
        "llama", "http://localhost:11434/v1", None, http=http, limiter=RateLimiter(1000)
    )
    assert c.provider == "ollama"
    c.generate(SYS, "u", Out, agent="demo", prompt_version="v1", use_cache=False)


def test_openai_client_raises_after_persistent_errors():
    c = _client(lambda req: httpx.Response(503), max_backoff_retries=2)
    with pytest.raises(LLMError, match="503"):
        c.complete([{"role": "user", "content": "x"}], json_mode=False)


def test_empty_reply_after_token_budget_is_a_clear_error_without_retries():
    """D-068: reasoning can use the whole max_tokens budget; that is reported, not retried."""
    from pusula.llm.base import Completion

    class Exhausted(MockLLMClient):
        def complete(self, messages, json_mode):
            self.calls.append(messages)
            return Completion(text="", output_tokens=4096, finish_reason="length")

    c = Exhausted({}, max_tokens=4096)
    with pytest.raises(LLMError, match="token budget"):
        c.generate("AGENT: x", "u", Out, agent="x", prompt_version="x.v1")
    assert len(c.calls) == 1
