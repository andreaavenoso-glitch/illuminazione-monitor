"""Standard presentation (PPTX) of one opportunity: what the app knows, in six fixed slides.

    1 Cover          who, what, which kind of notice, deadline
    2 In sintesi     the key facts (procedure, amount, duration, CIG, funding...) + the deadline panel
    3 Referenti      sindaco, assessore LL.PP., responsabile tecnico, RUP, PEC
    4 Documentazione the fields read from the documents, each with where it was found, and what was NOT found
    5 Prossimi passi proposed next step and checks to do
    6 Fonti e note   links, how the data was obtained, warning to verify

Pure function (``build_deck``): a value that is not known is shown as "non indicato", never guessed. An optional
company template (.pptx) can be the base: its master (logo, background, fonts) is kept and the blank layout is used.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.services.email_template import (
    CAMPO_LABEL,
    PROSSIMO_PASSO,
    SERVIZIO_LABEL,
    TIPO,
    _campo,
    _d,
    ruolo_label,
)
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

W, H = 13.333, 7.5
INDIGO_900, INDIGO_700, INDIGO_100, INDIGO_50 = (RGBColor.from_string(c) for c in ("312E81", "4338CA", "E0E7FF", "EEF2FF"))
INK, GREY, LIGHT, WHITE = (RGBColor.from_string(c) for c in ("1F2937", "6B7280", "F3F4F6", "FFFFFF"))
GREEN, AMBER, RED = (RGBColor.from_string(c) for c in ("15803D", "B45309", "B91C1C"))
FONT = "Calibri"
NA = "non indicato"


def _short(text: str | None, n: int) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _box(slide, x, y, w, h, fill=None, line=None, shape=MSO_SHAPE.RECTANGLE):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
    s.shadow.inherit = False
    return s


def _text(slide, x, y, w, h, text, *, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.size, r.font.bold, r.font.name = Pt(size), bold, FONT
        r.font.color.rgb = color
    return tb


def _bullets(slide, x, y, w, h, items: list[str], *, size=16):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        r = p.add_run()
        r.text = "•  " + item
        r.font.size, r.font.name = Pt(size), FONT
        r.font.color.rgb = INK
    return tb


def _header(slide, title: str, subtitle: str = "") -> None:
    _box(slide, 0, 0, W, 1.05, fill=INDIGO_700)
    _text(slide, 0.5, 0.18, 10.5, 0.6, title, size=28, bold=True, color=WHITE)
    if subtitle:
        _text(slide, 0.5, 0.66, 12, 0.35, subtitle, size=13, color=INDIGO_100)


def _footer(slide, n: int, ente: str, today: date) -> None:
    _text(slide, 0.5, 7.08, 9, 0.3, f"{ente} · scheda generata il {today:%d/%m/%Y}", size=10, color=GREY)
    _text(slide, 12.0, 7.08, 0.9, 0.3, str(n), size=10, color=GREY, align=PP_ALIGN.RIGHT)


def _table(slide, x, y, widths: list[float], header: list[str], rows: list[list[str]], *, size=13, row_h=0.46):
    shape = slide.shapes.add_table(len(rows) + 1, len(widths), Inches(x), Inches(y), Inches(sum(widths)), Inches(row_h * (len(rows) + 1)))
    tbl = shape.table
    for i, w in enumerate(widths):
        tbl.columns[i].width = Inches(w)
    for r_i, row in enumerate([header, *rows]):
        tbl.rows[r_i].height = Inches(row_h)
        for c_i, val in enumerate(row):
            cell = tbl.cell(r_i, c_i)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.fill.solid()
            cell.fill.fore_color.rgb = INDIGO_700 if r_i == 0 else (LIGHT if r_i % 2 == 0 else WHITE)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = ""
            run = p.add_run()
            run.text = val
            run.font.size, run.font.name = Pt(size), FONT
            run.font.bold = r_i == 0 or c_i == 0
            missing = val in (NA, "non individuato")
            run.font.color.rgb = WHITE if r_i == 0 else (GREY if missing else INK)
            run.font.italic = missing and r_i > 0
    return shape


def _deadline_panel(slide, x, y, w, h, scad: date | None, today: date, esito: str | None, nota: str | None) -> None:
    _box(slide, x, y, w, h, fill=INDIGO_50, line=INDIGO_100)
    _text(slide, x + 0.2, y + 0.15, w - 0.4, 0.3, "SCADENZA", size=12, bold=True, color=INDIGO_700)
    if scad:
        days = (scad - today).days
        color = RED if days < 0 else (AMBER if days <= 14 else GREEN)
        _text(slide, x + 0.2, y + 0.5, w - 0.4, 0.7, f"{scad:%d/%m/%Y}", size=34, bold=True, color=INDIGO_900)
        label = "SCADUTA" if days < 0 else ("scade oggi" if days == 0 else f"tra {days} giorni")
        _text(slide, x + 0.2, y + 1.25, w - 0.4, 0.4, label, size=18, bold=True, color=color)
        detail = _short(nota, 150) if nota else "Data letta nel documento: verificarla sull'originale."
    else:
        _text(slide, x + 0.2, y + 0.55, w - 0.4, 0.7, "non trovata", size=28, bold=True, color=GREY)
        detail = _short(nota, 150) if nota else "Da verificare sul documento originale."
    _text(slide, x + 0.2, y + 1.8, w - 0.4, h - 1.9, detail, size=12, color=GREY)


def _fonts_for_missing(campi: dict[str, dict] | None) -> list[str]:
    return [lab for k, lab in CAMPO_LABEL if not campi or k not in campi]


def build_deck(d: dict[str, Any], template: str | None = None) -> bytes:
    """The presentation of one opportunity as .pptx bytes. ``d`` keys: categoria, ente, provincia, descrizione,
    link, scadenza, scadenza_nota, visto_il, servizi, campi, documenti, referenti, pec, metodo, analisi_il, today."""
    today: date = d.get("today") or date.today()
    prs = Presentation(template) if template and Path(template).is_file() else Presentation()
    if not (template and Path(template).is_file()):
        prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    blank = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[len(prs.slide_layouts) - 1]
    ente = d.get("ente") or NA
    tipo = TIPO.get(d.get("categoria") or "", "Avviso")
    scad = _d(d.get("scadenza"))
    campi: dict[str, dict] = d.get("campi") or {}
    servizi = [SERVIZIO_LABEL.get(s, s) for s in (d.get("servizi") or [])]

    # 1 ------------------------------------------------------------------ cover
    s = prs.slides.add_slide(blank)
    _box(s, 0, 0, W, H, fill=INDIGO_900)
    _box(s, 0.6, 2.05, 0.12, 2.0, fill=RGBColor.from_string("38BDF8"))
    _text(s, 0.95, 1.2, 9, 0.5, f"{tipo.upper()} · SCHEDA OPPORTUNITÀ", size=16, bold=True, color=RGBColor.from_string("7DD3FC"))
    _text(s, 0.95, 1.95, 11.2, 1.2, ente, size=44, bold=True, color=WHITE)
    _text(s, 0.95, 3.2, 11.2, 1.5, _short(d.get("descrizione"), 230) or NA, size=20, color=INDIGO_100)
    meta = " · ".join(x for x in (d.get("provincia"), ", ".join(servizi)) if x)
    if meta:
        _text(s, 0.95, 5.0, 11, 0.4, meta, size=16, color=RGBColor.from_string("A5B4FC"))
    chip = f"Scadenza {scad:%d/%m/%Y}" if scad else "Scadenza da verificare"
    _box(s, 0.95, 5.7, 3.6, 0.55, fill=RGBColor.from_string("38BDF8"), shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    _text(s, 0.95, 5.7, 3.6, 0.55, chip, size=16, bold=True, color=INDIGO_900, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    _text(s, 0.95, 6.8, 9, 0.35, f"Generata il {today:%d/%m/%Y} dal monitor degli appalti di illuminazione pubblica", size=11, color=RGBColor.from_string("A5B4FC"))

    # 2 ------------------------------------------------------------------ in sintesi
    s = prs.slides.add_slide(blank)
    _header(s, "In sintesi", f"{tipo} · {ente}")
    facts = [
        ("Ente", ente + (f" ({d['provincia']})" if d.get("provincia") else "")),
        ("Tipo di atto", tipo),
        ("Servizi", ", ".join(servizi) or NA),
    ]
    for key, label in (("procedura", "Procedura"), ("importo_massimo_eur", "Importo massimo"), ("canone_annuo_eur", "Canone annuo di riferimento"), ("durata", "Durata"),
                       ("punti_luce", "Punti luce"), ("cig", "CIG"), ("criterio_aggiudicazione", "Criterio"),
                       ("finanziamento", "Finanziamento")):
        facts.append((label, _campo(key, campi[key]["valore"]) if key in campi else NA))
    _table(s, 0.5, 1.35, [2.2, 5.6], ["Dato", "Valore"], [[a, _short(b, 90)] for a, b in facts], size=14, row_h=0.5)
    _deadline_panel(s, 8.7, 1.35, 4.1, 3.6, scad, today, d.get("verifica_esito"), d.get("scadenza_nota"))
    visto = _d(d.get("visto_il"))
    _text(s, 8.7, 5.15, 4.1, 0.7, f"Individuato il {visto:%d/%m/%Y}" if visto else "", size=12, color=GREY)
    _footer(s, 2, ente, today)

    # 3 ------------------------------------------------------------------ referenti
    s = prs.slides.add_slide(blank)
    _header(s, "Referenti", "Chi contattare nel comune")
    people = d.get("referenti") or []
    rows, uncertain = [], False
    for ruolo, label in (("sindaco", "Sindaco"), ("assessore", "Assessore ai Lavori pubblici"),
                         ("responsabile_tecnico", "Referente tecnico"), ("rup", "RUP")):
        found = [p for p in people if p.get("ruolo") == ruolo][:2]
        if ruolo == "rup" and not found and "rup" in campi:
            rows.append([label, _short(str(campi["rup"]["valore"]), 60), "dalla documentazione", "letto nel documento"])
            continue
        if not found:
            rows.append([label, "non individuato", "", ""])
        for p in found:
            ok = p.get("stato") == "verificato"
            uncertain = uncertain or not ok
            contatti = " · ".join(x for x in (p.get("email"), p.get("telefono")) if x) or "—"
            rows.append([ruolo_label(p, label), _short(p.get("nome"), 40), _short(contatti, 55), "verificato" if ok else "da confermare"])
    if d.get("pec"):
        rows.append(["PEC dell'ente", d["pec"], "", "da IPA"])
    _table(s, 0.5, 1.35, [3.0, 3.6, 4.1, 1.6], ["Ruolo", "Nome", "Contatti", "Stato"], rows, size=13, row_h=0.5)
    if uncertain:
        _text(s, 0.5, 6.55, 12, 0.4, "I nomi «da confermare» vanno verificati sul sito del comune prima di un contatto.", size=12, color=AMBER)
    _footer(s, 3, ente, today)

    # 4 ------------------------------------------------------------------ documentazione
    s = prs.slides.add_slide(blank)
    _header(s, "Documentazione analizzata", "Dati letti dai documenti, con la fonte di ciascuno")
    drows = [[lab, _short(_campo(k, campi[k]["valore"]), 48), _short(campi[k].get("fonte") or "", 40)]
             for k, lab in CAMPO_LABEL if k in campi]
    if "scadenza" in campi:
        sd = _d(campi["scadenza"]["valore"])
        drows.append(["Scadenza", f"{sd:%d/%m/%Y}" if sd else str(campi["scadenza"]["valore"]),
                      _short(campi["scadenza"].get("fonte") or "", 40)])
    if drows:
        _table(s, 0.5, 1.35, [2.3, 3.6, 2.9], ["Campo", "Valore", "Fonte"], drows, size=12, row_h=0.44)
    else:
        _text(s, 0.5, 1.5, 8.8, 1, "Nessun dato estratto: la documentazione non è ancora stata analizzata.", size=16, color=GREY)
    docs = d.get("documenti") or []
    _text(s, 9.6, 1.35, 3.3, 0.4, f"Documenti letti ({len(docs)})", size=14, bold=True, color=INDIGO_700)
    _bullets(s, 9.6, 1.8, 3.3, 3.2, [_short(x.get("nome") or x.get("url"), 38) for x in docs[:7]] or [NA], size=11)
    missing = _fonts_for_missing(campi)
    if missing:
        _text(s, 0.5, 6.3, 12.3, 0.6, "Non trovato nei documenti: " + ", ".join(missing) + ".", size=12, color=GREY)
    _footer(s, 4, ente, today)

    # 5 ------------------------------------------------------------------ prossimi passi
    s = prs.slides.add_slide(blank)
    _header(s, "Prossimi passi", "Proposta operativa")
    steps = [PROSSIMO_PASSO.get(d.get("categoria") or "", "Valutare l'opportunità.")]
    if scad:
        days = (scad - today).days
        steps.append(f"Scadenza {scad:%d/%m/%Y}: " + (f"restano {days} giorni." if days >= 0 else "già passata, verificare se l'avviso è stato prorogato."))
    else:
        steps.append("Verificare la scadenza sul documento originale: l'app non l'ha trovata.")
    steps.append("Leggere i documenti originali (link alla slide successiva) prima di decidere.")
    if uncertain or not people:
        steps.append("Confermare i referenti sul sito del comune; i nomi non verificati non vanno usati così come sono.")
    steps.append("Predisporre il contatto con l'ufficio tecnico (testo standard dell'e-mail disponibile nell'app).")
    _bullets(s, 0.7, 1.5, 11.8, 5, steps, size=20)
    _footer(s, 5, ente, today)

    # 6 ------------------------------------------------------------------ fonti e note
    s = prs.slides.add_slide(blank)
    _header(s, "Fonti e note")
    links = [f"Avviso: {d.get('link') or NA}"] + [f"{_short(x.get('nome'), 30)}: {x.get('url')}" for x in docs[:5] if x.get("url")]
    _text(s, 0.5, 1.35, 12, 0.4, "Fonti", size=16, bold=True, color=INDIGO_700)
    _bullets(s, 0.5, 1.8, 12.3, 2.8, [_short(x, 150) for x in links], size=12)
    an = _d(d.get("analisi_il"))
    metodo = f"Dati estratti automaticamente ({d.get('metodo') or 'regole'})" + (f" il {an:%d/%m/%Y}" if an else "") + "."
    _text(s, 0.5, 4.9, 12.3, 0.4, "Note", size=16, bold=True, color=INDIGO_700)
    _bullets(s, 0.5, 5.35, 12.3, 1.6, [metodo, "Ogni dato va verificato sul documento ufficiale prima di usarlo in un'offerta.",
                                        "Il valore «non indicato» significa che non è scritto nei documenti letti, non che non esista."], size=13)
    _footer(s, 6, ente, today)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def deck_filename(ente: str | None, today: date | datetime) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in (ente or "scheda")).strip("_")[:50] or "scheda"
    return f"scheda_{safe}_{today:%Y%m%d}.pptx"
