import pytest
from app.collectors.deadline_hunt import doc_links
from app.collectors.doc_collect import LIVELLI, collect_docs, doc_name
from app.collectors.js_links import file_name_from_url, resolve_js_link
from app.collectors.main_content import has_document_links, main_region
from app.tasks.verify_records import attachment_links, notice_page

BASE = "https://www.comune.scanzanojonico.mt.it/novita/notizie/novita_171.html"
PDF = "javascript:SCHIOCCIOLA('en=e1015&MESSA=PUBBLICA&DSK=0000V601026BK&NOME=ver 3 NUOVO AVVISO X PPP-signed.pdf&FORM=pdf','EG0/EGDOCVISJS.HBL')"
ZIP = "javascript:SCHIOCCIOLA('en=e1015&MESSA=PUBBLICA&DSK=0000V501026BK&NOME=allegati tecnici.zip&FORM=zip','EG0/EGDOCVISJS.HBL')"


def test_the_javascript_call_becomes_the_address_it_opens():
    url = resolve_js_link(PDF, BASE)
    assert url == ("https://www.comune.scanzanojonico.mt.it/EG0/EGDOCVISJS.HBL?en=e1015&MESSA=PUBBLICA&DSK=0000V601026BK"
                   "&NOME=ver%203%20NUOVO%20AVVISO%20X%20PPP-signed.pdf&FORM=pdf")
    assert file_name_from_url(url) == "ver 3 NUOVO AVVISO X PPP-signed.pdf"
    assert doc_name(url) == "ver 3 NUOVO AVVISO X PPP-signed.pdf"


def test_other_shapes_and_non_documents():
    assert resolve_js_link("javascript:window.open('/files/allegato.pdf')", "https://c.it/p/x.html") == "https://c.it/files/allegato.pdf"
    assert resolve_js_link("javascript:void(0)", BASE) is None
    assert resolve_js_link("https://c.it/a.pdf", BASE) is None
    assert resolve_js_link("javascript:history.back()", BASE) is None


def _page(*items):
    body = "".join(f'<a href="{h}" title="{t}" aria-label="Scarica {t}"> {t} </a>' for h, t in items)
    return "<html><body><main><article><h1>Avviso</h1><p>" + "Proposte di finanza di progetto. " * 120 + f"</p></article><section id='allegati'>{body}</section></main></body></html>"


def test_the_attachments_of_the_scanzano_page_are_found():
    page = _page((PDF, "AVVISO PUBBLICO"), (ZIP, "Allegati tecnici"))
    links = [u for _, u in doc_links(page, BASE, seen=set())]
    assert any("FORM=pdf" in u and "EGDOCVISJS.HBL" in u for u in links)
    assert any("FORM=zip" in u for u in links)
    att = attachment_links(page, base_url=BASE, limit=8)
    assert any("FORM=pdf" in u for u in att) and any("FORM=zip" in u for u in att)
    assert has_document_links(main_region(page))
    assert has_document_links(notice_page(page)[1])


@pytest.mark.asyncio
async def test_the_document_behind_the_script_link_is_fetched_and_named(httpx_mock):
    from app.tasks.verify_records import _fetch_plain

    page = _page((PDF, "AVVISO PUBBLICO"))
    httpx_mock.add_response(url=BASE, text=page, headers={"content-type": "text/html"})
    httpx_mock.add_response(
        url=resolve_js_link(PDF, BASE), content=b"not a pdf at all", headers={"content-type": "application/octet-stream"}
    )
    docs, _ = await collect_docs(BASE, _fetch_plain, LIVELLI["base"])
    assert [d.name for d in docs] == ["pagina dell'avviso", "ver 3 NUOVO AVVISO X PPP-signed.pdf"]


def test_a_tiny_redirect_page_points_to_the_real_file():
    from app.collectors.js_links import js_redirect_target

    base = "https://c.it/EG0/EGDOCVISJS.HBL?x=1"
    assert js_redirect_target("<script>window.location.href='/DOC/avviso.pdf';</script>", base) == "https://c.it/DOC/avviso.pdf"
    assert js_redirect_target('<script>location.replace("../files/a.zip")</script>', base) == "https://c.it/files/a.zip"
    assert js_redirect_target("<script>window.open('https://store.it/a.pdf','_self')</script>", base) == "https://store.it/a.pdf"
    assert js_redirect_target('<meta http-equiv="refresh" content="0;url=/d/x.pdf">', base) == "https://c.it/d/x.pdf"
    assert js_redirect_target("<script>alert('ciao')</script>", base) is None
    assert js_redirect_target("<html>" + "x" * 5000 + "location.href='/a'</html>", base) is None  # a real page, not a redirect


@pytest.mark.asyncio
async def test_the_pdf_behind_a_redirect_page_is_downloaded_and_read(httpx_mock, monkeypatch):
    from app.tasks.verify_records import _fetch_plain

    first = "https://c.it/EG0/EGDOCVISJS.HBL?en=1&NOME=avviso.pdf&FORM=pdf"
    httpx_mock.add_response(url=first, text="<script >window.location.href='/DOC/real.pdf'</script>", headers={"content-type": "text/html"})
    httpx_mock.add_response(url="https://c.it/DOC/real.pdf", content=b"%PDF-1.4 fake", headers={"content-type": "application/pdf"})
    import app.tasks.verify_records as vr

    monkeypatch.setattr(vr, "pdf_to_text", lambda data: "Avviso pubblico, scadenza 20/01/2027" if data.startswith(b"%PDF") else "")
    text, raw = await _fetch_plain(first)
    assert text == "Avviso pubblico, scadenza 20/01/2027" and raw is None
