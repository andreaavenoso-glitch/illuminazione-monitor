"""Workbook of the referenti, one sheet per province plus an index, to share with colleagues.

Default (shareable) version: names and contacts only. ``interno=True`` adds the working
columns (reliability, action, source, dates), which are not for colleagues.
"""
from __future__ import annotations

import io
import re
from collections import defaultdict
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from shared_models.referenti_logic import FALLBACK_PEC, affidabilita, azione

_STEPS = [
    "Giunta / politici", "Scheda sindaco", "Schede assessori", "Uffici LL.PP.", "Resp. tecnico", "AT organizzazione",
    "AT personale", "Albo / decreti", "PEC (IPA)", "Elezioni / mandato", "Stampa 6 mesi", "Riscontro incrociato",
]
RUOLI_COL = (
    ("sindaco", "Sindaco"),
    ("assessore", "Assessore ai Lavori pubblici"),
    ("responsabile_tecnico", "Responsabile area tecnica"),
    ("rup", "RUP"),
)


def _cell(people: list[dict], ruolo: str, *, with_flag: bool = True) -> str:
    rows = [p for p in people if p["ruolo"] == ruolo]
    out = []
    for p in rows:
        s = p["nome"]
        if with_flag and p.get("stato") != "verificato":
            s += " (da confermare)"
        out.append(s)
    return "; ".join(out)


def _sheet_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", name).strip()[:28] or "Altro"
    n, i = base, 2
    while n in used:
        n = f"{base[:25]}_{i}"
        i += 1
    used.add(n)
    return n


def referenti_workbook(entries: list[dict], *, interno: bool = False) -> bytes:
    """``entries``: one dict per ente: ente, provincia, people (list of dicts with ruolo, nome,
    stato, email, telefono, fonte_url, data_fonte, motivo, verified_at)."""
    by_prov: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_prov[e.get("provincia") or "Senza provincia"].append(e)
    wb = Workbook()
    idx = wb.active
    idx.title = "Indice"
    idx.append(["Provincia", "Comuni", "Foglio"])
    used = {"Indice"}
    sheets: dict[str, str] = {}
    for prov in sorted(by_prov):
        sheets[prov] = _sheet_name(prov, used)
        idx.append([prov, len(by_prov[prov]), sheets[prov]])
    idx.append([])
    idx.append(["Totale", sum(len(v) for v in by_prov.values())])
    idx.append([])
    idx.append(["Se manca il nome del responsabile tecnico, scrivere alla PEC dell'ente " + FALLBACK_PEC + "."])

    head = ["Comune", *[label for _, label in RUOLI_COL], "Email", "PEC", "Telefono", "Mandato fino al"]
    if interno:
        head += ["Affidabilità", "% verificato", "Azione", "Fonti", "Verificato il", "Da confermare perché"]
    for prov in sorted(by_prov):
        ws = wb.create_sheet(sheets[prov])
        ws.append(head)
        for e in sorted(by_prov[prov], key=lambda x: x["ente"]):
            people = e["people"]
            pec = "; ".join(sorted({p["email"] for p in people if p["ruolo"] == "ente" and p.get("email")}))
            people = [p for p in people if p["ruolo"] != "ente"]
            emails = sorted({p["email"] for p in people if p.get("email")})
            phones = sorted({p["telefono"] for p in people if p.get("telefono")})
            ric = e.get("ricerca") or {}
            mand = ric.get("mandato_scadenza")
            row = [
                e["ente"], *[_cell(people, r) for r, _ in RUOLI_COL], "; ".join(emails), pec, "; ".join(phones),
                (f"{mand:%m/%Y}" + (" (in scadenza)" if mand and (mand.year, mand.month) <= (date.today().year + 1, date.today().month) else "") + " – stimata dall'ultima elezione") if mand else "",
            ]
            if interno:
                pct, label = affidabilita(people)
                row += [
                    label, pct, azione(people),
                    "; ".join(sorted({p["fonte_url"] for p in people if p.get("fonte_url")})),
                    max((str(p["verified_at"])[:10] for p in people if p.get("verified_at")), default=""),
                    "; ".join(sorted({p["motivo"] for p in people if p.get("motivo")})),
                ]
            ws.append(row)
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.freeze_panes = "A2"
        for i in range(1, len(head) + 1):
            ws.column_dimensions[get_column_letter(i)].width = 28 if i > 1 else 24
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    if interno:
        ck = wb.create_sheet("Checklist")
        ck.append(["Comune", *[f"{i}. {n}" for i, n in enumerate(_STEPS, 1)], "Lacune", "Stampa"])
        for e in sorted(entries, key=lambda x: x["ente"]):
            ric = e.get("ricerca") or {}
            by_n = {x["n"]: x for x in ric.get("passi", [])}
            cells = []
            for i in range(1, 13):
                x = by_n.get(i)
                cells.append("" if x is None else ("✔ " if x["ok"] else "✖ ") + " ".join(x.get("urls") or [x.get("nota") or ""])[:300])
            ck.append([e["ente"], *cells, "; ".join(ric.get("lacune") or []), ric.get("stampa") or ""])
        for c in ck[1]:
            c.font = Font(bold=True)
        ck.freeze_panes = "B2"
    for c in idx[1]:
        c.font = Font(bold=True)
    idx.column_dimensions["A"].width = 26
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
