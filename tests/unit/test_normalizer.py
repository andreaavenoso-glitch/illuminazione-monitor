from datetime import UTC, datetime
from decimal import Decimal

from app.domain.normalization import NormalizerInput, derive_flags, normalize


class TestDeriveFlags:
    def test_ppp_concessione(self) -> None:
        flags = derive_flags("Concessione PPP project financing illuminazione")
        assert flags["flag_ppp_doppio_oggetto"] == "Yes"
        assert flags["flag_concessione_ambito"] == "Yes"

    def test_in_house(self) -> None:
        flags = derive_flags("Affidamento in house all'azienda municipalizzata")
        assert flags["flag_in_house_ambito"] == "Yes"

    def test_om(self) -> None:
        flags = derive_flags("Servizio di manutenzione e global service")
        assert flags["flag_om"] == "Yes"

    def test_pre_gara(self) -> None:
        flags = derive_flags("Determina a contrarre per manifestazione di interesse")
        assert flags["flag_pre_gara"] == "Yes"

    def test_no_matches(self) -> None:
        flags = derive_flags("Generic tender text without special patterns")
        assert all(v == "No" for v in flags.values())


class TestNormalize:
    def test_in_scope_full_record(self) -> None:
        payload = NormalizerInput(
            raw_title="Relamping LED illuminazione pubblica Comune di Prato",
            raw_body="Accordo quadro illuminazione pubblica con telegestione",
            raw_url="https://example.test/bando/1",
            raw_date=datetime(2026, 4, 15, tzinfo=UTC),
            extracted={
                "ente": "Comune di Prato",
                "cig": "ABCDEFGH12",
                "importo": "1.250.000,00",
                "scadenza": "15/05/2026",
                "procedura": "aperta",
                "regione": "Toscana",
            },
            source_priority_rank=2,
        )
        result = normalize(payload)
        assert result is not None
        assert result.ente == "Comune di Prato"
        assert result.cig == "ABCDEFGH12"
        assert result.importo == Decimal("1250000.00")
        assert result.scadenza is not None and result.scadenza.month == 5
        assert "LED" in result.tag_tecnico
        assert "telegestione" in result.tag_tecnico
        assert "accordo quadro" in result.tag_tecnico
        assert result.validation_level == "L3"
        assert result.reliability_index == "Alta"
        assert result.is_weak_evidence is False
        assert result.macrosettore == "Illuminazione pubblica"

    def test_out_of_perimeter_returns_none(self) -> None:
        payload = NormalizerInput(
            raw_title="Servizio di facility management edifici scolastici",
            raw_body="Manutenzione impianti elettrici generici",
            raw_url="https://example.test/bando/2",
        )
        assert normalize(payload) is None

    def test_weak_evidence_no_identifiers(self) -> None:
        payload = NormalizerInput(
            raw_title="Illuminazione pubblica - informativa",
            raw_body="smart lighting",
            raw_url="https://example.test/news",
            extracted={"ente": "Comune di X"},
            source_priority_rank=6,
        )
        result = normalize(payload)
        assert result is not None
        assert result.is_weak_evidence is True
        assert result.reliability_index == "Bassa"

    def test_invalid_cig_is_dropped(self) -> None:
        payload = NormalizerInput(
            raw_title="Relamping LED illuminazione pubblica",
            raw_body=None,
            raw_url="https://example.test/bando/3",
            extracted={"ente": "Comune di Y", "cig": "not-a-cig"},
            source_priority_rank=2,
        )
        result = normalize(payload)
        assert result is not None
        assert result.cig is None

    def test_reliability_tiers(self) -> None:
        base = dict(
            raw_title="Accordo quadro illuminazione pubblica",
            raw_body=None,
            raw_url="https://example.test/x",
            extracted={"ente": "Comune Z"},
        )
        assert normalize(NormalizerInput(**base, source_priority_rank=1)).reliability_index == "Alta"
        assert normalize(NormalizerInput(**base, source_priority_rank=4)).reliability_index == "Media"
        assert normalize(NormalizerInput(**base, source_priority_rank=7)).reliability_index == "Bassa"

    def test_ppp_flag_from_procedura(self) -> None:
        payload = NormalizerInput(
            raw_title="Gara illuminazione pubblica LED",
            raw_body=None,
            raw_url="https://example.test/bando/4",
            extracted={
                "ente": "Comune W",
                "procedura": "Concessione con project financing",
                "cig": "ABCDEFGH12",
            },
            source_priority_rank=2,
        )
        result = normalize(payload)
        assert result is not None
        assert result.flag_ppp_doppio_oggetto == "Yes"
        assert result.flag_concessione_ambito == "Yes"
