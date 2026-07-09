"""Unit tests for the watchlist Albo Pretorio scan's pure record-building logic."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.collectors.albo_pretorio_llm import build_raw_record_kwargs, find_bandi_link


class TestBuildRawRecordKwargs:
    def test_uses_provided_url_when_present(self) -> None:
        now = datetime(2026, 7, 6, tzinfo=UTC)
        kwargs = build_raw_record_kwargs(
            url_albo="https://comune.test/albo",
            source_id=None,
            entity_id=None,
            record={
                "title": "Manifestazione di interesse illuminazione pubblica",
                "body": "Testo atto",
                "url": "https://comune.test/albo/atto/123",
                "date": "2026-07-01",
                "atto_tipo": "manifestazione_interesse",
                "ente": "Comune di Test",
                "scadenza": "2026-08-01",
            },
            now=now,
        )
        assert kwargs["raw_url"] == "https://comune.test/albo/atto/123"
        assert kwargs["raw_title"] == "Manifestazione di interesse illuminazione pubblica"
        assert kwargs["extracted_json"]["atto_tipo"] == "manifestazione_interesse"
        assert kwargs["extracted_json"]["perimeter_prevalidated"] is True
        assert kwargs["raw_date"] == datetime(2026, 7, 1, tzinfo=UTC)

    def test_disambiguates_url_when_missing(self) -> None:
        now = datetime(2026, 7, 6, tzinfo=UTC)
        kwargs_a = build_raw_record_kwargs(
            url_albo="https://comune.test/albo",
            source_id=None,
            entity_id=None,
            record={"title": "Atto A", "body": "x", "atto_tipo": "determina_a_contrarre"},
            now=now,
        )
        kwargs_b = build_raw_record_kwargs(
            url_albo="https://comune.test/albo",
            source_id=None,
            entity_id=None,
            record={"title": "Atto B", "body": "x", "atto_tipo": "determina_a_contrarre"},
            now=now,
        )
        # Two acts without their own URL on the same page must not collapse
        # into the same raw_url (the Consip/SmartLLM dedup-collision bug).
        assert kwargs_a["raw_url"] != kwargs_b["raw_url"]
        assert kwargs_a["checksum"] != kwargs_b["checksum"]

    def test_carries_entity_and_source_ids(self) -> None:
        now = datetime(2026, 7, 6, tzinfo=UTC)
        entity_id = uuid4()
        source_id = uuid4()
        kwargs = build_raw_record_kwargs(
            url_albo="https://comune.test/albo",
            source_id=source_id,
            entity_id=entity_id,
            record={"title": "Atto", "body": "x", "atto_tipo": "indagine_mercato"},
            now=now,
        )
        assert kwargs["entity_id"] == entity_id
        assert kwargs["source_id"] == source_id

    def test_falls_back_to_now_when_date_unparseable(self) -> None:
        now = datetime(2026, 7, 6, tzinfo=UTC)
        kwargs = build_raw_record_kwargs(
            url_albo="https://comune.test/albo",
            source_id=None,
            entity_id=None,
            record={"title": "Atto", "body": "x", "atto_tipo": "avviso_preinformazione", "date": "not-a-date"},
            now=now,
        )
        assert kwargs["raw_date"] == now


class TestFindBandiLink:
    def test_finds_exact_mandated_label(self) -> None:
        html = """
        <nav>
          <a href="/amministrazione-trasparente/">Amministrazione Trasparente</a>
          <a href="/amministrazione-trasparente/bandi-di-gara-e-contratti/">Bandi di gara e contratti</a>
          <a href="/amministrazione-trasparente/personale/">Personale</a>
        </nav>
        """
        result = find_bandi_link(html, base_url="https://comune.test/")
        assert result == "https://comune.test/amministrazione-trasparente/bandi-di-gara-e-contratti/"

    def test_resolves_relative_href_against_base_url(self) -> None:
        html = '<a href="bandi-gara-contratti">Bandi gara e contratti</a>'
        result = find_bandi_link(html, base_url="https://comune.test/trasparenza/")
        assert result == "https://comune.test/trasparenza/bandi-gara-contratti"

    def test_returns_none_when_no_match(self) -> None:
        html = """
        <nav>
          <a href="/organizzazione/">Organizzazione</a>
          <a href="/personale/">Personale</a>
        </nav>
        """
        assert find_bandi_link(html, base_url="https://comune.test/") is None

    def test_ignores_fragment_and_javascript_hrefs(self) -> None:
        html = """
        <a href="#">Bandi di gara e contratti</a>
        <a href="javascript:void(0)">Bandi di gara</a>
        <a href="/vero-link/">Bandi di gara e contratti</a>
        """
        result = find_bandi_link(html, base_url="https://comune.test/")
        assert result == "https://comune.test/vero-link/"
