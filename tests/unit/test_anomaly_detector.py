from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.domain.anomaly_detection import AnomalyContext, detect_anomalies


@dataclass
class FakeEvent:
    procurement_record_id: UUID
    event_type: str
    event_date: datetime
    description: str | None = None


@dataclass
class FakeRecord:
    id: UUID = field(default_factory=uuid4)
    ente: str = "Comune di Test"
    descrizione: str | None = "Gara illuminazione pubblica"
    stato_procedurale: str = "GARA PUBBLICATA"
    data_pubblicazione: datetime | None = None
    first_seen_at: datetime = field(default_factory=lambda: datetime(2026, 4, 1, tzinfo=UTC))


NOW = datetime(2026, 4, 22, 10, tzinfo=UTC)


def test_proroga_multipla_triggers_high_alert() -> None:
    r = FakeRecord()
    events = [
        FakeEvent(r.id, "proroga", NOW - timedelta(days=20)),
        FakeEvent(r.id, "proroga", NOW - timedelta(days=5)),
    ]
    cands = detect_anomalies(AnomalyContext(records=[r], events=events), now=NOW)
    assert len(cands) == 1
    assert cands[0].alert_type == "proroga_multipla"
    assert cands[0].severity == "high"


def test_single_proroga_does_not_trigger() -> None:
    r = FakeRecord()
    events = [FakeEvent(r.id, "proroga", NOW - timedelta(days=5))]
    cands = detect_anomalies(AnomalyContext(records=[r], events=events), now=NOW)
    assert not any(c.alert_type == "proroga_multipla" for c in cands)


def test_revoca_after_publication() -> None:
    r = FakeRecord(data_pubblicazione=NOW - timedelta(days=30))
    events = [FakeEvent(r.id, "revoca", NOW - timedelta(days=5))]
    cands = detect_anomalies(AnomalyContext(records=[r], events=events), now=NOW)
    assert any(c.alert_type == "revoca_post_pubblicazione" for c in cands)
    c = next(c for c in cands if c.alert_type == "revoca_post_pubblicazione")
    assert c.severity == "critical"


def test_revoca_before_publication_ignored() -> None:
    r = FakeRecord(data_pubblicazione=NOW - timedelta(days=5))
    events = [FakeEvent(r.id, "revoca", NOW - timedelta(days=30))]
    cands = detect_anomalies(AnomalyContext(records=[r], events=events), now=NOW)
    assert not any(c.alert_type == "revoca_post_pubblicazione" for c in cands)


def test_ricorso_tar_in_event_type() -> None:
    r = FakeRecord()
    events = [FakeEvent(r.id, "ricorso_tar", NOW - timedelta(days=2), "Ricorso TAR presentato")]
    cands = detect_anomalies(AnomalyContext(records=[r], events=events), now=NOW)
    assert any(c.alert_type == "ricorso_tar" for c in cands)


def test_procedura_ponte_on_descrizione() -> None:
    r = FakeRecord(descrizione="Procedura ponte a seguito di gara deserta")
    cands = detect_anomalies(AnomalyContext(records=[r], events=[]), now=NOW)
    assert any(c.alert_type == "procedura_ponte" for c in cands)


def test_stato_stallo_after_14_days() -> None:
    r = FakeRecord(
        stato_procedurale="RETTIFICA-PROROGA-CHIARIMENTI",
        first_seen_at=NOW - timedelta(days=20),
    )
    cands = detect_anomalies(AnomalyContext(records=[r], events=[]), now=NOW)
    assert any(c.alert_type == "stato_stallo" for c in cands)


def test_stato_stallo_under_14_days_skipped() -> None:
    r = FakeRecord(
        stato_procedurale="RETTIFICA-PROROGA-CHIARIMENTI",
        first_seen_at=NOW - timedelta(days=5),
    )
    cands = detect_anomalies(AnomalyContext(records=[r], events=[]), now=NOW)
    assert not any(c.alert_type == "stato_stallo" for c in cands)


def test_open_alert_dedup() -> None:
    r = FakeRecord(data_pubblicazione=NOW - timedelta(days=30))
    events = [FakeEvent(r.id, "revoca", NOW - timedelta(days=5))]
    open_keys = {f"revoca_post_pubblicazione:{r.id}"}
    cands = detect_anomalies(
        AnomalyContext(records=[r], events=events, open_alert_keys=open_keys),
        now=NOW,
    )
    assert not any(c.alert_type == "revoca_post_pubblicazione" for c in cands)


def test_multiple_rules_can_fire_together() -> None:
    r = FakeRecord(
        data_pubblicazione=NOW - timedelta(days=30),
        stato_procedurale="RETTIFICA-PROROGA-CHIARIMENTI",
        first_seen_at=NOW - timedelta(days=25),
    )
    events = [
        FakeEvent(r.id, "proroga", NOW - timedelta(days=15)),
        FakeEvent(r.id, "proroga", NOW - timedelta(days=3)),
        FakeEvent(r.id, "revoca", NOW - timedelta(days=1)),
    ]
    cands = detect_anomalies(AnomalyContext(records=[r], events=events), now=NOW)
    types = {c.alert_type for c in cands}
    assert "proroga_multipla" in types
    assert "revoca_post_pubblicazione" in types
    assert "stato_stallo" in types
