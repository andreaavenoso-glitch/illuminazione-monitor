import io
import os
from datetime import date

import pytest
from app.services.gate_deck import (
    DC,
    GateConfig,
    _fill_lines,
    _set_par,
    build_gate,
    gate_dates,
    is_gate_template,
    it_date,
)
from pptx import Presentation
from pptx.util import Inches


def test_italian_long_date():
    assert it_date(date(2026, 10, 1)) == "1 ottobre 2026"
    assert it_date(date(2026, 12, 13)) == "13 dicembre 2026"


def test_gate_dates_end_one_day_before_the_deadline_and_are_increasing():
    d = gate_dates(date(2026, 11, 2), date(2026, 12, 13))
    assert d[0] == date(2026, 11, 2) and d[-1] == date(2026, 12, 12)
    assert d == sorted(d) and len(d) == 8


def test_gate_dates_without_deadline_use_the_standard_weeks():
    d = gate_dates(date(2026, 9, 18), None)
    assert d[1] == date(2026, 10, 9) and d[-1] == date(2026, 11, 23)  # +3 and +9,5 weeks
    assert gate_dates(None, date(2026, 12, 1)) == [None] * 8


def test_deadline_already_too_close_does_not_go_backwards():
    d = gate_dates(date(2026, 12, 10), date(2026, 12, 12))
    assert d[-1] == date(2026, 12, 11) and d[0] == date(2026, 12, 10)


def _textbox():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(3))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "Esempio: "
    r.font.bold = True
    r2 = p.add_run()
    r2.text = "testo di esempio del modello"
    r2.font.bold = False
    return tb


def test_fill_lines_replaces_every_paragraph_and_keeps_label_bold():
    tb = _textbox()
    _fill_lines(tb.text_frame, [("Consistenza: ", "1057 punti luce"), ("Durata: ", DC), (None, "riga libera")])
    pars = tb.text_frame.paragraphs
    assert [p.text for p in pars] == ["Consistenza: 1057 punti luce", f"Durata: {DC}", "riga libera"]
    assert pars[0].runs[0].font.bold is True and pars[0].runs[1].font.bold is False
    assert "Esempio" not in " ".join(p.text for p in pars)


def test_set_par_drops_the_examples_extra_runs():
    tb = _textbox()
    _set_par(tb.text_frame.paragraphs[0], None, "solo questo")
    assert tb.text_frame.paragraphs[0].text == "solo questo"


def test_plain_presentation_is_not_a_gate_model():
    assert not is_gate_template(Presentation())


@pytest.mark.skipif(not os.environ.get("GATE_TEMPLATE"), reason="needs the company model (GATE_TEMPLATE=path.pptx)")
def test_real_model_is_filled_and_nothing_of_the_example_is_left():
    import zipfile

    template = os.environ["GATE_TEMPLATE"]
    assert is_gate_template(Presentation(template))
    data = build_gate(
        {"categoria": "gara", "ente": "Comune di Prova", "provincia": "Matera", "today": date(2026, 11, 23),
         "scadenza": "2026-12-20", "pec": "p@pec.prova.it", "campi": {}, "referenti": []},
        template, GateConfig(citta="Roma", autore="Autore"),
    )
    prs = Presentation(io.BytesIO(data))
    text = " ".join(sh.text_frame.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame)
    assert "Prova (Matera) Gate 1" in text and "20 dicembre 2026" in " ".join(
        c.text for sl in prs.slides for sh in sl.shapes if getattr(sh, "has_table", False) and sh.has_table
        for row in sh.table.rows for c in row.cells)
    z = zipfile.ZipFile(io.BytesIO(data))
    xml = " ".join(z.read(n).decode("utf8", "ignore") for n in z.namelist() if n.startswith("ppt/slides/slide"))
    for example in ("Bovezzo", "Coppolino", "Hera Luce", "Edison", "Ghidoni", "Bazzani"):
        assert example not in xml
    props = prs.core_properties
    assert props.title == "Gate 1 – Prova (Matera)" and props.author == "Autore" and props.last_modified_by == "Autore"
