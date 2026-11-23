import io
from datetime import date

from app.services.slide_deck import build_deck, deck_filename
from pptx import Presentation

TODAY = date(2026, 11, 23)


def _texts(data: bytes) -> list[str]:
    prs = Presentation(io.BytesIO(data))
    out: list[str] = []
    for slide in prs.slides:
        for sh in slide.shapes:
            if sh.has_text_frame:
                out.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                out += [c.text for row in sh.table.rows for c in row.cells]
    return out


FULL = dict(
    categoria="manifestazione_interesse", ente="Comune di Baranzate", provincia="Milano",
    descrizione="Avviso per manifestazione di interesse sul servizio di illuminazione pubblica",
    link="https://c.it/avviso", scadenza="2026-12-13", visto_il="2026-11-02", servizi=["illuminazione_pubblica"],
    scadenza_nota="letta in avviso.pdf",
    campi={"cig": {"valore": "B1234567AB", "fonte": "avviso.pdf"}, "importo_massimo_eur": {"valore": 480000.0, "fonte": "avviso.pdf"},
           "scadenza": {"valore": "2026-12-13", "fonte": "avviso.pdf"}},
    documenti=[{"nome": "avviso.pdf", "url": "https://c.it/avviso.pdf"}],
    referenti=[{"ruolo": "sindaco", "nome": "Giovanni Di Liberto", "stato": "verificato"},
               {"ruolo": "assessore", "nome": "Claudia Lesmo", "stato": "da_confermare"}],
    pec="protocollo@pec.c.it", today=TODAY,
)


def test_deck_has_the_six_standard_slides_with_the_known_data():
    data = build_deck(FULL)
    assert len(Presentation(io.BytesIO(data)).slides) == 6
    text = " | ".join(_texts(data))
    for expected in ("Comune di Baranzate", "B1234567AB", "€ 480.000,00", "13/12/2026", "tra 20 giorni",
                     "Giovanni Di Liberto", "da confermare", "protocollo@pec.c.it", "avviso.pdf"):
        assert expected in text


def test_unknown_values_are_marked_not_invented():
    data = build_deck(dict(categoria="pre_gara", ente="Comune X", descrizione=None, link="https://c.it", today=TODAY))
    text = " | ".join(_texts(data))
    assert "non indicato" in text and "non individuato" in text and "non trovata" in text
    assert "Nessun dato estratto" in text


def test_expired_deadline_is_flagged():
    text = " | ".join(_texts(build_deck({**FULL, "scadenza": "2026-11-01"})))
    assert "SCADUTA" in text


def test_missing_template_file_falls_back_to_the_default_design():
    assert len(Presentation(io.BytesIO(build_deck(FULL, template="/non/esiste.pptx"))).slides) == 6


def test_filename_is_safe():
    assert deck_filename("Comune di Cingia De' Botti", TODAY) == "scheda_Comune_di_Cingia_De__Botti_20261123.pptx"
