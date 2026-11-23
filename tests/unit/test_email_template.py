"""Mail standard con gli elementi dell'avviso."""
from __future__ import annotations

from datetime import date, datetime

from app.services.email_template import build_email

TODAY = date(2026, 11, 23)


def _mail(**kw):
    base = dict(
        categoria="manifestazione_interesse", ente="Comune di Scanzano Jonico",
        descrizione="Avviso pubblico ex art. 193 per proposte di finanza di progetto sull'illuminazione pubblica",
        link="https://c.it/avviso.pdf", scadenza=datetime(2027, 1, 20), visto_il=datetime(2026, 11, 22),
        servizi=["illuminazione_pubblica", "relamping_edifici"], provincia="MT", campi=None, referenti=[], pec=None,
        today=TODAY,
    )
    base.update(kw)
    return build_email(**base)


def test_subject_and_main_elements():
    m = _mail()
    assert m["oggetto"].startswith("[Manifestazione di interesse] Comune di Scanzano Jonico – Avviso pubblico")
    assert m["oggetto"].endswith("scadenza 20/01/2027")
    b = m["corpo"]
    assert "Tipo: Manifestazione di interesse" in b and "Ente: Comune di Scanzano Jonico (MT)" in b
    assert "Servizi: Illuminazione pubblica, Edifici pubblici e scuole" in b
    assert "Scadenza: 20/01/2027 (tra 58 giorni)" in b and "Documento: https://c.it/avviso.pdf" in b
    assert "Individuato il: 22/11/2026" in b and "Prossimo passo proposto: Valutare la presentazione" in b


def test_unknown_values_are_not_invented():
    b = _mail(scadenza=None)["corpo"]
    assert "Scadenza: non indicata (da verificare sul documento)" in b
    assert "Dati dalla documentazione" not in b and "Referenti del comune" not in b


def test_documentation_data_and_referenti_are_listed():
    campi = {
        "cig": {"valore": "9876543210"}, "importo_massimo_eur": {"valore": 3200000.0},
        "durata": {"valore": "15 anni"}, "procedura": {"valore": ["art. 193 / finanza di progetto"]},
        "rup": {"valore": "Francesco Chiarella"},
    }
    people = [
        {"ruolo": "sindaco", "nome": "Mario Rossi", "qualifica": "Sindaco", "email": "s@c.it", "telefono": None, "stato": "verificato"},
        {"ruolo": "assessore", "nome": "Giulia Bianchi", "qualifica": None, "email": None, "telefono": "0835 1", "stato": "da_confermare"},
    ]
    b = _mail(campi=campi, referenti=people, pec="protocollo@pec.c.it")["corpo"]
    assert "- Importo massimo: € 3.200.000,00" in b and "- CIG: 9876543210" in b and "- RUP: Francesco Chiarella" in b
    assert "- Sindaco: Mario Rossi (Sindaco) – s@c.it" in b
    assert "- Assessore ai Lavori pubblici: Giulia Bianchi – 0835 1 [da confermare]" in b
    assert "- PEC dell'ente: protocollo@pec.c.it" in b and "vanno verificati prima di un contatto" in b


def test_each_category_has_its_next_step():
    assert "prima della pubblicazione" in _mail(categoria="pre_gara")["corpo"]
    assert "requisiti" in _mail(categoria="gara")["corpo"]
