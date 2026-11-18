"""Regional structure: region names, record categories, routing, digest, IPA import."""
from __future__ import annotations

from datetime import date

import pytest
from app.digest import DigestItem, build_digest, parse_recipients
from shared_models.categories import GARA, MANIFESTAZIONE, PRE_GARA, categorize, mentions_lighting
from shared_models.regions import REGIONS, infer_region, normalize_region, region_from_nuts


class TestNormalizeRegion:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Lombardia", "Lombardia"),
            ("  lombardia ", "Lombardia"),
            ("Friuli-VG", "Friuli-Venezia Giulia"),
            ("Emilia Romagna", "Emilia-Romagna"),
            ("Trentino", "Trentino-Alto Adige"),
            ("Valle d'Aosta", "Valle d'Aosta"),
            ("Regione Siciliana", "Sicilia"),
        ],
    )
    def test_spellings(self, raw: str, expected: str) -> None:
        assert normalize_region(raw) == expected

    def test_unknown_and_empty(self) -> None:
        assert normalize_region("Atlantide") is None
        assert normalize_region("") is None
        assert normalize_region(None) is None

    def test_twenty_regions(self) -> None:
        assert len(REGIONS) == 20 == len(set(REGIONS))


class TestNuts:
    def test_nuts2_and_deeper_codes(self) -> None:
        assert region_from_nuts("ITF4") == "Puglia"
        assert region_from_nuts("itc4c") == "Lombardia"  # NUTS-3 code: first 4 chars
        assert region_from_nuts("ITH1") == "Trentino-Alto Adige"
        assert region_from_nuts("DE21") is None


class TestInferRegion:
    def test_explicit_region_wins(self) -> None:
        assert infer_region(regione="Puglia", nuts="ITC4") == "Puglia"

    def test_nuts_when_no_region(self) -> None:
        assert infer_region(nuts="ITF4") == "Puglia"

    def test_known_entity(self) -> None:
        assert infer_region(ente="Comune di Bari", entity_regions={"comune di bari": "Puglia"}) == "Puglia"

    def test_region_named_in_entity_text(self) -> None:
        assert infer_region(ente="Regione Lombardia - Direzione Generale") == "Lombardia"

    def test_none_rather_than_guess(self) -> None:
        assert infer_region(ente="Acme SpA") is None


class TestCategorize:
    def test_manifestazione_beats_stato(self) -> None:
        assert categorize(stato_procedurale="PRE-GARA", text="Avviso di manifestazione di interesse per la pubblica illuminazione") == MANIFESTAZIONE

    def test_pre_gara_by_stato_flag_or_keyword(self) -> None:
        assert categorize(stato_procedurale="PRE-GARA", text="x") == PRE_GARA
        assert categorize(stato_procedurale="GARA PUBBLICATA", text="x", flag_pre_gara="Yes") == PRE_GARA
        assert categorize(stato_procedurale="GARA PUBBLICATA", text="Proposta di project financing per i punti luce") == PRE_GARA
        assert categorize(stato_procedurale="GARA PUBBLICATA", text="avviso di preinformazione servizio luce") == PRE_GARA

    def test_gara_default_and_rettifica(self) -> None:
        assert categorize(stato_procedurale="GARA PUBBLICATA", text="Gara per illuminazione") == GARA
        assert categorize(stato_procedurale="RETTIFICA-PROROGA-CHIARIMENTI", text="proroga termini") == GARA

    def test_esiti_are_excluded(self) -> None:
        assert categorize(stato_procedurale="ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA", text="aggiudicazione") is None

    def test_keywords_match_whole_words(self) -> None:
        # "ppp" must not fire inside another word
        assert categorize(stato_procedurale="GARA PUBBLICATA", text="lavori di appppalto") == GARA

    def test_lighting_keywords(self) -> None:
        assert mentions_lighting("Servizio di illuminazione pubblica")
        assert not mentions_lighting("Fornitura di cancelleria")


