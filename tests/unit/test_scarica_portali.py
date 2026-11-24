"""The script that runs on the user's PC, against a fake ASP.NET portal (hidden state, "next" postback, detail button)."""
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from infra.scripts import scarica_portali as sp

NAV = '<nav><a href="/P/Albo.aspx">Albo Pretorio</a><a href="/P/Bandi.aspx">Bandi di gara e contratti</a><a href="/P/Atti.aspx">Atti Amministrativi</a><a href="/P/Personale.aspx">Personale</a></nav>'
FORM = '<form method="post" action="./{page}" id="aspnetForm"><input type="hidden" name="__VIEWSTATE" value="{vs}" /><input type="hidden" name="__EVENTTARGET" value="" /><input type="hidden" name="pagina" value="{n}" /><select name="ord"><option value="a">A</option><option value="b" selected>B</option></select>'
PAD = "<p>" + "testo " * 60 + "</p>"
SEEN_POSTS: list[dict] = []


def albo(n: int) -> str:
    items = "".join(
        f'<div class="row"><div><span class="h5"><div id="ctl00_RepAffissioniAlbo_RptAlbo_ctl{i:02d}_divFirst">N. {n}{i}</div></span></div>'
        f'<div class="col-lg-10"><span class="h5">ATTO {n}-{i} {"GESTIONE PUBBLICA ILLUMINAZIONE" if (n, i) == (3, 1) else "VARIO"}</span>'
        f'<a href="/dati/{n}{i}.PDF">{n}{i}.PDF</a></div></div>' for i in range(2))
    nxt = '<a id="ctl00_RepAffissioniAlbo_LnkNextTop" href="javascript:__doPostBack(\'ctl00$RepAffissioniAlbo$LnkNextTop\',\'\')">»</a>' if n < 3 else ""
    return f"<html><body>{NAV}{FORM.format(page='Albo.aspx', vs='X' * 50, n=n)}<span>Pag. {n} su 3</span>{nxt}{items}{PAD}</form></body></html>"


def bandi(n: int) -> str:
    righe = ""
    for i in range(2):
        og = "SERVIZIO DI PUBBLICA ILLUMINAZIONE E PPP" if (n, i) == (2, 0) else f"FORNITURA {n}{i}"
        righe += (f'<tr id="ctl00_RepBandi_ctl{i:02d}_TrBando"><td><span>1{i}/11/2026</span></td><td><strong>CIG{n}{i}</strong></td><td> {og} </td>'
                  f'<td><input type="submit" name="ctl00$RepBandi$ctl{i:02d}$BtnDett" value="Dettaglio" /></td></tr>')
    nxt = '<a id="ctl00_LnkNextTop" href="javascript:__doPostBack(\'ctl00$LnkNextTop\',\'\')">»</a>' if n < 2 else ""
    return f'<html><body>{NAV}{FORM.format(page="Bandi.aspx", vs="Y" * 50, n=n)}<span>Pag. {n} su 2</span>{nxt}<table id="tblbandi">{righe}</table>{PAD}</form></body></html>'


def _search(q: str = "") -> str:
    """The search box of the portal keeps the text that was searched (as every ASP.NET page does)."""
    return f'<input type="text" name="ctl00$TxtOggetto" value="{q}" /><input type="submit" name="ctl00$btnFiltra" value="Cerca" />'


