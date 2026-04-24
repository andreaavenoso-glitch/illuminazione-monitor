from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.reporting import ReportContext, build_daily_report


@dataclass
class FakeRecord:
    id: UUID
    ente: str
    descrizione: str | None = None
    importo: Decimal | None = None
    cig: str | None = None
    link_bando: str = "https://example.test/bando"
    regione: str | None = None
    scadenza: datetime | None = None
    stato_procedurale: str = "GARA PUBBLICATA"
    tipo_novita: str = "Nuovo oggi"
    score_commerciale: int | None = 50
    priorita_commerciale: str | None = "P2"
    is_weak_evidence: bool = False
    master_record_id: UUID | None = None


@dataclass
class FakeSource:
    id: UUID
    name: str


@dataclass
class FakeJobRun:
    source_id: UUID | None
    started_at: datetime
    status: str = "success"
    records_found: int = 10
    records_valid: int = 8
    records_weak: int = 2
    error_message: str | None = None


@dataclass
class FakeAlert:
    id: UUID
    alert_type: str
    severity: str
    description: str
    is_open: bool = True
    opened_at: datetime = field(default_factory=lambda: datetime(2026, 4, 22, tzinfo=UTC))
    procurement_record_id: UUID | None = None


def _today_ts() -> datetime:
    return datetime(2026, 4, 22, 9, 30, tzinfo=UTC)


def test_empty_context_produces_zeroed_report() -> None:
    now = _today_ts()
    result = build_daily_report(
        ReportContext(records=[], sources=[], job_runs=[], alerts=[]),
        today=now.date(),
        now=now,
    )
    assert result.report_date == date(2026, 4, 22)
    assert result.kpi == {
        "total_new": 0,
        "total_updates": 0,
        "total_pregara": 0,
        "total_weak": 0,
        "total_p1": 0,
        "valore_totale_eur": 0,
        "total_sources_ok": 0,
        "total_sources_failed": 0,
        "total_anomalie_aperte": 0,
    }
    assert "Nessuna gara pubblicata oggi" in result.markdown


def test_sections_populated() -> None:
    now = _today_ts()
    source_id = uuid4()
    sources = [FakeSource(id=source_id, name="TED EU")]

    records = [
        FakeRecord(
            id=uuid4(),
            ente="Comune di Prato",
            descrizione="Relamping LED illuminazione pubblica",
            importo=Decimal("8000000"),
            priorita_commerciale="P1",
            score_commerciale=85,
            tipo_novita="Nuovo oggi",
            stato_procedurale="GARA PUBBLICATA",
        ),
        FakeRecord(
            id=uuid4(),
            ente="Comune di Milano",
            descrizione="Proroga bando illuminazione pubblica",
            tipo_novita="Aggiornamento gara nota",
            stato_procedurale="RETTIFICA-PROROGA-CHIARIMENTI",
        ),
        FakeRecord(
            id=uuid4(),
            ente="Comune di Verona",
            descrizione="Delibera illuminazione pubblica",
            tipo_novita="Segnale pre-gara",
            stato_procedurale="PRE-GARA",
        ),
        FakeRecord(
            id=uuid4(),
            ente="Comune di X",
            descrizione="Notizia illuminazione senza dati",
            is_weak_evidence=True,
            tipo_novita="Nuovo oggi",
        ),
    ]

    job_runs = [
        FakeJobRun(source_id=source_id, started_at=now, status="success"),
    ]
    alerts = [
        FakeAlert(id=uuid4(), alert_type="proroga_multipla", severity="high", description="2 proroghe in 5 giorni"),
    ]

    result = build_daily_report(
        ReportContext(records=records, sources=sources, job_runs=job_runs, alerts=alerts),
        today=now.date(),
        now=now,
    )

    assert result.kpi["total_new"] == 1  # only the non-weak "Nuovo oggi" master
    assert result.kpi["total_updates"] == 1
    assert result.kpi["total_pregara"] == 1
    assert result.kpi["total_weak"] == 1
    assert result.kpi["total_p1"] == 1
    assert result.kpi["valore_totale_eur"] == 8_000_000.0
    assert result.kpi["total_sources_ok"] == 1
    assert result.kpi["total_anomalie_aperte"] == 1

    assert len(result.nuove_gare) == 1
    assert result.nuove_gare[0]["ente"] == "Comune di Prato"
    assert len(result.aggiornamenti) == 1
    assert len(result.pre_gara) == 1
    assert len(result.evidenze_deboli) == 1
    assert len(result.fonti_interrogate) == 1
    assert result.fonti_interrogate[0]["source_name"] == "TED EU"
    assert len(result.anomalie_aperte) == 1
    assert "Comune di Prato" in result.markdown


def test_duplicates_excluded_from_sections() -> None:
    now = _today_ts()
    master_id = uuid4()

    records = [
        FakeRecord(id=master_id, ente="Comune di Roma", tipo_novita="Nuovo oggi"),
        FakeRecord(
            id=uuid4(),
            ente="Comune di Roma",
            tipo_novita="Nuovo oggi",
            master_record_id=master_id,
        ),
    ]
    result = build_daily_report(
        ReportContext(records=records, sources=[], job_runs=[], alerts=[]),
        today=now.date(),
        now=now,
    )
    assert result.kpi["total_new"] == 1
    assert len(result.nuove_gare) == 1
    assert result.nuove_gare[0]["id"] == str(master_id)


def test_job_runs_outside_24h_are_ignored() -> None:
    now = _today_ts()
    source_id = uuid4()
    sources = [FakeSource(id=source_id, name="TED EU")]

    old_run = FakeJobRun(source_id=source_id, started_at=datetime(2026, 4, 20, tzinfo=UTC))

    result = build_daily_report(
        ReportContext(records=[], sources=sources, job_runs=[old_run], alerts=[]),
        today=now.date(),
        now=now,
    )
    assert result.fonti_interrogate == []
    assert result.kpi["total_sources_ok"] == 0


def test_closed_alerts_excluded() -> None:
    now = _today_ts()
    alerts = [
        FakeAlert(id=uuid4(), alert_type="x", severity="low", description="y", is_open=False),
    ]
    result = build_daily_report(
        ReportContext(records=[], sources=[], job_runs=[], alerts=alerts),
        today=now.date(),
        now=now,
    )
    assert result.kpi["total_anomalie_aperte"] == 0
    assert result.anomalie_aperte == []


def test_markdown_dashboard_contains_kpi_numbers() -> None:
    now = _today_ts()
    records = [
        FakeRecord(id=uuid4(), ente=f"Comune {i}", tipo_novita="Nuovo oggi", importo=Decimal("100000"))
        for i in range(3)
    ]
    result = build_daily_report(
        ReportContext(records=records, sources=[], job_runs=[], alerts=[]),
        today=now.date(),
        now=now,
    )
    md = result.markdown
    assert "| Nuove gare | 3 |" in md
    assert "# Report · Illuminazione pubblica" in md
