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


# --- regole di fiducia (Lombardia) ----------------------------------------------------
from datetime import date  # noqa: E402

from shared_models.referenti_logic import (  # noqa: E402
    affidabilita,
    azione,
    election_date,
    freshness,
    has_decree,
    page_date,
    press_search_url,
)

T = date(2026, 11, 23)


def test_page_and_election_dates():
    assert page_date("Ultimo aggiornamento: 10/04/2024. Altro 01/01/2020", T) == date(2024, 4, 10)
    assert page_date("nessuna data utile", T) is None
    assert election_date("Il sindaco eletto alle elezioni comunali del 9 giugno 2024", T) == date(2024, 6, 9)
    assert election_date("pagina senza elezioni", T) is None


def test_politici_need_a_page_after_the_election():
    # Albino: page of 10/04/2024, election 09/06/2024 -> to verify
    ok, why = freshness("assessore", date(2024, 4, 10), date(2024, 6, 9), False, T)
    assert not ok and "precedente alle elezioni" in why
    assert freshness("sindaco", date(2025, 3, 1), date(2024, 6, 9), False, T)[0]
    assert not freshness("sindaco", None, date(2024, 6, 9), False, T)[0]
    # election date unknown: the page must be recent
    assert not freshness("sindaco", date(2025, 3, 1), None, False, T)[0]
    assert freshness("sindaco", date(2026, 5, 1), None, False, T)[0]


def test_tecnici_need_12_months_or_a_decree():
    assert freshness("responsabile_tecnico", date(2026, 3, 1), date(2021, 10, 1), False, T)[0]
    assert not freshness("responsabile_tecnico", date(2025, 3, 1), date(2024, 6, 9), False, T)[0]  # after the vote, still old
    assert freshness("responsabile_tecnico", None, None, True, T)[0]
    assert has_decree("nominato con Decreto sindacale n. 12 del 2025")
    assert not has_decree("Mario Rossi, responsabile")


def test_affidabilita_and_azione():
    full = [{"ruolo": r, "stato": "verificato"} for r in ("sindaco", "assessore", "responsabile_tecnico")]
    assert affidabilita(full) == (100, "certo") and azione(full) == "Invia"
    two = full[:2]
    assert affidabilita(two) == (67, "ipotetico")
    mayor = [{"ruolo": "sindaco", "stato": "verificato"}, {"ruolo": "responsabile_tecnico", "stato": "verificato"}]
    assert affidabilita(mayor)[1] == "ipotetico" and azione(mayor) == "Invia – verifica nomi"
    assert azione([{"ruolo": "sindaco", "stato": "da_confermare"}]) == "Invia con cautela"
    assert azione([]) == "Da cercare" and affidabilita([]) == (0, "ipotetico")
    assert "tbs=qdr:m6" in press_search_url("Comune di Arluno")


def test_workbook_has_index_and_one_sheet_per_province():
    import io

    import openpyxl
    from app.services.referenti_export import referenti_workbook

    people = [
        {"ruolo": "sindaco", "nome": "Mario Rossi", "stato": "verificato", "email": "s@c.it", "telefono": None,
         "fonte_url": "https://c.it/g", "motivo": None, "verified_at": "2026-11-23"},
        {"ruolo": "assessore", "nome": "Giulia Bianchi", "stato": "da_confermare", "email": None, "telefono": None,
         "fonte_url": "https://c.it/g", "motivo": "pagina senza data", "verified_at": "2026-11-23"},
    ]
    entries = [
        {"ente": "Comune di Arluno", "provincia": "MI", "people": people},
        {"ente": "Comune di Albino", "provincia": "BG", "people": people[:1]},
    ]
    wb = openpyxl.load_workbook(io.BytesIO(referenti_workbook(entries)))
    assert wb.sheetnames == ["Indice", "BG", "MI"]
    mi = wb["MI"]
    assert [c.value for c in mi[1]][:3] == ["Comune", "Sindaco", "Assessore ai Lavori pubblici"]
    assert mi["C2"].value == "Giulia Bianchi (da confermare)" and "Affidabilità" not in [c.value for c in mi[1]]
    wb2 = openpyxl.load_workbook(io.BytesIO(referenti_workbook(entries, interno=True)))
    assert "Azione" in [c.value for c in wb2["MI"][1]]


def test_page_furniture_is_not_a_name():
    # real case: "Sindaco: Condividi Facebook Twitter" on the page of a comune
    from app.collectors.referenti import looks_like_name
    from app.collectors.rules_extract import extract_people_by_rules

    page = "Sindaco Condividi Facebook Twitter Stampa PDF. Altro testo."
    assert extract_people_by_rules(page) == []
    assert verify_person(_p("Condividi Facebook Twitter", "sindaco"), page) is None
    assert looks_like_name("Mario Rossi") and looks_like_name("Maria Rosaria De Luca")
    assert not looks_like_name("Facebook Twitter") and not looks_like_name("Area Tecnica")


