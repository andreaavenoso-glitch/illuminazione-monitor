from app.services.pc_collect import motivo_pc, pulisci_rapporto


def test_blocking_portals_and_block_like_failures_are_listed_for_the_pc():
    assert motivo_pc(["https://dgegovpa.it/Arluno/Albo/Albo"], None, 0) == "portale che rifiuta il server"
    assert motivo_pc(["https://www.halleyweb.com/c015010/zf/index.php"], None, 0) == "portale che rifiuta il server"
    assert "reset" in motivo_pc(["https://comune.x.it/albo"], "reset", 3)
    assert motivo_pc(["https://comune.x.it/albo"], "http_404", 3) is None      # a missing page is not a block
    assert motivo_pc(["https://comune.x.it/albo"], "reset", 0) is None         # healthy now
    assert motivo_pc(["https://comune.x.it/albo"], None, 0) is None


def test_the_report_is_cleaned_and_bounded():
    r = pulisci_rapporto({"stato": "boh", "pagine": "93", "sezioni": 12, "errori": ["x" * 500] * 30,
                          "ricerche": [{"parola": "illuminazione", "trovati": 1}, "spazzatura"], "note": "n" * 900, "extra": "no"})
    assert r["stato"] == "errore" and r["pagine"] == 93 and r["sezioni"] == 12
    assert len(r["errori"]) == 10 and len(r["errori"][0]) == 200 and len(r["note"]) == 300
    assert r["ricerche"] == [{"parola": "illuminazione", "trovati": True}] and "extra" not in r
    assert pulisci_rapporto({"stato": "ok"})["stato"] == "ok"
