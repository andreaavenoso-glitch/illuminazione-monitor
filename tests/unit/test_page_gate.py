"""Deterministic pre-filter in front of the Claude extraction."""
from __future__ import annotations

import pytest
from app.collectors.page_gate import detect_template, gate_page, pick_section_links

BASE = "https://www.comune.example.it/albo/"

DESIGN_ITALIA_LIST = """
<html><head><link rel="stylesheet" href="/bootstrap-italia/css/bootstrap-italia.min.css"></head>
<body><div class="it-header-slim-wrapper">Comune di Esempio</div>
<div class="cards">
 <article class="card"><h3><a href="/novita/avviso-1">Avviso di manifestazione di interesse per la manutenzione degli impianti di pubblica illuminazione</a></h3>
   <span>12/11/2026</span></article>
 <article class="card"><h3><a href="/novita/avviso-2">Concessione area pubblica in Piazza Padre Pio</a></h3><span>10/11/2026</span></article>
 <article class="card"><h3><a href="/novita/avviso-3">Avviso per la sollecitazione di proposte di finanza di progetto</a></h3><span>01/11/2026</span></article>
</div></body></html>
"""


class TestGate:
    def test_page_without_keywords_is_skipped(self) -> None:
        html = "<html><body><a href='/x'>Concessione area pubblica per somministrazione di alimenti</a></body></html>"
        res = gate_page(html, base_url=BASE)
        assert res.action == "skip" and res.html == ""

    def test_matching_entries_go_as_a_compact_list(self) -> None:
        res = gate_page(DESIGN_ITALIA_LIST, base_url=BASE)
        assert res.action == "compact"
        titles = [c.title for c in res.candidates]
        assert len(titles) == 2
        assert any("pubblica illuminazione" in t for t in titles)
        assert any("finanza di progetto" in t for t in titles)
        assert "Piazza Padre Pio" not in res.html
        assert len(res.html) < len(DESIGN_ITALIA_LIST)

    def test_relative_links_become_absolute_and_dates_are_kept(self) -> None:
        res = gate_page(DESIGN_ITALIA_LIST, base_url=BASE)
        first = next(c for c in res.candidates if "illuminazione" in c.title)
        assert first.href == "https://www.comune.example.it/novita/avviso-1"
        assert first.date == "12/11/2026"
        assert "https://www.comune.example.it/novita/avviso-1" in res.html

    def test_keywords_outside_links_fall_back_to_full_page(self) -> None:
        html = "<html><body><p>Il Comune intende affidare il servizio di illuminazione pubblica.</p></body></html>"
        res = gate_page(html, base_url=BASE)
        assert res.action == "full" and res.html == html

    def test_table_layout_uses_the_row_as_context(self) -> None:
        html = (
            "<table><tr><td>Determina n. 55</td><td>Affidamento fornitura corpi illuminanti LED</td>"
            "<td><a href='det55.pdf'>Scarica la determina completa</a></td></tr></table>"
        )
        res = gate_page(html, base_url=BASE)
        assert res.action == "compact"
        assert "corpi illuminanti" in res.candidates[0].snippet

    def test_digest_is_stable_and_changes_with_content(self) -> None:
        a = gate_page(DESIGN_ITALIA_LIST, base_url=BASE)
        b = gate_page(DESIGN_ITALIA_LIST.replace("Comune di Esempio", "Altro banner"), base_url=BASE)
        c = gate_page(DESIGN_ITALIA_LIST.replace("Concessione area", "Nuovo avviso illuminazione pubblica per le scuole"), base_url=BASE)
        assert a.digest == b.digest  # page chrome does not change the fingerprint
        assert a.digest != c.digest  # a new relevant entry does

    def test_candidates_are_capped_and_deduplicated(self) -> None:
        links = "".join(
            f"<li><a href='/a{i}'>Avviso illuminazione pubblica numero {i}</a></li>" for i in range(100)
        ) + "<li><a href='/a0'>Avviso illuminazione pubblica numero 0</a></li>"
        res = gate_page(f"<ul>{links}</ul>", base_url=BASE)
        assert len(res.candidates) == 60


class TestTemplateDetection:
    def test_known_platforms(self) -> None:
        assert detect_template(DESIGN_ITALIA_LIST) == "design_italia"
        assert detect_template("<img src='https://x.halleyweb.com/logo.png'>") == "halley"
        assert detect_template("<script src='/sicraweb/app.js'></script>") == "maggioli"
        assert detect_template("<p>nulla</p>") == "other"


