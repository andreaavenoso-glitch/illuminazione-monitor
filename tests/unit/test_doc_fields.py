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
