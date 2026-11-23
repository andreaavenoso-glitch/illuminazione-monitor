import pytest
from app.collectors.doc_collect import LIVELLI, Livello, collect_docs

PAGE = '<html><body>' + ' ' * 10 + '<a href="/a/avviso.pdf">Avviso pubblico</a><a href="/a/delibera.html">Delibera di giunta</a></body></html>'
DELIBERA = '<html><body><a href="/a/relazione.pdf">Relazione tecnica</a></body></html>'


async def fake_fetch(url):
    if url.endswith("/avviso/"):
        return "pagina", PAGE
    if url.endswith("delibera.html"):
        return "testo delibera", DELIBERA
    if url.endswith(".pdf"):
        return f"testo di {url.rsplit('/', 1)[-1]}", None
    return "", None


@pytest.mark.asyncio
async def test_base_reads_the_page_and_what_it_links_directly():
    docs, why = await collect_docs("https://c.it/avviso/", fake_fetch, LIVELLI["base"])
    names = [d.name for d in docs]
    assert names[0] == "pagina dell'avviso" and "avviso.pdf" in names and "delibera.html" in names
    assert "relazione.pdf" not in names  # that one is one level deeper


@pytest.mark.asyncio
async def test_deep_goes_one_level_further():
    docs, _ = await collect_docs("https://c.it/avviso/", fake_fetch, LIVELLI["approfondita"])
    assert "relazione.pdf" in [d.name for d in docs]
    assert max(d.depth for d in docs) == 2


@pytest.mark.asyncio
async def test_limits_of_documents_and_time_are_respected():
    docs, why = await collect_docs("https://c.it/avviso/", fake_fetch, Livello(max_docs=2, depth=3, budget_s=99, per_page=8))
    assert len(docs) == 2 and "massimo di 2" in why
    ticks = iter(range(0, 1000, 100))
    docs, why = await collect_docs("https://c.it/avviso/", fake_fetch, Livello(30, 3, 150.0, 8), clock=lambda: next(ticks))
    assert "tempo massimo" in why and len(docs) < 30


@pytest.mark.asyncio
async def test_unreadable_documents_are_kept_with_empty_text():
    async def nothing(url):
        return "", None

    docs, why = await collect_docs("https://c.it/avviso/", nothing, LIVELLI["base"])
    assert len(docs) == 1 and docs[0].text == "" and "esauriti" in why
