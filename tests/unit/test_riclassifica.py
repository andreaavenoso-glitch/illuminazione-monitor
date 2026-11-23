from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.tasks.analyze_record import applica_analisi
from shared_models.categories import categorize_record
from shared_models.riclassifica import is_higher, verdetto_da_documenti

TODAY = date(2026, 11, 23)
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)

AVVISO_PPP = (
    "CITTA' DI SCANZANO JONICO Provincia di Matera SETTORE TECNICO Palazzo Baronale Allegato A "
    "Avviso pubblico per la presentazione di proposte di finanza di progetto finalizzato a: Ammodernamento tecnologico, "
    "efficientamento energetico e gestione dell'impianto di pubblica illuminazione comunale. 1. Premesse " + "testo " * 20
    + " Con determinazione n. 216 è stata disposta la revoca in autotutela della determinazione n. 29/2026 e del relativo avviso. "
    "Le proposte devono pervenire entro le ore 12:00 del 20-01-2027."
)


def rec(**kw):
    base = dict(
        descrizione="Allegati tecnici e avviso", tipologia_gara_procedura=None, stato_procedurale="Pubblicato",
        flag_pre_gara=None, atto_tipo=None, ente="Comune di Scanzano Jonico", scadenza=None, servizio="illuminazione_pubblica",
        categoria_analisi=None, verifica_esito=None, verified_at=None, verifica_nota=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_heading_of_an_open_call_is_a_manifestazione_even_if_the_whole_text_mentions_a_revocation():
    v = verdetto_da_documenti([("avviso.pdf", AVVISO_PPP)])
    assert v.categoria == "manifestazione_interesse" and v.fonte == "avviso.pdf" and not v.chiuso


def test_heading_of_a_tender_is_a_gara_and_wins_over_a_call():
    gara = "Comune di X Bando di gara a procedura aperta per l'affidamento in concessione del servizio di illuminazione pubblica " + "testo " * 30
    v = verdetto_da_documenti([("avviso.pdf", AVVISO_PPP), ("bando.pdf", gara)])
    assert v.categoria == "gara" and v.fonte == "bando.pdf"


def test_award_and_revocation_headings_close_the_notice():
    v = verdetto_da_documenti([("esito.pdf", "Comune di X Avviso di aggiudicazione del servizio di illuminazione pubblica " + "testo " * 30)])
    assert v.chiuso and v.categoria is None
    v = verdetto_da_documenti([("det.pdf", "Comune di X Revoca in autotutela dell'avviso pubblico per l'illuminazione pubblica " + "testo " * 30)])
    assert v.chiuso


def test_short_or_generic_documents_prove_nothing():
    assert verdetto_da_documenti([("modulo.pdf", "Modulo di domanda " * 3), ("x.pdf", "")]).categoria is None
    assert verdetto_da_documenti([]).categoria is None


def test_reclassification_only_moves_up():
    assert is_higher("manifestazione_interesse", "pre_gara") and is_higher("gara", "manifestazione_interesse")
    assert not is_higher("manifestazione_interesse", "gara") and not is_higher(None, "pre_gara")
    assert is_higher("gara", None)  # was noise by title, the documents say it is a tender


def test_forced_category_beats_the_title():
    r = rec(descrizione="Allegati tecnici e avviso", categoria_analisi="gara")
    assert categorize_record(r) == "gara"
    assert categorize_record(rec()) == "pre_gara"


def test_analysis_moves_a_pre_gara_to_its_box_and_writes_the_deadline_from_the_document():
    r = rec()
    assert categorize_record(r) == "pre_gara"
    notes = applica_analisi(r, [("avviso.pdf", AVVISO_PPP)],
                            {"scadenza": {"valore": "2027-01-20", "fonte": "avviso.pdf"}, "ora_scadenza": {"valore": "12:00"}},
                            "approfondita", TODAY, NOW)
    assert categorize_record(r) == "manifestazione_interesse"
    assert r.scadenza == datetime(2027, 1, 20, 12, 0, tzinfo=UTC) and r.verifica_esito == "aperto"
    assert "20/01/2027 ore 12:00" in r.verifica_nota and any("riclassificato in manifestazione" in n for n in notes)


def test_a_past_deadline_found_in_the_documents_removes_the_noise():
    r = rec(descrizione="Avviso pubblico manifestazione di interesse illuminazione pubblica")
    applica_analisi(r, [], {"scadenza": {"valore": "2026-09-30", "fonte": "avviso.pdf"}}, "base", TODAY, NOW)
    assert r.verifica_esito == "chiuso" and "già passata" in r.verifica_nota


def test_base_analysis_keeps_the_listing_deadline_and_says_so_deep_one_aligns_it():
    existing = datetime(2026, 12, 5, 12, 0, tzinfo=UTC)
    r = rec(descrizione="Manifestazione di interesse illuminazione pubblica", scadenza=existing)
    applica_analisi(r, [], {"scadenza": {"valore": "2026-12-20", "fonte": "avviso.pdf"}}, "base", TODAY, NOW)
    assert r.scadenza == existing and "Approfondisci" in r.verifica_nota and r.verifica_esito == "aperto"
    applica_analisi(r, [], {"scadenza": {"valore": "2026-12-20", "fonte": "avviso.pdf"}}, "approfondita", TODAY, NOW)
    assert r.scadenza.date() == date(2026, 12, 20)


def test_an_outcome_found_by_the_analysis_closes_the_notice():
    r = rec()
    applica_analisi(r, [("esito.pdf", "Comune di X Avviso di aggiudicazione del servizio di illuminazione pubblica " + "testo " * 30)],
                    {}, "approfondita", TODAY, NOW)
    assert r.verifica_esito == "chiuso" and "aggiudicazione" in r.verifica_nota


def test_no_deadline_in_a_call_leaves_it_to_verify_with_a_note():
    r = rec(descrizione="Manifestazione di interesse illuminazione pubblica")
    applica_analisi(r, [], {}, "approfondita", TODAY, NOW)
    assert r.scadenza is None and "non trovata" in r.verifica_nota


def test_the_title_block_stops_at_the_premises():
    from shared_models.riclassifica import title_block

    t = "Comune di X Avviso pubblico per la presentazione di proposte di finanza di progetto. 1. Premesse La revoca in autotutela dell'avviso"
    assert "revoca" not in title_block(t).lower() and title_block(t).endswith("finanza di progetto.")
    assert "Considerato" not in title_block("Comune di X Avviso pubblico esplorativo per illuminazione pubblica Considerato che il comune ha deciso")
    assert title_block(None) == ""