class TestSectionLinks:
    HTML = """
    <ul>
     <li><a href="/at/bandi-gara">Bandi di gara e contratti</a></li>
     <li><a href="/at/provv">Provvedimenti</a></li>
     <li><a href="/at/personale">Personale</a></li>
     <li><a href="#top">Albo pretorio</a></li>
     <li><a href="/albo">Albo pretorio online</a></li>
    </ul>"""

    def test_picks_by_legal_section_names_only(self) -> None:
        urls = pick_section_links(self.HTML, base_url="https://c.it/at/", limit=8)
        assert urls == ["https://c.it/at/bandi-gara", "https://c.it/at/provv", "https://c.it/albo"]

    def test_limit_and_no_match(self) -> None:
        assert len(pick_section_links(self.HTML, base_url="https://c.it/", limit=2)) == 2
        assert pick_section_links("<a href='/x'>Contatti</a>", base_url="https://c.it/", limit=5) == []


@pytest.mark.asyncio
class TestScanIntegration:
    """_process_page: when Claude is called, and when the page is remembered."""

    def _setup(self, monkeypatch, *, ok=True):
        from collections import Counter
        from datetime import UTC, datetime
        from types import SimpleNamespace

        from app.tasks import collect_watchlist as cw

        calls: list[str] = []

        async def fake_extract(html, *, url, settings, label, status=None):
            calls.append(html)
            if status is not None:
                status["ok"] = ok
            return []

        monkeypatch.setattr(cw, "extract_albo_records", fake_extract)
        item = SimpleNamespace(content_hashes=None, source_id=None, entity_id=None)
        job = SimpleNamespace(records_found=0, records_valid=0, duplicates_removed=0)

        async def run(html, stats):
            await cw._process_page(
                SimpleNamespace(add=lambda *_: None), item, job,
                target_url=BASE, target_html=html, label="t",
                settings=SimpleNamespace(smart_collector_max_html_chars=80_000),
                now=datetime.now(tz=UTC), seen=set(), stats=stats,
            )

        return calls, item, run, Counter()

    async def test_page_without_keywords_never_reaches_claude(self, monkeypatch) -> None:
        calls, item, run, stats = self._setup(monkeypatch)
        await run("<html><body><a href='/x'>Concessione area pubblica per alimenti</a></body></html>", stats)
        assert calls == [] and stats["pages_skipped_no_keywords"] == 1

    async def test_unchanged_page_is_not_analysed_twice(self, monkeypatch) -> None:
        calls, item, run, stats = self._setup(monkeypatch)
        await run(DESIGN_ITALIA_LIST, stats)
        await run(DESIGN_ITALIA_LIST.replace("Comune di Esempio", "Altro banner"), stats)
        assert len(calls) == 1
        assert "<ul>" in calls[0] and "Piazza Padre Pio" not in calls[0]  # compact list, not the page
        assert stats["pages_to_claude_compact"] == 1 and stats["pages_unchanged"] == 1
        assert item.content_hashes and BASE in item.content_hashes

    async def test_failed_analysis_is_retried_next_time(self, monkeypatch) -> None:
        calls, item, run, stats = self._setup(monkeypatch, ok=False)
        await run(DESIGN_ITALIA_LIST, stats)
        await run(DESIGN_ITALIA_LIST, stats)
        assert len(calls) == 2 and not item.content_hashes


