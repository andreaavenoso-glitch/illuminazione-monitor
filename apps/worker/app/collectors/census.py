"""The census sheet of the lighting plant ("Scheda censimento livello 2"): the DATA SET behind the slides.

A comune attaches, among its technical documents, a workbook with a sheet of light fittings ("centri luminosi", one row per
fitting: source, power, support, line...) and one of electrical panels ("quadri"). Read as plain text the cells say nothing;
read by column they give the figures the Gate sheet asks for. Everything is counted from the rows; the only estimate is the
consumption (installed power x yearly hours of the panels) and it is labelled as such.
"""
from __future__ import annotations

import io
import json
import re
from collections import Counter
from typing import Any

MARKER = re.compile(r"\[\[CENSIMENTO (\{.*?\})\]\]", re.DOTALL)
_SAMPLE = "da nascondere"  # the example row of the template, not a plant


def _norm(h: Any) -> str:
    return " ".join(str(h or "").split()).lower()


def _num(x: Any) -> float | None:
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _col(headers: list[str], *needles: str, exclude: tuple[str, ...] = ()) -> int | None:
    for i, h in enumerate(headers):
        if all(n in h for n in needles) and not any(e in h for e in exclude):
            return i
    return None


def _count(rows: list[tuple], idx: int | None, n: int = 6) -> dict[str, int]:
    if idx is None:
        return {}
    c = Counter(str(r[idx]).strip() for r in rows if r[idx] not in (None, "") and str(r[idx]).strip() not in ("N.R.", "#N/A"))
    return dict(c.most_common(n))


def census_stats(content: bytes) -> dict[str, Any] | None:
    """The figures of a census workbook, or None when the file is not one (no sheet of fittings with source and power)."""
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 -- not a workbook, corrupt, protected
        return None
    fittings = panels = None
    for ws in wb.worksheets:
        head = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        h = [_norm(c) for c in head]
        if any("tipo sorgente" in x for x in h) and any("potenza sorgente" in x for x in h):
            fittings = (ws.title, h, ws)
        elif any("id quadro" in x or "codice quadro" in x for x in h):
            panels = (ws.title, h, ws)
    if fittings is None:
        return None
    title, h, ws = fittings
    rows = [r for r in ws.iter_rows(min_row=2, values_only=True)
            if any(c not in (None, "") for c in r) and str(r[0]).strip().lower() != _SAMPLE]
    if not rows:
        return None
    i_cl = _col(h, "centro luminoso")
    i_pw = _col(h, "potenza sorgente", exclude=("alim", "+"))
    i_pwa = _col(h, "potenza sorgente", "alim") or _col(h, "potenza sorgente", "+")
    i_sost = _col(h, "tipo sostegno")
    i_h = _col(h, "altezza sostegno")
    watts = []
    for r in rows:
        w = _num(r[i_pwa]) if i_pwa is not None else None
        watts.append(w if w else (_num(r[i_pw]) if i_pw is not None else None))
    watts = [w for w in watts if w]
    poles = [r for r in rows if i_sost is not None and r[i_sost] not in (None, "") and str(r[i_sost]).strip().lower() not in ("nessuno", "n.r.")]
    heights = [x for x in (_num(r[i_h]) for r in rows) if x] if i_h is not None else []
    n_panels, ore = None, None
    if panels is not None:
        ph = panels[1]
        qrows = [r for r in panels[2].iter_rows(min_row=2, values_only=True)
                 if any(c not in (None, "") for c in r) and str(r[0]).strip().lower() != _SAMPLE]
        n_panels = len(qrows) or None
        i_ore = _col(ph, "ore annue")
        hours = [x for x in (_num(r[i_ore]) for r in qrows) if x] if i_ore is not None else []
        ore = Counter(hours).most_common(1)[0][0] if hours else None
    return {
        "fogli": [title] + ([panels[0]] if panels else []),
        "apparecchi": len(rows),
        "centri_luminosi": len({r[i_cl] for r in rows if i_cl is not None and r[i_cl] not in (None, "")}) or None,
        "quadri": n_panels,
        "sorgenti": _count(rows, _col(h, "tipo sorgente")),
        "potenza_kw": round(sum(watts) / 1000, 1) if watts else None,
        "ore_annue": int(ore) if ore else None,
        "consumo_mwh": round(sum(watts) * ore / 1e6) if watts and ore else None,
        "tipo_apparecchio": _count(rows, _col(h, "tipo apparecchio")),
        "stato_apparecchio": _count(rows, _col(h, "stato apparecchio")),
        "tipo_sostegno": _count(rows, i_sost),
        "sostegni_con_palo": len(poles),
        "materiale_sostegno": _count(rows, _col(h, "materiale sostegno")),
        "stato_sostegno": _count(rows, _col(h, "stato sostegno")),
        "altezza_media_m": round(sum(heights) / len(heights), 1) if heights else None,
        "tipo_linea": _count(rows, _col(h, "tipo linea")),
        "ambito": _count(rows, _col(h, "tipologia dell")),
    }


def census_text(stats: dict[str, Any]) -> str:
    """The census as text for the field extractor: a machine-readable marker plus one human line."""
    parts = [f"[[CENSIMENTO {json.dumps(stats, ensure_ascii=False)}]]", f"Scheda di censimento degli impianti: {stats['apparecchi']} apparecchi"]
    if stats.get("centri_luminosi"):
        parts.append(f"su {stats['centri_luminosi']} centri luminosi")
    if stats.get("quadri"):
        parts.append(f"e {stats['quadri']} quadri")
    return " ".join(parts) + "."
