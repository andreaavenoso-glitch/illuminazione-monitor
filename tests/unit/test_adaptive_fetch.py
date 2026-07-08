"""Unit tests for the shared 3-tier adaptive fetch helper."""
from __future__ import annotations

import pytest
from app.collectors import adaptive_fetch as af


class TestCleanHtml:
    def test_strips_scripts_and_styles(self) -> None:
        html = "<html><head><style>body{color:red}</style></head><body>Testo<script>evil()</script></body></html>"
        cleaned = af.clean_html(html, max_chars=10_000)
        assert "evil()" not in cleaned
        assert "color:red" not in cleaned
        assert "Testo" in cleaned

    def test_truncates_to_budget(self) -> None:
        html = "x" * 100
        cleaned = af.clean_html(html, max_chars=10)
        assert cleaned.startswith("x" * 10)
        assert "[TRONCATO]" in cleaned


class TestAdaptiveFetch:
    @pytest.mark.asyncio
    async def test_returns_cleaned_html_on_success(self, httpx_mock) -> None:
        httpx_mock.add_response(url="https://example.test/albo", text="<p>Avviso pubblico</p>" + "x" * 5000)
        result = await af.adaptive_fetch(
            "https://example.test/albo",
            timeout=10.0,
            max_html_chars=80_000,
            playwright_min_chars=3_000,
            playwright_wait_ms=1,
            label="test",
        )
        assert "Avviso pubblico" in result

    @pytest.mark.asyncio
    async def test_empty_on_http_error_without_playwright_fallback(self, httpx_mock, monkeypatch) -> None:
        httpx_mock.add_response(url="https://example.test/albo", status_code=404)

        async def _no_playwright(*args, **kwargs):
            return None

        monkeypatch.setattr(af, "_fetch_with_playwright", _no_playwright)
        result = await af.adaptive_fetch(
            "https://example.test/albo",
            timeout=10.0,
            max_html_chars=80_000,
            playwright_min_chars=3_000,
            playwright_wait_ms=1,
            label="test",
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_falls_back_to_playwright_when_content_too_thin(self, httpx_mock, monkeypatch) -> None:
        httpx_mock.add_response(url="https://example.test/albo", text="<p>thin</p>")

        async def _fake_playwright(*args, **kwargs):
            return "rendered content " * 500

        monkeypatch.setattr(af, "_fetch_with_playwright", _fake_playwright)
        result = await af.adaptive_fetch(
            "https://example.test/albo",
            timeout=10.0,
            max_html_chars=80_000,
            playwright_min_chars=3_000,
            playwright_wait_ms=1,
            label="test",
        )
        assert "rendered content" in result

    @pytest.mark.asyncio
    async def test_keeps_plain_fetch_when_playwright_not_longer(self, httpx_mock, monkeypatch) -> None:
        httpx_mock.add_response(url="https://example.test/albo", text="<p>thin but real</p>")

        async def _shorter_playwright(*args, **kwargs):
            return "x"

        monkeypatch.setattr(af, "_fetch_with_playwright", _shorter_playwright)
        result = await af.adaptive_fetch(
            "https://example.test/albo",
            timeout=10.0,
            max_html_chars=80_000,
            playwright_min_chars=3_000,
            playwright_wait_ms=1,
            label="test",
        )
        assert "thin but real" in result
