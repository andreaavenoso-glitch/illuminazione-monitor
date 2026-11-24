"""Casi reali dal CSV Puglia: rumore escluso e allocazione pre-gara/gara/manifestazione."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from shared_models.categories import GARA, MANIFESTAZIONE, PRE_GARA, categorize
from shared_models.relevance import act_signature, collapse_duplicates, mentions_date


@pytest.mark.parametrize(
    "text",
    [
        "Liquidazione fattura servizio illuminazione pubblica",
        "Impegno di spesa canone mese di ottobre pubblica illuminazione",
        "Aggiudicazione definitiva servizio illuminazione votiva",
        "Revoca procedura illuminazione pubblica",
        "Ordinanza modifica viabilita illuminazione",
        "Protocollo d'intesa ricarica veicoli elettrici",
        "Polizza assicurativa impianti",
    ],
)
def test_noise_is_excluded(text):
    assert categorize(stato_procedurale=None, text=text) is None


def test_anac_is_excluded():
    assert categorize(stato_procedurale=None, text="Bando illuminazione", ente="ANAC") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Bando di gara procedura aperta servizio di pubblica illuminazione", GARA),
        ("Avviso di manifestazione di interesse per servizio illuminazione pubblica", MANIFESTAZIONE),
        ("Indagine di mercato project financing illuminazione pubblica", MANIFESTAZIONE),
        ("Procedura negoziata lavori illuminazione pubblica lettera d'invito", GARA),
    ],
)
def test_allocation(text, expected):
    assert categorize(stato_procedurale=None, text=text) == expected


def test_wording_beats_claude_label():
    assert (
        categorize(
            stato_procedurale=None,
            text="Avviso esplorativo manifestazione di interesse illuminazione",
            atto_tipo="delibera_giunta",
        )
        == MANIFESTAZIONE
    )


def test_delibera_indirizzo_is_pregara():
    r = categorize(
        stato_procedurale=None,
        text="Delibera di indirizzo per riqualificazione impianti di pubblica illuminazione",
        atto_tipo="delibera_giunta",
    )
    assert r == PRE_GARA


def test_duplicates_collapse():
    a = {"ente": "Comune di Nardò", "t": "Determina N. 1 del 06/11/2026 - Gestione impianti illuminazione"}
    b = {"ente": "Comune di Nardò", "t": "Determina N. 1 del 06/11/2026 - Gestione impianti illuminazione"}
    out = collapse_duplicates([a, b], lambda r: act_signature(r["ente"], r["t"]), lambda r: len(r["t"]))
    assert len(out) == 1


def test_mentions_date():
    d = date(2026, 11, 20)
    assert mentions_date("pubblicato il 20/11/2026", d)
    assert not mentions_date("pubblicato il 06/11/2026", d)
    _ = datetime(2026, 1, 1, tzinfo=UTC)


def test_awarded_notice_is_noise():
    assert categorize(stato_procedurale=None, text="Avviso di appalto aggiudicato riqualificazione impianti illuminazione") is None
    assert categorize(stato_procedurale=None, text="Avviso di post-informazione lavori illuminazione pubblica") is None


def test_only_old_dates():
    from shared_models.relevance import dates_in_text, only_old_dates

    today = date(2026, 11, 21)
    page = "Avviso (44 KB - Pubblicato il 01/03/2023) verbale n. 6 (Pubblicato il 30 giugno 2023)"
    assert len(dates_in_text(page)) == 2
    assert only_old_dates(page, today)
    assert not only_old_dates(page + " scadenza 30/11/2026", today)
    assert not only_old_dates("nessuna data qui", today)


# --- Basilicata: falsi positivi in gara / manifestazione ---------------------------
from types import SimpleNamespace  # noqa: E402

from shared_models.categories import categorize_record  # noqa: E402
from shared_models.relevance import is_confirmed_open, url_year  # noqa: E402


def _rec(text, atto=None, servizio=None, stato="PRE-GARA", ente="Comune di X"):
    return SimpleNamespace(
        descrizione=text, tipologia_gara_procedura=None, stato_procedurale=stato,
        flag_pre_gara=None, atto_tipo=atto, ente=ente, servizio=servizio,
    )


@pytest.mark.parametrize(
    "text",
    [
        "Avviso manifestazione di interesse ad aderire alla costituenda comunita energetica di Sasso di Castalda",
        "Comunita energetica rinnovabile - Manifestazione interesse Customer",
        "Manifestazione di interesse Comunita Energetica Rinnovabile",
        "Fornitura energia elettrica pubblica illuminazione - Societa Enel Energia",
    ],
)
def test_cer_membership_and_supply_are_noise(text):
    assert categorize(stato_procedurale=None, text=text) is None


def test_cer_with_procurement_wording_is_kept():
    assert (
        categorize(
            stato_procedurale=None,
            text="Manifestazione di interesse per la realizzazione e gestione impianti comunita energetica",
        )
        == MANIFESTAZIONE
    )


def test_out_of_scope_record_is_dropped():
    r = _rec("AVVISO SOLLECITAZIONE DI PROPOSTE FINANZA DI PROGETTO INFRASTRUTTURE COMUNALI LAGO LAUDEMIO")
    assert categorize_record(r) is None
    assert categorize_record(_rec("DETERMINA Determinazione Nr.95 del 13/05/2025")) is None
    ok = _rec("Avviso esplorativo servizio manutenzione impianti di pubblica illuminazione")
    assert categorize_record(ok) == MANIFESTAZIONE


def test_gara_and_manifestazione_need_a_future_deadline():
    today = date(2026, 11, 22)
    assert not is_confirmed_open(GARA, None, datetime(2026, 11, 22, tzinfo=UTC), None, today)
    assert not is_confirmed_open(MANIFESTAZIONE, None, None, None, today)
    assert is_confirmed_open(GARA, datetime(2026, 12, 1, tzinfo=UTC), None, None, today)
    assert not is_confirmed_open(GARA, datetime(2026, 11, 1, tzinfo=UTC), None, None, today)


def test_pregara_without_deadline_but_old_link_is_dropped():
    today = date(2026, 11, 22)
    old = "https://ww2.gazzettaamministrativa.it/x/_ruoti/2018/0004_Documenti_1517561687453/a.pdf"
    assert url_year(old) == 2018
    assert not is_confirmed_open(PRE_GARA, None, datetime(2026, 11, 22, tzinfo=UTC), old, today)
    assert is_confirmed_open(PRE_GARA, None, datetime(2026, 11, 20, tzinfo=UTC), "https://x.it/avviso/1", today)


# --- Basilicata 2: gli avvisi pubblici per proposte PPP sono manifestazioni -----------
@pytest.mark.parametrize(
    "text",
    [
        "Avviso pubblico ex art. 193 del D.Lgs. 36/2023 per la presentazione di proposte alternative di finanza di "
        "progetto relative all'ammodernamento dell'impianto di pubblica illuminazione.",
        "AVVISO PUBBLICO - SOLLECITAZIONE DI PROPOSTE A INIZIATIVA PRIVATA illuminazione pubblica",
    ],
)
def test_open_call_for_ppp_proposals_is_manifestazione(text):
    assert categorize(stato_procedurale="PRE-GARA", text=text, atto_tipo="proposta_ppp") == MANIFESTAZIONE


def test_ppp_page_with_deadline_is_manifestazione_without_it_is_pregara():
    t = "Proposte per l'ammodernamento e la gestione dell'illuminazione pubblica"
    assert categorize(stato_procedurale="PRE-GARA", text=t, atto_tipo="proposta_ppp", has_deadline=True) == MANIFESTAZIONE
    assert categorize(stato_procedurale="PRE-GARA", text=t, atto_tipo="proposta_ppp") == PRE_GARA


def test_acts_dealing_with_a_received_proposal_stay_pregara():
    delibera = (
        "DELIBERA DI GIUNTA N. 96 - PROPOSTA DI FINANZA DI PROGETTO ART. 193. AFFIDAMENTO IN CONCESSIONE "
        "AMPLIAMENTO DELLA RETE DI PUBBLICA ILLUMINAZIONE"
    )
    assert categorize(stato_procedurale="PRE-GARA", text=delibera, atto_tipo="proposta_ppp", has_deadline=True) == PRE_GARA
    valut = "Valutazione delle proposte pervenute a seguito di avviso pubblico illuminazione pubblica"
    assert categorize(stato_procedurale="PRE-GARA", text=valut, atto_tipo="proposta_ppp") == PRE_GARA
    atto = "Atto di indirizzo per l'esternalizzazione del servizio di illuminazione pubblica"
    assert categorize(stato_procedurale="PRE-GARA", text=atto, atto_tipo="determina_a_contrarre") == PRE_GARA


# --- Stato unico: pre-gara larga ma datata, manifestazioni e gare strette ----------------
from shared_models.relevance import APERTO, DA_VERIFICARE, SCADUTO, record_state  # noqa: E402

T = date(2026, 11, 22)
FUT = datetime(2026, 12, 15, tzinfo=UTC)
PAST = datetime(2026, 11, 1, tzinfo=UTC)


def test_gara_and_manifestazione_need_the_document_to_confirm_the_deadline():
    assert record_state(GARA, FUT, None, None, None, T) == (DA_VERIFICARE, False)  # deadline only from the list
    assert record_state(GARA, FUT, None, None, "non_trovata", T) == (DA_VERIFICARE, False)
    assert record_state(GARA, FUT, None, None, "aperto", T) == (APERTO, False)
    assert record_state(MANIFESTAZIONE, None, None, None, "non_trovata", T) == (DA_VERIFICARE, False)
    assert record_state(MANIFESTAZIONE, PAST, None, None, "aperto", T) == (SCADUTO, False)
    assert record_state(GARA, FUT, None, None, "chiuso", T) == (SCADUTO, False)


def test_pregara_needs_a_known_date_but_tolerates_unreadable_documents():
    assert record_state(PRE_GARA, None, None, None, None, T) == (DA_VERIFICARE, False)
    assert record_state(PRE_GARA, None, None, None, "recente", T) == (APERTO, False)
    assert record_state(PRE_GARA, None, datetime(2026, 11, 1, tzinfo=UTC), None, "non_trovata", T) == (APERTO, True)
    assert record_state(PRE_GARA, None, datetime(2025, 1, 1, tzinfo=UTC), None, "non_trovata", T) == (SCADUTO, False)
    assert record_state(PRE_GARA, None, None, None, "chiuso", T) == (SCADUTO, False)
    assert record_state(PRE_GARA, FUT, None, None, None, T) == (APERTO, False)
    old = "https://x.it/_ruoti/2018/a.pdf"
    assert record_state(PRE_GARA, None, None, old, None, T) == (SCADUTO, False)


def test_service_act_without_stronger_wording_is_pregara():
    r = categorize(stato_procedurale=None, text="Servizi di gestione degli impianti di pubblica illuminazione")
    assert r == PRE_GARA
    assert categorize(stato_procedurale="GARA PUBBLICATA", text="lavori di appalto") == GARA
