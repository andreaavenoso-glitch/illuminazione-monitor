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
