"""Daily report builder.

Pure function: given the day's procurement_records, source runs and open
alerts, produce the JSON + Markdown payload that the dashboard and the
exports will consume. Replaces the legacy ``generateReport`` Haiku call
from scripts/pipeline.js:244-276 with a deterministic section assembler.

Report shape (persisted as daily_reports.report_json)::

    {
        "report_date": "2026-04-22",
        "generated_at": "2026-04-22T07:00:00Z",
        "kpi": {
            "total_new": 4, "total_updates": 2, "total_pregara": 3,
            "total_weak": 5, "total_p1": 2, "valore_totale_eur": 42000000
        },
        "nuove_gare": [...], "aggiornamenti": [...], "pre_gara": [...],
        "evidenze_deboli": [...], "fonti_interrogate": [...],
        "anomalie_aperte": [...],
        "markdown": "# Report …"
    }
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any


@dataclass
class ReportContext:
    """Input bundle: caller (worker task) pre-loads these collections."""

    records: list[Any]
    sources: list[Any]
    job_runs: list[Any]  # today's job_run rows
    alerts: list[Any]  # open alerts only


@dataclass
class DailyReportData:
    report_date: date
    generated_at: datetime
    kpi: dict[str, Any]
    nuove_gare: list[dict]
    aggiornamenti: list[dict]
    pre_gara: list[dict]
    evidenze_deboli: list[dict]
    fonti_interrogate: list[dict]
    anomalie_aperte: list[dict]
    markdown: str

    def to_json(self) -> dict[str, Any]:
        return {
            "report_date": self.report_date.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "kpi": self.kpi,
            "nuove_gare": self.nuove_gare,
            "aggiornamenti": self.aggiornamenti,
            "pre_gara": self.pre_gara,
            "evidenze_deboli": self.evidenze_deboli,
            "fonti_interrogate": self.fonti_interrogate,
            "anomalie_aperte": self.anomalie_aperte,
            "markdown": self.markdown,
        }


def _is_today(ts: datetime | None, today: date) -> bool:
    return ts is not None and ts.date() == today


def _serialize_record(r: Any) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "ente": r.ente,
        "descrizione": r.descrizione,
        "importo": float(r.importo) if r.importo is not None else None,
        "cig": r.cig,
        "link_bando": r.link_bando,
        "regione": r.regione,
        "scadenza": r.scadenza.isoformat() if r.scadenza else None,
        "stato_procedurale": r.stato_procedurale,
        "tipo_novita": r.tipo_novita,
        "score": r.score_commerciale,
        "priorita": r.priorita_commerciale,
        "is_weak_evidence": r.is_weak_evidence,
    }


def build_daily_report(
    ctx: ReportContext,
    *,
    today: date | None = None,
    now: datetime | None = None,
) -> DailyReportData:
    today = today or datetime.now(tz=UTC).date()
    now = now or datetime.now(tz=UTC)

    masters = [r for r in ctx.records if getattr(r, "master_record_id", None) is None]

    nuove_gare_rows = [
        r
        for r in masters
        if r.tipo_novita in ("Nuovo oggi", "Nuovo emerso oggi ma pubblicato prima")
        and not r.is_weak_evidence
    ]
    aggiornamenti_rows = [
        r for r in masters if r.tipo_novita == "Aggiornamento gara nota"
    ]
    pre_gara_rows = [r for r in masters if r.stato_procedurale == "PRE-GARA"]
    evidenze_deboli_rows = [r for r in ctx.records if r.is_weak_evidence]

    p1_count = sum(1 for r in masters if r.priorita_commerciale == "P1")
    total_value = sum(
        float(r.importo)
        for r in masters
        if r.importo is not None and r.stato_procedurale == "GARA PUBBLICATA"
    )

    # fonti_interrogate: one row per source run today, latest status.
    runs_by_source: dict[str, Any] = {}
    for run in ctx.job_runs:
        if not _is_today(run.started_at, today):
            continue
        if run.source_id is None:
            continue
        prev = runs_by_source.get(str(run.source_id))
        if prev is None or run.started_at > prev.started_at:
            runs_by_source[str(run.source_id)] = run

    source_by_id = {str(s.id): s for s in ctx.sources}
    fonti_interrogate = [
        {
            "source_id": sid,
            "source_name": source_by_id[sid].name if sid in source_by_id else "(unknown)",
            "status": run.status,
            "records_found": run.records_found,
            "records_valid": run.records_valid,
            "records_weak": run.records_weak,
            "error_message": run.error_message,
        }
        for sid, run in runs_by_source.items()
    ]

    anomalie_aperte = [
        {
            "id": str(a.id),
            "alert_type": a.alert_type,
            "severity": a.severity,
            "description": a.description,
            "opened_at": a.opened_at.isoformat() if a.opened_at else None,
            "procurement_record_id": (
                str(a.procurement_record_id) if a.procurement_record_id else None
            ),
        }
        for a in ctx.alerts
        if a.is_open
    ]

    kpi = {
        "total_new": len(nuove_gare_rows),
        "total_updates": len(aggiornamenti_rows),
        "total_pregara": len(pre_gara_rows),
        "total_weak": len(evidenze_deboli_rows),
        "total_p1": p1_count,
        "valore_totale_eur": round(total_value, 2),
        "total_sources_ok": sum(1 for r in runs_by_source.values() if r.status == "success"),
        "total_sources_failed": sum(1 for r in runs_by_source.values() if r.status == "failed"),
        "total_anomalie_aperte": len(anomalie_aperte),
    }

    nuove_gare = [_serialize_record(r) for r in _top_by_score(nuove_gare_rows, 30)]
    aggiornamenti = [_serialize_record(r) for r in _top_by_score(aggiornamenti_rows, 30)]
    pre_gara = [_serialize_record(r) for r in _top_by_score(pre_gara_rows, 20)]
    evidenze_deboli = [_serialize_record(r) for r in evidenze_deboli_rows[:30]]

    markdown = _render_markdown(
        today=today,
        kpi=kpi,
        nuove_gare=nuove_gare_rows,
        aggiornamenti=aggiornamenti_rows,
        pre_gara=pre_gara_rows,
        fonti=fonti_interrogate,
    )

    return DailyReportData(
        report_date=today,
        generated_at=now,
        kpi=kpi,
        nuove_gare=nuove_gare,
        aggiornamenti=aggiornamenti,
        pre_gara=pre_gara,
        evidenze_deboli=evidenze_deboli,
        fonti_interrogate=fonti_interrogate,
        anomalie_aperte=anomalie_aperte,
        markdown=markdown,
    )


def _top_by_score(rows: list[Any], limit: int) -> list[Any]:
    return sorted(rows, key=lambda r: (-(r.score_commerciale or 0), r.ente))[:limit]


def _fmt_eur(value: float | Decimal | None) -> str:
    if value is None:
        return "n.d."
    return f"€{float(value):,.0f}".replace(",", ".")


def _render_markdown(
    *,
    today: date,
    kpi: dict[str, Any],
    nuove_gare: list[Any],
    aggiornamenti: list[Any],
    pre_gara: list[Any],
    fonti: list[dict],
) -> str:
    parts: list[str] = []
    parts.append(f"# Report · Illuminazione pubblica · {today.strftime('%d %B %Y')}")
    parts.append("")
    parts.append("## A. Nuove gare")
    if nuove_gare:
        for r in _top_by_score(nuove_gare, 10):
            scad = r.scadenza.strftime("%d/%m/%Y") if r.scadenza else "n.d."
            parts.append(
                f"- **[{r.priorita_commerciale or '?'}]** {r.ente} — "
                f"{(r.descrizione or '')[:80]} — {_fmt_eur(r.importo)} — scad {scad}"
            )
    else:
        parts.append("Nessuna gara pubblicata oggi.")
    parts.append("")

    parts.append("## B. Aggiornamenti")
    if aggiornamenti:
        for r in _top_by_score(aggiornamenti, 10):
            parts.append(
                f"- {r.ente} — {(r.descrizione or '')[:80]} — {r.stato_procedurale}"
            )
    else:
        parts.append("Nessun aggiornamento su gare note.")
    parts.append("")

    parts.append("## C. Segnali pre-gara")
    if pre_gara:
        for r in _top_by_score(pre_gara, 10):
            parts.append(
                f"- {r.ente} — {(r.descrizione or '')[:80]}"
            )
    else:
        parts.append("Nessun segnale pre-gara nuovo.")
    parts.append("")

    counters = Counter(f["status"] for f in fonti)
    parts.append("## D. Fonti interrogate")
    parts.append(
        f"{len(fonti)} fonti · "
        f"{counters.get('success', 0)} ok · "
        f"{counters.get('failed', 0)} errori · "
        f"{counters.get('partial', 0)} parziali"
    )
    parts.append("")

    parts.append("## Cruscotto")
    parts.append("| KPI | Valore |")
    parts.append("|---|---|")
    parts.append(f"| Nuove gare | {kpi['total_new']} |")
    parts.append(f"| Aggiornamenti | {kpi['total_updates']} |")
    parts.append(f"| Pre-gara | {kpi['total_pregara']} |")
    parts.append(f"| Evidenze deboli | {kpi['total_weak']} |")
    parts.append(f"| Priorità P1 | {kpi['total_p1']} |")
    parts.append(f"| Valore gare attive | {_fmt_eur(kpi['valore_totale_eur'])} |")
    parts.append(f"| Anomalie aperte | {kpi['total_anomalie_aperte']} |")

    return "\n".join(parts) + "\n"
