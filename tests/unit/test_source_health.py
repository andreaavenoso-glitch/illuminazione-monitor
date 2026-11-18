"""Unit tests for per-source health bookkeeping and fetch error classification."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from app.collectors import adaptive_fetch as af
from app.collectors.source_health import apply_scan_outcome

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def _item(**kw):
    base = {"last_success_at": None, "consecutive_failures": 0, "last_error": None}
    base.update(kw)
    return SimpleNamespace(**base)


class TestApplyScanOutcome:
    def test_success_records_time_and_clears_failure_state(self) -> None:
        item = _item(consecutive_failures=3, last_error="http_404")
        apply_scan_outcome(item, now=NOW, ok=True)
        assert item.last_success_at == NOW
        assert item.consecutive_failures == 0
        assert item.last_error is None

    def test_failure_increments_streak_and_keeps_error_kind(self) -> None:
        item = _item()
        apply_scan_outcome(item, now=NOW, ok=False, error="http_403")
        apply_scan_outcome(item, now=NOW, ok=False, error="http_403")
        assert item.consecutive_failures == 2
        assert item.last_error == "http_403"

    def test_failure_does_not_erase_the_last_success_time(self) -> None:
        earlier = datetime(2026, 11, 1, tzinfo=UTC)
        item = _item(last_success_at=earlier)
        apply_scan_outcome(item, now=NOW, ok=False, error="dns")
        assert item.last_success_at == earlier

    def test_failure_without_error_kind_falls_back_to_empty(self) -> None:
        item = _item()
        apply_scan_outcome(item, now=NOW, ok=False)
        assert item.last_error == "empty"

    def test_treats_a_missing_streak_as_zero(self) -> None:
        item = _item(consecutive_failures=None)
        apply_scan_outcome(item, now=NOW, ok=False, error="timeout")
        assert item.consecutive_failures == 1


def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://example.test/")
    return httpx.HTTPStatusError("boom", request=req, response=httpx.Response(code, request=req))


class TestClassifyFetchError:
    @pytest.mark.parametrize("code", [403, 404, 500])
    def test_http_status_becomes_http_code(self, code: int) -> None:
        assert af.classify_fetch_error(_status_error(code)) == f"http_{code}"

    def test_timeout(self) -> None:
        assert af.classify_fetch_error(httpx.ReadTimeout("")) == "timeout"

    def test_ssl(self) -> None:
        exc = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        assert af.classify_fetch_error(exc) == "ssl"

    def test_dns(self) -> None:
        exc = httpx.ConnectError("[Errno -2] Name or service not known")
        assert af.classify_fetch_error(exc) == "dns"

    def test_anything_else(self) -> None:
        # Only truly unknown failures stay "error"; connection problems have their own kind.
        assert af.classify_fetch_error(ValueError("boom")) == "error"


async def _no_browser(*args, **kwargs):
    return None


_KW = {
    "timeout": 10.0,
    "max_html_chars": 80_000,
    "playwright_min_chars": 3_000,
    "playwright_wait_ms": 1,
    "label": "test",
}


class TestAdaptiveFetchResult:
    @pytest.mark.asyncio
    async def test_reports_the_http_error_when_nothing_could_be_read(self, httpx_mock, monkeypatch) -> None:
        httpx_mock.add_response(url="https://example.test/albo", status_code=404)
        monkeypatch.setattr(af, "_fetch_with_playwright", _no_browser)
        result = await af.adaptive_fetch_result("https://example.test/albo", **_KW)
        assert result.text == ""
        assert result.error == "http_404"

    @pytest.mark.asyncio
    async def test_no_error_when_the_browser_recovers_the_page(self, httpx_mock, monkeypatch) -> None:
        httpx_mock.add_response(url="https://example.test/albo", status_code=403)

        async def _rendered(*args, **kwargs):
            return "contenuto reale " * 500

        monkeypatch.setattr(af, "_fetch_with_playwright", _rendered)
        result = await af.adaptive_fetch_result("https://example.test/albo", **_KW)
        assert "contenuto reale" in result.text
        assert result.error is None

    @pytest.mark.asyncio
    async def test_empty_body_with_status_200_is_reported_as_empty(self, httpx_mock, monkeypatch) -> None:
        httpx_mock.add_response(url="https://example.test/albo", text="")
        monkeypatch.setattr(af, "_fetch_with_playwright", _no_browser)
        result = await af.adaptive_fetch_result("https://example.test/albo", **_KW)
        assert result.text == ""
        assert result.error == "empty"

    @pytest.mark.asyncio
    async def test_healthy_page_has_no_error(self, httpx_mock) -> None:
        httpx_mock.add_response(url="https://example.test/albo", text="<p>Avviso</p>" + "x" * 5000)
        result = await af.adaptive_fetch_result("https://example.test/albo", **_KW)
        assert "Avviso" in result.text
        assert result.error is None


class TestMoreErrorKinds:
    def test_connect_refused(self) -> None:
        assert af.classify_fetch_error(httpx.ConnectError("All connection attempts failed")) == "connect"

    def test_too_many_redirects(self) -> None:
        assert af.classify_fetch_error(httpx.TooManyRedirects("Exceeded maximum allowed redirects.")) == "redirect"

    def test_protocol_error(self) -> None:
        assert af.classify_fetch_error(httpx.RemoteProtocolError("Server disconnected without sending a response.")) == "protocol"

    def test_dns_still_wins_over_connect(self) -> None:
        assert af.classify_fetch_error(httpx.ConnectError("[Errno -2] Name or service not known")) == "dns"


class TestSmartCollectorUnreadablePage:
    @pytest.mark.asyncio
    async def test_unreachable_page_is_an_error_not_an_empty_success(self, monkeypatch) -> None:
        from uuid import uuid4

        from app.collectors import smart_llm
        from app.collectors.base import CollectorError

        async def fake_fetch(*a, **kw):
            return af.FetchResult(text="", error="timeout")

        monkeypatch.setattr(smart_llm, "adaptive_fetch_result", fake_fetch)
        collector = smart_llm.SmartLLMCollector(uuid4(), "https://example.invalid", platform_type="generic_html")
        collector.settings = SimpleNamespace(
            anthropic_api_key="k", smart_collector_max_html_chars=1000,
            smart_collector_playwright_min_chars=10, smart_collector_playwright_wait_ms=1,
        )
        with pytest.raises(CollectorError, match="timeout"):
            await collector.fetch()


class TestBrowserErrorKinds:
    def test_connection_reset_is_recognised(self) -> None:
        assert af.classify_browser_error("Page.goto: net::ERR_CONNECTION_RESET at https://x/") == "reset"

    def test_other_kinds_and_unknown(self) -> None:
        assert af.classify_browser_error("net::ERR_NAME_NOT_RESOLVED") == "dns"
        assert af.classify_browser_error("net::ERR_CERT_DATE_INVALID") == "ssl"
        assert af.classify_browser_error("something odd") is None

    @pytest.mark.asyncio
    async def test_reset_reported_when_http_and_browser_both_fail(self, monkeypatch, httpx_mock) -> None:
        httpx_mock.add_exception(httpx.ConnectError("All connection attempts failed"))

        async def browser(url, **kw):
            kw["errors"].append("Page.goto: net::ERR_CONNECTION_RESET at https://x/")
            return None

        monkeypatch.setattr(af, "_fetch_with_playwright", browser)
        res = await af.adaptive_fetch_result(
            "https://x/", timeout=5, max_html_chars=1000, playwright_min_chars=10,
            playwright_wait_ms=1, label="t",
        )
        assert res.text == "" and res.error == "reset"

    @pytest.mark.asyncio
    async def test_http_status_beats_browser_message(self, monkeypatch, httpx_mock) -> None:
        httpx_mock.add_response(url="https://x/", status_code=404)

        async def browser(url, **kw):
            kw["errors"].append("net::ERR_CONNECTION_RESET")
            return None

        monkeypatch.setattr(af, "_fetch_with_playwright", browser)
        res = await af.adaptive_fetch_result(
            "https://x/", timeout=5, max_html_chars=1000, playwright_min_chars=10,
            playwright_wait_ms=1, label="t",
        )
        assert res.error == "http_404"
