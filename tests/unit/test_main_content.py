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


ALLEGATI_FUORI = f"""
<html><body><header><a href="/x">Menu</a></header>
<main>
<article><h1>Avviso pubblico</h1><p>{CORPO}</p></article>
<section id="allegati"><h2>Allegati</h2>
  <a href="/files/allegati-tecnici.zip">Allegati tecnici</a><a href="/files/AVVISO-PUBBLICO.pdf">AVVISO PUBBLICO</a></section>
</main>
<footer><a href="/files/Orari-Bus.pdf">Orari bus</a></footer></body></html>
"""


def test_the_attachments_section_next_to_the_article_is_kept():
    links = [u for _, u in doc_links(main_region(ALLEGATI_FUORI), "https://c.it/novita/n171.html", seen=set())]
    assert "https://c.it/files/allegati-tecnici.zip" in links and "https://c.it/files/AVVISO-PUBBLICO.pdf" in links
    assert not any("Orari-Bus" in u for u in links)


def test_attachments_outside_main_are_kept_when_main_is_an_article_only():
    page = (
        f"<html><body><div class='contenuto'><article><p>{CORPO}</p></article></div>"
        "<div class='it-allegati'><a href='/f/avviso.pdf'>AVVISO PUBBLICO</a></div></body></html>"
    )
    links = [u for _, u in doc_links(main_region(page), "https://c.it/n/1", seen=set())]
    assert "https://c.it/f/avviso.pdf" in links


def test_when_the_central_part_links_nothing_the_whole_page_is_used_for_the_links():
    from app.tasks.verify_records import notice_page

    page = (
        f"<html><body><main><article><p>{CORPO}</p></article></main>"
        "<div id='sx'><a href='/f/avviso.pdf'>AVVISO PUBBLICO</a></div></body></html>"
    )
    text, raw = notice_page(page)
    assert "impianti pubblicitari" in text  # the text is still the central part's
    links = [u for _, u in doc_links(raw, "https://c.it/n/1", seen=set())]
    assert "https://c.it/f/avviso.pdf" in links
