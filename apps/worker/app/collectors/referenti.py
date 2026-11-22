"""Find the political and technical contacts of an ente from its own website.

Nothing is inferred. Claude reads a page and proposes people; every proposal is then
checked deterministically against the page text: the name must be written there (a
hallucinated name is dropped), an e-mail or phone must appear literally, and the
person is "verificato" only when the role wording sits next to the name.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import anthropic
import structlog
from app.collectors.page_gate import safe_join
from app.config import WorkerSettings
from app.usage import record_usage
from bs4 import BeautifulSoup

log = structlog.get_logger(__name__)

RUOLI = ("sindaco", "assessore", "responsabile_tecnico", "rup")

# Menu entries that lead to the pages where these people are listed, with a weight.
_LINK_HINTS: tuple[tuple[str, int], ...] = (
    ("organi di governo", 30), ("amministratori", 30), ("giunta", 28), ("sindaco", 28),
    ("organi di indirizzo", 25), ("titolari di incarichi", 25), ("organizzazione", 20),
    ("organigramma", 25), ("uffici", 15), ("lavori pubblici", 25), ("area tecnica", 25),
    ("settore tecnico", 25), ("urbanistica", 10), ("personale", 12), ("responsabili", 20),
    ("telefoni", 12), ("contatti", 10), ("dirigenti", 15), ("posizioni organizzative", 15),
)
_ROLE_WORDS = re.compile(
    r"sindaco|assessore|assessora|vice ?sindaco|responsabile|rup|area tecnica|lavori pubblici|"
    r"ll\.? ?pp\.?|settore tecnico|ufficio tecnico",
    re.IGNORECASE,
)
_ROLE_NEAR = {
    "sindaco": re.compile(r"sindaco|sindaca", re.IGNORECASE),
    "assessore": re.compile(r"assessor[ea]|vice ?sindaco", re.IGNORECASE),
    "responsabile_tecnico": re.compile(
        r"responsabile|dirigente|area tecnica|settore tecnico|ufficio tecnico|lavori pubblici|ll\.? ?pp", re.IGNORECASE
    ),
    "rup": re.compile(r"\brup\b|responsabile unico|responsabile del procedimento", re.IGNORECASE),
}


def _squash(text: str) -> str:
    return " ".join(re.sub(r"[^\w@.+\-]+", " ", text.lower()).split())


def site_root(url: str) -> str | None:
    p = urlsplit(url)
    if not p.netloc:
        return None
    return urlunsplit((p.scheme or "https", p.netloc, "/", "", ""))


def rank_people_links(html: str, *, base_url: str, limit: int = 5) -> list[str]:
    """Links of a page most likely to lead to the administrators / technical offices,
    best first (menu entries only: short link text)."""
    soup = BeautifulSoup(html, "lxml")
    best: dict[str, int] = {}
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).lower().split())
        href = a["href"].strip()
        if not text or len(text) > 60 or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if href.lower().split("?")[0].endswith((".pdf", ".jpg", ".png", ".zip", ".doc", ".docx")):
            continue
        score = max((w for kw, w in _LINK_HINTS if kw in text), default=0)
        if score == 0:
            continue
        url = safe_join(base_url, href)
        if url and urlsplit(url).netloc == urlsplit(base_url).netloc:
            best[url] = max(best.get(url, 0), score)
    return [u for u, _ in sorted(best.items(), key=lambda kv: -kv[1])[:limit]]


def has_role_words(text: str) -> bool:
    return bool(_ROLE_WORDS.search(text))


def verify_person(person: dict[str, Any], page_text: str) -> dict[str, Any] | None:
    """The person with only what the page text backs up, or None when the name is not
    written there. ``stato`` = verificato when the role wording is within 160
    characters of the name."""
    nome = " ".join(str(person.get("nome") or "").split())
    ruolo = person.get("ruolo")
    if len(nome) < 5 or " " not in nome or ruolo not in RUOLI:
        return None
    hay = _squash(page_text)
    needle = _squash(nome)
    tokens = needle.split()
    reversed_name = " ".join(reversed(tokens))
    pos = hay.find(needle)
    if pos < 0:
        pos = hay.find(reversed_name)  # "Rossi Mario" listed surname first
    if pos < 0:
        return None
    window = hay[max(0, pos - 160): pos + len(needle) + 160]
    stato = "verificato" if _ROLE_NEAR[ruolo].search(window) else "da_confermare"

    def literal(value: Any) -> str | None:
        v = str(value or "").strip()
        return v if v and _squash(v) in hay else None

    return {
        "nome": nome,
        "ruolo": ruolo,
        "qualifica": (str(person.get("qualifica") or "").strip() or None),
        "email": literal(person.get("email")),
        "telefono": literal(person.get("telefono")),
        "citazione": (str(person.get("citazione") or "").strip()[:240] or None),
        "stato": stato,
    }


SYSTEM_PROMPT = """Estrai da una pagina del sito di un comune italiano le persone che servono per contattare l'ente su un appalto di illuminazione pubblica e servizi collegati.

