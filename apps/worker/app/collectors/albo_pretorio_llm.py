"""Claude-based extraction of pre-tender signals (manifestazioni di
interesse, avvisi di preinformazione, indagini di mercato) from Albo
Pretorio-style municipal notice-board pages.

Albo Pretorio pages list heterogeneous municipal acts (delibere, determine,
ordinanze, bandi...), not just tenders, so this uses a dedicated prompt
instead of the "bandi di gara" one in smart_llm.py -- it looks specifically
for the pre-tender signals that classify_stato_procedurale (§9.3) maps to
``PRE_GARA`` via the ``atto_tipo`` field.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urljoin
from uuid import UUID

import anthropic
import structlog
from app.config import WorkerSettings
from bs4 import BeautifulSoup

log = structlog.get_logger(__name__)

# D.Lgs. 33/2013 art. 37 mandates this exact taxonomy for the "Bandi di gara
# e contratti" sub-section of Amministrazione Trasparente, so real
# implementations almost always use this phrase (or a close variant) as the
# menu label -- letting find_bandi_link follow straight to the procurement
# listing instead of extracting from the transparency section's landing
# page, which is usually just a navigation menu with little content of its
# own.
BANDI_LINK_PATTERNS = (
    "bandi di gara e contratti",
    "bandi di gara",
    "bandi gara e contratti",
    "bandi gara contratti",
)


def find_bandi_link(html: str, *, base_url: str) -> str | None:
    """Find a link to the "Bandi di gara e contratti" sub-section within an
    Amministrazione Trasparente landing page. Returns an absolute URL, or
    None if no matching link is found.
    """
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True).lower()
        if not text:
            continue
        if any(pattern in text for pattern in BANDI_LINK_PATTERNS):
            href = a["href"].strip()
            if href and not href.startswith("#") and not href.lower().startswith("javascript:"):
                return urljoin(base_url, href)
    return None

ALBO_SYSTEM_PROMPT = """Sei un assistente specializzato nell'individuare segnali pre-gara per il settore dell'illuminazione pubblica italiana.

# CONTESTO
Stai analizzando l'HTML della pagina di un Albo Pretorio comunale (o pagina "determine"/"avvisi" di un ente pubblico), che elenca atti amministrativi eterogenei: delibere, determine, ordinanze, bandi, avvisi, ecc. Devi individuare SOLO gli atti che segnalano una FUTURA procedura di affidamento nel perimetro "illuminazione pubblica", NON i bandi di gara già pubblicati (quelli sono raccolti altrove).

# COSA CERCARE (perimetro "segnale pre-gara" + illuminazione pubblica)
- Manifestazioni di interesse per affidamento di servizi/lavori di illuminazione pubblica, relamping LED, telegestione, riqualificazione energetica impianti IP
- Avvisi pubblici di preinformazione relativi a future gare di illuminazione pubblica
- Indagini di mercato / indagini conoscitive per affidamenti di illuminazione pubblica
- Avvisi esplorativi per la ricerca di operatori economici nel settore illuminazione pubblica
- Determine a contrarre che avviano formalmente una procedura di affidamento nel settore illuminazione pubblica

NON includere:
- Bandi di gara già in pubblicazione con scadenza di presentazione offerte (categoria raccolta da altre fonti)
- Esiti di gara / aggiudicazioni
- Atti che non riguardano l'illuminazione pubblica (delibere di bilancio, nomine, ordinanze di viabilità generiche, ecc.)

# FORMATO OUTPUT
Restituisci SOLO un JSON con questa struttura:

{
  "records": [
    {
      "title": "Titolo dell'atto (max 500 char)",
      "body": "Descrizione/oggetto dell'atto (max 2000 char)",
      "url": "URL assoluto dell'atto (se solo relativo, lascia null)",
      "date": "Data pubblicazione formato ISO YYYY-MM-DD oppure null",
      "atto_tipo": "manifestazione_interesse | avviso_preinformazione | indagine_mercato | determina_a_contrarre",
      "ente": "Nome dell'ente pubblico",
      "scadenza": "YYYY-MM-DD o null (scadenza per manifestare interesse, se presente)"
    }
  ]
}

# REGOLE CRUCIALI
1. Includi SOLO atti che rientrano chiaramente nel perimetro sopra descritto.
2. Se NESSUN atto della pagina rientra nel perimetro, restituisci {"records": []}.
3. NON inventare dati: se un campo non è leggibile, metti null.
4. Massimo 50 record per chiamata. Se ce ne sono di più, prendi i più recenti.
5. NON aggiungere commenti, spiegazioni o testo fuori dal JSON.
"""

ALBO_RECORDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "url": {"type": ["string", "null"]},
                    "date": {"type": ["string", "null"]},
                    "atto_tipo": {"type": "string"},
                    "ente": {"type": ["string", "null"]},
                    "scadenza": {"type": ["string", "null"]},
                },
                "required": ["title", "body", "atto_tipo"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["records"],
    "additionalProperties": False,
}


async def extract_albo_records(
    html: str,
    *,
    url: str,
    settings: WorkerSettings,
    label: str,
) -> list[dict[str, Any]]:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_msg = (
        f"Fonte: {label}\n"
        f"URL: {url}\n"
        f"Data corrente: {datetime.now(tz=UTC).date().isoformat()}\n\n"
        f"HTML della pagina:\n\n{html}"
    )
    try:
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=8000,
            system=[
                {
                    "type": "text",
                    "text": ALBO_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
            output_config={"format": {"type": "json_schema", "schema": ALBO_RECORDS_SCHEMA}},
        )
    except anthropic.APIError as exc:
        log.warning("albo_pretorio.claude_error", label=label, error=str(exc))
        return []

    log.info(
        "albo_pretorio.claude_ok",
        label=label,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read=getattr(response.usage, "cache_read_input_tokens", 0),
        cache_create=getattr(response.usage, "cache_creation_input_tokens", 0),
    )

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("albo_pretorio.bad_json", label=label)
        return []
    records = data.get("records", [])
    return records if isinstance(records, list) else []


def _checksum(url: str, title: str | None, raw_date: datetime | None) -> str:
    payload = f"{url}|{title or ''}|{raw_date or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_raw_record_kwargs(
    *,
    url_albo: str,
    source_id: UUID | None,
    entity_id: UUID | None,
    record: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Turn one extracted Albo Pretorio record into RawRecord constructor
    kwargs. Pure function -- no DB/Celery dependency -- so it's unit-testable
    without the worker's full dependency stack.
    """
    title = record.get("title")
    url = record.get("url")
    if not url:
        # Without a per-record URL every act on the page would collapse into
        # one RawRecord on upsert (the same collision bug fixed for Consip
        # and SmartLLM). Disambiguate with the act's own title instead.
        disambiguator = title or ""
        url = f"{url_albo}#atto={quote(disambiguator)}" if disambiguator else url_albo

    date_str = record.get("date")
    raw_date: datetime | None = None
    if date_str:
        try:
            raw_date = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
        except ValueError:
            raw_date = None

    return {
        "source_id": source_id,
        "entity_id": entity_id,
        "raw_title": title,
        "raw_body": record.get("body"),
        "raw_url": url,
        "raw_date": raw_date or now,
        "extracted_json": {
            "ente": record.get("ente"),
            "scadenza": record.get("scadenza"),
            "atto_tipo": record.get("atto_tipo"),
            "extracted_by": "claude-haiku-4-5-albo",
            "perimeter_prevalidated": True,
        },
        "checksum": _checksum(url, title, raw_date),
    }