class TestDigest:
    def _items(self) -> list[DigestItem]:
        return [
            DigestItem(PRE_GARA, "Comune di Bari", "Preinformazione servizio luce", "https://x/1"),
            DigestItem(GARA, "Comune di Lecce", "Gara illuminazione", "https://x/2",
                       scadenza=date(2026, 12, 31), importo=1500000),
        ]

    def test_groups_sections_and_omits_empty(self) -> None:
        subject, text, html = build_digest("Puglia", self._items(), web_url="http://w")
        assert "[Puglia] 2 novita" in subject
        assert "PRE-GARE" in text and "GARE PUBBLICATE" in text
        assert "MANIFESTAZIONI" not in text
        assert "31/12/2026" in text and "1.500.000 EUR" in text
        assert "http://w/regions/Puglia" in text and "<h3>" in html

    def test_html_is_escaped(self) -> None:
        item = DigestItem(GARA, "A&B <srl>", "<script>x</script>", "https://x/?a=1&b=2")
        _, _, html = build_digest("Lazio", [item], web_url="http://w")
        assert "<script>" not in html and "&lt;srl&gt;" in html

    def test_parse_recipients(self) -> None:
        assert parse_recipients("a@x.it; b@y.it, a@x.it , nope") == ["a@x.it", "b@y.it"]
        assert parse_recipients(None) == []


class TestSelectSample:
    def _items(self):
        from types import SimpleNamespace

        return [SimpleNamespace(n=i, last_scan_at=None if i < 3 else "x") for i in range(8)]

    def test_no_limit_returns_all(self) -> None:
        from app.tasks.collect_watchlist import select_sample

        items = self._items()
        assert select_sample(items, None) == items
        assert select_sample(items, 50) == items

    def test_never_scanned_come_first(self) -> None:
        import random

        from app.tasks.collect_watchlist import select_sample

        picked = select_sample(self._items(), 5, random.Random(1))
        assert len(picked) == 5
        assert {i.n for i in picked[:3]} == {0, 1, 2}


class TestRealWorldWordings:
    """Titles modelled on real notices found on the web (comuni's albi,
    qualenergia listings): they must be in the lighting perimeter and land in
    the right category."""

    @pytest.mark.parametrize(
        "text",
        [
            "Manutenzione impianti di illuminazione pubblica a Cernusco sul Naviglio",
            "Sostituzione corpi illuminanti per impianto illuminazione pubblica",
            "Fornitura moduli retrofit a led per illuminazione pubblica",
            "Gestione ed efficientamento energetico impianti di illuminazione pubblica",
            "Conduzione e manutenzione pubblica illuminazione",
        ],
    )
    def test_maintenance_and_replacement_are_in_perimeter(self, text: str) -> None:
        from parsing_rules.perimeter import is_in_lighting_perimeter

        assert is_in_lighting_perimeter(text)

    def test_unrelated_text_is_not(self) -> None:
        from parsing_rules.perimeter import is_in_lighting_perimeter

        assert not is_in_lighting_perimeter("Fornitura di cancelleria per gli uffici comunali")

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Avviso di manifestazione di interesse con richiesta di preventivo per la manutenzione dell'impianto", MANIFESTAZIONE),
            ("Indagine di mercato per individuare operatori da invitare alla procedura negoziata", MANIFESTAZIONE),
            ("Avviso per la sollecitazione di proposte di finanza di progetto", PRE_GARA),
            ("Dichiarazione di pubblico interesse della proposta di project financing", PRE_GARA),
            ("Incarico di advisor tecnico-finanziario per la valutazione della proposta", PRE_GARA),
            ("Affidamento del servizio di verifica del PFTE", PRE_GARA),
            ("Affidamento incarico per la redazione del PRIC e censimento degli impianti", PRE_GARA),
        ],
    )
    def test_categories_from_wording(self, text: str, expected: str) -> None:
        assert categorize(stato_procedurale="GARA PUBBLICATA", text=text) == expected

    def test_claude_label_beats_wording(self) -> None:
        # The text alone would read as a tender; the model's label wins.
        assert categorize(stato_procedurale="PRE-GARA", text="Illuminazione pubblica", atto_tipo="manifestazione_interesse") == MANIFESTAZIONE
        assert categorize(stato_procedurale="PRE-GARA", text="Illuminazione pubblica", atto_tipo="incarico_ppp") == PRE_GARA
        assert categorize(stato_procedurale="PRE-GARA", text="x", atto_tipo="sconosciuto") == PRE_GARA

    def test_esito_stays_excluded_even_with_label(self) -> None:
        assert categorize(stato_procedurale="ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA", text="x", atto_tipo="incarico_ppp") is None

    def test_invented_term_was_removed(self) -> None:
        from shared_models.categories import PRE_GARA_KEYWORDS

        assert "piccs" not in PRE_GARA_KEYWORDS