# --- ricerca web con agente ---------------------------------------------------------------
def test_agent_result_is_normalized_and_freshness_decides_the_state():
    from app.collectors.referenti_agent import normalize_result, parse_json

    raw = """```json
    {"elezione_data": "2024-06-09", "mandato_scadenza": "2029-06-30",
     "pec": {"valore": "protocollo@pec.comune.it", "fonte_url": "https://indicepa.gov.it/x"},
     "persone": [
       {"ruolo": "sindaco", "nome": "Mario Rossi", "qualifica": "Sindaco", "email": "s@c.it", "telefono": null,
        "fonte_url": "https://c.it/giunta", "data_pagina": "2025-03-01", "decreto_in_vigore": false,
        "citazione": "Sindaco Mario Rossi", "stato": "VERIFICATO", "note": ""},
       {"ruolo": "assessore", "nome": "Giulia Bianchi", "qualifica": "Assessore LLPP", "email": null, "telefono": null,
        "fonte_url": "https://c.it/giunta", "data_pagina": "2024-04-10", "decreto_in_vigore": false,
        "citazione": "x", "stato": "VERIFICATO", "note": ""},
       {"ruolo": "responsabile_tecnico", "nome": "Condividi Facebook Twitter", "fonte_url": "https://c.it/u", "stato": "VERIFICATO"},
       {"ruolo": "bidello", "nome": "Luca Neri", "fonte_url": "https://c.it/u", "stato": "VERIFICATO"},
       {"ruolo": "responsabile_tecnico", "nome": "Paolo Verdi", "fonte_url": "https://c.it/u", "data_pagina": null,
        "decreto_in_vigore": true, "stato": "VERIFICATO"},
       {"ruolo": "rup", "nome": "Anna Gialli", "fonte_url": "", "stato": "VERIFICATO"}
     ],
     "lacune": ["telefono assessore"], "url_controllati": ["https://c.it/giunta"], "stampa": "nessun rimpasto"}
    ```"""
    out = normalize_result(parse_json(raw), date(2026, 11, 23))
    by = {p["nome"]: p for p in out["people"]}
    assert set(by) == {"Mario Rossi", "Giulia Bianchi", "Paolo Verdi"}  # furniture, unknown role, no source: dropped
    assert by["Mario Rossi"]["stato"] == "verificato"
    assert by["Giulia Bianchi"]["stato"] == "da_confermare" and "precedente alle elezioni" in by["Giulia Bianchi"]["motivo"]
    assert by["Paolo Verdi"]["stato"] == "verificato"  # decree in force
    assert out["pec"] == ("protocollo@pec.comune.it", "https://indicepa.gov.it/x")
    assert out["elezione"] == date(2024, 6, 9) and out["lacune"] == ["telefono assessore"]


def test_agent_parse_json_rejects_garbage():
    from app.collectors.referenti_agent import parse_json

    assert parse_json("niente json qui") is None and parse_json("{rotto") is None


def test_agent_tools_are_the_server_side_web_tools():
    from types import SimpleNamespace

    from app.collectors.referenti_agent import tools

    t = tools(SimpleNamespace(referenti_max_searches=5, referenti_max_fetches=9))
    assert [x["type"] for x in t] == ["web_search_20260209", "web_fetch_20260209"]
    assert t[0]["max_uses"] == 5 and t[1]["max_uses"] == 9


def test_web_search_is_billed_per_search():
    from types import SimpleNamespace

    from app.usage import usage_row

    u = SimpleNamespace(
        input_tokens=1000, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0,
        server_tool_use=SimpleNamespace(web_search_requests=5),
    )
    row = usage_row(u, model="claude-sonnet-5-5", purpose="referenti_agent", label="x")
    assert abs(row["cost_usd"] - (1000 * 2e-6 + 100 * 10e-6 + 5 * 0.01)) < 1e-6


def test_referenti_table_groups_people_by_role_and_adds_pec():
    from app.api.routes.regions import _referenti_table

    p = lambda ruolo, nome, stato="verificato", email=None: {  # noqa: E731
        "ruolo": ruolo, "nome": nome, "stato": stato, "email": email, "telefono": None,
        "fonte_url": "https://c.it", "qualifica": None, "motivo": None, "citazione": None,
    }
    people = {
        "Comune di A": [p("sindaco", "Mario Rossi"), p("assessore", "Giulia Bianchi"),
                        p("responsabile_tecnico", "Paolo Neri"), p("rup", "Anna Gialli")],
        "Comune di B": [p("ente", "PEC dell'ente", email="b@pec.it")],
    }
    rows = _referenti_table([{"ente": "Comune di A"}, {"ente": "Comune di C"}], [], people, {"Comune di A": {"passi_ok": 9}}, {"Comune di C": "c@pec.it"})
    by = {r["ente"]: r for r in rows}
    assert set(by) == {"Comune di A", "Comune di B", "Comune di C"}
    a = by["Comune di A"]
    assert [x["nome"] for x in a["sindaco"]] == ["Mario Rossi"] and a["azione"] == "Invia"
    assert [x["nome"] for x in a["tecnico"]] == ["Paolo Neri", "Anna Gialli"] and a["passi_ok"] == 9 and a["cercato"]
    assert by["Comune di C"]["pec"] == "c@pec.it" and by["Comune di C"]["azione"] == "Da cercare" and not by["Comune di C"]["cercato"]
    assert by["Comune di B"]["pec"] == "b@pec.it"


def test_menu_words_and_repeated_words_are_not_names():
    from app.collectors.referenti import looks_like_name
    from app.collectors.rules_extract import extract_people_by_rules

    # real false positive from a comune's menu: "Sindaco ... Incarichi Organizzazione Incarichi"
    assert not looks_like_name("Incarichi Organizzazione Incarichi")
    assert not looks_like_name("Titolari Incarichi")
    assert extract_people_by_rules("Sindaco Incarichi Organizzazione Incarichi politici Giunta") == []
    assert looks_like_name("Maria Rosaria De Luca")


def test_html_entities_in_links_are_decoded():
    from app.collectors.page_gate import safe_join

    assert safe_join("https://c.it/", "amministrazione/organi_di_governo/&num;organizzazione") == (
        "https://c.it/amministrazione/organi_di_governo/#organizzazione"
    )
    assert safe_join("https://c.it/a/", "b?x=1&amp;y=2") == "https://c.it/a/b?x=1&y=2"
