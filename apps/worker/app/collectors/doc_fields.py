"""Fields of a notice's documentation, extracted by rules (free). Each field keeps where it was found.

The set of fields is meant to grow (the data wanted for the presentation): add a function here and a
line in ``extract_fields``; nothing else changes (the table stores the fields as open JSON).
"""
from __future__ import annotations

import json
import re
from bisect import bisect_right
from datetime import date
from typing import Any

from app.collectors.census import MARKER as _CENSUS
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
    r"(?:spesa|costo|onere)[^.€]{0,70}?(?:annu\w*|/\s*anno|all.anno)[^.€]{0,50}?(?:€|euro)\s*(\d[\d.]*(?:,\d{1,2})?)|"
    r"(?:€|euro)\s*(\d[\d.]*(?:,\d{1,2})?)\s*(?:/\s*anno|all.anno|annui|annuo)",
    re.IGNORECASE,
)
# The yearly fee set as the BASE of the tender: not the historic spend of the comune ("canone annuo di riferimento ... € 230.000,00, oltre IVA")
_CANONE_ANNUO = re.compile(r"canone\s+annu\w*[^.€]{0,160}?(?:€|euro)\s*(\d[\d.]*(?:,\d{1,2})?)", re.IGNORECASE)
_PEC_ADDR = re.compile(r"[\w.+-]+@pec\.[\w.-]+|[\w.+-]+@[\w-]+\.legalmail\.it|[\w.+-]+@postecert\.it", re.IGNORECASE)
_ATTO = re.compile(
    r"(deliberazione|delibera|determina(?:zione)?)\s*(?:n\.?\s*\d+\s*)?(?:di\s+(giunta|consiglio)(?:\s+comunale)?|dirigenziale)?"
    r"[^.\n]{0,25}?\bn\.?\s*(\d{1,5})(?:\s*/\s*(\d{2,4}))?[^.\n]{0,20}?\bdel\s+(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})",
    re.IGNORECASE,
)
_IMPEGNO = re.compile(r"impegn\w*[^.€]{0,80}?(?:€|euro)\s*(\d[\d.]*(?:,\d{1,2})?)|(?:€|euro)\s*(\d[\d.]*(?:,\d{1,2})?)[^.]{0,40}?impegn", re.IGNORECASE)
_INCARICATO = re.compile(
    r"(?:affidat\w+|incaric\w+|conferit\w+|conferimento\s+(?:dell.)?incarico|a favore d\w+)\s+(?:a|alla|allo|al|del(?:la)?|di)\s+(?:(?:la\s+)?(?:societ[àa]|ditta|studio|r\.?t\.?p\.?)\s+)?"
    r"((?:[A-ZÀ-Ý][\w&'À-ÿ.-]*\s+){1,6}(?:S\.?\s?r\.?\s?l\.?|S\.?\s?p\.?\s?A\.?|S\.?\s?t\.?\s?p\.?|S\.?\s?c\.?\s?a\.?\s?r\.?\s?l\.?|S\.?\s?n\.?\s?c\.?))",
)
# A relative deadline: "entro e non oltre 60 (sessanta) giorni dalla data di pubblicazione del presente avviso".
_TERMINE_GIORNI = re.compile(
    r"entro\s+(?:e\s+non\s+oltre\s+)?(?:il\s+termine\s+(?:perentorio\s+)?di\s+)?(\d{1,3})\s*(?:\([a-zàèéìòù]+\)\s*)?giorni"
    r"(?:\s+(naturali(?:\s+e\s+consecutivi)?|solari|consecutivi|di\s+calendario|lavorativi|feriali))?"
    r"\s+(?:dalla|dal|da)\s+(?:data\s+(?:di\s+)?)?(pubblicazione|ricezione|invio|comunicazione|scadenza|notifica)",
    re.IGNORECASE,
)
_PER_PRESENTARE = re.compile(r"propost|offert|domand|manifestazion|candidatur|partecipa|present|pervenir|trasmett|inviar", re.IGNORECASE)
_NON_E_UN_TERMINE = re.compile(r"ricors|\btar\b|impugn|accesso agli atti|chiariment|quesit|richieste? di", re.IGNORECASE)
# --- significant elements of a PPP / tender notice -------------------------------------------------------------------
_PROPONENTE = re.compile(
    r"proposta\s+(?:della|di)\s+(?:societ[àa]\s+)?(?P<nome>(?:[A-ZÀ-Ý][\w&'À-ÿ-]*\s+){1,5}?(?:S\.?\s?p\.?\s?A|S\.?\s?r\.?\s?l|S\.?\s?c\.?\s?a\.?\s?r\.?\s?l|S\.?\s?t\.?\s?p))\s*\.?\s*,?\s*"
    r"(?:prot\.?\s*(?:n\.?\s*)?(?P<prot>\d+)\s+del\s+(?P<data>\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}))?",
)
_FINANZIAMENTO = re.compile(r"(PR\s+\w+\s+FESR(?:\s*FSE\+?)?\s*\d{4}\s*[–-]\s*\d{4}).{0,140}?Azione\s+([\dA-Z]+(?:\.[\dA-Z]+)*)", re.IGNORECASE)
_SCAD_FINANZIAMENTO = re.compile(r"domanda\s+regionale[^.]{0,60}?(\d{1,2}/\d{1,2}/\d{4})\s*,?\s*ore\s*(\d{1,2})\s*[:.,]\s*(\d{2})", re.IGNORECASE)
_REQUISITI = re.compile(r"requisiti\s+di\s+(?:capacit\w+|ordine|idoneit\w+|partecipazione)[^.]{0,220}\.", re.IGNORECASE)
_CRITERI_VALUTAZIONE = re.compile(r"criteri\s+di\s+valutazione[^.]{0,480}\.", re.IGNORECASE)
_ALLEGATO = re.compile(r"Allegat[oi]\s+([A-Z0-9]{1,3})\s*[–\-:]\s*([^.;]{5,70})")
_CONTRIBUTO = re.compile(r"contributo[^.%]{0,90}?(\d{1,3}(?:,\d+)?)\s*%", re.IGNORECASE)
_MEMBER = re.compile(r"\[([^\[\]]+?\.(?:pdf|docx|xlsx|txt|csv|html?|xml|md))\] ", re.IGNORECASE)
_FONDI = re.compile(r"PNRR|FESR|FSC|fondi (europei|strutturali)|conto termico|PR\s+\w+\s+FESR", re.IGNORECASE)


