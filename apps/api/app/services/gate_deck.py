"""The "Gate 1" sheet of an opportunity: the company's own PowerPoint model filled with what the app knows.

The model (cover, agenda, "1| Dati generali PF", "2| Note di progetto", "3| Pianificazione gate", closing) is kept
as it is, graphics and layouts included; only the texts of the opportunity are replaced. Rules:

* what the app knows is written (ente, deadline with hour and PEC, RUP, referenti, procedure, amount, duration...);
* what it does NOT know is written as "[da compilare]", never guessed;
* nothing of the model's own example (a specific comune's map, consistenza, competitors) is ever left behind: a
  generated deck for another comune must not carry the data of the example.

The model is a file of the user (``PPT_TEMPLATE_PATH``); it is not part of the repository.
"""
from __future__ import annotations

import copy
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.services.email_template import SERVIZIO_LABEL, TIPO, _d
from app.services.gate_content import (
    DC,
    concorrenza_items,
    desiderata_items,
    economica_rows,
    informazioni_items,
    procedura_text,
    refs,
)
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Pt

MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
        "novembre", "dicembre")
# Standard weeks of the gate (the model's own): kick-off, hand-over, go/no-go, pre-valutazione, fine progettazione...
GATE_WEEKS = (0.0, 3.0, 4.5, 5.5, 7.0, 8.0, 9.0, 9.5)


@dataclass
class GateConfig:
    citta: str = ""
    autore: str = ""
    resp_commerciale: str = ""
    resp_tecnico: str = ""


def it_date(d: date) -> str:
    return f"{d.day} {MESI[d.month - 1]} {d.year}"


def gate_dates(start: date | None, scadenza: date | None) -> list[date | None]:
    """The planned date of each of the 8 steps: from the day the opportunity was noticed to one day before the
    deadline, spread in proportion to the standard weeks of the gate. Without a deadline: the standard weeks."""
    if start is None:
        return [None] * len(GATE_WEEKS)
    if scadenza is None:
        return [start + timedelta(days=round(w * 7)) for w in GATE_WEEKS]
    end = scadenza - timedelta(days=1)
    span = (end - start).days
    if span <= 0:
        return [end if i == len(GATE_WEEKS) - 1 else start for i in range(len(GATE_WEEKS))]
    return [start + timedelta(days=round(span * w / GATE_WEEKS[-1])) for w in GATE_WEEKS]


MODEL_DIRS = ("/workspace/infra", "infra", "/app/infra")
NO_MODEL = (
    "Modello A2A (Gate 1) non trovato. Copia il file .pptx nella cartella infra/modelli del Codespace "
    "(oppure indica il percorso in PPT_TEMPLATE_PATH nel file .env) e lancia «bash aggiorna.sh»."
)


def find_gate_template(configured: str | None, dirs: tuple[str, ...] = MODEL_DIRS) -> str | None:
    """The A2A model to fill: the configured file, else the first Gate sheet found anywhere under the infra folder (a
    ``modelli`` folder is looked at first, but the file may be wherever it was dropped). None when there is none: the
    sheet must never come out in another design without anyone noticing."""
    from pathlib import Path

    candidates: list[str] = [configured] if configured else []
    for d in dirs:
        base = Path(d)
        if base.is_dir():
            found = [f for f in base.rglob("*.pptx") if not f.name.startswith("~") and len(f.relative_to(base).parts) <= 5]
            found.sort(key=lambda f: (0 if "modell" in f.parent.name.lower() and f.parent != base else 1, str(f)))
            candidates += [str(f) for f in found[:50]]
    for c in candidates:
        try:
            if Path(c).is_file() and is_gate_template(Presentation(c)):
                return c
        except Exception:  # noqa: BLE001 -- not a presentation / protected: next one
            continue
    return None


def is_gate_template(prs: Any) -> bool:
    titles = []
    for slide in prs.slides:
        for sh in slide.shapes:
            if sh.is_placeholder and sh.placeholder_format.type in (1, 3) and sh.has_text_frame:
                titles.append(sh.text_frame.text)
    joined = " ".join(titles).lower()
    return "dati generali pf" in joined and "pianificazione gate" in joined


# --- text helpers that keep the model's formatting ---------------------------------------------------------
def _drop_highlight(par: Any) -> None:
    for r in par.runs:
        rpr = r._r.rPr
        if rpr is not None:
            for el in rpr.findall(qn("a:highlight")):
                rpr.remove(el)


