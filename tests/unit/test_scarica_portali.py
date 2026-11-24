"""The script that runs on the user's PC, against a fake ASP.NET portal (hidden state, "next" postback, detail button)."""
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from infra.scripts import scarica_portali as sp

NAV = '<nav><a href="/P/Albo.aspx">Albo Pretorio</a><a href="/P/Bandi.aspx">Bandi di gara e contratti</a><a href="/P/Personale.aspx">Personale</a></nav>'
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


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): ...

    def _send(self, body: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        page = {"/P/Albo.aspx": albo(1), "/P/Bandi.aspx": bandi(1), "/P/Personale.aspx": "<html>PERSONALE" + PAD + "</html>"}.get(urllib.parse.urlsplit(self.path).path)
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
    assert any(d.get("ord") == "b" for d in SEEN_POSTS)  # the selected option of a select is sent back
    # the page 3 holds the act about lighting, reachable only by following the pager
    assert any("PUBBLICA ILLUMINAZIONE" in p["html"] and "_mpag=3" in p["url"] for p in pagine)


def test_files_are_written_in_groups_that_the_app_accepts(tmp_path):
    pagine = [{"url": f"https://x.it/{i}", "html": "<p>" + "a" * 300 + "</p>"} for i in range(7)]
    files = sp.scrivi(pagine, "https://x.it", tmp_path, per_file=3)
    assert [f.name for f in files] == ["monitor_pagine_01di03.json", "monitor_pagine_02di03.json", "monitor_pagine_03di03.json"]
    from shared_models.import_pagine import valida_pagine

    assert sum(len(valida_pagine(json.loads(f.read_text()))) for f in files) == 7
