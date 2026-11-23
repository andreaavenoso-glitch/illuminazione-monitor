"""Script a costo zero per i referenti: percorso del sito, regole di fiducia, stampa, checklist."""
from __future__ import annotations

from datetime import date

import pytest
from app.collectors.referenti_script import apply_press, menu_links, parse_press, score_link, search_referenti

TODAY = date(2026, 11, 23)
BASE = "https://www.comune.esempio.it"

SITE = {
    BASE + "/": '<a href="/amministrazione">Amministrazione</a><a href="/novita">Novità</a>'
                '<a href="/servizi">Servizi</a><footer>PEC comune.esempio@pec.it</footer>',
    BASE + "/amministrazione": "Amministrazione. " + "x " * 600
        + '<a href="/amministrazione/organi-politici">Organi politici</a><a href="/amministrazione/uffici">Uffici</a>'
        + '<a href="/amministrazione/personale">Personale</a>',
    BASE + "/amministrazione/organi-politici": (
        "Organi politici. Ultimo aggiornamento: 10/09/2026. Elezioni comunali del 9 giugno 2024. "
        "Sindaco: Mario Rossi. Assessore ai Lavori Pubblici e Illuminazione: Giulia Bianchi. "
        "Assessore alla Cultura: Anna Verdi. " + "x " * 600
        + '<a href="/scheda/rossi">Mario Rossi</a><a href="/scheda/bianchi">Giulia Bianchi</a><a href="/scheda/verdi">Anna Verdi</a>'
    ),
    BASE + "/scheda/rossi": "Scheda. Aggiornato al 10/09/2026. Mario Rossi, Sindaco. Email: sindaco@comune.esempio.it " + "x " * 600,
    BASE + "/scheda/bianchi": "Scheda. Aggiornato al 10/09/2026. Giulia Bianchi - Assessore ai lavori pubblici. " + "x " * 600,
    BASE + "/scheda/verdi": "Scheda. Aggiornato al 10/09/2026. Anna Verdi - Assessore alla cultura. " + "x " * 600,
    BASE + "/amministrazione/uffici": "Uffici. Aggiornato al 12/03/2026. Responsabile Area Tecnica: Paolo Neri, nominato con decreto sindacale n. 4. " + "x " * 600,
    BASE + "/amministrazione/personale": "Personale. Incarichi dirigenziali. " + "x " * 600,
}


async def fetch(url: str):
    html = SITE.get(url)
    return (html, html) if html else ("", None)


async def no_press(_u: str) -> str:
    return ""


def test_link_scoring_prefers_people_pages():
    assert score_link("Organi politici", "/a")[0] >= 30
    assert score_link("Mario Rossi", "/s/1", person_ok=True)[1] == {"scheda"}  # on a giunta page
    assert score_link("Sindaco Mario Rossi", "/s/1")[0] == 40
    assert score_link("Meteo", "/meteo")[0] == 0
    assert score_link("Giunta", "/giunta.pdf")[0] == 0
    assert any(t == "Organi politici" for _, _, t, _ in menu_links(SITE[BASE + "/amministrazione"], BASE + "/amministrazione"))


@pytest.mark.asyncio
async def test_full_search_follows_the_site_and_applies_the_rules():
    r = await search_referenti("Comune di Esempio", [BASE + "/"], fetch, no_press, pec="comune.esempio@pec.it", today=TODAY)
    by = {(p["ruolo"], p["nome"]): p for p in r["people"]}
    assert ("sindaco", "Mario Rossi") in by and ("assessore", "Giulia Bianchi") in by
    assert ("responsabile_tecnico", "Paolo Neri") in by
    assert not any(n == "Anna Verdi" and role == "assessore" and "Lavori" in (by[(role, n)]["qualifica"] or "") for role, n in by)
    assert by[("sindaco", "Mario Rossi")]["stato"] == "verificato"          # page after the election
    assert by[("sindaco", "Mario Rossi")]["email"] == "sindaco@comune.esempio.it"
    assert by[("responsabile_tecnico", "Paolo Neri")]["stato"] == "verificato"  # decree in force
    assert r["elezione"] == date(2024, 6, 9) and r["mandato_scadenza"] == date(2029, 6, 9)
    steps = {c["n"]: c for c in r["checklist"]}
    assert steps[1]["ok"] and steps[3]["ok"] and steps[4]["ok"] and steps[9]["ok"] and steps[10]["ok"]
    assert not steps[11]["ok"] and "RSS non raggiungibile" in steps[11]["nota"]
    assert steps[12]["ok"]  # the mayor is on two pages
    assert any("passi non riusciti" in x for x in r["lacune"])