def _money_to_float(raw: str) -> float | None:
    try:
        return float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def split_members(text: str) -> list[tuple[str | None, str]]:
    """The text of an archive is "[file.pdf] text [other.docx] text": one piece per file, so that a field can name its file."""
    marks = [(m.start(), m.end(), m.group(1)) for m in _MEMBER.finditer(text) if not m.group(1).startswith("Archivio con")]
    if not marks:
        return [(None, text)]
    out: list[tuple[str | None, str]] = []
    if text[: marks[0][0]].strip():
        out.append((None, text[: marks[0][0]]))
    for k, (_, end, name) in enumerate(marks):
        out.append((name, text[end: marks[k + 1][0] if k + 1 < len(marks) else len(text)]))
    return out


def _pos_of_date(flat: str, d: date) -> int | None:
    m = re.search(rf"\b0?{d.day}\s*[/.\-]\s*0?{d.month}\s*[/.\-]\s*(?:{d.year}|{d.year % 100:02d})\b", flat)
    return m.start() if m else None


def extract_fields(docs: list[tuple[str, str]], today: date) -> dict[str, dict[str, Any]]:
    """``docs`` = [(name, text)]. Returns {field: {"valore", "fonte", "contesto"}} for what is written. ``fonte`` names the
    document and, when it has several pages (a PDF, with a form feed between pages), the page: "avviso.pdf, p. 5"; a file
    inside an archive is named "allegati.zip › relazione.pdf"."""
    out: dict[str, dict[str, Any]] = {}

    def scan(name: str, text: str) -> None:
        parts = [" ".join(p.split()) for p in text.split("\f")]
        flat = " ".join(parts)
        starts, acc = [], 0
        for part in parts:
            starts.append(acc)
            acc += len(part) + 1

        def put(key: str, value: Any, contesto: str = "", pos: int | None = None, replace: bool = False) -> None:
            if value in (None, "", []) or (key in out and not replace):
                return
            fonte = name if pos is None or len(parts) < 2 else f"{name}, p. {bisect_right(starts, pos)}"
            out[key] = {"valore": value, "fonte": fonte, "contesto": " ".join(contesto.split())[:200]}

        def near(m: re.Match, before: int = 40, after: int = 40) -> str:
            return flat[max(0, m.start() - before): m.end() + after]

        if cm := _CENSUS.search(text):  # a lighting census read by column (census.py): the data set
            try:
                stats = json.loads(cm.group(1))
            except ValueError:
                stats = None
            if stats:
                sheets = " e ".join(f"«{t}»" for t in stats.get("fogli", []))
                put("censimento", stats, f"fogli {sheets}", replace=True)
                put("punti_luce", str(stats["apparecchi"]), "apparecchi censiti", replace=True)
                if stats.get("consumo_mwh"):
                    put("consumi_mwh", float(stats["consumo_mwh"]), "stima: potenza installata × ore annue dei quadri", replace=True)
        if m := _CIG.search(flat):
            put("cig", m.group(1), near(m), m.start())
        if d := deadline_from_text(flat):
            put("scadenza", d.isoformat(), pos=_pos_of_date(flat, d))
        amounts = []
        for m in _MONEY.finditer(flat):
            v = _money_to_float(m.group(1) or m.group(2))
            ctx = flat[max(0, m.start() - 90): m.end() + 20]
            if v and v >= 1000 and _MONEY_LABEL.search(ctx):
                amounts.append((v, ctx, m.start()))
        if amounts:
            top = max(amounts, key=lambda a: a[0])
            put("importo_massimo_eur", top[0], top[1], top[2])
            put("importi_citati_eur", sorted({a[0] for a in amounts}, reverse=True)[:6])
        if m := _DURATA.search(flat):
            put("durata", f"{m.group(1)} {m.group(2)}", near(m, 20, 30), m.start())
        if m := _PUNTI_LUCE.search(flat):
            put("punti_luce", m.group(1), near(m, 40, 30), m.start())
        if m := _ORA_SCADENZA.search(flat):
            put("ora_scadenza", f"{int(m.group(1)):02d}:{m.group(2)}", near(m, 20, 20), m.start())
        if m := _SOPRALLUOGO.search(flat):
            put("sopralluogo", " ".join(m.group(0).split())[:220], pos=m.start())
        if m := _CONSUMI.search(flat):
            kwh = _money_to_float(m.group(1))
            if kwh:
                put("consumi_mwh", round(kwh / (1000 if m.group(2).lower() == "kwh" else 1), 1), near(m, 40, 20), m.start())
        if m := _SPESA_ANNUA.search(flat):
            v = _money_to_float(m.group(1) or m.group(2))
            if v and v >= 1000:
                put("spesa_annua_eur", v, near(m, 20, 20), m.start())
        if m := _CANONE_ANNUO.search(flat):
            v = _money_to_float(m.group(1))
            if v and v >= 1000:
                put("canone_annuo_eur", v, near(m, 20, 60), m.start())
        if m := _PEC_ADDR.search(flat):
            put("pec_invio", m.group(0).lower().rstrip(".-_"), pos=m.start())
        atti = []
        for m in _ATTO.finditer(flat):
            kind = {"deliberazione": "Delibera", "delibera": "Delibera"}.get(m.group(1).lower(), "Determina")
            organ = {"giunta": " di Giunta", "consiglio": " di Consiglio"}.get((m.group(2) or "").lower(), "")
            anno = f"/{m.group(4)}" if m.group(4) else ""
            atti.append((f"{kind}{organ} n. {m.group(3)}{anno} del {m.group(5)}", m))
        if atti:
            put("atto_estremi", atti[0][0], near(atti[0][1], 20, 30), atti[0][1].start())
            put("atti_citati", list(dict.fromkeys(a for a, _ in atti))[:10], pos=atti[0][1].start())
        if m := _IMPEGNO.search(flat):
            v = _money_to_float(m.group(1) or m.group(2))
            if v and v >= 500:
                put("impegno_spesa_eur", v, near(m, 20, 30), m.start())
        if m := _INCARICATO.search(flat):
            put("incaricato", " ".join(m.group(1).split()), near(m, 30, 20), m.start())
        if m := _PROPONENTE.search(flat):
            nome = re.sub(r"\s+\.", ".", " ".join(m.group("nome").split()))
            nome = nome if nome.endswith(".") or not re.search(r"S\.?p\.?A$|S\.?r\.?l$", nome, re.I) else nome + "."
            put("proponente", {"nome": nome, "protocollo": m.group("prot"), "data": m.group("data")}, near(m, 30, 60), m.start())
        for m in _TERMINE_GIORNI.finditer(flat):
            before = flat[max(0, m.start() - 140): m.start()]
            if m.group(3).lower() != "pubblicazione" or _NON_E_UN_TERMINE.search(before) or not _PER_PRESENTARE.search(flat[max(0, m.start() - 200): m.end() + 60]):
                continue  # an appeal term, a request for clarifications, a term counted from something else
            kind = (m.group(2) or "").lower()
            put("termine_giorni", {"giorni": int(m.group(1)), "lavorativi": kind in ("lavorativi", "feriali")}, near(m, 60, 40), m.start())
            break
        procs = [(label, rx.search(flat)) for label, rx in _PROCEDURA]
        found = [(label, mm) for label, mm in procs if mm]
        put("procedura", [label for label, _ in found], pos=found[0][1].start() if found else None)
        if m := _CRITERIO.search(flat):
            put("criterio_aggiudicazione", m.group(0), near(m), m.start())
        if m := _FINANZIAMENTO.search(flat):
            prog = re.sub(r"\s*([–-])\s*", r"\1", " ".join(m.group(1).split()))
            put("finanziamento", f"{prog}, Azione {m.group(2)}", near(m, 20, 80), m.start())
        elif m := _FONDI.search(flat):
            put("finanziamento", m.group(0), near(m, 60, 60), m.start())
        if m := _SCAD_FINANZIAMENTO.search(flat):
            dd, mo, yy = (int(x) for x in m.group(1).split("/"))
            put("scadenza_finanziamento", f"{yy:04d}-{mo:02d}-{dd:02d} {int(m.group(2)):02d}:{m.group(3)}", near(m, 40, 20), m.start())
        if m := _CONTRIBUTO.search(flat):
            put("contributo_percentuale", m.group(1).replace(",", "."), near(m, 40, 20), m.start())
        if m := _REQUISITI.search(flat):
            put("requisiti", " ".join(m.group(0).split())[:260], pos=m.start())
        if m := _CRITERI_VALUTAZIONE.search(flat):
            put("criteri_valutazione", " ".join(m.group(0).split())[:260], pos=m.start())
        allegati = list(dict.fromkeys(f"Allegato {m.group(1)} – {m.group(2).strip()}" for m in _ALLEGATO.finditer(flat)))
        if allegati:
            put("allegati_citati", allegati[:8], pos=_ALLEGATO.search(flat).start())
        for p in extract_people_by_rules(text.replace("\f", " ")):
            if p["ruolo"] == "rup":
                pos = flat.find((p.get("citazione") or "")[:30]) if p.get("citazione") else -1
                put("rup", p["nome"], p.get("citazione") or "", pos if pos >= 0 else None)
        past = [d for d in dates_in_text(flat) if d <= today]
        if past:
            put("data_documento", max(past).isoformat())

    for name, text in docs:
        for member, piece in split_members(text):
            scan(name if member is None else f"{name} › {member}", piece)
    return out
