import pytest
from shared_models.import_pagine import ImportError_, valida_pagine

PAGE = "<html><body>" + "x" * 300 + "</body></html>"


def test_keeps_valid_pages_once_and_drops_the_rest():
    pages = valida_pagine({"pagine": [
        {"url": "https://dgegovpa.it/Arluno/Albo/Albo#a", "html": PAGE},
        {"url": "https://dgegovpa.it/Arluno/Albo/Albo", "html": PAGE},  # same address
        {"url": "javascript:alert(1)", "html": PAGE},
        {"url": "https://x.it/vuota", "html": "<p>x</p>"},
        "not a dict",
    ]})
    assert [p["url"] for p in pages] == ["https://dgegovpa.it/Arluno/Albo/Albo"]


def test_caps_the_size_of_a_page():
    pages = valida_pagine({"pagine": [{"url": "https://x.it/a", "html": "y" * 900_000}]})
    assert len(pages[0]["html"]) == 600_000


@pytest.mark.parametrize("bad", [None, [], {}, {"pagine": "x"}, {"pagine": []}, {"pagine": [{"url": "ftp://x", "html": PAGE}]}])
def test_rejects_what_is_not_a_bundle(bad):
    with pytest.raises(ImportError_):
        valida_pagine(bad)


def test_a_page_read_by_the_browser_is_served_without_touching_the_network():
    import asyncio

    from app.collectors import adaptive_fetch as af

    af.PREFETCHED.clear()
    af.PREFETCHED["https://dgegovpa.it/Arluno/Albo/Albo"] = "<html><body><p>Avviso pubblica illuminazione</p>" + "x" * 300 + "</body></html>"
    try:
        res = asyncio.run(af.adaptive_fetch_result("https://dgegovpa.it/Arluno/Albo/Albo#top", max_html_chars=100000, timeout=1,
                                                   playwright_min_chars=0, playwright_wait_ms=0, label="t"))
    finally:
        af.PREFETCHED.clear()
    assert "pubblica illuminazione" in res.text and res.error is None


def test_pick_comune_exact_unique_or_ambiguous():
    from app.services.browser_import import pick_comune

    c = [(1, "Comune di Arluno"), (2, "Comune di Arcore"), (3, "Comune di Arluno Nuovo")]
    assert pick_comune(c, "arluno")[0] == 1            # exact wins over "contains"
    assert pick_comune(c, "Comune di Arcore")[0] == 2
    item, others = pick_comune(c, "ar")
    assert item is None and "Comune di Arcore" in others  # ambiguous: the names are returned
    assert pick_comune(c, "xyz") == (None, [])


def test_a_host_served_by_the_browser_is_never_requested_for_what_it_did_not_send():
    import asyncio

    from app.collectors import adaptive_fetch as af

    af.PREFETCHED.clear()
    af.PREFETCHED["https://dgegovpa.it/Arluno/albo/albo.aspx"] = "<html><body>" + "x" * 300 + "</body></html>"
    try:
        res = asyncio.run(af.adaptive_fetch_result("https://www.dgegovpa.it/Arluno/albo/dati/1.PDF", max_html_chars=1000, timeout=1,
                                                   playwright_min_chars=0, playwright_wait_ms=0, label="t"))
    finally:
        af.PREFETCHED.clear()
    assert res.text == "" and res.error == "skipped_import"  # no network request: it returned at once


def test_detail_pages_of_the_import_are_recognised():
    from app.collectors.dgegov import is_detail_page

    assert is_detail_page("https://x.it/b.aspx?cig=BD8029248D")
    assert not is_detail_page("https://x.it/b.aspx?_mpag=2")
