"""Deterministic numeric audit (D-058): every number in a report must come from the input JSON.

Turkish formats are normalised before matching:
* decimal comma ``2,5`` and thousands dots ``1.234,5``; English ``0.0497`` also accepted;
* percent signs before or after (``%2,5``, ``2,5%``) and percent vs fraction (``%4,97`` matches an
  input value 4.97 *or* 0.0497);
* basis points (``50 bp``, ``50 baz puan``) also match 0.50 percentage points;
* numbers glued to letters are names, not values (``XU100``, ``BIST30``, ``VaR99``), and are
  ignored.
A small whitelist of structural integers (horizons, counts, confidence levels) is always allowed,
together with every number that appears in the input (values, strings and digits in key names).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LETTER = "A-Za-zÇĞİÖŞÜçğıöşüâîû"
NUM_RE = re.compile(
    rf"(?<![{LETTER}\d.,])([-−+](?=%))?(%\s?)?"
    rf"([-−+]?\d{{1,3}}(?:\.\d{{3}})+(?:,\d+)?|[-−+]?\d+(?:[.,]\d+)?)"
    rf"(\s?%)?(\s?(?:bp|baz puan|baz puanlık|puan))?(?![{LETTER}\d])",
    re.I,
)
WHITELIST = {float(x) for x in [*range(0, 13), 13, 21, 26, 52, 63, 95, 99, 100]}
REL_TOL, ABS_TOL = 0.02, 0.051


@dataclass
class Found:
    text: str
    value: float
    is_pct: bool
    is_bp: bool


def parse_number(s: str) -> float:
    s = s.replace("−", "-").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[-+]?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    return float(s)


def find_numbers(text: str) -> list[Found]:
    out = []
    for m in NUM_RE.finditer(text):
        try:
            v = parse_number((m.group(1) or "") + m.group(3))  # sign may stand before '%'
        except ValueError:
            continue
        unit = (m.group(5) or "").strip().lower()
        out.append(
            Found(
                m.group(0).strip(),
                v,
                bool(m.group(2) or m.group(4)),
                unit.startswith(("bp", "baz")),
            )
        )
    return out


def allowed_numbers(obj, out: set[float] | None = None) -> set[float]:
    """All numbers in a JSON-like input: values, numbers inside strings, digits in key names."""
    out = set() if out is None else out
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, int | float):
        out.add(float(obj))
    elif isinstance(obj, str):
        out.update(f.value for f in find_numbers(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.update(float(d) for d in re.findall(r"\d+", str(k)))
            allowed_numbers(v, out)
    elif isinstance(obj, list | tuple):
        for v in obj:
            allowed_numbers(v, out)
    return out


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(ABS_TOL, REL_TOL * abs(b))


def matches(f: Found, allowed: set[float]) -> bool:
    v = abs(f.value)
    if v in WHITELIST:
        return True
    cands = [v]
    if f.is_bp:
        cands.append(v / 100)  # 50 bp = 0.50 percentage points
    for x in allowed:
        ax = abs(x)
        for c in cands:
            if _close(c, ax) or _close(c, ax * 100) or _close(c, ax / 100):
                return True
    return False


def iter_texts(obj, path: str = ""):
    """Yield (field path, text) for every string in a report."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_texts(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_texts(v, f"{path}[{i}]")


def check_report(report: dict, allowed: set[float]) -> tuple[int, list[tuple[str, str, float]]]:
    """(numbers checked, [(field, text, value) not found in the input])."""
    n, bad = 0, []
    for field, text in iter_texts(report):
        for f in find_numbers(text):
            n += 1
            if not matches(f, allowed):
                bad.append((field, f.text, f.value))
    return n, bad