def _set_par(par: Any, label: str | None, value: str) -> None:
    """One paragraph = optional bold label + normal text, using the formatting of the paragraph's own runs."""
    runs = list(par.runs)
    if not runs:
        run = par.add_run()
        runs = [run]
    first = runs[0]
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    if label is None:
        first.text = value
        return
    first.text = label
    first.font.bold = True
    second = copy.deepcopy(first._r)
    first._r.addnext(second)
    from pptx.text.text import _Run

    run2 = _Run(second, par)
    run2.text = value
    run2.font.bold = False
    _drop_highlight(par)


def _fit_size(items: list[tuple[str | None, str]], base: float = 15.0) -> float | None:
    """A smaller type when the lines are many or long, so that the text stays inside the page (the model's own is 15 pt)."""
    total = sum(len(a or "") + len(b) for a, b in items)
    return 11.0 if total > 1100 else 12.0 if total > 800 else 13.5 if total > 600 else None


def _fill_lines(tf: Any, items: list[tuple[str | None, str]], size: float | None = None) -> None:
    """Replace all paragraphs of a text frame with ``items`` (label, text), cloned from its first paragraph."""
    paras = list(tf.paragraphs)
    proto = copy.deepcopy(paras[0]._p)
    for p in paras[1:]:
        p._p.getparent().remove(p._p)
    prev = tf.paragraphs[0]._p
    for _ in items[1:]:
        node = copy.deepcopy(proto)
        prev.addnext(node)
        prev = node
    for par, (label, value) in zip(tf.paragraphs, items, strict=False):
        _set_par(par, label, value)
        if size:
            for r in par.runs:
                r.font.size = Pt(size)


def _cell(cell: Any, text: str, *, bold_head: str | None = None, size: float | None = None) -> None:
    """A table cell with one paragraph; the first run's formatting is kept. ``bold_head`` is bold, ``text`` follows."""
    tf = cell.text_frame
    for p in tf.paragraphs[1:]:
        p._p.getparent().remove(p._p)
    par = tf.paragraphs[0]
    if bold_head:
        _set_par(par, bold_head, text)
    else:
        runs = list(par.runs)
        if not runs:
            par.add_run()
            runs = list(par.runs)
        runs[0].text = text
        for r in runs[1:]:
            r._r.getparent().remove(r._r)
    if size:
        for r in par.runs:
            r.font.size = Pt(size)


def _shape(slide: Any, name: str) -> Any:
    return next((sh for sh in slide.shapes if sh.name == name), None)


def _table(slide: Any, name: str | None = None) -> Any:
    for sh in slide.shapes:
        if getattr(sh, "has_table", False) and sh.has_table and (name is None or sh.name == name):
            return sh.table
    return None


def _title_ph(slide: Any) -> Any:
    return next((sh for sh in slide.shapes if sh.is_placeholder and sh.placeholder_format.type in (1, 3)), None)


# --- what the app knows ------------------------------------------------------------------------------------
def _v(campi: dict, key: str) -> Any:
    return campi[key]["valore"] if key in campi else None


def _person(p: dict) -> str:
    bits = [p.get("qualifica")] if p.get("qualifica") else []
    contatti = " · ".join(x for x in (p.get("telefono"), p.get("email")) if x)
    s = ", ".join(b for b in bits if b) or ""
    if contatti:
        s += (" – " if s else "") + contatti
    return s


def _people(d: dict, ruolo: str) -> list[dict]:
    return [p for p in (d.get("referenti") or []) if p.get("ruolo") == ruolo]


def _mark(p: dict, text: str) -> str:
    return text + ("" if p.get("stato") == "verificato" else " [da confermare]")


