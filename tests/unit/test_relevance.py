"""A deadline is binding: expired notices are noise."""
from __future__ import annotations

from datetime import UTC, date, datetime

from app.services.records_export import COLUMNS, records_csv
from shared_models.relevance import MAX_AGE_DAYS, is_actionable, is_expired_record

TODAY = date(2026, 11, 20)


def dt(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=UTC)


class TestIsActionable:
    def test_a_future_or_same_day_deadline_is_valid(self) -> None:
        assert is_actionable(dt(2026, 12, 1), None, TODAY)
        assert is_actionable(dt(2026, 11, 20), None, TODAY)  # last day still counts

    def test_a_past_deadline_is_noise_whatever_the_publication_date(self) -> None:
        assert not is_actionable(dt(2026, 11, 19), dt(2026, 11, 18), TODAY)
        assert not is_actionable(date(2024, 6, 30), None, TODAY)

    def test_the_deadline_wins_over_an_old_publication_date(self) -> None:
        # published long ago but still open: valid
        assert is_actionable(dt(2026, 12, 15), dt(2025, 1, 10), TODAY)

    def test_without_a_deadline_only_recent_notices_count(self) -> None:
        assert is_actionable(None, dt(2026, 10, 1), TODAY)
        assert not is_actionable(None, dt(2025, 3, 1), TODAY)
        edge = date(2026, 11, 20).toordinal() - MAX_AGE_DAYS
        assert is_actionable(None, date.fromordinal(edge), TODAY)
        assert not is_actionable(None, date.fromordinal(edge - 1), TODAY)

    def test_nothing_known_is_kept(self) -> None:
        assert is_actionable(None, None, TODAY)


class TestIsExpiredRecord:
    def test_extracted_records(self) -> None:
        assert is_expired_record({"scadenza": "2026-11-19"}, TODAY)
        assert not is_expired_record({"scadenza": "2026-11-20"}, TODAY)
        assert not is_expired_record({"scadenza": "2027-01-31"}, TODAY)

    def test_missing_or_unreadable_deadline_is_not_expired(self) -> None:
        assert not is_expired_record({}, TODAY)
        assert not is_expired_record({"scadenza": None}, TODAY)
        assert not is_expired_record({"scadenza": "entro fine mese"}, TODAY)

    def test_iso_datetime_is_read_by_its_date(self) -> None:
        assert is_expired_record({"scadenza": "2026-11-01T10:00:00"}, TODAY)


class TestCsv:
    def test_header_rows_and_excel_friendly_encoding(self) -> None:
        out = records_csv([{"regione": "Puglia", "ente": "Comune di Bari", "descrizione": "Illuminazione; led",
                            "scadenza": "2026-12-01", "ancora_valido": "si", "link": "https://x/1"}])
        assert out.startswith("\ufeff" + ";".join(COLUMNS))
        assert "Comune di Bari" in out and '"Illuminazione; led"' in out  # the separator inside a field is quoted

    def test_empty(self) -> None:
        assert records_csv([]).count("\n") == 1
