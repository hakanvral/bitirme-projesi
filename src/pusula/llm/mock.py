"""Deterministic mock provider for tests (never touches the network).

``responses`` maps an agent name (found in the system prompt's first line ``AGENT: <name>``) to a
JSON string or a callable(messages) -> str. A list of strings is consumed in order, which lets
tests simulate an invalid first reply followed by a valid one.
"""

from __future__ import annotations

import re

from pusula.llm.base import Completion, LLMClient


class MockLLMClient(LLMClient):
    provider = "mock"

    def __init__(self, responses: dict, model: str = "mock-1", **kw) -> None:
        super().__init__(model, **kw)
        self.responses = {k: (list(v) if isinstance(v, list) else v) for k, v in responses.items()}
        self.calls: list[list[dict]] = []

    def supports_json_mode(self) -> bool:
        return True

    def complete(self, messages: list[dict], json_mode: bool) -> Completion:
        self.calls.append(messages)
        m = re.search(r"AGENT:\s*([\w-]+)", messages[0]["content"])
        agent = m.group(1) if m else ""
        r = self.responses.get(agent, "{}")
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        text = r(messages) if callable(r) else r
        return Completion(text=text, input_tokens=len(str(messages)) // 4,
                          output_tokens=len(text) // 4, latency_s=0.0)  # fmt: skip
