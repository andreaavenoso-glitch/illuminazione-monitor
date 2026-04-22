"""Importo parser.

Ported from scripts/pipeline.js:166 — handles Italian currency formatting:
    "€ 1.234.567,89"  -> 1234567.89
    "1234567.89"      -> 1234567.89
    "1.234"           -> 1234.00 (thousands separator treated correctly)
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_CURRENCY_STRIP = re.compile(r"[€£$\s]")
# A dot that is followed by exactly 3 digits (and optional end) → thousands sep.
_DOT_THOUSANDS = re.compile(r"\.(?=\d{3}(?:\D|$))")


def parse_importo(raw: str | float | int | None) -> Decimal | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return Decimal(str(raw))
        except InvalidOperation:
            return None

    s = str(raw).strip()
    if not s or s.lower() in {"n.d.", "nd", "na", "n/a"}:
        return None

    s = _CURRENCY_STRIP.sub("", s)
    # Italian format: dots = thousands, comma = decimal.
    if "," in s:
        s = _DOT_THOUSANDS.sub("", s)
        s = s.replace(",", ".")
    else:
        # No comma: if multiple dots or a dot followed by 3 digits, treat as thousands sep.
        if s.count(".") > 1 or _DOT_THOUSANDS.search(s):
            s = _DOT_THOUSANDS.sub("", s)

    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    if value < 0:
        return None
    return value
