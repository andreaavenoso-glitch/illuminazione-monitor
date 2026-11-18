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
                target_url=BASE, target_html=html, label="t", settings=None,
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
