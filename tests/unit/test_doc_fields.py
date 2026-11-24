"""Dati estratti dalla documentazione di un avviso (regole, gratis), con la fonte di ogni dato."""
from __future__ import annotations

from datetime import date

from app.collectors.doc_fields import extract_fields

TODAY = date(2026, 11, 23)
AVVISO = (
    "Avviso pubblico ex art. 193 del D.Lgs. 36/2023 per la presentazione di proposte di finanza di progetto. "
    "CIG: 9876543210. Il canone massimo annuo e' pari a € 250.000,00 oltre IVA. Valore dell'investimento stimato "
    "euro 3.200.000,00. Il parco comprende 2.350 punti luce. La durata della concessione e' di 15 anni. "
    "Criterio: offerta economicamente piu' vantaggiosa. Finanziamento: PR Basilicata FESR 2021-2027. "
    "Le proposte devono pervenire entro le ore 12:00 del 20-01-2027. "
    "Responsabile unico del progetto: Arch. Francesco Chiarella, nominato con Delibera. Pubblicato il 19/11/2026."
)


def test_fields_are_extracted_with_their_source():
    f = extract_fields([("AVVISO.pdf", AVVISO)], TODAY)
    assert f["cig"]["valore"] == "9876543210" and f["cig"]["fonte"] == "AVVISO.pdf"
    assert f["scadenza"]["valore"] == "2027-01-20"
    assert f["importo_massimo_eur"]["valore"] == 3_200_000.0
    assert set(f["importi_citati_eur"]["valore"]) == {250_000.0, 3_200_000.0}
    assert f["durata"]["valore"] == "15 anni"
    assert f["punti_luce"]["valore"] == "2.350"
    assert "art. 193 / finanza di progetto" in f["procedura"]["valore"]
    assert f["criterio_aggiudicazione"]["valore"].lower().startswith("offerta economicamente")
    assert f["finanziamento"]["valore"].startswith("FESR") or "FESR" in f["finanziamento"]["valore"]
    assert f["rup"]["valore"] == "Francesco Chiarella"
    assert f["data_documento"]["valore"] == "2026-11-19"


def test_nothing_is_invented_when_the_text_has_no_data():
    assert extract_fields([("x", "Pagina senza dati utili")], TODAY) == {}


def test_first_document_wins_for_a_field():
    f = extract_fields([("a.pdf", "CIG: AAAAAAAAAA"), ("b.pdf", "CIG: BBBBBBBBBB")], TODAY)
    assert f["cig"]["valore"] == "AAAAAAAAAA" and f["cig"]["fonte"] == "a.pdf"


def test_fields_for_the_gate_sheet():
    from datetime import date

    from app.collectors.doc_fields import extract_fields

    text = (
        "Le offerte vanno presentate entro le ore 12:00 del 17/11/2026 via PEC a protocollo@pec.comune.x.it. "
        "Il sopralluogo è obbligatorio e va concordato con l'Ufficio Tecnico. "
        "Consumi pari a 170.000 kWh/anno. La spesa storica annua è di € 175.000,00 IVA inclusa."
    )
    f = extract_fields([("avviso.pdf", text)], date(2026, 11, 23))
    assert f["ora_scadenza"]["valore"] == "12:00"
    assert "sopralluogo" in f["sopralluogo"]["valore"].lower()
    assert f["consumi_mwh"]["valore"] == 170.0
    assert f["spesa_annua_eur"]["valore"] == 175000.0
    assert f["pec_invio"]["valore"] == "protocollo@pec.comune.x.it"


def test_the_yearly_fee_of_the_tender_is_not_the_historic_spend():
    from datetime import date

    from app.collectors.doc_fields import extract_fields

    t = ("Il canone annuo di riferimento da porre a base della successiva gara nello scenario integralmente privato è pari a "
         "€ 230.000,00, oltre IVA, comprensivo dell'energia elettrica.")
    f = extract_fields([("avviso.pdf", t)], date(2026, 11, 23))
    assert f["canone_annuo_eur"]["valore"] == 230000.0
    assert "spesa_annua_eur" not in f
    f2 = extract_fields([("a.pdf", "La spesa storica annua è di € 175.000,00 IVA inclusa.")], date(2026, 11, 23))
    assert f2["spesa_annua_eur"]["valore"] == 175000.0 and "canone_annuo_eur" not in f2