class TestLinkScoring:
    def test_section_names_and_topics_score_high(self) -> None:
        from app.collectors.page_gate import score_link

        assert score_link("Bandi di gara e contratti", "/x") >= 10
        assert score_link("Avvisi pubblici", "/x") >= 10
        assert score_link("Manutenzione illuminazione pubblica", "/x") >= 10  # keyword + topic
        assert score_link("Determinazioni dirigenziali 2026", "/x") >= 4

    def test_real_world_noise_seen_in_the_first_dry_run(self) -> None:
        """Sections and news that wasted a whole page budget (Puglia dry run)."""
        from app.collectors.page_gate import score_link

        noise = [
            "Piano triennale per la prevenzione della corruzione e della trasparenza",
            "Personale non a tempo indeterminato",
            "Contrattazione collettiva",
            "Contrattazione integrativa",
            "Rendiconti gruppi consiliari regionali provinciali",
            "Sanzioni per mancata comunicazione dei dati",
            "Bandi di concorso",
            "Criteri e modalita",
            "Avviso agli elettori affetti da infermita",
            "Avviso tessera elettorale",
            "Avviso di convocazione per la selezione dei candidati volontari al servizio civile",
            "Avviso pubblico esplorativo per manifestazione d'interesse per la celebrazione di matrimoni",
        ]
        for text in noise:
            assert score_link(text, "/x") == 0, text
        useful = [
            "Bandi di gara e contratti", "Avvisi pubblici", "Avvisi", "Atti delle amministrazioni aggiudicatrici",
            "Provvedimenti dirigenti", "Determinazioni", "Delibere", "Albo pretorio", "Amministrazione trasparente",
        ]
        for text in useful:
            assert score_link(text, "/x") >= 4, text

    def test_junk_files_and_act_titles_score_zero(self) -> None:
        from app.collectors.page_gate import score_link

        assert score_link("Contatti", "/contatti") == 0
        assert score_link("Privacy e cookie", "/privacy") == 0
        assert score_link("Avvisi", "/docs/avvisi.pdf") == 0
        assert score_link("Eventi culturali dell'estate", "/eventi") == 0
        long_title = "Avviso pubblico per la manifestazione di interesse " + "x" * 80
        assert score_link(long_title, "/a") == 0  # an act's own title, not a menu entry

    def test_rank_links_orders_dedups_and_keeps_pagination(self) -> None:
        from app.collectors.page_gate import rank_links

        html = (
            "<a href='/personale'>Personale</a><a href='/a'>Avvisi</a>"
            "<a href='/b'>Bandi di gara e contratti</a><a href='/b/'>Bandi di gara e contratti</a>"
            "<a href='/contatti'>Contatti</a><a href='/p2' rel='next'>2</a>"
            "<a href='/p3'>Pagina successiva</a>"
        )
        ranked = rank_links(html, base_url="https://c.it/x", limit=10)
        urls = [u for u, _ in ranked]
        assert urls[0] == "https://c.it/b"
        assert "https://c.it/contatti" not in urls and "https://c.it/personale" not in urls
        assert urls.count("https://c.it/b") + urls.count("https://c.it/b/") == 1
        assert "https://c.it/p2" in urls and "https://c.it/p3" in urls

    def test_same_site_and_normalize(self) -> None:
        from app.collectors.page_gate import normalize_url, same_site

        assert same_site("https://www.c.it/a", "https://c.it/b")
        assert same_site("https://albo.c.it/a", "https://www.c.it/")
        assert not same_site("https://x.halleyweb.com/", "https://c.it/")
        assert normalize_url("https://WWW.c.it/a/#top") == normalize_url("https://c.it/a")


class FakeFetched:
    def __init__(self, text="", url=None, error=None):
        self.text, self.url, self.error = text, url, error