@pytest.mark.asyncio
async def test_page_before_the_election_is_only_to_confirm():
    old = dict(SITE)
    old[BASE + "/amministrazione/organi-politici"] = old[BASE + "/amministrazione/organi-politici"].replace(
        "10/09/2026", "10/04/2024"
    )
    old[BASE + "/scheda/rossi"] = old[BASE + "/scheda/rossi"].replace("10/09/2026", "10/04/2024")

    async def f(url):
        h = old.get(url)
        return (h, h) if h else ("", None)

    r = await search_referenti("Comune di Esempio", [BASE + "/"], f, no_press, pec=None, today=TODAY)
    sindaco = next(p for p in r["people"] if p["ruolo"] == "sindaco")
    assert sindaco["stato"] == "da_confermare" and "precedente alle elezioni" in sindaco["motivo"]
    assert not next(c for c in r["checklist"] if c["n"] == 9)["ok"]


RSS = """<rss><channel>
<item><title>Esempio, rimpasto in giunta: Bianchi lascia i lavori pubblici</title><pubDate>Mon, 03 Nov 2026 10:00:00 GMT</pubDate><link>https://n.it/1</link></item>
<item><title>Sagra del paese</title><pubDate>Mon, 03 Nov 2026 10:00:00 GMT</pubDate><link>https://n.it/2</link></item>
<item><title>Vecchio rimpasto</title><pubDate>Mon, 03 Mar 2025 10:00:00 GMT</pubDate><link>https://n.it/3</link></item>
</channel></rss>"""


def test_press_signals_downgrade_the_named_person():
    sig = parse_press(RSS, TODAY)
    assert len(sig) == 1 and sig[0][1].startswith("Esempio, rimpasto")
    people = [
        {"ruolo": "assessore", "nome": "Giulia Bianchi", "stato": "verificato", "motivo": None},
        {"ruolo": "sindaco", "nome": "Mario Rossi", "stato": "verificato", "motivo": None},
    ]
    apply_press(people, sig)
    assert people[0]["stato"] == "da_confermare" and "stampa del 03/11/2026" in people[0]["motivo"]
    assert people[1]["stato"] == "verificato"
    assert parse_press("non xml", TODAY) == []


def test_two_word_menu_entries_are_not_people_unless_on_a_giunta_page():
    from app.collectors.referenti_script import menu_links, score_link

    # real case: "Animali Domestici" under "topics" ate the page budget as a "person"
    assert score_link("Animali Domestici", "/it/topics/animale-domestico")[0] == 0
    assert score_link("Mario Rossi", "/it/page/53648")[0] == 0
    assert score_link("Mario Rossi", "/it/page/53648", person_ok=True)[1] == {"scheda"}
    assert "scheda" in score_link("Sindaco Mario Rossi", "/x")[1]  # says so itself
    assert "scheda" in score_link("Mario Rossi", "/amministratori/mario-rossi")[1]  # so does the address
    html = '<a href="/p/1">Mario Rossi</a><a href="/p/2">Animali Domestici</a>'
    on_giunta = {t for _, _, t, _ in menu_links(html, "https://c.it/giunta", {"giunta"})}
    assert "Mario Rossi" in on_giunta
    assert menu_links(html, "https://c.it/home", set()) == []


def test_vendor_hosted_trasparenza_is_followed_but_other_hosts_are_not():
    from app.collectors.referenti_script import menu_links

    html = ('<a href="https://dgegovpa.it/Arluno/amministrazionetrasparente/Organi">Organi politici</a>'
            '<a href="https://www.altro-sito.it/organi">Organi politici</a>')
    urls = [u for _, u, _, _ in menu_links(html, "https://www.comune.arluno.mi.it/", set())]
    assert urls == ["https://dgegovpa.it/Arluno/amministrazionetrasparente/Organi"]


def test_votive_lighting_is_not_public_lighting():
    from shared_models.categories import categorize

    assert categorize(stato_procedurale=None, text="Tariffe illuminazione votiva cimitero anno 2023") is None
    assert categorize(stato_procedurale=None, text="Avviso cittadini servizio illuminazione votiva del cimitero") is None


def test_generic_link_uses_card_title_and_menu_words_are_not_names():
    html = (
        '<div><h3>Giunta Comunale</h3><p>La Giunta è composta dal sindaco</p><a href="/it/page/x1">Vai alla Pagina</a></div>'
        '<div><h3>Sindaco</h3><a href="/it/page/x2">Vai alla Pagina</a></div>'
        '<a href="/it/legal_notices">Note legali</a><a href="/it/page/fb">Feedback accessibilità</a>'
        '<a href="/it/page/m">Mario Rossi</a>'
    )
    out = {u: (sc, t) for sc, u, _, t in menu_links(html, "https://c.it/it/page/organi", {"giunta"})}
    assert "giunta" in out["https://c.it/it/page/x1"][1] and "giunta" in out["https://c.it/it/page/x2"][1]
    assert "https://c.it/it/legal_notices" not in out and "https://c.it/it/page/fb" not in out
    assert "scheda" in out["https://c.it/it/page/m"][1]
