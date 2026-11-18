"""IPA open-data CSV parsing for the per-region comuni import."""
from __future__ import annotations

from infra.scripts.import_ipa import parse_ipa_rows
from infra.scripts.seed_regions import parse_list

CSV = (
    "Codice_IPA;Denominazione_ente;Tipologia;Comune;Provincia;Regione;Sito_istituzionale;Link_Amministrazione_Trasparente\n"
    "c_a662;Comune di Bari;Comuni e loro Consorzi e Associazioni;Bari;BA;Puglia;www.comune.bari.it;https://trasparenza.comune.bari.it\n"
    "c_e506;Comune di Lecce;Comuni e loro Consorzi e Associazioni;Lecce;LE;Puglia;comune.lecce.it;\n"
    "x_1;ASL Bari;Aziende Sanitarie Locali;Bari;BA;Puglia;asl.bari.it;\n"
    "c_f205;Comune di Milano;Comuni e loro Consorzi e Associazioni;Milano;MI;Lombardia;comune.milano.it;https://t.milano.it\n"
)


def test_keeps_only_comuni_of_the_region() -> None:
    rows = parse_ipa_rows(CSV, "Puglia")
    assert [r["name"] for r in rows] == ["Comune di Bari", "Comune di Lecce"]


def test_urls_are_normalised_and_missing_ones_none() -> None:
    bari, lecce = parse_ipa_rows(CSV, "puglia")
    assert bari["trasparenza"] == "https://trasparenza.comune.bari.it"
    assert bari["sito"] == "https://www.comune.bari.it"
    assert lecce["trasparenza"] is None and lecce["sito"] == "https://comune.lecce.it"


def test_handles_bom_and_comma_delimiter() -> None:
    text = "﻿Denominazione_ente,Tipologia,Provincia,Regione,Link_Amministrazione_Trasparente\nComune di Foggia,Comuni,FG,Puglia,https://t.foggia.it\n"
    assert parse_ipa_rows(text, "Puglia")[0]["trasparenza"] == "https://t.foggia.it"


def test_parse_list() -> None:
    assert parse_list(" Lombardia, Puglia ,,") == ["Lombardia", "Puglia"]
    assert parse_list(None) == []