def build_gate(d: dict[str, Any], template: str, cfg: GateConfig) -> bytes:
    """The model filled for one opportunity, as .pptx bytes."""
    prs = Presentation(template)
    slides = list(prs.slides)
    today: date = d.get("today") or date.today()
    campi: dict[str, dict] = d.get("campi") or {}
    ente = d.get("ente") or DC
    comune = ente.removeprefix("Comune di ").removeprefix("Comune ").strip()
    provincia = d.get("provincia")
    luogo = f"{comune} ({provincia})" if provincia else comune
    tipo = TIPO.get(d.get("categoria") or "", "Avviso")
    scad = _d(d.get("scadenza"))
    servizi = [SERVIZIO_LABEL.get(s, s) for s in (d.get("servizi") or [])]
    proc = _v(campi, "procedura")
    pec = _v(campi, "pec_invio") or d.get("pec")

    by_index: dict[int, Callable[[Any], None]] = {}

    def slide_cover(s: Any) -> None:
        title = _shape(s, "Title")
        if title is not None:
            runs = list(title.text_frame.paragraphs[0].runs)
            if len(runs) >= 2:  # "Riqualificazione del comune di " + bold "<comune> Gate 1"
                runs[1].text = f"{luogo} Gate 1"
                for r in runs[2:]:
                    r._r.getparent().remove(r._r)
            elif runs:
                runs[0].text = f"Riqualificazione del comune di {luogo} Gate 1"
        sub = _shape(s, "Subtitle")
        if sub is not None:
            art193 = isinstance(proc, list) and any("193" in x for x in proc)
            text = ("Proposta PPP (art. 193 c.4 D.Lgs. 36/2023) per gli impianti di pubblica illuminazione" if art193
                    else f"{tipo}: " + (", ".join(servizi) or "servizi di illuminazione pubblica"))
            _cell_like(sub.text_frame, text)
        doc = _shape(s, "Documenttype")
        if doc is not None:
            pars = doc.text_frame.paragraphs
            _set_par(pars[0], None, f"{cfg.citta} {it_date(today)}".strip())
            if len(pars) > 1:
                _set_par(pars[1], None, cfg.autore)

    def slide_dati(s: Any) -> None:
        t = _table(s, "Tabella 4")
        if t is None:
            return
        _cell(t.cell(1, 1), f"{luogo} – abitanti e superficie: {DC}")
        _cell(t.cell(2, 1), DC)
        ora = _v(campi, "ora_scadenza")
        if scad:
            head = it_date(scad) + (f", ore {ora}" if ora else "")
            _cell(t.cell(3, 1), (f" – via PEC a {pec}" if pec else "") + refs(campi, "scadenza", "ora_scadenza", "pec_invio", width=22), bold_head=head, size=10)
        else:
            _cell(t.cell(3, 1), " – verificare sul documento originale", bold_head="Scadenza non trovata")
        sop = _v(campi, "sopralluogo")
        sop = (sop if len(str(sop)) <= 150 else str(sop)[:147].rstrip() + "…") if sop else sop
        _cell(t.cell(4, 1), (sop + refs(campi, "sopralluogo", width=22)) if sop else "Non indicato nei documenti letti – da verificare", size=10)
        # RUP / referenti tecnici
        rup = (_people(d, "rup") or [None])[0]
        tec = (_people(d, "responsabile_tecnico") or [None])[0]
        who = rup or tec
        cell = t.cell(5, 1)
        tf = cell.text_frame
        pars = tf.paragraphs
        if who:
            ruolo = "RUP" if who is rup else "Responsabile Area Tecnica"
            _set_par(pars[0], _mark(who, who["nome"]), f" – {ruolo}" + (f", {who['qualifica']}" if who.get("qualifica") and who is not rup else ""))
            contatti = " – ".join(x for x in (who.get("telefono"), who.get("email")) if x)
            _set_par(pars[1], None, contatti or "contatti non trovati") if len(pars) > 1 else None
        elif _v(campi, "rup"):
            _set_par(pars[0], str(_v(campi, "rup")), " – RUP" + refs(campi, "rup", width=22))
            _set_par(pars[1], None, "contatti non trovati") if len(pars) > 1 else None
        else:
            _set_par(pars[0], "Non individuato", " – usare «Referenti del comune» nell'app")
            _set_par(pars[1], None, DC) if len(pars) > 1 else None
        for p in pars[2:]:
            p._p.getparent().remove(p._p)
        _cell(t.cell(6, 1), procedura_text(campi, tipo, d.get("link")), size=10)

    def slide_posizionamento(s: Any) -> None:
        pic = _shape(s, "Immagine 5")
        if pic is not None:  # the map of the example comune must never stay in another comune's deck
            pic._element.getparent().remove(pic._element)
        frame = next((sh for sh in s.shapes if getattr(sh, "has_table", False) and sh.has_table), None)
        t = frame.table if frame is not None else None
        if t is None:
            return
        # without the map the table takes the whole width of the slide
        total = sum(c.width for c in t.columns)
        new_total = 9_900_000
        for c in t.columns:
            c.width = int(c.width * new_total / total)
        frame.left, frame.width = 540_000, new_total
        for r in range(1, len(t.rows)):
            _cell(t.cell(r, 1), DC)
        _cell(t.cell(1, 1), f"{provincia + ' – ' if provincia else ''}{DC}")

    def slide_economica(s: Any) -> None:
        t = _table(s, "Tabella PEF")
        if t is not None:
            for i, (voce, valore, fonte) in enumerate(economica_rows(campi), start=1):
                _cell(t.cell(i, 0), voce)
                _cell(t.cell(i, 1), valore)
                _cell(t.cell(i, 2), fonte)
        note = _shape(s, "Testo 21")
        if note is not None:
            _set_par(note.text_frame.paragraphs[0], "Leva energetica: ", DC)

    def slide_info_pa(s: Any) -> None:
        t = _table(s)
        if t is None:
            return
        items = informazioni_items(campi, tipo, d.get("link"), d.get("documenti") or [], scad, d.get("scadenza_nota"))
        _fill_lines(t.cell(1, 0).text_frame, items[:9])

    def slide_desiderata(s: Any) -> None:
        tb = _shape(s, "CasellaDiTesto 9")
        if tb is None:
            return
        items = desiderata_items(campi)
        _fill_lines(tb.text_frame, items, _fit_size(items))

    def slide_concorrenza(s: Any) -> None:
        tb = _shape(s, "CasellaDiTesto 9")
        if tb is None:
            return
        _fill_lines(tb.text_frame, concorrenza_items(campi))

    def slide_interlocutori(s: Any) -> None:
        tb = _shape(s, "CasellaDiTesto 9")
        if tb is None:
            return
        items: list[tuple[str | None, str]] = []
        rup = _people(d, "rup")
        if rup:
            for p in rup[:1]:
                items.append((_mark(p, p["nome"]) + ": ", "RUP" + (f" – {_person(p)}" if _person(p) else "")))
        elif _v(campi, "rup"):
            items.append((f"{_v(campi, 'rup')}: ", "RUP (dalla documentazione)"))
        for p in _people(d, "responsabile_tecnico")[:2]:
            items.append(("Referente tecnico: ", _mark(p, p["nome"]) + (f" ({_person(p)})" if _person(p) else "")))
        for p in _people(d, "sindaco")[:1]:
            items.append((_mark(p, p["nome"]) + ": ", "Sindaco" + (f" – {_person(p)}" if _person(p) else "")))
        for p in _people(d, "assessore")[:5]:
            items.append((_mark(p, p["nome"]) + ": ", (p.get("qualifica") or "Assessore") + (f" – {_person(p)}" if p.get("email") or p.get("telefono") else "")))
        if d.get("pec"):
            items.append(("PEC dell'ente: ", d["pec"]))
        if not items:
            items = [("Referenti: ", "non individuati – usare «Referenti del comune» nell'app")]
        _fill_lines(tb.text_frame, items[:9])

    def slide_gate(s: Any) -> None:
        t = _table(s)
        if t is None:
            return
        _cell(t.cell(0, 0), comune)
        runs0 = t.cell(0, 0).text_frame.paragraphs[0].runs
        if runs0 and len(comune) > 8:  # the model's cell fits about 8 letters: smaller type for longer names
            size = runs0[0].font.size.pt if runs0[0].font.size else 12.0
            runs0[0].font.size = Pt(max(5.0, round(size * 8 / len(comune), 1)))
        resp = [cfg.resp_commerciale, cfg.resp_commerciale, cfg.resp_tecnico, cfg.resp_tecnico, cfg.resp_tecnico,
                cfg.resp_commerciale, cfg.resp_commerciale, cfg.resp_commerciale]
        start = _d(d.get("visto_il")) or today
        dates = gate_dates(start, scad)
        for i in range(8):
            _cell(t.cell(1, i + 1), resp[i] or "–")
            _cell(t.cell(2, i + 1), f"{dates[i]:%d/%m/%Y}" if dates[i] else "")
            _cell(t.cell(3, i + 1), "")

    by_index.update({0: slide_cover, 2: slide_dati, 3: slide_posizionamento, 4: slide_economica, 6: slide_info_pa,
                     7: slide_desiderata, 8: slide_concorrenza, 9: slide_interlocutori, 11: slide_gate})
    for idx, fn in by_index.items():
        if idx < len(slides):
            fn(slides[idx])
    # the model's own file properties (title of another meeting, original author) must not travel with the sheet
    cp = prs.core_properties
    cp.title = f"Gate 1 – {luogo}"
    cp.author = cp.last_modified_by = cfg.autore
    cp.subject = cp.keywords = cp.comments = cp.category = ""
    cp.revision = 1
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _cell_like(tf: Any, text: str) -> None:
    par = tf.paragraphs[0]
    _set_par(par, None, text)
    for p in tf.paragraphs[1:]:
        p._p.getparent().remove(p._p)


def gate_filename(ente: str | None, today: date | datetime) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in (ente or "scheda")).strip("_")[:50] or "scheda"
    return f"Gate_1_{safe}_{today:%Y%m%d}.pptx"