# RUOLI (campo "ruolo")
- sindaco
- assessore: assessore (o vicesindaco) con delega a lavori pubblici, manutenzioni, illuminazione pubblica, energia, ambiente, urbanistica o patrimonio
- responsabile_tecnico: responsabile/dirigente dell'area o settore tecnico, lavori pubblici, manutenzioni, patrimonio
- rup: Responsabile Unico del Progetto/Procedimento, SOLO se la pagina lo indica per un atto

# REGOLE
1. Riporta SOLO persone il cui nome e cognome sono SCRITTI nella pagina. NON dedurre, NON completare, NON usare conoscenze esterne.
2. Per il sindaco e gli assessori includi solo chi e' attuale secondo la pagina; ignora ex amministratori.
3. email e telefono: SOLO se scritti nella pagina accanto alla persona o al suo ufficio, copiati identici; altrimenti null.
4. "qualifica": la qualifica come scritta (es. "Assessore ai Lavori Pubblici"). "citazione": breve frase copiata dalla pagina (max 200 caratteri) che contiene il nome.
5. Se non trovi nessuno, restituisci una lista vuota.

# FORMATO
Solo JSON: {"persone": [{"nome": "...", "ruolo": "...", "qualifica": "...|null", "email": "...|null", "telefono": "...|null", "citazione": "..."}]}
"""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "persone": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "ruolo": {"type": "string", "enum": list(RUOLI)},
                    "qualifica": {"type": ["string", "null"]},
                    "email": {"type": ["string", "null"]},
                    "telefono": {"type": ["string", "null"]},
                    "citazione": {"type": ["string", "null"]},
                },
                "required": ["nome", "ruolo", "qualifica", "email", "telefono", "citazione"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["persone"],
    "additionalProperties": False,
}


async def extract_people(text: str, *, url: str, ente: str, settings: WorkerSettings) -> list[dict[str, Any]]:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1500,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"Ente: {ente}\nURL: {url}\n\nTesto della pagina:\n\n{text[:30000]}"}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
    except anthropic.APIError as exc:
        log.warning("referenti.claude_error", url=url, error=str(exc))
        return []
    await record_usage(response.usage, model=settings.anthropic_model, purpose="referenti", label=ente[:60])
    raw = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    people = data.get("persone") if isinstance(data, dict) else None
    return people if isinstance(people, list) else []


def merge_people(found: list[tuple[dict[str, Any], str]]) -> list[dict[str, Any]]:
    """One entry per (ruolo, name); a verified copy beats an unconfirmed one, and
    contacts from any copy fill the gaps. Each entry keeps the page it was read from."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for person, url in found:
        key = (person["ruolo"], _squash(person["nome"]))
        cur = out.get(key)
        entry = {**person, "fonte_url": url}
        if cur is None:
            out[key] = entry
            continue
        if cur["stato"] != "verificato" and person["stato"] == "verificato":
            entry["email"] = entry["email"] or cur["email"]
            entry["telefono"] = entry["telefono"] or cur["telefono"]
            out[key] = entry
        else:
            cur["email"] = cur["email"] or person["email"]
            cur["telefono"] = cur["telefono"] or person["telefono"]
    return list(out.values())
