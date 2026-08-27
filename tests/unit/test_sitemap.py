"""Unit tests for sitemap-first page discovery.

httpx is mocked via pytest-httpx -- no real network calls are made.
"""
from __future__ import annotations

import pytest
from app.collectors.sitemap import MAX_SITEMAP_URLS, discover_sitemap_urls

SIMPLE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://comune.test/amministrazione-trasparente/bandi-di-gara-e-contratti/</loc></url>
  <url><loc>https://comune.test/amministrazione-trasparente/provvedimenti/</loc></url>
  <url><loc>https://comune.test/notizie/festa-paese/</loc></url>
  <url><loc>https://comune.test/servizi/anagrafe/</loc></url>
</urlset>
"""

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://comune.test/sitemap-trasparenza.xml</loc></sitemap>
  <sitemap><loc>https://comune.test/sitemap-notizie.xml</loc></sitemap>
</sitemapindex>
"""

SUB_SITEMAP_TRASPARENZA = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://comune.test/trasparenza/avvisi-pubblici/</loc></url>
  <url><loc>https://comune.test/uffici/organigramma/</loc></url>
</urlset>
"""

SUB_SITEMAP_NOTIZIE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://comune.test/notizie/sagra-paese/</loc></url>
</urlset>
"""


class TestDiscoverSitemapUrls:
    @pytest.mark.asyncio
    async def test_filters_to_relevant_urls_only(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://comune.test/sitemap.xml", text=SIMPLE_SITEMAP
        )
        urls = await discover_sitemap_urls("https://comune.test/trasparenza/")
        assert urls == [
            "https://comune.test/amministrazione-trasparente/bandi-di-gara-e-contratti/",
            "https://comune.test/amministrazione-trasparente/provvedimenti/",
        ]

    @pytest.mark.asyncio
    async def test_no_sitemap_returns_empty(self, httpx_mock) -> None:
        httpx_mock.add_response(url="https://comune.test/sitemap.xml", status_code=404)
        httpx_mock.add_response(url="https://comune.test/sitemap_index.xml", status_code=404)
        urls = await discover_sitemap_urls("https://comune.test/trasparenza/")
        assert urls == []

    @pytest.mark.asyncio
    async def test_sitemap_with_no_relevant_urls_returns_empty(self, httpx_mock) -> None:
        # No relevant URLs on the first sitemap tried: discovery falls
        # through to the next known path before giving up.
        irrelevant = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://comune.test/eventi/festa/</loc></url>
        </urlset>"""
        httpx_mock.add_response(url="https://comune.test/sitemap.xml", text=irrelevant)
        httpx_mock.add_response(url="https://comune.test/sitemap_index.xml", status_code=404)
        urls = await discover_sitemap_urls("https://comune.test/")
        assert urls == []

    @pytest.mark.asyncio
    async def test_follows_sitemap_index_sub_sitemaps(self, httpx_mock) -> None:
        httpx_mock.add_response(url="https://comune.test/sitemap.xml", text=SITEMAP_INDEX)
        httpx_mock.add_response(
            url="https://comune.test/sitemap-trasparenza.xml", text=SUB_SITEMAP_TRASPARENZA
        )
        httpx_mock.add_response(
            url="https://comune.test/sitemap-notizie.xml", text=SUB_SITEMAP_NOTIZIE
        )
        urls = await discover_sitemap_urls("https://comune.test/")
        assert urls == ["https://comune.test/trasparenza/avvisi-pubblici/"]

    @pytest.mark.asyncio
    async def test_procurement_specific_urls_are_ranked_before_generic_ones(self, httpx_mock) -> None:
        # A generic "avviso"/"delibera" URL matches almost any municipal
        # notice (TARI payments, elections, waste collection...) and would
        # otherwise crowd out a genuine "bandi-di-gara" page once
        # MAX_EXTRA_PAGES caps how many of these actually get read.
        mixed = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://comune.test/news/avviso-pagamento-tari/</loc></url>
          <url><loc>https://comune.test/delibera/giunta-123/</loc></url>
          <url><loc>https://comune.test/amministrazione-trasparente/bandi-di-gara/</loc></url>
          <url><loc>https://comune.test/news/avviso-elezioni/</loc></url>
        </urlset>"""
        httpx_mock.add_response(url="https://comune.test/sitemap.xml", text=mixed)
        urls = await discover_sitemap_urls("https://comune.test/")
        assert urls[0] == "https://comune.test/amministrazione-trasparente/bandi-di-gara/"
        assert set(urls) == {
            "https://comune.test/news/avviso-pagamento-tari/",
            "https://comune.test/delibera/giunta-123/",
            "https://comune.test/amministrazione-trasparente/bandi-di-gara/",
            "https://comune.test/news/avviso-elezioni/",
        }

    @pytest.mark.asyncio
    async def test_caps_result_at_max_sitemap_urls(self, httpx_mock) -> None:
        many = "".join(
            f"<url><loc>https://comune.test/trasparenza/bandi-{i}/</loc></url>"
            for i in range(MAX_SITEMAP_URLS + 10)
        )
        sitemap = f"""<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{many}</urlset>"""
        httpx_mock.add_response(url="https://comune.test/sitemap.xml", text=sitemap)
        urls = await discover_sitemap_urls("https://comune.test/")
        assert len(urls) == MAX_SITEMAP_URLS
