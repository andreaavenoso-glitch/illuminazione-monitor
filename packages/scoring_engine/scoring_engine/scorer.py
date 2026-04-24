"""Commercial scoring engine.

Port of scripts/pipeline.js:222-240 — computes an integer opportunity score
and maps it to a priority tier P1-P4. The input model is intentionally a
plain dataclass so the module has no SQLAlchemy or Pydantic dependencies:
the worker builds a :class:`ScoringInput` from a ``ProcurementRecord`` and
writes back the two output fields.

Scoring bands
-------------

Importo:
    > 10M    → 35
    > 5M     → 28
    > 2M     → 20
    > 1M     → 14
    > 500k   → 8
    else     → 3

Stato procedurale:
    GARA PUBBLICATA          → 25
    RETTIFICA-…              → 20
    PRE-GARA (forte)         → 20
    PRE-GARA (debole)        → 8
    ESITO-…                  → 10

Scadenza residua:
    ≤ 3 giorni → 20
    ≤ 7        → 15
    ≤ 15       → 10
    ≤ 30       → 5

Flags:
    PPP        → 8
    PNRR       → 6
    sopra soglia UE → 4

Tag tecnico “accordo/global service” → 3

Priority mapping:
    P1  score ≥ 70
        oppure importo > 5M e stato = GARA PUBBLICATA
        oppure scadenza tra 0 e 2 giorni
    P2  score ≥ 50
    P3  score ≥ 30
    P4  altrimenti
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class ScoringInput:
    importo: Decimal | float | None
    stato_procedurale: str
    scadenza: datetime | None
    flag_ppp: bool = False
    flag_pnrr: bool = False
    flag_sopra_soglia_ue: bool = False
    pre_gara_forza: str | None = None  # "forte" | "debole" | None
    tag_tecnico: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScoringOutput:
    score: int
    priority: str  # P1 | P2 | P3 | P4
    days_to_deadline: int | None


def _importo_band(importo: Decimal | float | None) -> int:
    if importo is None:
        return 3
    value = float(importo)
    if value > 10_000_000:
        return 35
    if value > 5_000_000:
        return 28
    if value > 2_000_000:
        return 20
    if value > 1_000_000:
        return 14
    if value > 500_000:
        return 8
    return 3


def _stato_points(stato: str, pre_gara_forza: str | None) -> int:
    if stato == "GARA PUBBLICATA":
        return 25
    if stato.startswith("RETTIFICA"):
        return 20
    if stato == "PRE-GARA":
        return 20 if pre_gara_forza == "forte" else 8
    if stato.startswith("ESITO"):
        return 10
    return 0


def _scadenza_points(scadenza: datetime | None, today: date) -> tuple[int, int | None]:
    if scadenza is None:
        return 0, None
    target = scadenza.date() if isinstance(scadenza, datetime) else scadenza
    days = (target - today).days
    if days <= 3:
        return 20, days
    if days <= 7:
        return 15, days
    if days <= 15:
        return 10, days
    if days <= 30:
        return 5, days
    return 0, days


def _tag_bonus(tags: tuple[str, ...]) -> int:
    lowered = tuple(t.lower() for t in tags)
    return 3 if any("accordo" in t or "global" in t for t in lowered) else 0


def score_record(payload: ScoringInput, *, now: datetime | None = None) -> ScoringOutput:
    today = (now or datetime.now(tz=UTC)).date()
    score = _importo_band(payload.importo)
    score += _stato_points(payload.stato_procedurale, payload.pre_gara_forza)
    scadenza_pts, days_to_deadline = _scadenza_points(payload.scadenza, today)
    score += scadenza_pts
    if payload.flag_ppp:
        score += 8
    if payload.flag_pnrr:
        score += 6
    if payload.flag_sopra_soglia_ue:
        score += 4
    score += _tag_bonus(payload.tag_tecnico)

    importo_float = float(payload.importo) if payload.importo is not None else None
    priority = compute_priority(
        score=score,
        importo=importo_float,
        stato=payload.stato_procedurale,
        days_to_deadline=days_to_deadline,
    )
    return ScoringOutput(score=score, priority=priority, days_to_deadline=days_to_deadline)


def compute_priority(
    *,
    score: int,
    importo: float | None,
    stato: str,
    days_to_deadline: int | None,
) -> str:
    if score >= 70:
        return "P1"
    if importo is not None and importo > 5_000_000 and stato == "GARA PUBBLICATA":
        return "P1"
    if days_to_deadline is not None and 0 <= days_to_deadline <= 2:
        return "P1"
    if score >= 50:
        return "P2"
    if score >= 30:
        return "P3"
    return "P4"
