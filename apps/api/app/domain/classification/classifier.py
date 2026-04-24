"""Procedural state + novelty classification.

Port of scripts/pipeline.js:212-220 (``classifyDet``) with the §9.3 novelty
rule added.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime

from shared_models.enums import StatoProcedurale, TipoNovita

_ESITO_RE = re.compile(r"esito|aggiudic|revoca|deserta|annullat", re.IGNORECASE)
_RETTIFICA_RE = re.compile(r"proroga|rettifica|chiariment", re.IGNORECASE)
_PRE_GARA_RE = re.compile(
    r"delibera|determin[ae]|manifestazione\s+d['’]?interesse|avviso\s+preinformazione",
    re.IGNORECASE,
)


def classify_stato_procedurale(
    *,
    descrizione: str | None,
    raw_body: str | None,
    cig: str | None,
    link: str | None,
    atto_tipo: str | None = None,
) -> str:
    """Return one of the four ``stato_procedurale`` enum values."""
    haystack = " ".join(filter(None, [descrizione, raw_body, atto_tipo]))
    if atto_tipo and atto_tipo != "notizia":
        return StatoProcedurale.PRE_GARA.value
    if _ESITO_RE.search(haystack):
        return StatoProcedurale.ESITO.value
    if _RETTIFICA_RE.search(haystack):
        return StatoProcedurale.RETTIFICA.value
    if _PRE_GARA_RE.search(haystack):
        return StatoProcedurale.PRE_GARA.value
    if cig and link:
        return StatoProcedurale.GARA_PUBBLICATA.value
    # Default: treat as a published tender with weak evidence, consumer decides.
    return StatoProcedurale.GARA_PUBBLICATA.value


def classify_tipo_novita(
    *,
    first_seen_at: datetime,
    data_pubblicazione: datetime | None,
    is_existing_record: bool,
    stato_procedurale: str,
    now: datetime | None = None,
) -> str:
    """§9.3 — determine the ``tipo_novita`` enum value."""
    if stato_procedurale == StatoProcedurale.PRE_GARA.value:
        return TipoNovita.SEGNALE_PRE_GARA.value

    if is_existing_record:
        return TipoNovita.AGGIORNAMENTO.value

    today = (now or datetime.now(tz=UTC)).date()
    if first_seen_at.date() != today:
        # Still labelled as new when the master record is first seen,
        # regardless of pipeline day. The caller controls the reference day.
        return TipoNovita.NUOVO_OGGI.value

    if data_pubblicazione is None:
        return TipoNovita.NUOVO_OGGI.value
    if data_pubblicazione.date() < today:
        return TipoNovita.NUOVO_EMERSO_OGGI.value
    return TipoNovita.NUOVO_OGGI.value
