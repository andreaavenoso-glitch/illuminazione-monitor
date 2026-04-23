"""Deduplication: collapse equivalent procurement_records.

Port of scripts/pipeline.js:202-210 — uses CIG when available, falls back to a
fuzzy "ente|oggetto|importo-bucket" key. Within a group, the row with the
lowest ``source_priority_rank`` is the master (§9.2: scheda gara > portale
committente > albo > GURI/TED > ANAC > stampa > snippet); the others are
flagged via ``master_record_id`` so the dashboard can hide them while keeping
the audit trail intact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


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
    """Pick the master record (lowest source_priority_rank, ties broken by
    earliest first_seen_at) and return ids of the master + duplicates.

    Records must expose ``id``, ``source_priority_rank``, ``first_seen_at``.
    Caller is responsible for persisting the ``master_record_id`` updates.
    """
    if not records:
        return DedupGroup(key="", master_id=None)

    sorted_records = sorted(
        records,
        key=lambda r: (r.source_priority_rank or 999, r.first_seen_at),
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
