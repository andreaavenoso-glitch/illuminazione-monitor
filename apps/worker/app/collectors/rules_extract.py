"""Extraction without Claude: free, deterministic, less flexible.

``extract_records_by_rules`` turns the candidate rows the page gate already isolated
(an entry that mentions one of the services) into records shaped like Claude's, using
only the wording of the entry: the act type from its title, the publication date from
the date written in the row, the deadline from the deadline wording of the row.
``extract_people_by_rules`` reads "Sindaco: Mario Rossi" style lines for the referenti.

Both are used when ``EXTRACTION_MODE=rules`` or, in ``auto``, when Claude is
unavailable (no credit): the scan then goes on instead of stopping. What they cannot
do -- pages without a list structure, odd layouts -- is skipped, never invented.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from app.collectors.referenti import looks_like_name
from shared_models.categories import is_noise
from shared_models.relevance import dates_in_text, deadline_from_text
from shared_models.services import mentions_any_service

# --- atto_tipo from the wording of the title (first match wins) -------------------------
_ATTO_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bando_gara", re.compile(r"bando di gara|procedura aperta|disciplinare di gara|avviso di gara|gara (europea|telematica)", re.I)),
    ("manifestazione_interesse", re.compile(r"manifestazion\w* d.interesse|sollecitazione di (manifestazion|proposte)|avviso (pubblico )?esplorativo", re.I)),
    ("indagine_mercato", re.compile(r"indagine (di mercato|esplorativa)|consultazione preliminare", re.I)),
    ("avviso_preinformazione", re.compile(r"preinformazione|pre-informazione", re.I)),
    ("proposta_ppp", re.compile(r"finanza di progetto|project financing|\bppp\b|partenariato pubblico|art\.? ?193|proposta di", re.I)),
    ("incarico_ppp", re.compile(r"advisor|valutatore|verifica del? pfte", re.I)),
    ("incarico_tecnico", re.compile(r"incarico|progettazione|\bpfte\b|\bpric\b|censimento|diagnosi energetica", re.I)),
)


def atto_tipo_from_text(text: str) -> str:
    for tipo, rx in _ATTO_RULES:
        if rx.search(text):
            return tipo
    return "determina_a_contrarre"  # a delibera / determina / atto di indirizzo on the service


def _publication_date(text: str, today: date) -> str | None:
    """First past date written in the row (within five years), ISO; None if none."""
    for d in dates_in_text(text):
        if today - timedelta(days=5 * 365) <= d <= today:
            return d.isoformat()
    return None


def extract_records_by_rules(
    candidates: Iterable[Any], *, ente: str | None, today: date
) -> list[dict[str, Any]]:
    """Records (Claude's shape) from the page gate's candidate rows. A row that is noise
    or mentions no service is left out."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for c in candidates:
        text = f"{c.title} {c.snippet}".strip()
        if is_noise(text, ente) or not mentions_any_service(text):
            continue
        key = (c.href, c.title)
        if key in seen:
            continue
        seen.add(key)
        deadline = deadline_from_text(c.snippet)
        out.append({
            "title": c.title[:500],
            "body": c.snippet[:2000],
            "url": c.href,
            "date": _publication_date(f"{c.date or ''} {c.snippet}", today),
            "atto_tipo": atto_tipo_from_text(c.title),
            "ente": ente,
            "scadenza": deadline.isoformat() if deadline else None,
            "extracted_by": "rules",
        })
    return out


# --- referenti ------------------------------------------------------------------------
_TITLE = r"(?:(?:Dott|Dr|Ing|Arch|Avv|Geom|Prof|Rag|Per|Ind)\.?(?:ssa)?\s+)*"
_CAP = r"[A-ZÀ-Ý][A-Za-zÀ-ÿ'’]{1,}"
_NAME = rf"{_TITLE}({_CAP}(?:\s+{_CAP}){{1,2}})"
_STOP = {
    "lavori", "pubblici", "area", "tecnica", "comune", "settore", "ufficio", "servizio", "giunta", "comunale",
    "consiglio", "sindaco", "sindaca", "assessore", "assessora", "vice", "responsabile", "urbanistica",
    "manutenzioni", "patrimonio", "ambiente", "energia", "illuminazione", "pubblica", "delega", "deleghe",
    "email", "telefono", "tel", "pec", "orari", "contatti", "segretario", "organi", "governo", "unico",
    "progetto", "procedimento", "dirigente", "opere", "tecnici", "tecnico", "infrastrutture", "trasporti",
    "bilancio", "tributi", "sociali", "cultura", "sport", "scuola", "turismo", "protezione", "civile",
}
_ROLES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("rup", re.compile(r"\bR\.?U\.?P\.?\b|responsabile unico del (?:progetto|procedimento)|responsabile del procedimento", re.I)),
    ("sindaco", re.compile(r"(?<![@\w.-])sindac[oa](?![@\w-])", re.I)),
    ("assessore", re.compile(r"\bassessor[ea]\b|\bvice ?sindaco\b", re.I)),
    ("responsabile_tecnico", re.compile(
        r"responsabile (?:dell['’]?\s*)?(?:area|settore|servizio|ufficio)\s+(?:tecnic\w+|lavori pubblici|manutenzion\w+|patrimonio|ll\.? ?pp\.?)|"
        r"dirigente (?:dell['’]?\s*)?(?:area|settore)\s+tecnic\w+", re.I)),
)
_ANY_ROLE = re.compile("|".join(f"(?:{rx.pattern})" for _, rx in _ROLES), re.I)
_DELEGA = re.compile(
    r"lavori pubblici|ll\.? ?pp|opere pubbliche|manutenzion|illuminazion|energi|ambiente|urbanistic|patrimonio|"
    r"servizi tecnici|infrastrutture",
    re.I,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\d)(?:\+39\s?)?0\d{1,3}[\s/.-]?\d{5,8}(?!\d)")


