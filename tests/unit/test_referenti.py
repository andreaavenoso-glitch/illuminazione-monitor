"""Referenti: nulla di dedotto, tutto verificato contro il testo della pagina."""
from __future__ import annotations

from app.collectors.referenti import merge_people, rank_people_links, site_root, verify_person

PAGE = (
    "Organi di governo. Il Sindaco Mario Rossi riceve su appuntamento. "
    "Assessore ai Lavori Pubblici e illuminazione pubblica: Giulia Bianchi, tel. 0835 123456, "
    "email lavoripubblici@comune.esempio.it. Area Tecnica - Responsabile: Verdi Paolo."
)


def _p(nome, ruolo, **kw):
    return {"nome": nome, "ruolo": ruolo, "qualifica": None, "email": None, "telefono": None, "citazione": None, **kw}


def test_person_written_on_the_page_is_verified():
    r = verify_person(_p("Mario Rossi", "sindaco"), PAGE)
    assert r and r["stato"] == "verificato"


def test_invented_name_is_dropped():
    assert verify_person(_p("Luca Neri", "sindaco"), PAGE) is None
    assert verify_person(_p("Mario", "sindaco"), PAGE) is None


def test_contacts_must_appear_literally():
    ok = verify_person(
        _p("Giulia Bianchi", "assessore", email="lavoripubblici@comune.esempio.it", telefono="0835 123456"), PAGE
    )
    assert ok["email"] == "lavoripubblici@comune.esempio.it" and ok["telefono"] == "0835 123456"
    fake = verify_person(_p("Giulia Bianchi", "assessore", email="giulia@altro.it", telefono="333 000"), PAGE)
    assert fake["email"] is None and fake["telefono"] is None


def test_surname_first_and_role_wording_next_to_the_name():
    r = verify_person(_p("Paolo Verdi", "responsabile_tecnico"), PAGE)
    assert r and r["stato"] == "verificato"


def test_role_not_next_to_name_is_only_to_confirm():
    page = "Elenco dipendenti. Anna Gialli. " + "x " * 200 + "Il sindaco e' un altro."
    r = verify_person(_p("Anna Gialli", "sindaco"), page)
    assert r and r["stato"] == "da_confermare"


def test_unknown_role_is_dropped():
    assert verify_person(_p("Mario Rossi", "bidello"), PAGE) is None


def test_merge_prefers_verified_and_keeps_source():
    a = {**verify_person(_p("Mario Rossi", "sindaco"), "Anna. " + "x " * 200 + " Mario Rossi"), "email": None}
    b = verify_person(_p("Mario Rossi", "sindaco", email="s@c.it"), "Sindaco Mario Rossi s@c.it")
    out = merge_people([(a, "https://c.it/a"), (b, "https://c.it/b")])
    assert len(out) == 1 and out[0]["stato"] == "verificato" and out[0]["fonte_url"] == "https://c.it/b"


def test_rank_people_links_picks_menu_entries_on_same_site():
    html = (
        '<a href="/amministrazione/giunta">Giunta</a><a href="/uffici/lavori-pubblici">Lavori pubblici</a>'
        '<a href="https://altro.it/giunta">Giunta</a><a href="/doc.pdf">Giunta</a><a href="/meteo">Meteo</a>'
    )
    links = rank_people_links(html, base_url="https://www.comune.esempio.it/")
    assert links == ["https://www.comune.esempio.it/amministrazione/giunta", "https://www.comune.esempio.it/uffici/lavori-pubblici"]


def test_site_root():
    assert site_root("https://www.comune.x.it/albo/a?b=1") == "https://www.comune.x.it/"
    assert site_root("nonurl") is None
