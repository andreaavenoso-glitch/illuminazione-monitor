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


def _mail_by_category(cat, descr, campi=None):
    from datetime import date

    from app.services.email_template import build_email

    return build_email(
        categoria=cat, ente="Comune di Prova", descrizione=descr, link="https://c.it/a", scadenza=None,
        visto_il=None, servizi=["illuminazione_pubblica"], provincia="Matera", campi=campi, referenti=[],
        pec=None, today=date(2026, 11, 23),
    )["corpo"]


def test_pre_gara_email_says_which_signal_and_the_main_data_of_the_act():
    campi = {
        "atto_estremi": {"valore": "Delibera di Giunta n. 115 del 02/09/2026"},
        "impegno_spesa_eur": {"valore": 24400.0},
        "incaricato": {"valore": "Verifica Tecnica S.r.l."},
        "cig": {"valore": "B1234567AB"},
    }
    body = _mail_by_category("pre_gara", "Delibera di Giunta con impegno di spesa per la manutenzione degli impianti", campi)
    assert "Di cosa si tratta: Delibera, Impegno di spesa, Manutenzione degli impianti" in body
    assert "Atto: Delibera di Giunta n. 115 del 02/09/2026" in body and "Impegno di spesa: € 24.400,00" in body
    assert "Incaricato: Verifica Tecnica S.r.l." in body
    assert "CIG" not in body and "scheda di sintesi" not in body  # short: the main information only


def test_manifestazione_and_gara_email_have_the_full_data_and_mention_the_summary_sheet():
    campi = {"cig": {"valore": "B1234567AB"}, "sopralluogo": {"valore": "Obbligatorio, da concordare"}}
    for cat in ("manifestazione_interesse", "gara"):
        body = _mail_by_category(cat, "Avviso per illuminazione pubblica", campi)
        assert "CIG: B1234567AB" in body and "Sopralluogo: Obbligatorio, da concordare" in body
        assert "In allegato la scheda di sintesi" in body and "Di cosa si tratta" not in body
