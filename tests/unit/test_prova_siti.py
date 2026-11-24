"""Rapporto delle limitazioni della prova gratuita."""
from __future__ import annotations

from infra.scripts.prova_siti import limitations


def test_limitations_are_listed_in_words():
    sites = [
        {"ente": "A", "error": "reset"},
        {"ente": "B", "pages_full": 3, "stopped_by": "pages",
         "hunts": [{"deadline": None, "reason": "nessun altro link a documenti da seguire", "notes": ["PDF senza testo (scansione) o protetto"]},
                   {"deadline": "2027-01-20", "reason": "", "notes": []}],
         "checklist": [{"passo": "Giunta / organi politici", "ok": False}, {"passo": "PEC (IPA)", "ok": True}]},
    ]
    out = limitations(sites)
    joined = "\n".join(out)
    assert "Siti non leggibili (1): A" in joined and "3 pagine nominano i servizi" in joined
    assert "budget" in joined and "PDF senza testo" in joined and "Referenti B: passi non riusciti — Giunta" in joined


def test_no_limitations():
    assert limitations([{"ente": "A", "pages": 5, "checklist": [{"passo": "x", "ok": True}]}]) == [
        "Nessuna limitazione rilevata su questi siti."
    ]


def test_riepilogo_totals_per_size_class_and_gold():
    from infra.scripts.prova_siti import riepilogo

    ok = {"ente": "Comune di Segrate", "fascia": "L", "pages": 30,
          "records": [{"categoria": "manifestazione_interesse"}, {"categoria": "pre_gara"}],
          "hunts": [{"deadline": "2027-01-20"}, {"deadline": None}],
          "analisi": [{"campi": ["cig", "durata"]}, {"campi": ["cig"]}],
          "referenti": [{"ruolo": "sindaco", "nome": "Paolo Di Chio"}, {"ruolo": "assessore", "nome": "Gianluca Poldi"}],
          "checklist": [{"ok": True}, {"ok": False}]}
    bad = {"ente": "Comune di Perugia", "fascia": "XL", "error": "http_403 forbidden", "records": [], "hunts": [], "analisi": []}
    r = riepilogo([ok, bad], [{"ente": "Comune di Segrate", "cognome": "Di Chio", "ruolo": "sindaco"},
                              {"ente": "Comune di Segrate", "cognome": "Rossi", "ruolo": ""}])
    t = r["totale"]
    assert t["siti"] == 2 and t["letti"] == 1 and t["letti_pct"] == 50.0 and t["bloccati"] == 1
    assert t["avvisi"] == 2 and t["scadenza"] == {"cercate": 2, "trovate": 1, "trovate_pct": 50.0}
    assert t["referenti"]["con_sindaco_pct"] == 100.0 and t["referenti"]["con_tecnico_pct"] == 0.0
    assert t["analisi"]["campi_trovati_pct"] == {"cig": 100.0, "durata": 50.0}
    assert set(r["per_fascia"]) == {"L", "XL"} and r["per_fascia"]["XL"]["bloccati"] == 1
    assert r["riferimento_referenti"] == {"attesi": 2, "trovati": 1, "recall_pct": 50.0,
                                          "per_ente": [{"ente": "Comune di Segrate", "attesi": 2, "trovati": 1}]}


def test_campione_is_spread_over_size_classes_and_provinces():
    from infra.scripts.campione import fascia_di, load_population, stratified

    assert [fascia_di(x) for x in (500, 3000, 8000, 30000, 200000, None)] == ["XS", "S", "M", "L", "XL", "n/d"]
    items = [{"nome": f"c{i}", "provincia": "MI" if i % 2 else "BG", "fascia": "XS" if i < 80 else "XL", "url": "u"} for i in range(100)]
    s = stratified(items, 10)
    assert 8 <= len(s) <= 12 and {x["fascia"] for x in s} == {"XS", "XL"}  # the 20 large ones are not drowned out
    assert {x["provincia"] for x in s} == {"MI", "BG"}
    assert stratified(items, 10) == stratified(items, 10)  # repeatable
    import os
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Comune;Popolazione residente\nArluno;11.800\nComune di Segrate;36.000\n")
    try:
        assert load_population(f.name) == {"arluno": 11800, "segrate": 36000}
    finally:
        os.unlink(f.name)


def test_campione_unknown_sizes_do_not_drown_the_known_ones(tmp_path):
    from infra.scripts.campione import load_fasce, stratified

    items = [{"nome": f"u{i}", "provincia": "MI", "fascia": "n/d", "url": "u"} for i in range(1400)]
    items += [{"nome": f"k{i}", "provincia": "BG", "fascia": "L" if i < 10 else "S", "url": "u"} for i in range(70)]
    s = stratified(items, 60)
    known = [x for x in s if x["fascia"] != "n/d"]
    assert len(known) >= 20 and {x["fascia"] for x in known} == {"L", "S"}  # about half of the sample has a size

    p = tmp_path / "f.csv"
    p.write_text('"id",comune,provincia,fascia_pop_stimata\n1,Romano di Lombardia,BG,L\n2,Arluno,MI,M\n3,X,MI,??\n', encoding="utf-8")
    assert load_fasce(str(p)) == {"romano di lombardia": "L", "arluno": "M"}


def test_unreachable_hosts_are_reported():
    from infra.scripts.prova_siti import limitations

    out = limitations([{"ente": "A", "pages": 3, "checklist": [{"passo": "x", "ok": True}]}],
                      {("www.halleyweb.com", "reset"): 5, ("albo.apkappa.it", "timeout"): 2})
    assert any("halleyweb.com (5)" in x and "apkappa.it (2)" in x for x in out)


def test_limitations_explains_429_as_a_wait_not_a_broken_site():
    from infra.scripts.prova_siti import limitations

    out = limitations([{"ente": "Comune di Pioltello", "error": "http_429"}, {"ente": "Comune di X", "error": "connect"}])
    text = " ".join(out)
    assert "limita le richieste" in text and "Pioltello" in text
    assert "Comune di X" in text and "errore di rete" in text
