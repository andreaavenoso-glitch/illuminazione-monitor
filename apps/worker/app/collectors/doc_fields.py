"""Fields of a notice's documentation, extracted by rules (free). Each field keeps where it was found.

The set of fields is meant to grow (the data wanted for the presentation): add a function here and a
line in ``extract_fields``; nothing else changes (the table stores the fields as open JSON).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.collectors.rules_extract import extract_people_by_rules
from shared_models.relevance import dates_in_text, deadline_from_text

_CIG = re.compile(r"\bCIG\s*[:n.°]*\s*([0-9A-Z]{10})\b")
_MONEY = re.compile(
    r"(?:€|euro|eur)\s*([\d]{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)|"
    r"([\d]{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*(?:€|euro\b)",
    re.IGNORECASE,
)
_MONEY_LABEL = re.compile(
    r"importo|valore|base d.asta|canone|investimento|quadro economico|corrispettivo|spesa|costo", re.IGNORECASE
)
_DURATA = re.compile(r"durata[^.\n]{0,70}?(\d{1,2})\s*\(?\w*\)?\s*(ann[oi]|mesi)", re.IGNORECASE)
_PUNTI_LUCE = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d{2,6})\s*(?:punti\s*luce|apparecchi)", re.IGNORECASE)
_PROCEDURA = (
    ("art. 193 / finanza di progetto", re.compile(r"art\.?\s*193|finanza di progetto|project financing", re.I)),
    ("partenariato pubblico-privato", re.compile(r"partenariato pubblico|\bppp\b", re.I)),
    ("concessione", re.compile(r"\bconcessione\b", re.I)),
    ("procedura aperta", re.compile(r"procedura aperta", re.I)),
    ("procedura negoziata", re.compile(r"procedura negoziata", re.I)),
    ("accordo quadro", re.compile(r"accordo quadro", re.I)),
    ("manifestazione di interesse", re.compile(r"manifestazion\w* d.interesse|avviso esplorativo", re.I)),
)
_CRITERIO = re.compile(r"offerta economicamente pi[uù]['’]?\s+vantaggiosa|minor prezzo|\bOEPV\b", re.IGNORECASE)
_ORA_SCADENZA = re.compile(r"(?:entro|scadenz\w*|termine)[^.]{0,90}?ore\s*(\d{1,2})\s*[:.,]\s*(\d{2})", re.IGNORECASE)
_SOPRALLUOGO = re.compile(r"[^.]{0,100}\bsopralluog\w*[^.]{0,160}", re.IGNORECASE)
_CONSUMI = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?)\s*(MWh|kWh)\s*(?:/|all.|l.|per\s)?\s*anno", re.IGNORECASE)
_SPESA_ANNUA = re.compile(
    r"(?:spesa|costo|canone|onere)[^.€]{0,70}?(?:annu\w*|/\s*anno|all.anno)[^.€]{0,50}?(?:€|euro)\s*(\d[\d.]*(?:,\d{1,2})?)|"
    r"(?:€|euro)\s*(\d[\d.]*(?:,\d{1,2})?)\s*(?:/\s*anno|all.anno|annui|annuo)",
    re.IGNORECASE,
)
_PEC_ADDR = re.compile(r"[\w.+-]+@pec\.[\w.-]+|[\w.+-]+@[\w-]+\.legalmail\.it|[\w.+-]+@postecert\.it", re.IGNORECASE)
_FONDI = re.compile(r"PNRR|FESR|FSC|fondi (europei|strutturali)|conto termico|PR\s+\w+\s+FESR", re.IGNORECASE)


def _money_to_float(raw: str) -> float | None:
    try:
        return float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def extract_fields(docs: list[tuple[str, str]], today: date) -> dict[str, dict[str, Any]]:
    """``docs`` = [(name, text)]. Returns {field: {"valore", "fonte", "contesto"}} for what is written."""
    out: dict[str, dict[str, Any]] = {}

    def put(key: str, value: Any, fonte: str, contesto: str = "") -> None:
        if key not in out and value not in (None, "", []):
            out[key] = {"valore": value, "fonte": fonte, "contesto": " ".join(contesto.split())[:200]}

    for name, text in docs:
        flat = " ".join(text.split())
        if m := _CIG.search(flat):
            put("cig", m.group(1), name, flat[max(0, m.start() - 40): m.end() + 40])
        if d := deadline_from_text(flat):
            put("scadenza", d.isoformat(), name)
        amounts = []
        for m in _MONEY.finditer(flat):
            v = _money_to_float(m.group(1) or m.group(2))
            ctx = flat[max(0, m.start() - 90): m.end() + 20]
            if v and v >= 1000 and _MONEY_LABEL.search(ctx):
                amounts.append((v, ctx))
        if amounts:
            top = max(amounts, key=lambda a: a[0])
            put("importo_massimo_eur", top[0], name, top[1])
            put("importi_citati_eur", sorted({a[0] for a in amounts}, reverse=True)[:6], name)
        if m := _DURATA.search(flat):
            put("durata", f"{m.group(1)} {m.group(2)}", name, flat[max(0, m.start() - 20): m.end() + 30])
        if m := _PUNTI_LUCE.search(flat):
            put("punti_luce", m.group(1), name, flat[max(0, m.start() - 40): m.end() + 30])
        if m := _ORA_SCADENZA.search(flat):
            put("ora_scadenza", f"{int(m.group(1)):02d}:{m.group(2)}", name, flat[max(0, m.start() - 20): m.end() + 20])
        if m := _SOPRALLUOGO.search(flat):
            put("sopralluogo", " ".join(m.group(0).split())[:220], name)
        if m := _CONSUMI.search(flat):
            kwh = _money_to_float(m.group(1))
            if kwh:
                put("consumi_mwh", round(kwh / (1000 if m.group(2).lower() == "kwh" else 1), 1), name,
                    flat[max(0, m.start() - 40): m.end() + 20])
        if m := _SPESA_ANNUA.search(flat):
            v = _money_to_float(m.group(1) or m.group(2))
            if v and v >= 1000:
                put("spesa_annua_eur", v, name, flat[max(0, m.start() - 20): m.end() + 20])
        if m := _PEC_ADDR.search(flat):
            put("pec_invio", m.group(0).lower().rstrip(".-_"), name)
        procs = [label for label, rx in _PROCEDURA if rx.search(flat)]
        put("procedura", procs, name)
        if m := _CRITERIO.search(flat):
            put("criterio_aggiudicazione", m.group(0), name, flat[max(0, m.start() - 40): m.end() + 40])
        if m := _FONDI.search(flat):
            put("finanziamento", m.group(0), name, flat[max(0, m.start() - 60): m.end() + 60])
        for p in extract_people_by_rules(text):
            if p["ruolo"] == "rup":
                put("rup", p["nome"], name, p.get("citazione") or "")
        past = [d for d in dates_in_text(flat) if d <= today]
        if past:
            put("data_documento", max(past).isoformat(), name)
    return out
