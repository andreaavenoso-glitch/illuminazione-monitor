"""Lettura automatica della scadenza dai documenti (pagina o PDF)."""
from __future__ import annotations

from datetime import date

import pytest
from app.tasks.verify_records import html_to_text, judge
from shared_models.relevance import deadline_from_text

TODAY = date(2026, 11, 22)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Le offerte devono pervenire entro il 15/12/2026 ore 12:00", date(2026, 12, 15)),
        ("Scadenza: 05-01-2027", date(2027, 1, 5)),
        ("termine ultimo per la presentazione delle manifestazioni: 10 dicembre 2026", date(2026, 12, 10)),
        ("Pubblicato il 01/03/2023. Nessun altro termine", None),
        ("Scadenza 10/12/2026 e poi entro il 20/12/2026", date(2026, 12, 20)),
        ("", None),
    ],
)
def test_deadline_from_text(text, expected):
    assert deadline_from_text(text) == expected


def test_first_date_after_the_cue_wins():
    t = "scadenza presentazione offerte 12/12/2026 (bando pubblicato il 30/11/2026)"
    assert deadline_from_text(t) == date(2026, 12, 12)


def test_judge_open_closed_and_unknown():
    assert judge("termine per la presentazione delle offerte: 15/12/2026", TODAY) == ("aperto", date(2026, 12, 15), None)
    assert judge("scadenza 10/03/2023", TODAY) == ("chiuso", date(2023, 3, 10), None)
    assert judge("Avviso di appalto aggiudicato pubblicato il 01/03/2023", TODAY) == ("chiuso", None, None)
    assert judge("", TODAY) == ("non_trovata", None, None)
    assert judge("Il comune intende avviare una indagine. Termine da definire.", TODAY)[0] == "claude"
    assert judge("pagina senza date ne parole chiave", TODAY) == ("non_trovata", None, None)


def test_judge_pregara_reads_the_date_of_the_act():
    assert judge("Delibera di giunta del 18/08/2026 - proposta di finanza di progetto", TODAY, "pre_gara") == (
        "recente", None, date(2026, 8, 18),
    )
    assert judge("Delibera del 16/08/2017 approvazione progetto", TODAY, "pre_gara")[0] == "chiuso"
    assert judge("Atto di indirizzo senza alcuna data", TODAY, "pre_gara") == ("non_trovata", None, None)
    # a pre-gara never goes to Claude
    assert judge("termini da definire, scadenza prossima", TODAY, "pre_gara")[0] == "non_trovata"


def test_html_to_text_strips_tags_so_cue_and_date_meet():
    html = "<p><b>Scadenza:</b> </p><span>05/12/2026</span><script>var x=1</script>"
    assert deadline_from_text(html_to_text(html)) == date(2026, 12, 5)
