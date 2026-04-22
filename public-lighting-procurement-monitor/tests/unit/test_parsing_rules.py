from datetime import datetime, timezone
from decimal import Decimal

import pytest

from parsing_rules import (
    days_until,
    is_in_lighting_perimeter,
    parse_italian_date,
    parse_importo,
    score_perimeter,
    valid_cig,
)
from parsing_rules.regex import CPV_LIGHTING_CODES, contains_lighting_cpv


class TestCIG:
    @pytest.mark.parametrize(
        "value",
        ["ABCDEFGH12", "9A1234567B", "12345678", "ABCD1234EF"],
    )
    def test_valid_cig(self, value: str) -> None:
        assert valid_cig(value) is True

    @pytest.mark.parametrize(
        "value",
        [None, "", "abc", "abcdefghij1234", "ABCDEFG!"],
    )
    def test_invalid_cig(self, value: str | None) -> None:
        assert valid_cig(value) is False


class TestImporto:
    def test_italian_format(self) -> None:
        assert parse_importo("€ 1.234.567,89") == Decimal("1234567.89")

    def test_no_currency_symbol(self) -> None:
        assert parse_importo("1.234.567,89") == Decimal("1234567.89")

    def test_plain_number(self) -> None:
        assert parse_importo("1234567.89") == Decimal("1234567.89")

    def test_integer_like(self) -> None:
        assert parse_importo("5000000") == Decimal("5000000")

    def test_thousands_dot_only(self) -> None:
        assert parse_importo("1.234") == Decimal("1234")

    def test_small_decimal(self) -> None:
        assert parse_importo("99,5") == Decimal("99.5")

    @pytest.mark.parametrize("raw", [None, "", "n.d.", "abc", "N/A"])
    def test_none_or_invalid(self, raw: str | None) -> None:
        assert parse_importo(raw) is None

    def test_numeric_input(self) -> None:
        assert parse_importo(1500.5) == Decimal("1500.5")


class TestDates:
    def test_italian_date(self) -> None:
        result = parse_italian_date("15/03/2026")
        assert result == datetime(2026, 3, 15, tzinfo=timezone.utc)

    def test_iso_date(self) -> None:
        result = parse_italian_date("2026-03-15")
        assert result == datetime(2026, 3, 15, tzinfo=timezone.utc)

    def test_iso_datetime_utc(self) -> None:
        result = parse_italian_date("2026-03-15T10:30:00Z")
        assert result == datetime(2026, 3, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_none_inputs(self) -> None:
        assert parse_italian_date(None) is None
        assert parse_italian_date("n.d.") is None
        assert parse_italian_date("garbage") is None

    def test_days_until(self) -> None:
        now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert days_until("20/03/2026", now=now) == 5
        assert days_until("10/03/2026", now=now) == -5
        assert days_until(None, now=now) is None


class TestPerimeter:
    def test_in_scope_simple(self) -> None:
        assert is_in_lighting_perimeter("Gara per illuminazione pubblica del Comune di X") is True

    def test_out_of_scope(self) -> None:
        assert (
            is_in_lighting_perimeter("Servizio di facility management e climatizzazione edifici")
            is False
        )

    def test_relamping_in_scope(self) -> None:
        assert is_in_lighting_perimeter("Progetto di relamping LED sulle strade cittadine") is True

    def test_score_with_multiple_hits(self) -> None:
        score = score_perimeter(
            "accordo quadro illuminazione pubblica con servizio smart lighting e telegestione"
        )
        assert score.in_scope is True
        assert len(score.include_hits) >= 3

    def test_negative_outweighs_positive(self) -> None:
        score = score_perimeter(
            "impianto elettrico generico per edifici, facility management, climatizzazione"
        )
        assert score.in_scope is False
        assert score.score < 0


class TestCPV:
    def test_lighting_cpv_detected(self) -> None:
        codes_to_check = {"34928510", "45316110", "50232000"}
        assert codes_to_check.issubset(CPV_LIGHTING_CODES)

    def test_text_with_lighting_cpv(self) -> None:
        assert contains_lighting_cpv("CPV codici: 34928510-8, altro: 99999999") is True

    def test_text_without_lighting_cpv(self) -> None:
        assert contains_lighting_cpv("CPV: 72000000 servizi informatici") is False

    def test_text_empty(self) -> None:
        assert contains_lighting_cpv(None) is False
        assert contains_lighting_cpv("") is False