@pytest.mark.asyncio
class TestBestFirstCrawl:
    """The crawl goes as deep as the links lead, best link first, within budgets."""

    def _site(self):
        # home -> trasparenza -> bandi -> avvisi -> 2026 -> list with the notice (5 levels)
        link = lambda href, text: f"<a href='{href}'>{text}</a>"  # noqa: E731
        return {
            "https://c.it/": link("/trasparenza", "Amministrazione trasparente") + link("/contatti", "Contatti"),
            "https://c.it/trasparenza": link("/bandi", "Bandi di gara e contratti") + link("/personale", "Personale"),
            "https://c.it/bandi": link("/avvisi", "Avvisi pubblici"),
            "https://c.it/avvisi": link("/avvisi/2026", "Avvisi 2026"),
            "https://c.it/avvisi/2026": link("/avvisi/2026/lista", "Elenco avvisi 2026"),
            "https://c.it/avvisi/2026/lista": (
                "<ul><li><a href='/a/1'>Avviso di manifestazione di interesse per la manutenzione "
                "dell'illuminazione pubblica</a></li></ul>"
            ),
        }

    async def _run(self, pages, *, max_pages=20, max_depth=5, budget=150.0, clock=None, seeds=()):
        from app.collectors.crawler import crawl
        from app.collectors.page_gate import gate_page

        fetched_urls, analysed = [], []

        async def fetch(url):
            fetched_urls.append(url)
            return FakeFetched(pages.get(url, ""), url, None if url in pages else "http_404")

        async def on_page(url, html, depth):
            g = gate_page(html, base_url=url)
            if g.action != "skip":
                analysed.append((url, depth))
            return g

        kwargs = {"clock": clock} if clock else {}
        res = await crawl(
            start_url="https://c.it/", start_html=pages["https://c.it/"], seeds=list(seeds),
            fetch=fetch, on_page=on_page, max_pages=max_pages, max_depth=max_depth,
            time_budget_s=budget, **kwargs,
        )
        return res, fetched_urls, analysed

    async def test_reaches_a_notice_five_levels_down(self) -> None:
        res, fetched, analysed = await self._run(self._site())
        assert analysed == [("https://c.it/avvisi/2026/lista", 5)]
        assert "https://c.it/contatti" not in fetched and "https://c.it/personale" not in fetched
        assert max(v.depth for v in res.visits) == 5

    async def test_depth_cap_stops_the_descent(self) -> None:
        res, _, analysed = await self._run(self._site(), max_depth=3)
        assert analysed == []
        assert max(v.depth for v in res.visits) == 3

    async def test_page_budget_stops_the_crawl(self) -> None:
        res, fetched, _ = await self._run(self._site(), max_pages=2)
        assert len(fetched) == 2 and res.stopped_by == "pages"

    async def test_time_budget_stops_the_crawl(self) -> None:
        ticks = iter(range(0, 1000, 100))
        res, fetched, _ = await self._run(self._site(), budget=150.0, clock=lambda: next(ticks))
        assert res.stopped_by == "time" and len(fetched) < 5

    async def test_unreadable_pages_are_recorded_and_skipped(self) -> None:
        pages = self._site()
        del pages["https://c.it/bandi"]
        res, _, _ = await self._run(pages)
        assert any(v.action == "unreadable" and v.error == "http_404" for v in res.visits)

    async def test_pages_are_visited_once(self) -> None:
        pages = self._site()
        pages["https://c.it/bandi"] = "<a href='/trasparenza'>Amministrazione trasparente</a><a href='/avvisi'>Avvisi pubblici</a>"
        _, fetched, _ = await self._run(pages)
        assert len(fetched) == len(set(fetched))

    async def test_seeds_are_opened_first(self) -> None:
        _, fetched, _ = await self._run(self._site(), seeds=["https://c.it/avvisi"])
        assert fetched[0] == "https://c.it/avvisi"


class TestRobustness:
    def test_malformed_hrefs_do_not_crash(self) -> None:
        """A real site had an href Python cannot parse ("Invalid IPv6 URL")."""
        from app.collectors.page_gate import extract_candidates, pick_section_links, rank_links, safe_join

        assert safe_join("https://c.it/", "http://[broken") is None
        assert safe_join("https://c.it/a/", "../b") == "https://c.it/b"
        html = (
            "<a href='http://[broken'>Bandi di gara e contratti</a>"
            "<a href='/ok'>Avvisi pubblici</a>"
            "<li><a href='http://[x'>Manutenzione illuminazione pubblica impianti</a></li>"
        )
        assert [u for u, _ in rank_links(html, base_url="https://c.it/")] == ["https://c.it/ok"]
        assert pick_section_links(html, base_url="https://c.it/", limit=5) == ["https://c.it/ok"]
        from bs4 import BeautifulSoup

        assert extract_candidates(BeautifulSoup(html, "lxml"), "https://c.it/") == []

    def test_entries_past_the_first_80000_characters_are_seen(self) -> None:
        filler = "<p>" + "testo di riempimento " * 6000 + "</p>"  # ~126k characters
        tail = "<ul><li><a href='/a'>Avviso di manifestazione di interesse per l'illuminazione pubblica</a></li></ul>"
        res = gate_page(filler + tail, base_url=BASE)
        assert res.action == "compact" and len(res.candidates) == 1

    def test_full_fallback_is_cut_to_the_limit(self) -> None:
        text = "<p>" + "Servizio di illuminazione pubblica. " * 5000 + "</p>"
        res = gate_page(text, base_url=BASE, full_limit=1000)
        assert res.action == "full" and len(res.html) == 1000