def _clean_name(raw: str) -> str | None:
    toks = raw.split()
    while toks and toks[0].lower().rstrip(".") in _STOP:
        toks.pop(0)
    if len(toks) < 2 or any(t.lower() in _STOP for t in toks):
        return None
    name = " ".join(t[0].upper() + t[1:].lower() if t.isupper() else t for t in toks)
    return name if looks_like_name(name) else None


def extract_people_by_rules(text: str) -> list[dict[str, Any]]:
    """People next to a role cue: "Sindaco: Mario Rossi", "Assessore ai LL.PP. Giulia
    Bianchi", "Mario Rossi - Sindaco", "Responsabile unico del progetto: Arch. Francesco
    Chiarella". The assessore needs a delega on public works / energy / environment
    nearby. Output has Claude's shape; ``verify_person`` still checks it on the text."""
    flat = " ".join(text.split())
    people: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for ruolo, rx in _ROLES:
        for m in rx.finditer(flat):
            after = flat[m.end(): m.end() + 110]
            # the next person's role ends this person's text
            nxt = _ANY_ROLE.search(after)
            if nxt:
                after = after[: nxt.start()]
            before = flat[max(0, m.start() - 60): m.start()]
            cand = None
            between = ""
            # the first real name after the role (delega words such as "Lavori Pubblici" are
            # skipped), or one just before it ("Mario Rossi - Sindaco")
            for nm in re.finditer(_NAME, after):
                cand = _clean_name(nm.group(1))
                if cand:
                    between = after[: nm.start()]
                    break
            if cand is None:
                bm = re.search(rf"{_NAME}\s*[-–,(:]*\s*$", before)
                if bm:
                    cand = _clean_name(bm.group(1))
                    between = after[:60]
            if cand is None:
                continue
            # the delega has to belong to THIS person: text between the role and the name
            if ruolo == "assessore" and not _DELEGA.search(flat[m.start(): m.end()] + " " + between):
                continue
            key = (ruolo, cand.lower())
            if key in seen:
                continue
            seen.add(key)
            tail = flat[m.end(): m.end() + 260]
            email = _EMAIL.search(tail)
            phone = _PHONE.search(tail)
            people.append({
                "nome": cand,
                "ruolo": ruolo,
                "qualifica": flat[m.start(): m.end()].strip()[:80],
                "email": email.group(0) if email else None,
                "telefono": phone.group(0) if phone else None,
                "citazione": flat[max(0, m.start() - 30): m.end() + 80][:200],
            })
    return people


