from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from scoring_engine import ScoringInput, compute_priority, score_record


class TestImportoBands:
    @pytest.mark.parametrize(
        "importo,expected_min",
        [
            (Decimal("12000000"), 35),
            (Decimal("6000000"), 28),
            (Decimal("3000000"), 20),
            (Decimal("1500000"), 14),
            (Decimal("700000"), 8),
            (Decimal("100000"), 3),
            (None, 3),
        ],
    )
    def test_band(self, importo, expected_min) -> None:
        result = score_record(
            ScoringInput(
                importo=importo,
                stato_procedurale="UNKNOWN",
                scadenza=None,
            ),
            now=datetime(2026, 4, 22, tzinfo=UTC),
        )
        assert result.score >= expected_min


class TestStatoPoints:
    NOW = datetime(2026, 4, 22, tzinfo=UTC)

    def test_gara_pubblicata_adds_25(self) -> None:
        result = score_record(
            ScoringInput(importo=None, stato_procedurale="GARA PUBBLICATA", scadenza=None),
            now=self.NOW,
        )
        assert result.score == 3 + 25  # importo base + stato

    def test_pre_gara_forte_adds_20(self) -> None:
        result = score_record(
            ScoringInput(
                importo=None,
                stato_procedurale="PRE-GARA",
                scadenza=None,
                pre_gara_forza="forte",
            ),
            now=self.NOW,
        )
        assert result.score == 3 + 20

    def test_pre_gara_debole_adds_8(self) -> None:
        result = score_record(
            ScoringInput(
                importo=None,
                stato_procedurale="PRE-GARA",
                scadenza=None,
                pre_gara_forza="debole",
            ),
            now=self.NOW,
        )
        assert result.score == 3 + 8


class TestScadenza:
    NOW = datetime(2026, 4, 22, 12, tzinfo=UTC)

    @pytest.mark.parametrize(
        "days,expected_pts",
        [(2, 20), (5, 15), (10, 10), (20, 5), (45, 0)],
    )
    def test_proximity_bonus(self, days, expected_pts) -> None:
        scad = self.NOW + timedelta(days=days)
        result = score_record(
            ScoringInput(importo=None, stato_procedurale="x", scadenza=scad),
            now=self.NOW,
        )
        assert result.days_to_deadline == days
        assert result.score == 3 + expected_pts


class TestFlagsAndTags:
    NOW = datetime(2026, 4, 22, tzinfo=UTC)

    def test_ppp_pnrr_soglia(self) -> None:
        result = score_record(
            ScoringInput(
                importo=None,
                stato_procedurale="x",
                scadenza=None,
                flag_ppp=True,
                flag_pnrr=True,
                flag_sopra_soglia_ue=True,
            ),
            now=self.NOW,
        )
        assert result.score == 3 + 8 + 6 + 4

    def test_accordo_quadro_bonus(self) -> None:
        result = score_record(
            ScoringInput(
                importo=None,
                stato_procedurale="x",
                scadenza=None,
                tag_tecnico=("accordo quadro",),
            ),
            now=self.NOW,
        )
        assert result.score == 3 + 3


class TestPriorityMapping:
    def test_p1_by_score(self) -> None:
        assert (
            compute_priority(score=80, importo=1000, stato="PRE-GARA", days_to_deadline=None) == "P1"
        )

    def test_p1_by_importo_and_stato(self) -> None:
        assert (
            compute_priority(score=10, importo=6_000_000, stato="GARA PUBBLICATA", days_to_deadline=None)
            == "P1"
        )

    def test_p1_by_imminent_deadline(self) -> None:
        assert (
            compute_priority(score=5, importo=None, stato="GARA PUBBLICATA", days_to_deadline=1) == "P1"
        )

    def test_tiers(self) -> None:
        assert compute_priority(score=55, importo=None, stato="x", days_to_deadline=None) == "P2"
        assert compute_priority(score=35, importo=None, stato="x", days_to_deadline=None) == "P3"
        assert compute_priority(score=10, importo=None, stato="x", days_to_deadline=None) == "P4"


class TestEndToEnd:
    def test_high_value_active_gara(self) -> None:
        now = datetime(2026, 4, 22, tzinfo=UTC)
        scad = now + timedelta(days=4)
        result = score_record(
            ScoringInput(
                importo=Decimal("8000000"),
                stato_procedurale="GARA PUBBLICATA",
                scadenza=scad,
                flag_ppp=True,
                flag_pnrr=True,
                tag_tecnico=("accordo quadro", "smart lighting"),
            ),
            now=now,
        )
        # 28 (imp band 5-10M) + 25 (gara) + 15 (4d deadline) + 8 (ppp) + 6 (pnrr) + 3 (accordo)
        assert result.score == 85
        assert result.priority == "P1"
