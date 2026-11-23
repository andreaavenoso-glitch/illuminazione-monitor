"""Shared 3-tier adaptive HTML fetch: plain HTTP, then a headless-browser
fallback when the page content is too thin (typical of JS-rendered listings).

Extracted from ``SmartLLMCollector`` so other collectors (e.g. the watchlist
Albo Pretorio scan) can reuse the same fetch strategy without depending on
the ``Source``/``platform_type`` model that ``SmartLLMCollector`` is built
around.
"""
from __future__ import annotations

import re
from collections import Counter
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
    # The address that actually answered; differs from the requested one when
    # a variant (www on/off, http) had to be used.
    url: str | None = None


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


_BROWSER_ERROR_KINDS = (
    ("ERR_CONNECTION_RESET", "reset"),
    ("ERR_NAME_NOT_RESOLVED", "dns"),
    ("ERR_CERT", "ssl"),
    ("ERR_SSL", "ssl"),
    ("ERR_CONNECTION_REFUSED", "connect"),
    ("ERR_TIMED_OUT", "timeout"),
    ("Timeout", "timeout"),
)


def classify_browser_error(message: str) -> str | None:
    """Kind for a Playwright navigation error, or None when unrecognised.
    ``reset`` (the server cut the connection) is the usual signature of a
    firewall/WAF refusing automated or datacenter clients."""
    for needle, kind in _BROWSER_ERROR_KINDS:
        if needle in message:
            return kind
    return None


def url_variants(url: str, error: str | None) -> list[str]:
    """Other spellings of ``url`` worth one quick try after a connection-level
    failure: www on/off (the most common cause: a site answering only on one
    of them, e.g. unionecomunimessapia.it works, www.unionecomunimessapia.it
    resets), plus plain http when the failure was a certificate problem."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    host = parts.netloc
    if not host:
        return []
    toggled = host[4:] if host.lower().startswith("www.") else f"www.{host}"
    out = [urlunsplit(parts._replace(netloc=toggled))]
    if error == "ssl":
        out.append(urlunsplit(parts._replace(scheme="http")))
        out.append(urlunsplit(parts._replace(scheme="http", netloc=toggled)))
    return [v for v in dict.fromkeys(out) if v != url]


# Only connection-level failures can be fixed by another spelling of the
# address. A page that answered (404/403, or 200 with nothing in it) would
# just be asked again for no reason.
_VARIANT_ERRORS = frozenset({"connect", "reset", "dns", "ssl", "timeout", "error", "protocol", "redirect"})


def _worth_trying_variants(error: str | None) -> bool:
    return error in _VARIANT_ERRORS


async def _adaptive_fetch_result_impl(
    url: str,
    *,
    timeout: float,
    max_html_chars: int,
    playwright_min_chars: int,
    playwright_wait_ms: int,
    label: str,
    try_variants: bool = True,
) -> FetchResult:
    """Fetch ``url``; if it cannot be reached at all, quickly try its likely
    variants (www on/off, http). The result's ``url`` is the address that
    worked, so callers can resolve links against it and store the fix."""
    kwargs = {
        "max_html_chars": max_html_chars,
        "playwright_min_chars": playwright_min_chars,
        "playwright_wait_ms": playwright_wait_ms,
        "label": label,
    }
    first = await _fetch_single(url, timeout=timeout, **kwargs)
    if first.text or not try_variants or not _worth_trying_variants(first.error):
        return first
    for variant in url_variants(url, first.error):
        # Short timeout and no browser: if plain HTTP cannot even connect,
        # the browser will not either, and this must stay cheap for the many
        # sites that are simply down.
        tried = await _fetch_single(
            variant, timeout=min(timeout, 20.0), browser_if_http_failed=False, **kwargs
        )
        if tried.text:
            log.info("adaptive_fetch.variant_worked", label=label, url=url, variant=variant)
            return tried
    return first


async def _fetch_single(
    url: str,
    *,
    timeout: float,
    max_html_chars: int,
    playwright_min_chars: int,
    playwright_wait_ms: int,
    label: str,
    browser_if_http_failed: bool = True,
) -> FetchResult:
    """Fetch ``url`` with plain HTTP; fall back to a headless browser if the
    cleaned content comes back thinner than ``playwright_min_chars``.
    """
    http_error: str | None = None
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": _USER_AGENT_HTTP,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
        },
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

    browser_errors: list[str] = []
    # A host that does not even answer the TCP connection in time will not
    # answer a browser either (one dead albo cost 140 s of timeouts + browser).
    host_dead = http_error == "timeout" and not cleaned
    if len(cleaned) < playwright_min_chars and (cleaned or browser_if_http_failed) and not host_dead:
        rendered = await _fetch_with_playwright(
            url,
            timeout=timeout,
            wait_ms=playwright_wait_ms,
            max_html_chars=max_html_chars,
            label=label,
            errors=browser_errors,
        )
        if rendered and len(rendered) > len(cleaned):
            cleaned = rendered
            log.info("adaptive_fetch.playwright_fetched", label=label, url=url, chars=len(cleaned))

    if cleaned:
        return FetchResult(text=cleaned, url=url)
    # An HTTP status (404, 403...) is the most specific; otherwise the
    # browser's own message says more than a bare "connect"/"error".
    if http_error and http_error.startswith("http_"):
        return FetchResult(text="", error=http_error)
    browser_kind = classify_browser_error(browser_errors[0]) if browser_errors else None
    return FetchResult(text="", error=browser_kind or http_error or "empty")


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
    errors: list[str] | None = None,
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
        if errors is not None:
            errors.append(str(exc))
        return None

    return clean_html(html, max_html_chars)


# Hosts that could not be read, with the reason: shows which platforms are out of reach from this server
# (vendor albi that reset or time out connections from data centres).
FAILURES: Counter = Counter()


# Hosts that have answered at least once in this process: when one of them fails, it is probably a hiccup.
_HOST_OK: set[str] = set()
RETRY_PAUSE = 2.0
RETRY_ENABLED = True  # tests of a single attempt switch it off
_PERMANENT = ("http_403", "http_404", "http_401", "http_410", "ssl", "dns")


def _worth_retry(netloc: str, error: str | None) -> bool:
    """One more try only for what may be momentary (timeout, connection, 5xx, empty page) and only on a host
    that works or is not known to fail: platforms that always reset our connections would just cost double."""
    if error and (error in _PERMANENT or error.startswith("http_4") and error != "http_429"):
        return False
    if netloc in _HOST_OK:
        return True
    return sum(n for (h, _), n in FAILURES.items() if h == netloc) < 2


async def adaptive_fetch_result(url: str, **kwargs) -> FetchResult:
    import asyncio
    from urllib.parse import urlsplit

    netloc = urlsplit(url).netloc
    res = await _adaptive_fetch_result_impl(url, **kwargs)
    if not res.text and RETRY_ENABLED and _worth_retry(netloc, res.error):
        await asyncio.sleep(RETRY_PAUSE)
        log.info("adaptive_fetch.retry", url=url, error=res.error)
        res = await _adaptive_fetch_result_impl(url, **kwargs)
    if res.text:
        _HOST_OK.add(netloc)
    else:
        FAILURES[(netloc, res.error or "vuota")] += 1
    return res