class TestDiscoveredPlatforms:
    START = "https://www.montesantangelo.it"

    def test_provincial_portal_is_found(self) -> None:
        from app.collectors.page_gate import discovered_platforms

        urls = [
            "https://www.montesantangelo.it/en/news/x",
            "https://appalti.provincia.foggia.it/PortaleAppalti/it/ppgare_bandi_lista.wp?actionPath=/a",
            "https://appalti.provincia.foggia.it/PortaleAppalti/it/altra",
        ]
        found = discovered_platforms(urls, self.START)
        assert list(found) == ["appalti.provincia.foggia.it"]
        assert found["appalti.provincia.foggia.it"].endswith("actionPath=/a")  # first URL seen

    def test_own_site_social_and_unrelated_hosts_are_not_platforms(self) -> None:
        from app.collectors.page_gate import discovered_platforms

        urls = [
            "https://montesantangelo.it/albo", "https://albo.montesantangelo.it/x",
            "https://www.facebook.com/comune", "https://www.example.org/pagina",
            "http://[broken",
        ]
        assert discovered_platforms(urls, self.START) == {}

    def test_known_vendor_platforms_by_host_or_path(self) -> None:
        from app.collectors.page_gate import discovered_platforms

        urls = [
            "https://app.albofornitori.it/alboeproc/albo_x", "https://gare.comune-altro.it/",
            "https://x.example.it/PortaleAppalti/it/home", "https://start.toscana.it/tendering",
        ]
        assert set(discovered_platforms(urls, self.START)) == {
            "app.albofornitori.it", "gare.comune-altro.it", "x.example.it",
        }


class TestSecondDryRunFindings:
    """Things the real Puglia dry run showed."""

    def test_vendor_hosted_albo_and_trasparenza_are_not_regional_platforms(self) -> None:
        from app.collectors.page_gate import discovered_platforms

        urls = [
            "https://trasparenza.parsec326.it/en/web/mesagne/bandi-di-gara-e-contratti",
            "https://trasparenza.tinnvision.cloud/traspamm/80010060756/2/home.html",
            "https://albo.tinnvision.cloud/?ente=80010060756",
            "http://www.albo.tinnservice.com/?idente=80010060756",
            "https://lecce.trasparenza-valutazione-merito.it/web/trasparenza/albo-pretorio",
            "http://albo.egov.ba.it/web/ruvo-di-puglia",
        ]
        assert discovered_platforms(urls, "https://www.comune.melendugno.le.it") == {}

    def test_real_procurement_portals_still_found(self) -> None:
        from app.collectors.page_gate import discovered_platforms

        found = discovered_platforms(
            ["https://appalti.provincia.foggia.it/PortaleAppalti/it/ppgare_bandi_lista.wp",
             "https://www.traspare.com/home"],
            "https://www.montesantangelo.it",
        )
        assert set(found) == {"appalti.provincia.foggia.it", "traspare.com"}

    def test_session_ids_do_not_make_new_pages(self) -> None:
        from app.collectors.page_gate import normalize_url

        a = "https://trasparenza.parsec326.it/en/web/mesagne/albo-pretoreo;jsessionid=4E394BE4B62269ECBC003DBA34CBBCAC"
        b = "https://trasparenza.parsec326.it/en/web/mesagne/albo-pretoreo;jsessionid=2B908F428E240387A9828CACAEC4DAE7"
        assert normalize_url(a) == normalize_url(b) == normalize_url("https://trasparenza.parsec326.it/en/web/mesagne/albo-pretoreo")


@pytest.mark.asyncio
class TestPolitenessAndDuplicates:
    async def test_pause_between_requests_to_the_same_host_only(self) -> None:
        from app.collectors.crawler import crawl
        from app.collectors.page_gate import gate_page

        now = [0.0]
        slept: list[float] = []

        async def sleep(s):
            slept.append(round(s, 2))
            now[0] += s

        pages = {
            "https://c.it/": "<a href='/a'>Avvisi pubblici</a><a href='/b'>Bandi di gara e contratti</a>"
                             "<a href='https://gare.altro.it/x'>Albo pretorio</a>",
            "https://c.it/a": "x", "https://c.it/b": "x", "https://gare.altro.it/x": "x",
        }

        async def fetch(url):
            now[0] += 0.1  # a request takes 100 ms
            return FakeFetched(pages.get(url, ""), url)

        async def on_page(url, html, depth):
            return gate_page(html, base_url=url)

        await crawl(
            start_url="https://c.it/", start_html=pages["https://c.it/"], seeds=[], fetch=fetch,
            on_page=on_page, max_pages=10, max_depth=3, time_budget_s=1000, delay_s=1.0,
            clock=lambda: now[0], sleep=sleep,
        )
        # Three pages on c.it/gare.altro.it: only the second c.it request waits (the other
        # host and the first request of each host do not).
        assert len([s for s in slept if s > 0]) == 1
        assert 0.8 <= max(slept) <= 1.0

    async def test_same_content_under_two_addresses_is_analysed_once(self, monkeypatch) -> None:
        from collections import Counter
        from datetime import UTC, datetime
        from types import SimpleNamespace

        from app.tasks import collect_watchlist as cw

        calls: list[str] = []

        async def fake_extract(html, *, url, settings, label, status=None):
            calls.append(url)
            return []

        monkeypatch.setattr(cw, "extract_albo_records", fake_extract)
        item = SimpleNamespace(content_hashes=None, source_id=None, entity_id=None)
        job = SimpleNamespace(records_found=0, records_valid=0, duplicates_removed=0)
        stats, digests = Counter(), set()
        for url in ("https://c.it/utilita/trasparenza", "https://c.it/amministrazione/trasparenza"):
            await cw._process_page(
                SimpleNamespace(add=lambda *_: None), item, job,
                target_url=url, target_html=DESIGN_ITALIA_LIST, label="t",
                settings=SimpleNamespace(smart_collector_max_html_chars=80_000),
                now=datetime.now(tz=UTC), seen=set(), stats=stats, digests=digests,
            )
        assert len(calls) == 1 and stats["pages_duplicate_content"] == 1

    async def test_no_browser_after_a_connect_timeout_and_no_variants_when_disabled(self, monkeypatch, httpx_mock) -> None:
        import httpx
        from app.collectors import adaptive_fetch as af

        httpx_mock.add_exception(httpx.ConnectTimeout("t"), url="https://dead.it/")
        called = []

        async def browser(url, **kw):
            called.append(url)
            return None

        monkeypatch.setattr(af, "_fetch_with_playwright", browser)
        res = await af.adaptive_fetch_result(
            "https://dead.it/", timeout=5, max_html_chars=1000, playwright_min_chars=10,
            playwright_wait_ms=1, label="t", try_variants=False,
        )
        assert res.error == "timeout" and called == []
        assert len(httpx_mock.get_requests()) == 1  # no www variant either


