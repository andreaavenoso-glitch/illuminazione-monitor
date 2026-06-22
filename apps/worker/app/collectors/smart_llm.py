"""LLM-based universal collector for public-lighting procurement.

Strategy:
- Fetch the HTML of the source's known "list of bandi" URL.
- Strip noise (scripts/styles) and truncate to a budget.
- Send to Claude Haiku 4.5 with a cached system prompt describing the
  schema + Italian public-lighting perimeter rules.
- Get back a structured JSON list of records via output_config.format.
- Convert to RawRecordDrafts and let BaseCollector.persist do the rest.

Cost target: ~$0.01/call with cache hits on the system prompt (~3k tokens).
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

import anthropic
import httpx
import structlog
from app.collectors.base import BaseCollector, CollectorResult, RawRecordDraft
from app.config import get_worker_settings
from shared_models import RawRecord
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


SYSTEM_PROMPT = """Sei un assistente specializzato nell'estrazione di bandi di gara pubblici italiani per il settore dell'illuminazione pubblica.

# CONTESTO
Stai analizzando l'HTML di una pagina di un portale di e-procurement italiano (ANAC, TED EU, GURI, ASMECOMM, Traspare, SATER, ecc.) o di un sito di un ente pubblico. Devi estrarre TUTTI i bandi di gara visibili nella pagina che rientrano nel perimetro "illuminazione pubblica".