def atti(n: int, q: str) -> str:
    """Search page: empty when opened, the acts that match once «Cerca» is pressed (2 pages for «illuminazione», none otherwise)."""
    if not q:
        return f"<html><body>{NAV}{FORM.format(page='Atti.aspx', vs='Z' * 50, n=1)}{_search()}{PAD}</form></body></html>"
    if q != "illuminazione":
        return f"<html><body>{NAV}{FORM.format(page='Atti.aspx', vs='Z' * 50, n=1)}{_search(q)}<p>Trovati 0 Atti</p>{PAD}</form></body></html>"
    title = "DELIBERA DI GIUNTA: INCARICO DI SUPPORTO AL RUP E AVVIO MANIFESTAZIONE DI INTERESSE PER LA PUBBLICA ILLUMINAZIONE" if n == 2 else "ALTRO ATTO"
    item = (f'<div class="row"><div><span class="h5"><div id="ctl00_RepAffissioniAlbo_RptAlbo_ctl00_divFirst">N. {n}</div></span></div>'
            f'<div class="col-lg-10"><span class="h5">{title}</span><a href="/dati/atto{n}.PDF">atto{n}.PDF</a></div></div>')
    nxt = '<a id="ctl00_RepAffissioniAlbo_LnkNextTop" href="javascript:__doPostBack(\'ctl00$RepAffissioniAlbo$LnkNextTop\',\'\')">»</a>' if n < 2 else ""
    return (f"<html><body>{NAV}{FORM.format(page='Atti.aspx', vs='Z' * 50, n=n)}{_search(q)}<span>Trovati 4 Atti</span><span>Pag. {n} su 2</span>{nxt}{item}{PAD}</form></body></html>")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): ...

    def _send(self, body: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        page = {"/P/Albo.aspx": albo(1), "/P/Bandi.aspx": bandi(1), "/P/Atti.aspx": atti(1, ""), "/P/Personale.aspx": "<html>PERSONALE" + PAD + "</html>"}.get(urllib.parse.urlsplit(self.path).path)
        self._send(page or "no", 200 if page else 404)

    def do_POST(self):
        d = dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers["Content-Length"])).decode(), keep_blank_values=True))
        SEEN_POSTS.append(d)
        assert d.get("__VIEWSTATE"), "the hidden state must be sent back"
        n = int(d.get("pagina", 1))
        if any(k.endswith("BtnDett") for k in d):
            return self._send("<html><body><h1>Dettaglio procedura</h1>Importo 100.000 euro scadenza 15/01/2027 ore 12:00" + PAD + "</body></html>")
        if d.get("__EVENTTARGET", "").endswith("LnkNextTop"):
            n += 1
        if self.path.endswith("Atti.aspx"):
            return self._send(atti(n, d.get("ctl00$TxtOggetto", "")))
        self._send(albo(n) if self.path.endswith("Albo.aspx") else bandi(n))


def test_follows_every_page_of_each_list_and_opens_the_details_of_lighting_procedures(tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_port}"
        pagine = sp.scarica(f"{base}/P/Albo.aspx", massimo=100, pausa=0, dettagli=True, max_liste=10, max_pagine_lista=60)
    finally:
        srv.shutdown()
    urls = [p["url"].replace(base, "") for p in pagine]
    assert [u for u in urls if u.startswith("/P/Albo")] == ["/P/Albo.aspx", "/P/Albo.aspx?_mpag=2", "/P/Albo.aspx?_mpag=3"]
    assert [u for u in urls if u.startswith("/P/Bandi") and "cig" not in u] == ["/P/Bandi.aspx", "/P/Bandi.aspx?_mpag=2"]
    assert any(u.endswith("Bandi.aspx?cig=CIG20") for u in urls)  # the lighting procedure's detail
    assert not any("cig=CIG21" in u or "cig=CIG10" in u for u in urls)  # the other rows' details are not opened
    assert not any("Personale" in u for u in urls)
    assert all(len(p["html"]) < 5000 and "XXXXX" not in p["html"] for p in pagine)  # state stripped
    # the search page «Atti Amministrativi» opens empty: the script searches by keyword and follows the results
    assert not any(u == "/P/Atti.aspx" and "PUBBLICA" in p["html"] for u, p in zip(urls, pagine, strict=False))
    ricerche = [p for u, p in zip(urls, pagine, strict=False) if "_q=illuminazione" in u]
    assert len(ricerche) == 2 and any("INCARICO DI SUPPORTO AL RUP" in p["html"] for p in ricerche)
    assert not any("_q=partenariato" in u or "_q=supporto" in u for u in urls)  # keywords with no result are not saved
    assert any(d.get("ord") == "b" for d in SEEN_POSTS)  # the selected option of a select is sent back
    # the page 3 holds the act about lighting, reachable only by following the pager
    assert any("PUBBLICA ILLUMINAZIONE" in p["html"] and "_mpag=3" in p["url"] for p in pagine)


