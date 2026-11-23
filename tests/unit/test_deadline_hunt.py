"""Ricerca della scadenza andando in profondita' (pagina -> allegati -> PDF) finche' non si trova."""
from __future__ import annotations

from datetime import date

import pytest
from app.collectors.deadline_hunt import Doc, doc_links, hunt_deadline

BASE = "https://www.comune.esempio.it"


def make_fetch(pages: dict[str, Doc]):
    calls: list[str] = []

    async def fetch(url: str, depth: int) -> Doc:
        calls.append(url)
        d = pages.get(url)
        if d is None:
            return Doc(url, "html", "", None, depth, "non apribile: errore 404")
        return Doc(d.url, d.kind, d.text, d.raw, depth, d.note)

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


def html(url: str, text: str, links: str = "") -> Doc:
    return Doc(url, "html", text, f"<html><body><p>{text}</p>{links}</body></html>", 0)


def pdf(url: str, text: str, note: str = "") -> Doc:
    return Doc(url, "pdf", text, None, 0, note)


@pytest.mark.asyncio
async def test_page_with_the_deadline_stops_at_once():
    pages = {BASE + "/a": html(BASE + "/a", "Avviso. Le proposte devono pervenire entro il 20/01/2027.")}
    f = make_fetch(pages)
    h = await hunt_deadline(BASE + "/a", f)
    assert h.deadline == date(2027, 1, 20) and len(h.docs) == 1 and f.calls == [BASE + "/a"]


@pytest.mark.asyncio
async def test_goes_to_the_pdf_when_the_page_has_no_deadline():
    start = BASE + "/novita/1.html"
    pages = {
        start: html(start, "Approvato l'avviso pubblico per la finanza di progetto.",
                    '<a href="https://docs.altro.it/files/avviso.pdf">AVVISO PUBBLICO</a><a href="/chi-siamo">Chi siamo</a>'),
        "https://docs.altro.it/files/avviso.pdf": pdf("https://docs.altro.it/files/avviso.pdf",
                                                      "Termini: le proposte entro le ore 12:00 del 20-01-2027."),
    }
    f = make_fetch(pages)
    h = await hunt_deadline(start, f)
    assert h.deadline == date(2027, 1, 20) and h.found_in == "https://docs.altro.it/files/avviso.pdf"
    assert f.calls == [start, "https://docs.altro.it/files/avviso.pdf"]  # "Chi siamo" never opened
    assert "scadenza letta in avviso.pdf dopo 2 documenti" in h.trail()


@pytest.mark.asyncio
async def test_follows_a_scheda_page_and_then_its_pdf():
    start = BASE + "/bandi/12"
    scheda = BASE + "/bandi/12/allegati"
    doc = BASE + "/files/bando.pdf"
    pages = {
        start: html(start, "Bando di gara illuminazione.", '<a href="/bandi/12/allegati">Documenti e allegati</a>'),
        scheda: html(scheda, "Allegati disponibili.", '<a href="/files/bando.pdf">Bando di gara</a>'),
        doc: pdf(doc, "Scadenza presentazione offerte: 05/02/2027"),
    }
    h = await hunt_deadline(start, make_fetch(pages))
    assert h.deadline == date(2027, 2, 5) and [d.depth for d in h.docs] == [0, 1, 2]


@pytest.mark.asyncio
async def test_explains_why_nothing_was_found():
    start = BASE + "/n"
    pages = {
        start: html(start, "Avviso senza date.", '<a href="/files/avviso.pdf">Avviso</a>'),
        BASE + "/files/avviso.pdf": pdf(BASE + "/files/avviso.pdf", "", "PDF senza testo (scansione) o protetto"),
    }
    h = await hunt_deadline(start, make_fetch(pages))
    assert h.deadline is None and "PDF senza testo (scansione)" in h.trail() and "nessun altro link" in h.reason


@pytest.mark.asyncio
async def test_limits_documents_and_time():
    start = BASE + "/n"
    links = "".join(f'<a href="/files/a{i}.pdf">Allegato {i}</a>' for i in range(8))
    pages = {start: html(start, "Avviso.", links)}
    for i in range(8):
        pages[BASE + f"/files/a{i}.pdf"] = pdf(BASE + f"/files/a{i}.pdf", "nessuna data qui")
    h = await hunt_deadline(start, make_fetch(pages), max_docs=4)
    assert len(h.docs) == 4 and "limite di 4 documenti" in h.reason

    t = iter([0.0, 0.0, 100.0, 100.0, 100.0])
    h2 = await hunt_deadline(start, make_fetch(pages), budget_s=90, clock=lambda: next(t))
    assert "tempo massimo" in h2.reason and len(h2.docs) == 1


def test_doc_links_prefers_pdfs_and_skips_the_rest():
    raw = (
        '<a href="/f/avviso.pdf">Scarica</a><a href="/img/logo.png">Avviso</a><a href="/f/x.zip">Allegati</a>'
        '<a href="https://altro.it/pagina">Avviso pubblico</a><a href="https://store.it/d/bando.pdf">Bando</a>'
        '<a href="/scheda/7">Scheda dettaglio</a><a href="/contatti">Contatti</a>'
    )
    links = [u for _, u in doc_links(raw, BASE + "/n/1", seen=set())]
    assert BASE + "/f/avviso.pdf" in links and "https://store.it/d/bando.pdf" in links and BASE + "/scheda/7" in links
    assert not any(u.endswith(".png") or u == "https://altro.it/pagina" or u.endswith("/contatti") for u in links)
    assert BASE + "/f/x.zip" in links  # archives are read now (the technical attachments are often a .zip)
    assert links[0].endswith((".pdf", ".zip"))  # documents first


def test_manual_verification_retries_what_was_not_found():
    import inspect

    from app.services.admin_service import dispatch_verify  # noqa: F401  (module imports fine)

    src = inspect.getsource(dispatch_verify)
    assert '"force": True' in src
