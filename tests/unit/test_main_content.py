from datetime import date

from app.collectors.deadline_hunt import doc_links
from app.collectors.main_content import main_region, main_text
from shared_models.relevance import SCADUTO, record_state

CORPO = "Procedura telematica aperta per l'affidamento in concessione del servizio degli impianti pubblicitari. " * 6
PAGE = f"""
<html><body>
<header><a href="/pnrr">Attuazione PNRR EU</a></header>
<nav><a href="/amministrazione">Amministrazione</a></nav>
<div class="sidebar"><h3>Ultime notizie</h3>
  <p>Graduatoria definitiva 19 Novembre 2026</p><a href="/files/Orari-Bus-2026.pdf">Orari bus</a></div>
<main><article><h1>Procedura telematica aperta</h1><p>{CORPO}</p>
  <a href="/files/BANDO_E_DISCIPLINARE-GARA.pdf">BANDO E DISCIPLINARE GARA</a>
  <p>Ultimo aggiornamento 20 Settembre 2022</p></article></main>
<footer><a href="/files/Orario-guardia-medica.pdf">Orario guardia medica</a> PEC protocollo@pec.comune.it</footer>
</body></html>
"""


def test_the_site_around_the_notice_is_left_out():
    text = main_text(PAGE)
    assert "impianti pubblicitari" in text and "Ultimo aggiornamento 20 Settembre 2022" in text
    for chrome in ("PNRR", "Ultime notizie", "19 Novembre 2026", "Orari bus", "guardia medica", "protocollo@pec"):
        assert chrome not in text


def test_only_the_links_of_the_notice_are_followed():
    links = [u for _, u in doc_links(main_region(PAGE), "https://c.it/2021/procedura/", seen=set())]
    assert "https://c.it/files/BANDO_E_DISCIPLINARE-GARA.pdf" in links
    assert not any("Orari-Bus" in u or "guardia-medica" in u for u in links)
    # read as a whole page the unrelated documents would have been followed too
    whole = [u for _, u in doc_links(PAGE, "https://c.it/2021/procedura/", seen=set())]
    assert any("Orari-Bus" in u for u in whole)


def test_a_page_without_structure_is_read_as_a_whole():
    flat = "<html><body><div>" + "Avviso pubblico per illuminazione pubblica. " * 30 + "</div></body></html>"
    assert "Avviso pubblico" in main_text(flat)
    tiny = "<html><body><p>Poco testo</p></body></html>"
    assert main_region(tiny) == tiny or "Poco testo" in main_text(tiny)


def test_a_tender_or_call_with_no_deadline_and_an_old_address_is_over():
    today = date(2026, 11, 23)
    old = "https://www.policoro.basilicata.it/29/07/2021/procedura-telematica-aperta/"
    new = "https://www.comune.it/2026/11/avviso-manifestazione/"
    for cat in ("gara", "manifestazione_interesse"):
        assert record_state(cat, None, None, old, None, today)[0] == SCADUTO
        assert record_state(cat, None, None, new, None, today)[0] == "da_verificare"
    # a deadline always decides, whatever the address says
    assert record_state("gara", date(2026, 12, 20), None, old, "aperto", today)[0] == "aperto"