def test_files_are_written_in_groups_that_the_app_accepts(tmp_path):
    pagine = [{"url": f"https://x.it/{i}", "html": "<p>" + "a" * 300 + "</p>"} for i in range(7)]
    files = sp.scrivi(pagine, "https://x.it", tmp_path, per_file=3)
    assert [f.name for f in files] == ["monitor_pagine_01di03.json", "monitor_pagine_02di03.json", "monitor_pagine_03di03.json"]
    from shared_models.import_pagine import valida_pagine

    assert sum(len(valida_pagine(json.loads(f.read_text()))) for f in files) == 7


def test_the_api_address_comes_from_the_address_of_the_app():
    assert sp.indirizzo_api("https://abc-3000.app.github.dev/regions/Lombardia".split("/regions")[0]) == "https://abc-8000.app.github.dev"
    assert sp.indirizzo_api("http://localhost:3000/") == "http://localhost:8000"
    assert sp.indirizzo_api("https://abc-8000.app.github.dev") == "https://abc-8000.app.github.dev"


class _FakeApp(BaseHTTPRequestHandler):
    visti: list[dict] = []
    comuni: list[dict] = []
    rapporti: list[dict] = []

    def log_message(self, *a): ...

    def _json(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/auth/login":
            d = json.loads(body)
            return self._json(200, {"access_token": "T0K"}) if d["password"] == "giusta123" else self._json(401, {"detail": "Invalid credentials"})
        if self.path == "/regions/Lombardia/rapporto-pc":
            self.rapporti.extend(json.loads(body)["comuni"])
            return self._json(200, {"salvati": 1})
        if self.path == "/regions/Lombardia/import-pagine":
            self.visti.append({"auth": self.headers.get("Authorization"), "gh": self.headers.get("X-Github-Token"), "body": body})
            return self._json(200, {"status": "dispatched", "pagine": 2, "task_id": "x"})
        self._json(404, {})

    def do_GET(self):
        if self.path.startswith("/regions/Lombardia/comuni-da-pc"):
            return self._json(200, {"comuni": self.comuni})
        self._json(200, {"status": "done", "items": [{"records_found": 3}]}) if self.path == "/regions/Lombardia/scan" else self._json(404, {})


def test_pages_are_sent_straight_to_the_app_with_login(tmp_path, monkeypatch, capsys):
    import time as _t

    monkeypatch.setattr(_t, "sleep", lambda s: None)
    f = tmp_path / "monitor_pagine_01di01.json"
    f.write_text(json.dumps({"pagine": [{"url": "https://x.it/a", "html": "<p>" + "a" * 300 + "</p>"}]}))
    srv = HTTPServer(("127.0.0.1", 0), _FakeApp)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        app = sp.App(f"http://127.0.0.1:{srv.server_port}", github_token="ghp_x")
        app.login("a@b.it", "giusta123")
        n = sp.invia_all_app([f], app, "Lombardia", "Arluno")
    finally:
        srv.shutdown()
    assert n == 2
    v = _FakeApp.visti[-1]
    assert v["auth"] == "Bearer T0K" and v["gh"] == "ghp_x"
    assert b'name="comune"\r\n\r\nArluno' in v["body"] and b'filename="monitor_pagine_01di01.json"' in v["body"] and b"https://x.it/a" in v["body"]
    assert "3 record trovati" in capsys.readouterr().out


def test_wrong_password_stops_before_downloading_anything():
    import pytest

    srv = HTTPServer(("127.0.0.1", 0), _FakeApp)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(SystemExit) as e:
            sp.App(f"http://127.0.0.1:{srv.server_port}").login("a@b.it", "sbagliata1")
    finally:
        srv.shutdown()
    assert "password" in str(e.value)


def test_a_short_or_empty_password_is_explained_before_calling_the_app():
    import pytest

    with pytest.raises(SystemExit) as e:
        sp.App("http://127.0.0.1:1").login("admin@example.com", "")
    assert "almeno 8" in str(e.value) and "0 caratteri" in str(e.value)
    with pytest.raises(SystemExit) as e:
        sp.App("http://127.0.0.1:1").login("non-una-email", "password-lunga")
    assert "email" in str(e.value).lower()


def test_serial_mode_reads_every_blocked_comune_sends_pages_and_reports_each_one(tmp_path, monkeypatch):
    import time as _t

    monkeypatch.setattr(_t, "sleep", lambda s: None)
    portal = HTTPServer(("127.0.0.1", 0), H)
    fake = HTTPServer(("127.0.0.1", 0), _FakeApp)
    for srv in (portal, fake):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{portal.server_port}"
    _FakeApp.visti.clear()
    _FakeApp.rapporti.clear()
    _FakeApp.comuni = [
        {"id": "id-ok", "ente": "Comune Uno", "siti": [f"{base}/P/Albo.aspx"], "motivo": "portale che rifiuta il server"},
        {"id": "id-strano", "ente": "Comune Due", "siti": [f"{base}/P/Personale.aspx"], "motivo": "sito non raggiungibile dal server (reset)"},
        {"id": "id-giu", "ente": "Comune Tre", "siti": ["http://127.0.0.1:1/x"], "motivo": "portale che rifiuta il server"},
    ]
    try:
        app = sp.App(f"http://127.0.0.1:{fake.server_port}")
        app.login("a@b.it", "giusta123")
        kw = dict(tutti=False, riparti=False, limite=None, massimo=100, pausa=0, dettagli=True, max_sezioni=10, max_pagine_lista=60,
                  per_file=60, parole=None)
        esiti = sp.lavora_elenco(app, "Lombardia", tmp_path, **kw)
        # a second run with --riparti skips what is done
        assert sp.lavora_elenco(app, "Lombardia", tmp_path, **{**kw, "riparti": True}) == {"ok": 0, "non_riconosciuto": 0, "errore": 0}
    finally:
        portal.shutdown()
        fake.shutdown()
    assert esiti == {"ok": 1, "non_riconosciuto": 1, "errore": 1}
    per_id = {r["id"]: r for r in _FakeApp.rapporti}
    assert per_id["id-ok"]["stato"] == "ok" and per_id["id-ok"]["pagine"] >= 8
    assert per_id["id-strano"]["stato"] == "non_riconosciuto" and "lettore dedicato" in per_id["id-strano"]["note"]
    assert per_id["id-giu"]["stato"] == "errore" and per_id["id-giu"]["errori"]
    # the pages were sent knowing the exact comune (no name to guess)
    assert any(b'name="item_id"\r\n\r\nid-ok' in v["body"] for v in _FakeApp.visti)
    assert not any(b"id-giu" in v["body"] for v in _FakeApp.visti)  # nothing to send for an unreachable comune


def test_http_address_is_retried_as_https_like_a_browser_does(monkeypatch):
    b = sp.Browser(0)
    visti = []

    def finto(req):
        visti.append(req.full_url)
        if req.full_url.startswith("http://"):
            b.errori.append("timeout")
            return None
        return ("<html>ok</html>", req.full_url)

    monkeypatch.setattr(b, "_vai", finto)
    assert b.get("http://halleyweb.com/c1/x") == ("<html>ok</html>", "https://halleyweb.com/c1/x")
    assert visti == ["http://halleyweb.com/c1/x", "https://halleyweb.com/c1/x"]
    assert b.errori == []  # the first attempt is not an error when https answers


def test_a_site_that_does_not_answer_is_tried_once_per_comune_not_once_per_address(tmp_path, monkeypatch):
    import time as _t

    monkeypatch.setattr(_t, "sleep", lambda s: None)
    fake = HTTPServer(("127.0.0.1", 0), _FakeApp)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    _FakeApp.rapporti.clear()
    _FakeApp.comuni = [{"id": "id-giu", "ente": "Comune Giù", "siti": ["http://127.0.0.1:1/a", "http://127.0.0.1:1/b", "http://127.0.0.1:1/c"], "motivo": "x"}]
    try:
        app = sp.App(f"http://127.0.0.1:{fake.server_port}")
        app.login("a@b.it", "giusta123")
        sp.lavora_elenco(app, "Lombardia", tmp_path, tutti=False, riparti=False, limite=None, massimo=50, pausa=0, dettagli=True,
                         max_sezioni=5, max_pagine_lista=5, per_file=60, parole=None)
    finally:
        fake.shutdown()
    r = _FakeApp.rapporti[-1]
    assert r["stato"] == "errore" and len(r["errori"]) == 1  # not three timeouts: the host is known to be down after the first
