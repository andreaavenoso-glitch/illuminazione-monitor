"""Estrazione senza Claude: avvisi dagli elenchi, referenti, modalita' e ripiego automatico."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from app import claude_state
from app.collectors.page_gate import Candidate
from app.collectors.rules_extract import (
    atto_tipo_from_text,
    extract_people_by_rules,
    extract_records_by_rules,
)

TODAY = date(2026, 11, 23)


def _c(title, snippet="", date_=None, href="https://c.it/a"):
    return Candidate(title=title, href=href, snippet=snippet or title, date=date_)


def test_records_by_rules_shape_and_fields():
    rows = [
        _c(
            "Avviso esplorativo per l'affidamento del servizio di manutenzione degli impianti di pubblica illuminazione",
            "Avviso esplorativo per l'affidamento del servizio di manutenzione degli impianti di pubblica illuminazione "
            "pubblicato il 18/11/2026. Le manifestazioni devono pervenire entro il 05/12/2026",
            "18/11/2026",
        ),
    ]
    (r,) = extract_records_by_rules(rows, ente="Comune di X", today=TODAY)
    assert r["atto_tipo"] == "manifestazione_interesse"
    assert r["date"] == "2026-11-18" and r["scadenza"] == "2026-12-05"
    assert r["ente"] == "Comune di X" and r["url"] == "https://c.it/a" and r["extracted_by"] == "rules"


def test_records_by_rules_drop_noise_and_out_of_scope():
    rows = [
        _c("Liquidazione fattura servizio di pubblica illuminazione"),
        _c("Concessione area pubblica per somministrazione di alimenti"),
        _c("Determina a contrarre servizio di manutenzione impianti di pubblica illuminazione"),
    ]
    out = extract_records_by_rules(rows, ente=None, today=TODAY)
    assert [r["atto_tipo"] for r in out] == ["determina_a_contrarre"]


@pytest.mark.parametrize(
    ("title", "tipo"),
    [
        ("Procedura aperta per il servizio di illuminazione pubblica", "bando_gara"),
        ("Avviso pubblico ex art. 193 per la presentazione di proposte", "proposta_ppp"),
        ("Indagine di mercato per impianti di videosorveglianza", "indagine_mercato"),
        ("Avviso di preinformazione illuminazione", "avviso_preinformazione"),
        ("Affidamento incarico di progettazione PFTE illuminazione", "incarico_tecnico"),
        ("Atto di indirizzo manutenzione illuminazione", "determina_a_contrarre"),
    ],
)
def test_atto_tipo_from_text(title, tipo):
    assert atto_tipo_from_text(title) == tipo


PAGE = (
    "Organi di governo. Sindaco: Mario Rossi, tel 0835 123456 email sindaco@comune.it. "
    "Assessore ai Lavori Pubblici e Illuminazione: Giulia Bianchi. Assessore alla Cultura: Anna Verdi. "
    "Responsabile Area Tecnica: Dott. Paolo Neri. Responsabile unico del progetto: Arch. Francesco Chiarella, nominato. "
    "GIOVANNI BIANCHI - Vicesindaco con delega ai lavori pubblici"
)


def test_people_by_rules():
    got = {(p["ruolo"], p["nome"]) for p in extract_people_by_rules(PAGE)}
    assert got == {
        ("rup", "Francesco Chiarella"),
        ("sindaco", "Mario Rossi"),
        ("assessore", "Giulia Bianchi"),
        ("assessore", "Giovanni Bianchi"),
        ("responsabile_tecnico", "Paolo Neri"),
    }  # no assessore alla Cultura, and the e-mail "sindaco@" is not a role cue
    sindaco = next(p for p in extract_people_by_rules(PAGE) if p["ruolo"] == "sindaco")
    assert sindaco["email"] == "sindaco@comune.it" and sindaco["telefono"] == "0835 123456"


def _s(mode, key="k"):
    return SimpleNamespace(extraction_mode=mode, anthropic_api_key=key)


def test_modes():
    claude_state.reset()
    assert claude_state.use_claude(_s("auto")) and claude_state.use_claude(_s("claude"))
    assert not claude_state.use_claude(_s("rules"))
    assert not claude_state.use_claude(_s("auto", key=""))  # no key: free rules
    claude_state.mark_down("credit")
    assert not claude_state.use_claude(_s("auto"))  # in the retry window
    assert claude_state.use_claude(_s("claude"))  # never falls back
    claude_state.reset()
    assert claude_state.use_claude(_s("auto"))
    assert claude_state.mode(_s("boh")) == "auto"


LIST = (
    '<ul><li><a href="/atto/1">Avviso esplorativo servizio di manutenzione degli impianti di pubblica illuminazione</a>'
    " 18/11/2026</li></ul>"
)


@pytest.mark.asyncio
async def test_auto_mode_falls_back_to_rules_when_claude_has_no_credit(monkeypatch):
    from app.tasks import collect_watchlist as cw

    claude_state.reset()

    async def no_credit(html, *, url, settings, label, status=None):
        status.update(ok=False, fatal=True, error="Your credit balance is too low")
        return []

    async def no_detail(*_a, **_k):
        return None

    monkeypatch.setattr(cw, "extract_albo_records", no_credit)
    monkeypatch.setattr(cw, "_fetch_page", no_detail)
    added = []
    item = SimpleNamespace(content_hashes=None, source_id=None, entity_id=None)
    job = SimpleNamespace(records_found=0, records_valid=0, duplicates_removed=0)
    stats = Counter()
    await cw._process_page(
        SimpleNamespace(add=added.append), item, job,
        target_url="https://c.it/albo/", target_html=LIST, label="t",
        settings=SimpleNamespace(
            smart_collector_max_html_chars=80_000, extraction_mode="auto", anthropic_api_key="k",
        ),
        now=datetime.now(tz=UTC), seen=set(), stats=stats,
    )
    assert stats["claude_down_fallback"] == 1 and stats["pages_by_rules"] == 1
    assert job.records_valid == 1 and len(added) == 1
    assert not item.content_hashes  # not remembered: Claude re-reads it when available again
    assert claude_state.is_down()
    claude_state.reset()
