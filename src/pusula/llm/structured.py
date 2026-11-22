"""Extract a JSON object from model text (tolerant of code fences, prose and reasoning tags)."""

from __future__ import annotations

import json
import re


class JsonExtractionError(ValueError):
    pass


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def extract_json(text: str) -> dict:
    """Return the first top-level JSON object in ``text``."""
    if not text or not text.strip():
        raise JsonExtractionError("empty reply")
    t = _THINK.sub("", text)
    for cand in [m.group(1) for m in _FENCE.finditer(t)] + [t]:
        start = cand.find("{")
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(cand)):
                ch = cand[i]
                if in_str:
                    esc = (ch == "\\") and not esc
                    if ch == '"' and not esc:
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(cand[start : i + 1])
                        except json.JSONDecodeError:
                            break
                        if isinstance(obj, dict):
                            return obj
                        break
            start = cand.find("{", start + 1)
    raise JsonExtractionError("no valid JSON object found in the reply")


def feedback_message(error: str) -> str:
    return (
        "Your previous answer could not be used because it was not valid JSON for the required "
        f"schema. Error:\n{error}\n\nReturn ONLY the corrected JSON object, with no other text."
    )
