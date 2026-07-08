"""Shared 3-tier adaptive HTML fetch: plain HTTP, then a headless-browser
fallback when the page content is too thin (typical of JS-rendered listings).

Extracted from ``SmartLLMCollector`` so other collectors (e.g. the watchlist
Albo Pretorio scan) can reuse the same fetch strategy without depending on
the ``Source``/``platform_type`` model that ``SmartLLMCollector`` is built
around.
"""
from __future__ import annotations

import re

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


async def adaptive_fetch(
    url: str,
    *,
    timeout: float,
    max_html_chars: int,
    playwright_min_chars: int,
    playwright_wait_ms: int,
    label: str,
) -> str:
    """Fetch ``url`` with plain HTTP; fall back to a headless browser if the
    cleaned content comes back thinner than ``playwright_min_chars``.
    """
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
            log.warning("adaptive_fetch.fetch_failed", label=label, url=url, error=str(exc))
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

    return cleaned


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
