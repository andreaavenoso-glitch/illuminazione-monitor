"""Deduplication: collapse equivalent procurement_records.

Port of scripts/pipeline.js:202-210 — uses CIG when available, falls back to a
fuzzy "ente|oggetto|importo-bucket" key. Within a group, the master is picked
by lifecycle stage first (§ _STAGE_RANK below), then by lowest
``source_priority_rank`` (§9.2: scheda gara > portale committente > albo >
GURI/TED > ANAC > stampa > snippet) as a tiebreaker among records at the same
stage; the others are flagged via ``master_record_id`` so the dashboard can
hide them while keeping the audit trail intact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

# Same CIG can legitimately carry records at different points in a tender's
# life (the bando itself, then weeks later its esito di aggiudicazione) --
# these land in the same dedup group since they share a CIG. Picking the
# master by source reliability alone let a stale "GARA PUBBLICATA" from a
# highly-ranked source outrank a correct, more recent "ESITO" from a
# lower-ranked one, leaving already-awarded/revoked/deserted tenders showing
# as still open. A record further along in the lifecycle is master
# regardless of which source reported it; source rank only breaks ties
# within the same stage. Unrecognised/missing values sort last (assumed
# least informative, same effect as the old "or 999" rank fallback).
_STAGE_RANK: dict[str, int] = {
    "ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA": 0,
    "RETTIFICA-PROROGA-CHIARIMENTI": 1,
    "GARA PUBBLICATA": 2,
    "PRE-GARA": 3,
}
_UNKNOWN_STAGE_RANK = 4


def compute_dedup_key(
    *,
    cig: str | None,
    ente: str,
    oggetto: str | None,
    importo: Decimal | float | None,
) -> str:
    """Return a stable bucket key for grouping near-duplicates."""
    if cig:
        cig_upper = cig.strip().upper()
        if cig_upper:
            return f"cig:{cig_upper}"

    importo_bucket = "x"
    if importo is not None:
        try:
            importo_bucket = str(int(round(float(importo) / 50_000) * 50_000))
        except (TypeError, ValueError):
            importo_bucket = "x"

    ente_part = (ente or "").strip().lower()[:28]
    oggetto_part = (oggetto or "").strip().lower()[:38]
    return f"eo:{ente_part}|{oggetto_part}|{importo_bucket}"


@dataclass
class DedupGroup:
    key: str
    master_id: str | None
    duplicate_ids: list[str] = field(default_factory=list)
    member_count: int = 0


def deduplicate_group(records: list) -> DedupGroup:
    """Pick the master record (furthest-along lifecycle stage first, then
    lowest source_priority_rank, ties broken by earliest first_seen_at) and
    return ids of the master + duplicates.

    Records must expose ``id``, ``stato_procedurale``, ``source_priority_rank``,
    ``first_seen_at``. Caller is responsible for persisting the
    ``master_record_id`` updates.
    """
    if not records:
        return DedupGroup(key="", master_id=None)

    sorted_records = sorted(
        records,
        key=lambda r: (
            _STAGE_RANK.get(r.stato_procedurale, _UNKNOWN_STAGE_RANK),
            r.source_priority_rank or 999,
            r.first_seen_at,
        ),
    )
    master = sorted_records[0]
    duplicates = [r for r in sorted_records[1:]]
    key = compute_dedup_key(
        cig=master.cig,
        ente=master.ente,
        oggetto=master.descrizione,
        importo=master.importo,
    )
    return DedupGroup(
        key=key,
        master_id=str(master.id),
        duplicate_ids=[str(r.id) for r in duplicates],
        member_count=len(records),
    )
