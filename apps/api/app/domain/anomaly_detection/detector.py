"""Anomaly detector (spec §10.3).

Pure function: given today's procurement_records + their record_events,
produce a list of AnomalyCandidate objects that the worker persists as
open Alert rows (deduping against already-open alerts with the same key).

Rules implemented
-----------------

- **proroga_multipla** (high): same record has ≥2 ``proroga`` events in the
  last 30 days.
- **revoca_post_pubblicazione** (critical): record has a ``revoca`` event
  after ``data_pubblicazione``.
- **ricorso_tar** (high): any event whose type or description mentions
  ``ricorso``/``TAR``.
- **procedura_ponte** (medium): record tag or state contains
  ``deserta`` followed by a new ``GARA PUBBLICATA`` for the same ente
  within 30 days (heuristic on descrizione keywords).
- **stato_stallo** (low): record is still ``RETTIFICA-…`` for more
  than 14 consecutive days from first event.

Each candidate carries an ``alert_key`` that the worker uses to avoid
opening duplicate alerts for the same phenomenon.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class AnomalyContext:
    records: list[Any]
    events: list[Any]  # all record_events, any age
    open_alert_keys: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class AnomalyCandidate:
    alert_key: str  # stable key for dedup (record_id + type)
    procurement_record_id: str | None
    alert_type: str
    severity: str  # low | medium | high | critical
    description: str


def _events_by_record(events: list[Any]) -> dict[str, list[Any]]:
    by_record: dict[str, list[Any]] = defaultdict(list)
    for e in events:
        by_record[str(e.procurement_record_id)].append(e)
    for evts in by_record.values():
        evts.sort(key=lambda e: e.event_date)
    return by_record


def detect_anomalies(
    ctx: AnomalyContext,
    *,
    now: datetime | None = None,
) -> list[AnomalyCandidate]:
    now = now or datetime.now(tz=UTC)
    thirty_days_ago = now - timedelta(days=30)
    fourteen_days_ago = now - timedelta(days=14)

    by_record = _events_by_record(ctx.events)
    candidates: list[AnomalyCandidate] = []

    for record in ctx.records:
        rid = str(record.id)
        events_for_record = by_record.get(rid, [])

        # 1. Proroga multipla in 30gg
        recent_events = [e for e in events_for_record if e.event_date >= thirty_days_ago]
        event_types = Counter(e.event_type.lower() for e in recent_events if e.event_type)
        if event_types.get("proroga", 0) >= 2:
            candidates.append(
                AnomalyCandidate(
                    alert_key=f"proroga_multipla:{rid}",
                    procurement_record_id=rid,
                    alert_type="proroga_multipla",
                    severity="high",
                    description=(
                        f"{event_types['proroga']} proroghe registrate negli ultimi 30 giorni"
                    ),
                )
            )

        # 2. Revoca post pubblicazione
        if record.data_pubblicazione is not None:
            for ev in events_for_record:
                if (ev.event_type or "").lower() == "revoca" and ev.event_date > record.data_pubblicazione:
                    candidates.append(
                        AnomalyCandidate(
                            alert_key=f"revoca_post_pubblicazione:{rid}",
                            procurement_record_id=rid,
                            alert_type="revoca_post_pubblicazione",
                            severity="critical",
                            description=(
                                f"Revoca rilevata il {ev.event_date.date()} dopo pubblicazione del "
                                f"{record.data_pubblicazione.date()}"
                            ),
                        )
                    )
                    break

        # 3. Ricorso / TAR
        for ev in events_for_record:
            etype = (ev.event_type or "").lower()
            edesc = (ev.description or "").lower()
            if "ricorso" in etype or "tar" in etype or "ricorso" in edesc or "tar " in edesc:
                candidates.append(
                    AnomalyCandidate(
                        alert_key=f"ricorso_tar:{rid}",
                        procurement_record_id=rid,
                        alert_type="ricorso_tar",
                        severity="high",
                        description=(
                            ev.description
                            or f"Ricorso/TAR registrato il {ev.event_date.date()}"
                        ),
                    )
                )
                break

        # 4. Procedura ponte — gara deserta/annullata seguita da nuova procedura
        descr = (record.descrizione or "").lower()
        if record.stato_procedurale == "GARA PUBBLICATA" and (
            "ponte" in descr or "deserta" in descr or "a seguito di revoca" in descr
        ):
            candidates.append(
                AnomalyCandidate(
                    alert_key=f"procedura_ponte:{rid}",
                    procurement_record_id=rid,
                    alert_type="procedura_ponte",
                    severity="medium",
                    description="Possibile procedura ponte dopo gara deserta/annullata",
                )
            )

        # 5. Stato stallo — RETTIFICA da >14 giorni
        if record.stato_procedurale == "RETTIFICA-PROROGA-CHIARIMENTI":
            stuck_since = events_for_record[0].event_date if events_for_record else record.first_seen_at
            if stuck_since <= fourteen_days_ago:
                delta_days = (now - stuck_since).days
                candidates.append(
                    AnomalyCandidate(
                        alert_key=f"stato_stallo:{rid}",
                        procurement_record_id=rid,
                        alert_type="stato_stallo",
                        severity="low",
                        description=f"Gara in stato RETTIFICA da {delta_days} giorni",
                    )
                )

    # Drop candidates that already have an open alert with the same key.
    return [c for c in candidates if c.alert_key not in ctx.open_alert_keys]
