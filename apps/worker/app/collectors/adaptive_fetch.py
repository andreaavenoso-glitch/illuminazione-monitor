"""Shared 3-tier adaptive HTML fetch: plain HTTP, then a headless-browser
fallback when the page content is too thin (typical of JS-rendered listings).

Extracted from ``SmartLLMCollector`` so other collectors (e.g. the watchlist
Albo Pretorio scan) can reuse the same fetch strategy without depending on
the ``Source``/``platform_type`` model that ``SmartLLMCollector`` is built
around.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger(__name__)

_USER_AGENT_HTTP = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_USER_AGENT_PLAYWRIGHT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def clean_html(html: str, max_chars: int) -> str:
    """Remove scripts/styles and collapse whitespace; truncate to budget."""
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    html = re.sub(r"\s+", " ", html)
    if len(html) > max_chars:
        html = html[:max_chars] + "...[TRONCATO]"
    return html


@dataclass(frozen=True)
class FetchResult:
    """Outcome of a fetch: the cleaned page text, plus a short error kind
    when no content could be read at all (``None`` whenever there is text,
    even if the plain HTTP attempt failed and the browser fallback recovered
    the page -- a source that can be read is a healthy one).
    """

    text: str
    error: str | None = None


def classify_fetch_error(exc: BaseException) -> str:
    """Short, stable label for why a fetch failed. The distinction matters
    for what to do next: ``http_404``/``dns`` mean the address is probably
    wrong (worth searching for the right one), ``http_403`` means the site
    blocks us (a different address won't help), ``ssl`` is the server's own
    certificate problem, ``timeout`` may well be transient.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TooManyRedirects):
        return "redirect"
    msg = str(exc).lower()
    if "certificate" in msg or "ssl" in msg:
        return "ssl"
    if (
        "name or service not known" in msg
        or "nodename nor servname" in msg
        or "temporary failure in name resolution" in msg
        or "getaddrinfo" in msg
    ):
        return "dns"
    if isinstance(exc, httpx.ConnectError):
        # The server exists but refused or dropped the connection.
        return "connect"
    if isinstance(exc, httpx.RemoteProtocolError):
        return "protocol"
    return "error"


async def adaptive_fetch_result(
    url: str,
    *,
    timeout: float,
    max_html_chars: int,
    playwright_min_chars: int,
    playwright_wait_ms: int,
    label: str,
) -> FetchResult:
    """Fetch ``url`` with plain HTTP; fall back to a headless browser if the
    cleaned content comes back thinner than ``playwright_min_chars``.
    """
    http_error: str | None = None
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT_HTTP},
    ) as http:
        try:
            resp = await http.get(url)
            resp.raise_for_status()
            html = resp.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            http_error = classify_fetch_error(exc)
            # str(exc) is empty for timeouts: log the kind and type instead.
            log.warning(
                "adaptive_fetch.fetch_failed", label=label, url=url,
                kind=http_error, exc_type=type(exc).__name__, error=str(exc),
            )
            html = ""

    cleaned = clean_html(html, max_html_chars) if html else ""
    log.info("adaptive_fetch.fetched", label=label, url=url, chars=len(cleaned))

    if len(cleaned) < playwright_min_chars:
        rendered = await _fetch_with_playwright(
            url,
            timeout=timeout,
            wait_ms=playwright_wait_ms,
            max_html_chars=max_html_chars,
            label=label,
        )
        if rendered and len(rendered) > len(cleaned):
            cleaned = rendered
            log.info("adaptive_fetch.playwright_fetched", label=label, url=url, chars=len(cleaned))

    if cleaned:
        return FetchResult(text=cleaned)
    return FetchResult(text="", error=http_error or "empty")


async def adaptive_fetch(
    url: str,
    *,
    timeout: float,
    max_html_chars: int,
    playwright_min_chars: int,
    playwright_wait_ms: int,
    label: str,
) -> str:
    """Text-only wrapper around :func:`adaptive_fetch_result`."""
    result = await adaptive_fetch_result(
        url,
        timeout=timeout,
        max_html_chars=max_html_chars,
        playwright_min_chars=playwright_min_chars,
        playwright_wait_ms=playwright_wait_ms,
        label=label,
    )
    return result.text


async def _fetch_with_playwright(
    url: str,
    *,
    timeout: float,
    wait_ms: int,
    max_html_chars: int,
    label: str,
) -> str | None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("adaptive_fetch.playwright_not_installed", label=label)
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent=_USER_AGENT_PLAYWRIGHT)
                await page.goto(url, timeout=int(timeout * 1000))
                await page.wait_for_timeout(wait_ms)
                html = await page.content()
            finally:
                await browser.close()
    except Exception as exc:  # noqa: BLE001 — browser automation has many failure modes
        log.warning("adaptive_fetch.playwright_failed", label=label, url=url, error=str(exc))
        return None

    return clean_html(html, max_html_chars)
