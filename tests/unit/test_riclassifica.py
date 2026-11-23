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
        categoria_analisi=None, verifica_esito=None, verified_at=None, verifica_nota=None, cig=None,
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


TOLVE_PAGE = (
    "CIG: 79706368E6 BDNCP: https://dati.anticorruzione.it/superset/dashboard/dettaglio_cig/?cig=79706368E6 Atti "
    "DETERMINAZIONE n. 253 reg. gen. n. 528 del 2026 Unità organizzativa: AREA TECNICA Appalto di concessione del servizio di "
    "pubblica illuminazione, comprensivo della riqualificazione energetica. Liquidazione di spesa 7a-8a-9a-10a e 11a mensilità."
)


def test_old_cig_and_new_cig():
    from shared_models.relevance import old_cig

    for cig in ("79706368E6", "8123456789", "Z1234567AB"):
        assert old_cig(cig), cig
    for cig in ("B1234567AB", "A03B26CC31", "BB366E64FD", None, "", "123"):
        assert not old_cig(cig), cig


def test_a_gara_with_an_old_cig_and_no_deadline_is_over():
    from shared_models.relevance import SCADUTO, record_state

    assert record_state("gara", None, None, "https://c.it/x", None, TODAY, "79706368E6")[0] == SCADUTO
    assert record_state("gara", None, None, "https://c.it/x", None, TODAY, "B1234567AB")[0] == "da_verificare"
    # an open deadline always wins
    assert record_state("gara", date(2026, 12, 20), None, "https://c.it/x", "aperto", TODAY, "79706368E6")[0] == "aperto"


def test_contract_in_execution_is_recognised():
    from shared_models.riclassifica import contratto_in_corso

    assert "anteriore al 2024" in contratto_in_corso("testo", "79706368E6")
    assert "liquidazione" in contratto_in_corso(TOLVE_PAGE, "B1234567AB")
    assert contratto_in_corso("Avviso pubblico per proposte di finanza di progetto", "B1234567AB") is None
    assert contratto_in_corso(None, None) is None


def test_the_card_of_a_running_contract_is_closed_by_the_analysis():
    r = rec(descrizione="Appalto di concessione del servizio di pubblica illuminazione", atto_tipo="bando_gara", cig="79706368E6")
    assert categorize_record(r) == "gara"
    applica_analisi(r, [], {"cig": {"valore": "79706368E6", "fonte": "pagina"}}, "approfondita", TODAY, NOW, page_text=TOLVE_PAGE)
    assert r.verifica_esito == "chiuso" and "anteriore al 2024" in r.verifica_nota


def test_an_open_deadline_in_the_documents_beats_the_old_cig():
    r = rec(descrizione="Manifestazione di interesse illuminazione pubblica", cig="79706368E6")
    applica_analisi(r, [], {"cig": {"valore": "79706368E6", "fonte": "x"}, "scadenza": {"valore": "2026-12-20", "fonte": "avviso.pdf"}},
                    "approfondita", TODAY, NOW, page_text=TOLVE_PAGE)
    assert r.verifica_esito == "aperto"


def test_a_pre_gara_is_not_closed_for_mentioning_the_running_contract():
    r = rec(descrizione="Delibera di Giunta: atto di indirizzo per il nuovo servizio di illuminazione pubblica", cig="79706368E6")
    assert categorize_record(r) == "pre_gara"
    applica_analisi(r, [], {"cig": {"valore": "79706368E6", "fonte": "x"}}, "base", TODAY, NOW, page_text=TOLVE_PAGE)
    assert r.verifica_esito != "chiuso"


SCANZANO_VECCHIO = (
    "AVVISO PUBBLICO DI MANIFESTAZIONE DI INTERESSE (ai sensi dell'art. 193 del D.Lgs. 36/2023) Oggetto: Ammodernamento "
    "tecnologico, efficientamento energetico, messa a norma e gestione dell'impianto di pubblica illuminazione. "
    "Gli operatori possono presentare la propria proposta di project financing entro e non oltre 60 (sessanta) giorni "
    "dalla data di pubblicazione del presente avviso, in conformità all'art. 193. Determinazione n. 29 del 12/03/2026."
)


def test_a_relative_deadline_is_read_from_the_document():
    from app.collectors.doc_fields import extract_fields

    f = extract_fields([("avviso.pdf", SCANZANO_VECCHIO)], TODAY)
    assert f["termine_giorni"]["valore"] == {"giorni": 60, "lavorativi": False}
    assert "scadenza" not in f and f["data_documento"]["valore"] == "2026-03-12"


def test_appeals_and_clarification_terms_are_not_deadlines():
    from app.collectors.doc_fields import extract_fields

    t = ("Avviso per la presentazione delle offerte. Avverso il presente atto è ammesso ricorso al TAR entro 30 giorni dalla "
         "pubblicazione. Le richieste di chiarimenti vanno inviate entro 10 giorni dalla pubblicazione del bando.")
    assert "termine_giorni" not in extract_fields([("a.pdf", t)], TODAY)
    t2 = "Le offerte devono pervenire entro 15 giorni dalla ricezione della lettera di invito."
    assert "termine_giorni" not in extract_fields([("a.pdf", t2)], TODAY)  # counted from something else


def test_an_old_avviso_with_a_relative_deadline_is_closed():
    from app.collectors.doc_fields import extract_fields

    r = rec(descrizione="Avviso pubblico di manifestazione di interesse art. 193 illuminazione pubblica", atto_tipo="manifestazione_interesse")
    r.data_pubblicazione = None
    f = extract_fields([("avviso.pdf", SCANZANO_VECCHIO)], TODAY)
    applica_analisi(r, [("avviso.pdf", SCANZANO_VECCHIO)], f, "approfondita", TODAY, NOW)
    assert r.scadenza.date() == date(2026, 5, 11) and r.verifica_esito == "chiuso"
    assert "stimata 11/05/2026" in r.verifica_nota and "già passata" in r.verifica_nota


def test_a_recent_avviso_with_a_relative_deadline_is_estimated_but_still_to_verify():
    from shared_models.relevance import DA_VERIFICARE, record_state

    r = rec(descrizione="Avviso pubblico di manifestazione di interesse illuminazione pubblica", atto_tipo="manifestazione_interesse")
    r.data_pubblicazione = datetime(2026, 11, 10, tzinfo=UTC)
    f = {"termine_giorni": {"valore": {"giorni": 60, "lavorativi": False}, "fonte": "a.pdf"}}
    applica_analisi(r, [], f, "approfondita", TODAY, NOW)
    assert r.scadenza.date() == date(2027, 1, 9) and r.verifica_esito == "stimata" and "da confermare" in r.verifica_nota
    assert record_state("manifestazione_interesse", r.scadenza, None, "https://c.it/x", r.verifica_esito, TODAY)[0] == DA_VERIFICARE


def test_working_days_are_not_guessed():
    r = rec(descrizione="Manifestazione di interesse illuminazione pubblica", atto_tipo="manifestazione_interesse")
    r.data_pubblicazione = None
    f = {"termine_giorni": {"valore": {"giorni": 30, "lavorativi": True}, "fonte": "a.pdf"}}
    applica_analisi(r, [], f, "base", TODAY, NOW)
    assert r.scadenza is None and "lavorativi" in r.verifica_nota
