"""Rapporto delle limitazioni della prova gratuita."""
from __future__ import annotations

from infra.scripts.prova_siti import limitations


def test_limitations_are_listed_in_words():
    sites = [
        {"ente": "A", "error": "reset"},
        {"ente": "B", "pages_full": 3, "stopped_by": "pages",
         "hunts": [{"deadline": None, "reason": "nessun altro link a documenti da seguire", "notes": ["PDF senza testo (scansione) o protetto"]},
                   {"deadline": "2027-01-20", "reason": "", "notes": []}],
         "checklist": [{"passo": "Giunta / organi politici", "ok": False}, {"passo": "PEC (IPA)", "ok": True}]},
    ]
    out = limitations(sites)
    joined = "\n".join(out)
    assert "Siti non leggibili (1): A" in joined and "3 pagine nominano i servizi" in joined
    assert "budget" in joined and "PDF senza testo" in joined and "Referenti B: passi non riusciti — Giunta" in joined


def test_no_limitations():
    assert limitations([{"ente": "A", "pages": 5, "checklist": [{"passo": "x", "ok": True}]}]) == [
        "Nessuna limitazione rilevata su questi siti."
    ]
