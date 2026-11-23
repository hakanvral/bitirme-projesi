"""Deterministic numeric audit (D-058, D-065): every number in a report must come from the input.

Turkish formats are normalised before matching:
* decimal comma ``2,5`` and thousands dots ``1.234,5``; English ``0.0497`` also accepted;
* percent signs before or after (``%2,5``, ``2,5%``) and percent vs fraction (``%4,97`` matches an
  input value 4.97 *or* 0.0497);
* basis points (``50 bp``, ``50 baz puan``) also match 0.50 percentage points;
* numbers glued to letters are names, not values (``XU100``, ``BIST30``, ``VaR99``), and are
  ignored.

Context-aware matching (prompt v3, D-065). A number is matched together with its unit and context:
* **units must be compatible**: a percentage matches a percent field (``*_yuzde``), a percentage
  point field or a fraction; counts (``*_sayisi``) only match bare numbers; basis points
  match bp, percentage points or plain rate fields; a bare number matches any value with the
  same magnitude;
* **numbers inside input strings** (e.g. the scenario name ``"Petrol çöküşü (Brent −%30)"``) that
  carry a sign or a unit are *shock descriptions*. They only match a report number if the report
  mentions the same context (a keyword of that string, e.g. "Brent", within the same sentence
  window), the signs do not contradict, and an unsigned report number is not described with the
  opposite direction word ("artarsa" for a −%30 shock). So an invented threshold "fiyat %30
  düşerse" cannot be justified by an unrelated "−%30" scenario.
A small whitelist of structural integers (horizons, counts, confidence levels) is always allowed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

LETTER = "A-Za-zÇĞİÖŞÜçğıöşüâîû"
NUM_RE = re.compile(
    rf"(?<![{LETTER}\d.,])([-−+](?=%))?(%\s?)?"
    rf"([-−+]?\d{{1,3}}(?:\.\d{{3}})+(?:,\d+)?|[-−+]?\d+(?:[.,]\d+)?)"
    rf"(\s?%)?(\s?(?:bp|baz puanlık|baz puan|puan))?(?![{LETTER}\d])",
    re.I,
)
WHITELIST = {float(x) for x in [*range(0, 13), 13, 21, 26, 52, 63, 95, 99, 100]}
REL_TOL, ABS_TOL = 0.02, 0.051
WINDOW = 70  # characters on each side of a report number used as its context
STOPWORDS = {"şoku", "şok", "senaryo", "senaryosu", "son", "için", "veya", "ile"}
UP_WORDS = ("art", "yüksel", "sıçra", "zıpla", "tırman", "çık")
DOWN_WORDS = ("düş", "azal", "geril", "çöküş", "çök", "indir", "kayb", "kayıp", "gerile")


@dataclass
class Found:
    text: str
    value: float
    is_pct: bool
    is_bp: bool
    signed: bool = False
    is_pp: bool = False  # "puan" (percentage points / index points)
    start: int = 0
    end: int = 0


@dataclass
class Allowed:
    """One number that may be quoted, with its unit and (for text numbers) context."""

    value: float
    unit: str  # pct | pp | bp | count | num
    source: str  # value (a computed JSON value) | text (a number inside an input string)
    signed: bool = False
    keywords: set[str] = field(default_factory=set)
    text: str = ""


def _tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


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
        raw = (m.group(1) or "") + m.group(3)  # sign may stand before '%'
        try:
            v = parse_number(raw)
        except ValueError:
            continue
        unit = (m.group(5) or "").strip().lower()
        out.append(
            Found(
                m.group(0).strip(),
                v,
                bool(m.group(2) or m.group(4)),
                unit.startswith(("bp", "baz")),
                signed=raw[:1] in "-−+",
                is_pp=unit == "puan",
                start=m.start(),
                end=m.end(),
            )
        )
    return out


def _key_unit(key: str) -> str:
    k = key.lower()
    if "yuzde_puan" in k or k.endswith("_pp"):
        return "pp"
    if k.endswith("_bp"):
        return "bp"
    if k.endswith("_yuzde") or "_yuzde_" in k:
        return "pct"
    if "sayisi" in k or k.endswith(("_gun", "_hafta", "_adet")):
        return "count"
    return "num"


def _keywords(text: str) -> set[str]:
    words = re.findall(rf"[{LETTER}0-9/]+", _tr_lower(text))
    out = set()
    for w in words:
        for part in w.split("/"):
            if len(part) >= 3 and not part.isdigit() and part not in STOPWORDS:
                out.add(part)
    return out


def allowed_numbers(obj, out: list[Allowed] | None = None, key: str = "") -> list[Allowed]:
    """All numbers in a JSON-like input: values (unit from the key name), numbers inside strings
    (with their context keywords) and digits in key names."""
    out = [] if out is None else out
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, int | float):
        out.append(Allowed(float(obj), _key_unit(key), "value"))
    elif isinstance(obj, str):
        kws = _keywords(obj)
        for f in find_numbers(obj):
            unit = "pct" if f.is_pct else "bp" if f.is_bp else "pp" if f.is_pp else "num"
            out.append(Allowed(f.value, unit, "text", f.signed, kws, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(Allowed(float(d), "num", "value") for d in re.findall(r"\d+", str(k)))
            allowed_numbers(v, out, str(k))
    elif isinstance(obj, list | tuple):
        for v in obj:
            allowed_numbers(v, out, key)
    return out


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(ABS_TOL, REL_TOL * abs(b))


def _candidates(f: Found, a: Allowed) -> list[float]:
    """Values of the allowed number, expressed in the unit of the report number (empty list =
    incompatible units)."""
    x = abs(a.value)
    if a.unit == "count":  # counts (days, weeks) only match bare numbers
        return [] if (f.is_bp or f.is_pct or f.is_pp) else [x]
    if f.is_bp:  # 50 bp ↔ 50 bp, 0.50 pp / %0,50, a rate field of 0.50
        return {"bp": [x], "pp": [x * 100], "pct": [x * 100], "num": [x * 100, x]}[a.unit]
    if f.is_pct:
        return {"pct": [x], "pp": [x], "num": [x, x * 100], "bp": [x / 100]}[a.unit]
    if f.is_pp:
        return {"pp": [x], "pct": [x], "num": [x], "bp": [x / 100]}[a.unit]
    return {"pct": [x], "pp": [x], "bp": [x], "num": [x, x * 100, x / 100]}[a.unit]


def _context_ok(f: Found, a: Allowed, text: str) -> bool:
    """Shock-like numbers from input strings need the same context in the report (D-065)."""
    if a.source != "text" or not (a.signed or a.unit != "num"):
        return True
    low = _tr_lower(text)
    if _tr_lower(a.text) in low:
        return True
    win = low[max(0, f.start - WINDOW) : f.end + WINDOW]
    if not any(k in win for k in a.keywords):
        return False
    if a.signed and f.signed and (a.value < 0) != (f.value < 0):
        return False
    if a.signed and not f.signed:
        after = low[f.end : f.end + 25]  # the verb usually follows the number in Turkish
        opposite = UP_WORDS if a.value < 0 else DOWN_WORDS
        if any(w in after for w in opposite):
            return False
    return True


def matches(f: Found, allowed: list[Allowed], text: str = "") -> bool:
    v = abs(f.value)
    if v in WHITELIST and not f.is_bp:
        return True
    for a in allowed:
        if any(_close(v, c) for c in _candidates(f, a)) and _context_ok(f, a, text):
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


def check_report(report: dict, allowed: list[Allowed]) -> tuple[int, list[tuple[str, str, float]]]:
    """(numbers checked, [(field, text, value) not found in the input])."""
    n, bad = 0, []
    for fld, text in iter_texts(report):
        for f in find_numbers(text):
            n += 1
            if not matches(f, allowed, text):
                bad.append((fld, f.text, f.value))
    return n, bad