# PERIMETRO "ILLUMINAZIONE PUBBLICA"
Includi gare che riguardano:
- Illuminazione pubblica (lampioni, pali, corpi illuminanti su strade/piazze/parchi)
- Relamping LED (sostituzione corpi illuminanti)
- Telegestione / smart lighting / IoT illuminazione
- Riqualificazione energetica impianti di illuminazione
- Global service / manutenzione impianti IP
- Concessione del servizio di illuminazione pubblica
- Accordo quadro per forniture di apparecchi illuminanti
- Servizi di pronto intervento su impianti IP
- Progettazione impianti illuminazione pubblica
- Semafori e impianti semaforici (se inclusi nell'IP)
- Codici CPV: 34928510, 34993000, 50232000, 45316110

ESCLUDI gare che riguardano:
- Illuminazione di edifici/uffici/scuole interna
- Climatizzazione / riscaldamento
- Fotovoltaico (a meno che non sia integrato con IP)
- Facility management generale senza menzione illuminazione
- Materiale elettrico generico (cavi, quadri, ecc.) senza riferimento IP

# FORMATO OUTPUT
Restituisci SOLO un JSON con questa struttura:

{
  "records": [
    {
      "title": "Titolo del bando (max 500 char)",
      "body": "Descrizione/oggetto del bando (max 2000 char). Includi importi, scadenze, CIG, CUP, procedura, ente, regione se visibili.",
      "url": "URL assoluto del bando (se solo relativo, lascia null)",
      "date": "Data pubblicazione formato ISO YYYY-MM-DD oppure null se non trovabile",
      "importo_eur": 1234567.89,
      "cig": "CODICE_CIG_10_CARATTERI o null",
      "scadenza": "YYYY-MM-DD o null",
      "ente": "Nome del committente",
      "regione": "Nome regione italiana o null",
      "provincia": "Sigla provincia o null"
    }
  ]
}

# REGOLE CRUCIALI
1. Includi SOLO bandi che chiaramente rientrano nel perimetro IP. In dubbio, INCLUDI con flag nei body "PERIMETRO_INCERTO".
2. Se NESSUN bando della pagina rientra nel perimetro, restituisci {"records": []}.
3. NON inventare dati: se un campo non è leggibile, metti null.
4. Importi: estrai solo il valore numerico in euro (rimuovi €, separatori migliaia, gestisci virgola decimale italiana).
5. Date: converti formato italiano (gg/mm/aaaa) in ISO (yyyy-mm-dd).
6. CIG: codice alfanumerico di 10 caratteri maiuscoli, es. "A12B34C56D".
7. Massimo 50 record per chiamata. Se ce ne sono di più, prendi i più recenti.
8. NON aggiungere commenti, spiegazioni o testo fuori dal JSON.
"""


RECORDS_SCHEMA: dict[str, Any] = {
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
                    "importo_eur": {"type": ["number", "null"]},
                    "cig": {"type": ["string", "null"]},
                    "scadenza": {"type": ["string", "null"]},
                    "ente": {"type": ["string", "null"]},
                    "regione": {"type": ["string", "null"]},
                    "provincia": {"type": ["string", "null"]},
                },
                "required": ["title", "body"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["records"],
    "additionalProperties": False,
}


PLATFORM_SEARCH_URLS: dict[str, str] = {
    "ted": "https://api.ted.europa.eu/v3/notices/search?fields=publication-number,title,buyer-name,description-proc&query=classification-cpv%3D34928510%20OR%20classification-cpv%3D34993000%20OR%20classification-cpv%3D50232000%20OR%20classification-cpv%3D45316110",
    "anac": "https://dati.anticorruzione.it/superset/dashboard/appalti/",
    "bdncp": "https://dati.anticorruzione.it/opendata/dataset",
    "guri": "https://www.gazzettaufficiale.it/ricercaTesto?numero=&numeroSezione=&pagina=1&tipoSerie=serie_generale&tipoProvvedimento=BANDO&keyword=illuminazione+pubblica&giorno_dataPubblicazioneGazzetta=&mese_dataPubblicazioneGazzetta=&anno_dataPubblicazioneGazzetta=&giorno_a=&mese_a=&anno_a=",
    "asmecomm": "https://piattaforma.asmecomm.it/categorie_merceologiche.php",
    "traspare": "https://www.traspare.com/elenco-gare-pubbliche/",
    "tuttogare": "https://www.tuttogare.it/index.php?option=com_content&view=article&id=8",
    "sater": "https://piattaformaintercenter.regione.emilia-romagna.it/portale_ic/bandi-di-gara",
    "start_toscana": "https://start.toscana.it/tendering/tenders/list.do?searchType=2",
    "digitalpa": "https://www.digitalpa.it/gare-appalti",
    "portale_appalti": "https://portaleappalti.dsitalia.com/PortaleAppalti/it/homepage.wp",
    "sintel": "https://www.ariaspa.it/wps/portal/site/aria/acquistipervoi/Sintel/elencoBandi",
    "net4market": "https://app.albofornitori.it/avvisi",
    "acquistinrete": "https://www.acquistinretepa.it/opencms/opencms/scheda_iniziativa.html?idIniziativa=illuminazione",
    "sardegnacat": "https://www.sardegnacat.it/esop/guest/go/public/opportunity/current",
}


def _clean_html(html: str, max_chars: int) -> str:
    """Remove scripts/styles and collapse whitespace; truncate to budget."""
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    html = re.sub(r"\s+", " ", html)
    if len(html) > max_chars:
        html = html[:max_chars] + "...[TRONCATO]"
    return html


class SmartLLMCollector(BaseCollector):
    name: ClassVar[str] = "smart_llm"

    def __init__(
        self,
        source_id: UUID,
        base_url: str,
        *,
        platform_type: str = "",
        timeout: float = 60.0,
    ) -> None:
        super().__init__(source_id, base_url, timeout=timeout)
        self.platform_type = platform_type
        self.settings = get_worker_settings()
        self.search_url = PLATFORM_SEARCH_URLS.get(platform_type, self.base_url)

    async def fetch(self, *, since: datetime | None = None) -> list[RawRecordDraft]:
        if not self.settings.anthropic_api_key:
            log.warning(
                "smart_collector.no_api_key",
                platform=self.platform_type,
                hint="set ANTHROPIC_API_KEY in .env",
            )
            return []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
        ) as http:
            try:
                resp = await http.get(self.search_url)
                resp.raise_for_status()
                html = resp.text
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                log.warning(
                    "smart_collector.fetch_failed",
                    platform=self.platform_type,
                    url=self.search_url,
                    error=str(exc),
                )
                return []

        cleaned = _clean_html(html, self.settings.smart_collector_max_html_chars)
        log.info(
            "smart_collector.fetched",
            platform=self.platform_type,
            url=self.search_url,
            chars=len(cleaned),
        )

        records = await self._extract_with_claude(cleaned)
        return [self._to_draft(r) for r in records]

    async def _extract_with_claude(self, html: str) -> list[dict[str, Any]]:
        client = anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        user_msg = (
            f"Fonte: {self.platform_type or 'generic'}\n"
            f"URL: {self.search_url}\n"
            f"Data corrente: {datetime.now(tz=UTC).date().isoformat()}\n\n"
            f"HTML della pagina:\n\n{html}"
        )
        try:
            response = await client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=8000,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_msg}],
                output_config={"format": {"type": "json_schema", "schema": RECORDS_SCHEMA}},
            )
        except anthropic.APIError as exc:
            log.warning(
                "smart_collector.claude_error",
                platform=self.platform_type,
                error=str(exc),
            )
            return []

        log.info(
            "smart_collector.claude_ok",
            platform=self.platform_type,
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
            log.warning("smart_collector.bad_json", platform=self.platform_type)
            return []
        records = data.get("records", [])
        return records if isinstance(records, list) else []

    def _to_draft(self, record: dict[str, Any]) -> RawRecordDraft:
        url = record.get("url") or self.search_url
        date_str = record.get("date")
        raw_date: datetime | None = None
        if date_str:
            try:
                raw_date = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except ValueError:
                raw_date = None
        return RawRecordDraft(
            raw_url=url,
            raw_title=record.get("title"),
            raw_body=record.get("body"),
            raw_html=None,
            raw_date=raw_date,
            extracted={
                "importo_eur": record.get("importo_eur"),
                "cig": record.get("cig"),
                "scadenza": record.get("scadenza"),
                "ente": record.get("ente"),
                "regione": record.get("regione"),
                "provincia": record.get("provincia"),
                "extracted_by": "claude-haiku-4-5",
            },
        )

    async def persist(
        self,
        session: AsyncSession,
        drafts: list[RawRecordDraft],
    ) -> CollectorResult:
        # Override to skip the keyword perimeter filter — Claude already
        # applied semantic perimeter rules upstream.
        result = CollectorResult(found=len(drafts))
        seen: set[str] = set()
        for draft in drafts:
            checksum = draft.checksum()
            if checksum in seen:
                result.duplicates_removed += 1
                continue
            seen.add(checksum)
            session.add(
                RawRecord(
                    source_id=self.source_id,
                    raw_title=draft.raw_title,
                    raw_body=draft.raw_body,
                    raw_html=draft.raw_html,
                    raw_url=draft.raw_url,
                    raw_date=draft.raw_date or datetime.now(tz=UTC),
                    extracted_json=draft.extracted or None,
                    checksum=checksum,
                )
            )
            result.valid += 1
        return result
