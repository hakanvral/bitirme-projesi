"""Load versioned prompt files (``agents/prompts/<name>.md``; first line ``prompt_version: …``)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=32)
def _raw(name: str) -> tuple[str, str]:
    text = (DIR / f"{name}.md").read_text(encoding="utf-8")
    first, _, body = text.partition("\n")
    if not first.startswith("prompt_version:"):
        raise ValueError(f"{name}.md must start with 'prompt_version: …'")
    return first.split(":", 1)[1].strip(), body


def system_prompt(name: str, schema: type[BaseModel]) -> tuple[str, str]:
    """(prompt_version, system text with the shared rules and the JSON schema filled in)."""
    version, body = _raw(name)
    common = (DIR / "_common.md").read_text(encoding="utf-8")
    sch = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    return version, body.replace("{common}", common).replace("{schema}", sch)