@pytest.mark.asyncio
class TestRunLimited:
    async def test_never_more_than_the_limit_at_once_and_all_are_run(self) -> None:
        import asyncio

        from app.tasks.collect_watchlist import run_limited

        active = peak = 0
        done: list[int] = []

        async def worker(i):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            done.append(i)

        await run_limited(list(range(10)), worker, 3)
        assert sorted(done) == list(range(10)) and peak == 3

    async def test_a_failing_worker_does_not_stop_the_others(self) -> None:
        from app.tasks.collect_watchlist import run_limited

        done: list[int] = []

        async def worker(i):
            if i == 2:
                raise RuntimeError("boom")
            done.append(i)

        await run_limited([1, 2, 3, 4], worker, 2)
        assert sorted(done) == [1, 3, 4]


class TestThirdDryRunFindings:
    def test_votive_lamps_and_sports_lighting_are_not_public_lighting(self) -> None:
        html = (
            "<ul><li><a href='/a'>Avviso ai cittadini: servizio illuminazione lampade votive esercizio 2026</a></li>"
            "<li><a href='/b'>Lavori di adeguamento illuminazione impianti sportivi comunali</a></li></ul>"
        )
        assert gate_page(html, base_url=BASE).action == "skip"
        # ...but real public lighting next to them still passes.
        real = html + "<li><a href='/c'>Manutenzione degli impianti di illuminazione pubblica</a></li>"
        res = gate_page(real, base_url=BASE)
        assert res.action == "compact" and len(res.candidates) == 1

    def test_comune_tenant_on_a_vendor_platform_is_not_a_regional_site(self) -> None:
        from app.collectors.page_gate import discovered_platforms

        found = discovered_platforms(
            ["https://comunesansevero.traspare.com/albo", "https://www.traspare.com/home"],
            "https://www.comune.san-severo.fg.it",
        )
        assert list(found) == ["traspare.com"]  # hosts are reported without "www."


class TestSitemapFilter:
    def test_words_match_at_the_start_of_a_word_only(self) -> None:
        from app.collectors.sitemap import _filter_relevant

        urls = [
            "https://c.it/wp-content/uploads/2023/11/Chiesa-Madre-Sgaramella.jpg",  # "gara" inside a name + a file
            "https://c.it/biblioteche-digitali/chiesa-madre-sgaramella/",            # same name, not a tender
            "https://c.it/amministrazione-trasparente/bandi-di-gara-e-contratti",
            "https://c.it/gare-e-appalti",
            "https://c.it/wp-content/uploads/trasparenza_rifiuti.png",
            "https://c.it/amministrazione/elezioni/avviso-tessera-elettorale",
        ]
        assert _filter_relevant(urls) == [
            "https://c.it/amministrazione-trasparente/bandi-di-gara-e-contratti",
            "https://c.it/gare-e-appalti",
        ]
