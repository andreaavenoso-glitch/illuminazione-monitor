"""Open the page / PDF behind every gara or manifestazione without a deadline and read it.

A published tender or call for interest always has a deadline, so one without a
readable deadline is "da verificare" and kept out of lists and emails (see
``shared_models.relevance.is_confirmed_open``). Doing that check by hand is just
opening the link and finding the date, which is exactly what this task does:

1. fetch the link (HTML, with the browser fallback for JS pages; or PDF text),
2. a deterministic reading of the deadline ("scadenza", "entro il", "termine per la
   presentazione...") -- free, settles most notices,
3. if the document only carries dates that are all old -> closed,
4. otherwise, when the text has deadline wording the pattern missed, one small
   Claude call; else "non_trovata" (stays to verify).
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from app import claude_state
from app.celery_app import celery_app
from app.collectors.adaptive_fetch import adaptive_fetch_result
from app.config import WorkerSettings, get_worker_settings
from app.db import SessionLocal
from bs4 import BeautifulSoup
from shared_models import ProcurementRecord
from shared_models.categories import categorize_record
from shared_models.relevance import (
    STRICT_CATEGORIES,
    deadline_from_text,
    only_old_dates,
    recent_date_in_text,
    today_utc,
)
from sqlalchemy import select

log = logging.getLogger(__name__)

RECENT_DAYS = 365
RECHECK_AFTER_DAYS = 7
MAX_PDF_PAGES = 12
MAX_TEXT_CHARS = 60000
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
_CLAUDE_CUES = ("scadenz", "entro il", "entro le", "termine", "presentazione delle", "manifestare")


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return " ".join(soup.get_text(" ").split())


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = [(p.extract_text() or "") for p in reader.pages[:MAX_PDF_PAGES]]
    except Exception:  # noqa: BLE001 - scanned/encrypted/corrupt PDF
        return ""
    return " ".join(" ".join(parts).split())


_ATTACH_TEXT = re.compile(
    r"avviso|bando|disciplinare|invito|manifestazione|lettera|capitolato|proposte?|determina|allegat", re.IGNORECASE
)
_ATTACH_HREF = re.compile(r"\.pdf($|\?)|/download|/allegat|getfile|/documento|attachment", re.IGNORECASE)
_NOT_ATTACH = (".jpg", ".jpeg", ".png", ".gif", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx", ".p7m")


def attachment_links(html: str, *, base_url: str, limit: int = 3) -> list[str]:
    """Links to the notice's own documents (the deadline is often only in the attached
    PDF, not in the page): same site, a PDF or a download/allegato link, preferring
    ones named like the notice ("Avviso pubblico", "Bando", "Disciplinare")."""
    from app.collectors.page_gate import safe_join

    soup = BeautifulSoup(html, "lxml")
    base_host = urlsplit(base_url).netloc
    scored: dict[str, int] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        path = href.lower().split("?")[0]
        if path.endswith(_NOT_ATTACH):
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        by_text = bool(_ATTACH_TEXT.search(text)) and len(text) <= 120
        by_href = bool(_ATTACH_HREF.search(href))
        if not (by_text and by_href) and not path.endswith(".pdf"):
            continue
        url = safe_join(base_url, href)
        if not url or urlsplit(url).netloc != base_host or url == base_url:
            continue
        scored[url] = max(scored.get(url, 0), (2 if by_text else 0) + (1 if path.endswith(".pdf") else 0))
    return [u for u, _ in sorted(scored.items(), key=lambda kv: -kv[1])[:limit]]


async def _fetch_plain(url: str) -> tuple[str, str | None]:
    """(text, raw html or None) with plain HTTP; ('', None) when it cannot be read."""
    low = url.lower().split("?")[0]
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=_UA) as c:
            r = await c.get(url)
        ctype = r.headers.get("content-type", "").lower()
        if r.status_code < 400 and ("pdf" in ctype or low.endswith(".pdf") or r.content[:4] == b"%PDF"):
            return pdf_to_text(r.content)[:MAX_TEXT_CHARS], None
        if r.status_code < 400 and len(r.text) > 3000:
            return html_to_text(r.text)[:MAX_TEXT_CHARS], r.text
    except Exception as exc:  # noqa: BLE001
        log.info("verify.plain_fetch_failed url=%s err=%s", url, exc)
    return "", None


async def fetch_document_text(url: str, settings: WorkerSettings, *, attachments: bool = True) -> str:
    """Text of the document behind ``url`` ('' when it cannot be read). For a web page,
    the text of its own attached documents (up to 3 PDFs) is appended: the deadline is
    often only there."""
    text, raw = await _fetch_plain(url)
    if not text:
        res = await adaptive_fetch_result(
            url,
            timeout=30,
            max_html_chars=settings.crawl_max_html_chars,
            playwright_min_chars=settings.smart_collector_playwright_min_chars,
            playwright_wait_ms=settings.smart_collector_playwright_wait_ms,
            label="verify",
            try_variants=False,
        )
        if not res.text:
            return ""
        text, raw = html_to_text(res.text)[:MAX_TEXT_CHARS], res.text
    if attachments and raw:
        parts = [text]
        for link in attachment_links(raw, base_url=url):
            att, _ = await _fetch_plain(link)
            if att:
                parts.append(f" [ALLEGATO {link}] {att}")
        text = " ".join(parts)[: MAX_TEXT_CHARS * 2]
    return text


def judge(text: str, today: date, category: str = "gara") -> tuple[str, date | None, date | None]:
    """(esito, scadenza, data dell'atto) from the document text, no network.

    esito: aperto (future deadline read) | chiuso (deadline passed / only old dates) |
    recente (pre-gara: its own date is in the window) | non_trovata | claude (gara or
    manifestazione whose text has deadline wording the pattern missed: ask Claude).
    """
    if not text.strip():
        return "non_trovata", None, None
    deadline = deadline_from_text(text)
    if deadline is not None:
        return ("aperto" if deadline >= today else "chiuso"), deadline, None
    if only_old_dates(text, today):
        return "chiuso", None, None
    if category not in STRICT_CATEGORIES:
        act = recent_date_in_text(text, today)
        return ("recente", None, act) if act else ("non_trovata", None, None)
    low = text.lower()
    if any(c in low for c in _CLAUDE_CUES):
        return "claude", None, None
    return "non_trovata", None, None


async def _claude_deadline(text: str, url: str, settings: WorkerSettings) -> date | None:
    from app.collectors.albo_pretorio_llm import extract_bando_detail

    details = await extract_bando_detail(text[:20000], url=url, settings=settings, label="verify")
    raw = (details or {}).get("scadenza")
    try:
        return date.fromisoformat(str(raw)[:10]) if raw else None
    except ValueError:
        return None


async def verify_region(region: str, *, limit: int = 200) -> dict[str, int]:
    settings = get_worker_settings()
    today = today_utc()
    now = datetime.now(tz=UTC)
    out = {"checked": 0, "aperto": 0, "chiuso": 0, "non_trovata": 0, "errors": 0}
    async with SessionLocal() as session:
        recs = (
            await session.execute(
                select(ProcurementRecord)
                .where(
                    ProcurementRecord.regione == region,
                    ProcurementRecord.master_record_id.is_(None),
                    ProcurementRecord.first_seen_at >= now - timedelta(days=RECENT_DAYS),
                )
                .order_by(ProcurementRecord.first_seen_at.desc())
            )
        ).scalars().all()
        todo: list[tuple[ProcurementRecord, str]] = []
        for r in recs:
            cat = categorize_record(r)
            if cat is None:
                continue
            if cat not in STRICT_CATEGORIES and r.scadenza is not None:
                continue  # pre-gara with a deadline: already dated
            if r.verified_at is not None and (
                r.verifica_esito != "non_trovata" or r.verified_at > now - timedelta(days=RECHECK_AFTER_DAYS)
            ):
                continue
            todo.append((r, cat))
        sem = asyncio.Semaphore(3)

        async def one(r: ProcurementRecord, cat: str) -> None:
            async with sem:
                try:
                    text = await asyncio.wait_for(fetch_document_text(r.link_bando, settings), timeout=120)
                    esito, deadline, act = judge(text, today, cat)
                    if esito == "claude":
                        # the deadline wording was not parsed: Claude when available, else unknown
                        deadline = (
                            await _claude_deadline(text, r.link_bando, settings)
                            if claude_state.use_claude(settings)
                            else None
                        )
                        esito = "non_trovata" if deadline is None else ("aperto" if deadline >= today else "chiuso")
                    if deadline is not None:
                        # the document is the source of truth, over what the list page said
                        r.scadenza = datetime(deadline.year, deadline.month, deadline.day, tzinfo=UTC)
                    if act is not None:
                        r.data_pubblicazione = datetime(act.year, act.month, act.day, tzinfo=UTC)
                    r.verifica_esito = esito
                    r.verified_at = now
                    out[esito] += 1
                except Exception as exc:  # noqa: BLE001
                    out["errors"] += 1
                    log.warning("verify.failed url=%s err=%s", r.link_bando, exc)
                out["checked"] += 1

        await asyncio.gather(*(one(r, c) for r, c in todo[:limit]))
        await session.commit()
    log.info("verify.done region=%s %s", region, out)
    return out


@celery_app.task(name="app.tasks.verify_records.verify_region_records", soft_time_limit=3600, time_limit=3700)
def verify_region_records(region: str, respect_stop: bool = False) -> dict[str, int]:
    from app.stop import region_stopped

    if respect_stop and asyncio.run(region_stopped(region)):  # chained after a collection the user stopped
        return {"checked": 0, "stopped": 1}
    return asyncio.run(verify_region(region))
