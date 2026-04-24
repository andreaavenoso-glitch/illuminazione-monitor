"""Raw → ProcurementRecord normalization.

Port of scripts/pipeline.js:159-200 (``normalize``) with the §5 schema
expanded: the legacy `pipeline.js` produced a flat JSON object with booleans
for flags, whereas the new schema uses "Yes"/"No" strings. The §9.1 weak
evidence rule is applied here.

This module is intentionally free of SQLAlchemy imports: it operates on
dataclasses and plain values so it can be unit-tested with synthetic inputs
and reused by the worker with minimal coupling.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from parsing_rules import (
    is_in_lighting_perimeter,
    parse_importo,
    parse_italian_date,
    valid_cig,
)
from sector_dictionaries import extract_tags

_YES = "Yes"
_NO = "No"

_PPP_RE = re.compile(r"\bppp\b|project[\s.\-]?fin|concessione", re.IGNORECASE)
_CONCESSIONE_RE = re.compile(r"concessione|affidament[oa]\s+concessione", re.IGNORECASE)
_IN_HOUSE_RE = re.compile(r"in\s*house", re.IGNORECASE)
_OM_RE = re.compile(r"manutenzione|global\s+service|gestione\s+impianti|o\s*&\s*m|servizio\s+luce", re.IGNORECASE)
_PRE_GARA_RE = re.compile(
    r"delibera|determin[ae]|avviso\s+preinformazione|manifestazione\s+d['’]?interesse|indagine\s+di\s+mercato",
    re.IGNORECASE,
)


@dataclass
class NormalizerInput:
    raw_title: str | None
    raw_body: str | None
    raw_url: str
    raw_date: datetime | None = None
    extracted: dict | None = None
    source_priority_rank: int = 999
    regione_hint: str | None = None
    provincia_hint: str | None = None
    comune_hint: str | None = None
    ente_hint: str | None = None


@dataclass
class NormalizedRecord:
    ente: str
    descrizione: str | None
    importo: Decimal | None
    cig: str | None
    data_pubblicazione: datetime | None
    scadenza: datetime | None
    regione: str | None
    provincia: str | None
    comune: str | None
    tipologia_gara_procedura: str | None
    link_bando: str
    macrosettore: str
    source_priority_rank: int
    tag_tecnico: list[str]
    flag_concessione_ambito: str
    flag_ppp_doppio_oggetto: str
    flag_in_house_ambito: str
    flag_om: str
    flag_pre_gara: str
    validation_level: str
    reliability_index: str
    is_weak_evidence: bool
    notes: list[str] = field(default_factory=list)


def derive_flags(text: str) -> dict[str, str]:
    """Return the five Yes/No procurement flags from free-text."""
    return {
        "flag_ppp_doppio_oggetto": _YES if _PPP_RE.search(text) else _NO,
        "flag_concessione_ambito": _YES if _CONCESSIONE_RE.search(text) else _NO,
        "flag_in_house_ambito": _YES if _IN_HOUSE_RE.search(text) else _NO,
        "flag_om": _YES if _OM_RE.search(text) else _NO,
        "flag_pre_gara": _YES if _PRE_GARA_RE.search(text) else _NO,
    }


def normalize(payload: NormalizerInput) -> NormalizedRecord | None:
    """Transform a raw record into a NormalizedRecord. Returns None if the
    text is not within the lighting perimeter (§10.2 score < 1).
    """
    combined = " ".join(filter(None, [payload.raw_title, payload.raw_body]))
    if not is_in_lighting_perimeter(combined):
        return None

    extracted = payload.extracted or {}
    descrizione = payload.raw_title or _first_str(extracted, "oggetto", "titolo", "descrizione")
    ente = payload.ente_hint or _first_str(
        extracted, "ente", "stazione_appaltante", "amministrazione", "buyer"
    )
    cig_raw = _first_str(extracted, "cig", "cig_raw")
    cig = cig_raw.strip().upper() if cig_raw else None
    if cig and not valid_cig(cig):
        cig = None

    importo = parse_importo(_first_str(extracted, "importo", "importo_raw", "valore", "total_value"))
    data_pubblicazione = payload.raw_date or parse_italian_date(
        _first_str(extracted, "data_pubblicazione", "data_pub", "pub_date")
    )
    scadenza = parse_italian_date(_first_str(extracted, "scadenza", "scadenza_raw", "deadline"))
    procedura = _first_str(extracted, "procedura", "procedura_raw", "tipo_procedura")

    flags = derive_flags(combined + " " + (procedura or ""))
    importo_float = float(importo) if importo is not None else None
    tags = extract_tags(combined, importo=importo_float)

    notes: list[str] = []
    for key, value in flags.items():
        if value == _YES:
            notes.append(f"flag:{key}")

    # Validation level + weak evidence per §9.1:
    # must have ente + oggetto + stato + link + one of importo/cig/scadenza/procedura.
    has_any_identifier = any(v is not None for v in (importo, cig, scadenza, procedura))
    has_core = bool(ente) and bool(descrizione) and bool(payload.raw_url)
    is_weak = not (has_core and has_any_identifier)

    validation_level = "L3" if (cig and importo) else ("L2" if has_any_identifier else "L1")
    reliability_index = _reliability_from_rank(payload.source_priority_rank)

    if not ente:
        # Without an ente the record cannot enter procurement_records.
        ente = _first_str(extracted, "amministrazione_titolare", "buyer_name_1") or "n.d."
        is_weak = True

    return NormalizedRecord(
        ente=ente,
        descrizione=descrizione,
        importo=importo,
        cig=cig,
        data_pubblicazione=data_pubblicazione,
        scadenza=scadenza,
        regione=payload.regione_hint or _first_str(extracted, "regione"),
        provincia=payload.provincia_hint or _first_str(extracted, "provincia"),
        comune=payload.comune_hint or _first_str(extracted, "comune"),
        tipologia_gara_procedura=procedura,
        link_bando=payload.raw_url,
        macrosettore="Illuminazione pubblica",
        source_priority_rank=payload.source_priority_rank,
        tag_tecnico=tags,
        flag_concessione_ambito=flags["flag_concessione_ambito"],
        flag_ppp_doppio_oggetto=flags["flag_ppp_doppio_oggetto"],
        flag_in_house_ambito=flags["flag_in_house_ambito"],
        flag_om=flags["flag_om"],
        flag_pre_gara=flags["flag_pre_gara"],
        validation_level=validation_level,
        reliability_index=reliability_index,
        is_weak_evidence=is_weak,
        notes=notes,
    )


def _first_str(data: dict, *keys: str) -> str | None:
    for k in keys:
        value = data.get(k)
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        elif isinstance(value, str):
            if value.strip():
                return value.strip()
        else:
            return str(value)
    return None


def _reliability_from_rank(rank: int) -> str:
    # §9.2 priority ranks: 1=scheda gara, 2=portale committente, 3=albo,
    # 4=GURI/TED, 5=ANAC, 6=stampa, 7=snippet. Map to Alta/Media/Bassa.
    if rank <= 3:
        return "Alta"
    if rank <= 5:
        return "Media"
    return "Bassa"
