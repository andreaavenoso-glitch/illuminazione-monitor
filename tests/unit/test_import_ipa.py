"""IPA open-data CSV parsing for the per-region comuni import."""
from __future__ import annotations

from infra.scripts.import_ipa import parse_ipa_rows, xlsx_to_text
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


def test_header_spelling_is_tolerant() -> None:
    text = "denominazione ente\ttipologia\tregione\tlink amministrazione trasparente\nComune di Lecce\tComuni\tPuglia\thttps://t.lecce.it\n"
    assert parse_ipa_rows(text, "Puglia")[0]["trasparenza"] == "https://t.lecce.it"


def test_xlsx_roundtrip(tmp_path) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Denominazione_ente", "Tipologia", "Regione", "Link_Amministrazione_Trasparente"])
    ws.append(["Comune di Taranto", "Comuni e loro Consorzi e Associazioni", "Puglia", "https://t.taranto.it"])
    ws.append(["Comune di Roma", "Comuni", "Lazio", None])
    path = tmp_path / "amm.xlsx"
    wb.save(path)
    rows = parse_ipa_rows(xlsx_to_text(str(path)), "Puglia")
    assert [r["name"] for r in rows] == ["Comune di Taranto"]
    assert rows[0]["trasparenza"] == "https://t.taranto.it"


def test_old_txt_release_columns() -> None:
    text = (
        "cod_amm\tdes_amm\tcomune\tprovincia\tregione\tsito_istituzionale\ttipologia_istat\n"
        "c_a662\tComune di Bari\tBari\tBA\tPuglia\twww.comune.bari.it\tComuni e loro Consorzi e Associazioni\n"
        "054\tAzienda Unita' Sanitaria Locale Umbria 1\tPerugia\tPG\tUmbria\thttps://www.uslumbria1.it\tAziende Sanitarie Locali\n"
    )
    rows = parse_ipa_rows(text, "Puglia")
    assert rows == [
        {"name": "Comune di Bari", "provincia": "BA", "pec": None, "sito": "https://www.comune.bari.it", "trasparenza": None}
    ]


def test_capture_samples_summary() -> None:
    from infra.scripts.capture_samples import slug, summarize

    reports = [
        {"ente": "A", "error": "reset"},
        {"ente": "B", "template": "halley", "links_source": "labels",
         "pages": [{"gate": "skip"}, {"gate": "compact"}]},
        {"ente": "C", "template": "design_italia", "links_source": "none_would_ask_claude", "pages": []},
    ]
    s = summarize(reports)
    assert s["counts"]["comuni"] == 3 and s["counts"]["unreachable"] == 1
    assert s["counts"]["comuni_with_a_gated_page"] == 1 and s["counts"]["comuni_with_no_extra_page"] == 1
    assert s["templates"] == {"halley": 1, "design_italia": 1} and s["errors"] == {"reset": 1}
    assert slug("Comune di Sant'Agata (FG)") == "comune-di-sant-agata-fg"


def test_only_comuni_and_unioni_by_default() -> None:
    from infra.scripts.import_ipa import is_comune_name

    text = (
        "Denominazione_ente\tTipologia\tRegione\tSito_istituzionale\n"
        "Comune di Bari\tComuni e loro Consorzi e Associazioni\tPuglia\twww.comune.bari.it\n"
        "Unione dei Comuni della Messapia\tComuni e loro Consorzi e Associazioni\tPuglia\twww.u.it\n"
        "Consorzio Tutela e Prevenzione Randagismo San Francesco\tComuni e loro Consorzi e Associazioni\tPuglia\twww.c.it\n"
        "C.E.A. Centro di Educazione Ambientale\tComuni e loro Consorzi e Associazioni\tPuglia\twww.cea.it\n"
    )
    assert [r["name"] for r in parse_ipa_rows(text, "Puglia")] == ["Comune di Bari", "Unione dei Comuni della Messapia"]
    assert len(parse_ipa_rows(text, "Puglia", only_comuni=False)) == 4
    assert is_comune_name("Comune di Diso") and not is_comune_name("Consorzio X")


def test_check_extraction_evaluation() -> None:
    from infra.scripts.check_extraction import CASES, SAMPLE_HTML, evaluate

    assert len(CASES) == 10 and SAMPLE_HTML.count("<li>") == 10
    ok_records = [
        {"title": "Avviso ... manutenzione degli impianti di pubblica illuminazione", "body": ""},
        {"title": "sollecitazione di proposte di finanza di progetto", "body": ""},
        {"title": "sistemi di videosorveglianza urbana", "body": ""},
        {"title": "colonnine di ricarica per veicoli elettrici", "body": ""},
        {"title": "efficientamento energetico degli edifici scolastici", "body": ""},
        {"title": "incarico di advisor tecnico-finanziario", "body": ""},
    ]
    assert all(ok for _, ok, _ in evaluate(ok_records))
    # a record that should have been left out is a failure; a missing one too
    bad = evaluate(ok_records[:-1] + [{"title": "rilascio della tessera elettorale", "body": ""}])
    failed = {label for label, ok, _ in bad if not ok}
    assert failed == {"incarico advisor per proposta PPP", "notizia elettorale"}


def test_pec_is_taken_from_the_ipa_mail_columns() -> None:
    text = (
        "cod_amm\tdes_amm\tcomune\tprovincia\tregione\tsito_istituzionale\ttipologia_istat\t"
        "mail1\ttipo_mail1\tmail2\ttipo_mail2\n"
        "c_a662\tComune di Bari\tBari\tBA\tPuglia\twww.comune.bari.it\tComuni e loro Consorzi e Associazioni\t"
        "info@comune.bari.it\tAltro\tProtocollo@PEC.comune.bari.it\tPec\n"
    )
    assert parse_ipa_rows(text, "Puglia")[0]["pec"] == "protocollo@pec.comune.bari.it"


def test_cleanup_keeps_ipa_comuni_and_flags_the_rest():
    from infra.scripts.pulisci_regione import split_valid_old

    ents = [
        ("1", "Comune di Arluno", "comune"),
        ("2", "Arluno", "comune"),                 # seed leftover with a plain name
        ("3", "Romano di Lombardia", "comune"),    # seed leftover
        ("4", "Regione Lombardia", "regione"),     # not a comune: left alone
        ("5", "Comune di Milano", None),
    ]
    valid, old = split_valid_old(ents, {"Comune di Arluno", "Comune di Milano"})
    assert [e[1] for e in valid] == ["Comune di Arluno", "Comune di Milano"]
    assert [e[1] for e in old] == ["Arluno", "Romano di Lombardia"]
