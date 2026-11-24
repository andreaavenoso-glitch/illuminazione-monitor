#!/usr/bin/env python3
"""Scarica da un portale di albo / trasparenza le pagine con gli atti, per caricarle nell'app (Raccolta -> «Leggilo con il tuo browser»).

DA ESEGUIRE SUL TUO PC (non nel Codespace): i portali come dgegovpa.it e halleyweb.com rifiutano le connessioni dei server,
mentre dal tuo computer rispondono. Serve solo Python 3.9+ (nessun pacchetto da installare).

    python scarica_portali.py https://dgegovpa.it/Arluno/Albo/Albo

Cosa fa, da solo:
  1. legge la pagina e il suo menu, e individua le sezioni utili (Albo, Trasparenza, Atti, Bandi, Gare...);
  2. di ogni elenco legge TUTTE le pagine («successiva», «Pag. 1 su 34»), come farebbe una persona che le sfoglia;
  3. per i bandi che parlano di illuminazione / PPP apre anche il «Dettaglio»;
  4. scrive i file monitor_pagine_01diNN.json nella cartella indicata (--out, di default «monitor_pagine»).
Poi li carica nell'app, oppure li lasci tu nel riquadro «Portale che blocca il server» della scheda Raccolta.

TUTTI I COMUNI CHE IL SERVER NON LEGGE (anche di più regioni, una alla volta), con rapporto per ciascuno:

    python scarica_portali.py --bloccati --regione Lombardia --app https://NOME-3000.app.github.dev
    python scarica_portali.py --bloccati --regione Lombardia --app ... --riparti      # dopo un'interruzione
    python scarica_portali.py --bloccati --regione Lombardia --app ... --limite 5     # solo una prova

Legge dall'app l'elenco dei comuni da leggere dal PC, li scorre uno per uno, invia le pagine e segna nell'app l'esito di
ognuno (letto / portale non riconosciuto / non raggiungibile): lo vedi nella scheda Siti della regione.

COLLEGAMENTO DIRETTO ALL'APP (niente file da caricare a mano): indica dove sta l'app e il comune, e lo script fa il login come
faresti tu dalla pagina e invia le pagine all'analisi:

    python scarica_portali.py https://dgegovpa.it/Arluno/Albo/Albo --app https://NOME-3000.app.github.dev --comune Arluno

--app è l'indirizzo con cui apri l'app nel browser (va bene anche quello della porta 3000: lo script usa la porta 8000 dell'API).
Chiede email e password dell'app (o: variabili MONITOR_EMAIL e MONITOR_PASSWORD). Se la porta 8000 del Codespace è privata
serve anche --github-token (un token personale GitHub), oppure rendi pubblica la porta 8000 (l'API ha comunque il suo login).

Gentile col portale: una richiesta alla volta, con una pausa (--pausa, di default 0,5 s) e un limite di pagine (--max).
"""
from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

UA = "Mozilla/5.0 (compatible; MonitorIlluminazione/1.0; lettura di atti pubblici)"
SEZ = re.compile(r"albo|trasparen|atti|bandi|gar[ae]|delibere|determin|avvis|contratti|concession|appalti|manifestazion", re.I)
KW = re.compile(r"illumin|luce|energia|ppp|partenariato|finanza.?di.?progetto|project.?financing|concession|manifestazion|avviso|delibera|determina|bando|gara|proposta|esito|affidament|procedura|contratt", re.I)
LUCE = re.compile(r"illumin|pubblica illuminazione|finanza.?di.?progetto|project.?financing|\bppp\b|partenariato|punti luce|impianti? (di )?(illuminazione|semaforic)|servizio luce|energia elettrica|concession|manifestazion", re.I)
NO = re.compile(r"\.(pdf|jpe?g|png|gif|zip|docx?|xlsx?|p7m|csv|xml)(\?|$)|login|logout|mailto:|tel:|javascript:", re.I)
PAGINA = re.compile(r"Pag\.\s*(\d+)\s*su\s*(\d+)", re.I)
POSTBACK = re.compile(r"__doPostBack\(\s*'([^']+)'")
MAX_FILE = 6_000_000  # byte per file: il server ne accetta 12 MB e 80 pagine


class PortaleNonRaggiungibile(Exception):
    """La pagina di partenza del portale non si apre (rete, blocco, indirizzo errato)."""


# Segni che la pagina è un elenco del portale che lo script sa leggere (ASP.NET: «Pag. 1 su 4», «Trovati 52…», tabelle e voci d'albo)
RICONOSCIUTO = re.compile(r"Pag\.\s*\d+\s*su\s*\d+|Trovat[ie]\s+\d+|id=\"tblbandi\"|RptAlbo|RepBandi", re.I)


# --- lettura dell'HTML con la sola libreria standard ---------------------------------------------------------------
class Pagina(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict] = []
        self.campi: list[tuple[str, str, str, bool]] = []  # name, value, type, checked
        self.action: str | None = None
        self._a: dict | None = None
        self._sel: dict | None = None
        self._in_form = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and self.action is None:
            self.action, self._in_form = a.get("action") or "", True
        elif tag == "a" and a.get("href"):
            self._a = {"href": a["href"], "id": a.get("id") or "", "text": ""}
        elif tag == "input" and a.get("name"):
            self.campi.append((a["name"], a.get("value") or "", (a.get("type") or "text").lower(), "checked" in a))
        elif tag == "select" and a.get("name"):
            self._sel = {"name": a["name"], "first": None, "chosen": None}
        elif tag == "option" and self._sel is not None:
            v = a.get("value", "")
            if self._sel["first"] is None:
                self._sel["first"] = v
            if "selected" in a:
                self._sel["chosen"] = v
        elif tag == "textarea" and a.get("name"):
            self.campi.append((a["name"], "", "textarea", False))

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self._a["text"] = " ".join(self._a["text"].split())
            self.links.append(self._a)
            self._a = None
        elif tag == "select" and self._sel is not None:
            v = self._sel["chosen"] if self._sel["chosen"] is not None else (self._sel["first"] or "")
            self.campi.append((self._sel["name"], v, "select", False))
            self._sel = None

    def handle_data(self, data):
        if self._a is not None:
            self._a["text"] += data


def leggi_html(html: str) -> Pagina:
    p = Pagina()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 -- HTML rotto: si usa quel che si è letto
        pass
    return p


# --- rete -----------------------------------------------------------------------------------------------------------
class Browser:
    def __init__(self, pausa: float, timeout: float = 30.0) -> None:
        self.pausa = pausa
        self.timeout = timeout
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.op.addheaders = [("User-Agent", UA), ("Accept-Language", "it-IT,it;q=0.9")]
        self.richieste = 0
        self.errori: list[str] = []

    def _vai(self, req: urllib.request.Request) -> tuple[str, str] | None:
        time.sleep(self.pausa)
        self.richieste += 1
        try:
            with self.op.open(req, timeout=self.timeout) as r:
                raw = r.read()
                enc = r.headers.get_content_charset() or "utf-8"
                return raw.decode(enc, errors="replace"), r.geturl()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"   ! non riuscito: {req.full_url[:90]} ({exc})", file=sys.stderr)
            self.errori.append(f"{req.full_url[:120]}: {exc}")
            return None

    def get(self, url: str) -> tuple[str, str] | None:
        r = self._vai(urllib.request.Request(url))
        if r is None and url.startswith("http://"):  # i browser aprono «http://» come «https://»: lo si prova anche qui
            r = self._vai(urllib.request.Request("https://" + url[len("http://"):]))
            if r is not None and self.errori:
                self.errori.pop()  # il primo tentativo (http) non è un errore se https risponde
        return r

    def post(self, url: str, dati: list[tuple[str, str]]) -> tuple[str, str] | None:
        body = urllib.parse.urlencode(dati).encode()
        return self._vai(urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}))


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def assoluto(base: str, href: str) -> str | None:
    try:
        u = urllib.parse.urljoin(base, href.strip())
        return urllib.parse.urldefrag(u)[0] if urllib.parse.urlsplit(u).scheme in ("http", "https") else None
    except ValueError:
        return None


def percorso(u: str) -> str:
    p = urllib.parse.urlsplit(u)
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}".lower()


def con_pagina(url: str, n: int) -> str:
    """Indirizzo con il numero di pagina dell'elenco (serve all'app per distinguere le pagine; il portale lo ignora)."""
    return url if n <= 1 else f"{url}{'&' if '?' in url else '?'}_mpag={n}"


def con_cig(url: str, cig: str) -> str:
    base = re.sub(r"[?&]_mpag=\d+", "", url)
    return f"{base}{'&' if '?' in base else '?'}cig={cig}"


def alleggerisci(html: str) -> str:
    """Toglie ciò che non serve all'analisi (script, stili, immagini vettoriali, stato interno ASP.NET): una pagina passa da
    ~300 KB a poche decine."""
    html = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<svg\b.*?</svg>|<!--.*?-->", "", html, flags=re.S | re.I)
    return re.sub(r'(name="__(?:VIEWSTATE|EVENTVALIDATION|VIEWSTATEGENERATOR|PREVIOUSPAGE)"[^>]*?value=")[^"]*', r"\1", html, flags=re.I)


# --- ASP.NET WebForms -------------------------------------------------------------------------------------------------
def campi_del_form(p: Pagina) -> list[tuple[str, str]]:
    out = []
    for name, value, tipo, checked in p.campi:
        if tipo in ("submit", "button", "image", "file", "reset"):
            continue
        if tipo in ("checkbox", "radio") and not checked:
            continue
        out.append((name, value))
    return out


def invia_form(b: Browser, pagina_url: str, html: str, target: str | None = None, bottone: tuple[str, str] | None = None,
               modifiche: dict[str, str] | None = None) -> tuple[str, str] | None:
    """Ripete ciò che fa il browser quando si preme un pulsante della pagina: stessa form, stesso stato."""
    p = leggi_html(html)
    dati = dict(campi_del_form(p))
    dati.update(modifiche or {})
    dati["__EVENTTARGET"] = target or ""
    dati["__EVENTARGUMENT"] = ""
    pairs = list(dati.items()) + ([bottone] if bottone else [])
    return b.post(assoluto(pagina_url, p.action or pagina_url) or pagina_url, pairs)


def campo_ricerca(p: Pagina) -> tuple[str, str] | None:
    """(campo «Oggetto», pulsante «Cerca») di una pagina di ricerca del portale, se c'è."""
    oggetto = next((n for n, _, t, _ in p.campi if n.endswith("TxtOggetto") and t == "text"), None)
    cerca = next((n for n, v, t, _ in p.campi if n.endswith("btnFiltra") and t == "submit"), None)
    return (oggetto, cerca) if oggetto and cerca else None


def senza_risultati(html: str) -> bool:
    """La pagina di ricerca appena aperta non mostra ancora nessun elenco («Trovati N …» assente) o ne mostra zero."""
    m = re.search(r"Trovat[ie]\s+(\d+)", html)
    return m is None or int(m.group(1)) == 0


PAROLE = ["illuminazione", "manifestazione di interesse", "finanza di progetto", "partenariato pubblico privato", "supporto al RUP"]


def con_ricerca(url: str, parola: str) -> str:
    base = re.sub(r"[?&]_q=[^&]*", "", url)
    return f"{base}{'&' if '?' in base else '?'}_q={urllib.parse.quote(parola)}"


def pulsante_successiva(p: Pagina) -> str | None:
    for a in p.links:
        if a["id"].endswith("LnkNextTop") or a["id"].endswith("LnkNext"):
            m = POSTBACK.search(a["href"])
            if m:
                return m.group(1)
    return None


def righe_bandi(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r"<tr[^>]*RepBandi_ctl(\d+)_TrBando.*?</tr>", html, re.S | re.I):
        riga = m.group(0)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", riga, re.S | re.I)
        if len(tds) < 3:
            continue
        testo = lambda s: " ".join(re.sub(r"<[^>]+>", " ", s).split())  # noqa: E731
        bt = re.search(r'name="([^"]*BtnDett)"', riga)
        out.append({"cig": testo(tds[1]), "oggetto": testo(tds[2]), "bottone": bt.group(1) if bt else None})
    return out


# --- il lavoro --------------------------------------------------------------------------------------------------------
def scarica(inizio: str, massimo: int, pausa: float, dettagli: bool, max_liste: int, max_pagine_lista: int,
            parole: list[str] | None = None) -> list[dict]:
    return scarica_con_rapporto(inizio, massimo, pausa, dettagli, max_liste, max_pagine_lista, parole)[0]


def scarica_con_rapporto(inizio: str, massimo: int, pausa: float, dettagli: bool, max_liste: int, max_pagine_lista: int,
                         parole: list[str] | None = None, silenzioso: bool = False) -> tuple[list[dict], dict]:
    """Le pagine del portale e il RAPPORTO della lettura (stato ok / non_riconosciuto, sezioni, ricerche, errori, note)."""
    b = Browser(pausa)
    ricerche: list[dict] = []
    segni = [0]  # pagine che sembrano un elenco del portale
    parole = PAROLE if parole is None else parole
    pagine: dict[str, str] = {}

    def dire(*a: object) -> None:
        if not silenzioso:
            print(*a)

    def aggiungi(url: str, html: str) -> bool:
        if url in pagine:
            return False
        if RICONOSCIUTO.search(html):
            segni[0] += 1
        pagine[url] = alleggerisci(html)
        if len(pagine) % 10 == 0:
            dire(f"   {len(pagine)} pagine…")
        return True

    primo = b.get(inizio)
    if not primo:
        raise PortaleNonRaggiungibile(b.errori[-1] if b.errori else "la pagina di partenza non si apre")
    html0, url0 = primo
    origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(url0))
    p0 = leggi_html(html0)
    stesso_sito = lambda u: u and u.startswith(origin) and not NO.search(u)  # noqa: E731

    liste = [url0]
    for a in p0.links:
        u = assoluto(url0, a["href"])
        if stesso_sito(u) and SEZ.search(u) and percorso(u) != percorso(url0) and u not in liste:
            liste.append(u)
    liste = liste[: max_liste]
    dire(f"Sezioni da leggere: {len(liste)}")
    for u in liste:
        dire("  -", u)

    dettagli_url: list[str] = []

    def percorri(nome: str, url: str, html: str) -> None:
        """Registra la pagina e tutte le successive dell'elenco (pulsante «successiva»), aprendo i dettagli utili.
        `nome` è l'indirizzo con cui la pagina viene salvata, `url` quello a cui il portale va scritto."""
        n = 1
        aggiungi(con_pagina(nome, n), html)
        while True:
            p = leggi_html(html)
            # i bandi sull'illuminazione: si apre il «Dettaglio» dalla pagina in cui compaiono
            if dettagli:
                for riga in righe_bandi(html):
                    if riga["bottone"] and LUCE.search(riga["oggetto"]):
                        d = invia_form(b, url, html, bottone=(riga["bottone"], "Dettaglio"))
                        if d:
                            aggiungi(con_cig(nome, riga["cig"]), d[0])
            for a in p.links:  # siti senza pulsanti ASP.NET: i collegamenti ai dettagli
                u = assoluto(url, a["href"])
                if stesso_sito(u) and (KW.search(a["text"]) or KW.search(u)) and not POSTBACK.search(a["href"]) and u not in dettagli_url:
                    dettagli_url.append(u)
            tot = PAGINA.search(html)
            target = pulsante_successiva(p)
            if not target or not tot or n >= int(tot.group(2)) or n >= max_pagine_lista or len(pagine) >= massimo:
                break
            nxt = invia_form(b, url, html, target=target)
            if not nxt:
                break
            html = nxt[0]
            n += 1
            aggiungi(con_pagina(nome, n), html)

    for lu in liste:
        if len(pagine) >= massimo:
            break
        r = (html0, url0) if lu == url0 else b.get(lu)
        if not r:
            continue
        html, url = r
        percorri(url, url, html)
        # le pagine di ricerca (es. «Atti Amministrativi»: delibere, decreti…) si aprono vuote: si cerca per parole chiave
        ric = campo_ricerca(leggi_html(html))
        if ric and senza_risultati(html):
            dire(f"  ricerca in {url}")
            for parola in parole:
                if len(pagine) >= massimo:
                    break
                res = invia_form(b, url, html, bottone=(ric[1], "Cerca"), modifiche={ric[0]: parola})
                trovati = bool(res and not senza_risultati(res[0]))
                ricerche.append({"parola": parola, "trovati": trovati})
                if res and trovati:
                    dire(f"    «{parola}»: " + (PAGINA.search(res[0]).group(0) if PAGINA.search(res[0]) else "risultati trovati"))
                    percorri(con_ricerca(url, parola), url, res[0])

    for u in dettagli_url:  # collegamenti ai dettagli (non ASP.NET), un livello
        if len(pagine) >= massimo:
            break
        if u not in pagine:
            r = b.get(u)
            if r:
                aggiungi(u, r[0])

    dire(f"Fatto: {len(pagine)} pagine, {b.richieste} richieste.")
    riconosciuto = segni[0] > 0 or any(r["trovati"] for r in ricerche)
    if riconosciuto and len(pagine) > 1:
        stato, note = "ok", f"{len(pagine)} pagine, {len(liste)} sezioni, ricerche con risultati: {sum(r['trovati'] for r in ricerche)}/{len(ricerche)}"
    else:
        stato = "non_riconosciuto"
        note = ("nessun elenco riconoscibile (né «Pag. N su M», né tabelle di bandi, né voci d'albo): portale diverso da quelli noti, "
                "serve un lettore dedicato" if not riconosciuto else "una sola pagina letta")
    rapporto = {"stato": stato, "pagine": len(pagine), "sezioni": len(liste), "ricerche": ricerche, "errori": b.errori[:10], "note": note}
    return [{"url": u, "html": h} for u, h in pagine.items()], rapporto


def scrivi(pagine: list[dict], origine: str, cartella: Path, per_file: int) -> list[Path]:
    cartella.mkdir(parents=True, exist_ok=True)
    gruppi: list[list[dict]] = [[]]
    peso = 0
    for p in pagine:
        w = len(p["html"].encode("utf-8", errors="ignore"))
        if gruppi[-1] and (len(gruppi[-1]) >= per_file or peso + w > MAX_FILE):
            gruppi.append([])
            peso = 0
        gruppi[-1].append(p)
        peso += w
    for old in cartella.glob("monitor_pagine_*.json"):
        old.unlink()
    out = []
    for i, g in enumerate(gruppi, 1):
        f = cartella / f"monitor_pagine_{i:02d}di{len(gruppi):02d}.json"
        f.write_text(json.dumps({"origine": origine, "pagine": g}, ensure_ascii=False), encoding="utf-8")
        out.append(f)
    return out


# --- collegamento con l'app -----------------------------------------------------------------------------------------
def indirizzo_api(app: str) -> str:
    """L'indirizzo dell'API dall'indirizzo con cui si apre l'app (nei Codespaces la pagina è sulla porta 3000, l'API sulla 8000)."""
    app = app.strip().rstrip("/")
    return re.sub(r"-3000\.app\.github\.dev", "-8000.app.github.dev", app).replace("localhost:3000", "localhost:8000")


def multipart(campi: dict[str, str], nome_file: str, contenuto: bytes) -> tuple[bytes, str]:
    conf = "----monitorportali" + str(int(time.time() * 1000))
    parti = [f'--{conf}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in campi.items()]
    parti.append(f'--{conf}\r\nContent-Disposition: form-data; name="file"; filename="{nome_file}"\r\n'
                 f"Content-Type: application/json\r\n\r\n".encode() + contenuto + b"\r\n")
    parti.append(f"--{conf}--\r\n".encode())
    return b"".join(parti), f"multipart/form-data; boundary={conf}"


class App:
    """L'app vista dallo script: login e invio delle pagine, con le stesse regole della pagina web (utente amministratore)."""

    def __init__(self, indirizzo: str, github_token: str | None = None) -> None:
        self.api = indirizzo_api(indirizzo)
        self.extra = {"X-Github-Token": github_token} if github_token else {}
        self.token: str | None = None

    def _chiama(self, metodo: str, percorso: str, corpo: bytes | None = None, tipo: str | None = None) -> tuple[int, dict]:
        h = dict(self.extra)
        if tipo:
            h["Content-Type"] = tipo
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.api + percorso, data=corpo, headers=h, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "{}")
            except ValueError:
                return e.code, {}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            sys.exit(f"Non riesco a raggiungere l'app ({self.api}): {exc}\n"
                     "Controlla che il Codespace sia acceso e che la porta 8000 sia pubblica (oppure usa --github-token).")

    def login(self, email: str, password: str) -> None:
        email, password = email.strip(), password.strip("\r\n")
        if "@" not in email:
            sys.exit(f"L'email «{email}» non sembra un indirizzo valido.")
        if len(password) < 8:
            sys.exit(f"La password che hai scritto ha {len(password)} caratteri, ma l'app ne vuole almeno 8. "
                     "Nel Prompt dei comandi non si vede cosa scrivi: riprova, oppure usa --mostra-password (la vedi mentre scrivi) "
                     'oppure --password "LA-TUA-PASSWORD".')
        code, body = self._chiama("POST", "/auth/login", json.dumps({"email": email, "password": password}).encode(), "application/json")
        if code == 401 and body.get("detail") == "Invalid credentials":
            sys.exit("Email o password dell'app non corrette.")
        if code == 422:
            sys.exit("L'app ha rifiutato i dati di accesso (formato non valido): controlla email e password, senza spazi in più. "
                     f"Dettaglio: {json.dumps(body.get('detail'), ensure_ascii=False)[:300]}")
        if code != 200 or "access_token" not in body:
            sys.exit(f"Accesso all'app non riuscito (codice {code}). Se la porta 8000 del Codespace è privata serve --github-token, "
                     "oppure rendila pubblica dalla scheda «Porte» di VS Code.")
        self.token = body["access_token"]

    def comuni_da_pc(self, regione: str, tutti: bool = False) -> list[dict]:
        code, body = self._chiama("GET", f"/regions/{urllib.parse.quote(regione)}/comuni-da-pc" + ("?tutti=true" if tutti else ""))
        if code != 200:
            sys.exit(f"Non riesco a leggere dall'app l'elenco dei comuni (codice {code}): {body.get('detail') or ''}")
        return list(body.get("comuni") or [])

    def rapporto(self, regione: str, comuni: list[dict]) -> None:
        corpo = json.dumps({"comuni": comuni}, ensure_ascii=False).encode()
        code, _ = self._chiama("POST", f"/regions/{urllib.parse.quote(regione)}/rapporto-pc", corpo, "application/json")
        if code != 200:
            print(f"  ! il rapporto non è stato salvato (codice {code})", file=sys.stderr)

    def invia(self, regione: str, comune: str, file: Path, item_id: str | None = None) -> dict:
        campi = {"comune": comune, **({"item_id": item_id} if item_id else {})}
        corpo, tipo = multipart(campi, file.name, file.read_bytes())
        code, body = self._chiama("POST", f"/regions/{urllib.parse.quote(regione)}/import-pagine", corpo, tipo)
        if code != 200:
            raise RuntimeError(str(body.get("detail") or f"errore {code}"))
        return body

    def esito(self, regione: str) -> dict | None:
        return self._chiama("GET", f"/regions/{urllib.parse.quote(regione)}/scan")[1] or None


def invia_all_app(files: list[Path], app: App, regione: str, comune: str, attesa: int = 180) -> int:
    inviate = 0
    for f in files:
        try:
            r = app.invia(regione, comune, f)
            inviate += int(r.get("pagine", 0))
            print(f"  inviato {f.name}: {r.get('pagine')} pagine")
        except RuntimeError as exc:
            print(f"  ! {f.name}: {exc}", file=sys.stderr)
    if not inviate:
        return 0
    print("Analisi in corso nell'app…")
    fine = time.time() + attesa
    while time.time() < fine:
        time.sleep(5)
        run = app.esito(regione)
        if run and run.get("status") != "running":
            trovati = sum(int(i.get("records_found") or 0) for i in run.get("items", []))
            print(f"Analisi conclusa ({run.get('status')}): {trovati} record trovati. Li vedi nell'app, nelle schede Pre-gare / Manifestazioni / Gare / Da verificare.")
            return inviate
    print("L'analisi continua: guarda l'avanzamento nella scheda Raccolta dell'app.")
    return inviate


def unisci_rapporti(rapporti: list[dict]) -> dict:
    """Un solo rapporto per il comune, dai rapporti dei suoi indirizzi: ok se almeno uno è ok."""
    if not rapporti:
        return {"stato": "errore", "pagine": 0, "sezioni": 0, "ricerche": [], "errori": [], "note": "nessun indirizzo da leggere"}
    stati = {r["stato"] for r in rapporti}
    stato = "ok" if "ok" in stati else ("non_riconosciuto" if "non_riconosciuto" in stati else "errore")
    return {"stato": stato, "pagine": sum(r.get("pagine", 0) for r in rapporti), "sezioni": sum(r.get("sezioni", 0) for r in rapporti),
            "ricerche": [x for r in rapporti for x in r.get("ricerche", [])], "errori": [e for r in rapporti for e in r.get("errori", [])][:10],
            "note": " | ".join(r["note"] for r in rapporti if r.get("note"))[:300]}


def lavora_elenco(app: App, regione: str, cartella: Path, *, tutti: bool, riparti: bool, limite: int | None, massimo: int, pausa: float,
                  dettagli: bool, max_sezioni: int, max_pagine_lista: int, per_file: int, parole: list[str] | None) -> dict[str, int]:
    """Tutti i comuni che il server non legge, uno dopo l'altro: legge dal PC, invia le pagine all'app e manda il rapporto.
    Si può interrompere (Ctrl+C) e riprendere con --riparti: i comuni già fatti sono ricordati in un file della cartella."""
    cartella.mkdir(parents=True, exist_ok=True)
    stato_file = cartella / f"stato_{re.sub(r'[^A-Za-z0-9]+', '_', regione)}.json"
    fatti: set[str] = set(json.loads(stato_file.read_text())) if riparti and stato_file.exists() else set()
    lista = [c for c in app.comuni_da_pc(regione, tutti) if c["id"] not in fatti]
    if limite:
        lista = lista[:limite]
    print(f"Comuni da leggere dal PC: {len(lista)}" + (f" (già fatti e saltati: {len(fatti)})" if fatti else ""))
    esiti = {"ok": 0, "non_riconosciuto": 0, "errore": 0}
    host_giu: set[str] = set()
    for i, c in enumerate(lista, 1):
        print(f"[{i}/{len(lista)}] {c['ente']} — {c.get('motivo', '')}")
        pagine_c: dict[str, dict] = {}
        rapporti: list[dict] = []
        for url in c["siti"][:3]:
            if _host(url) in host_giu:  # lo stesso sito non risponde già: inutile aspettare altri timeout
                continue
            try:
                pg, rap = scarica_con_rapporto(url, massimo, pausa, dettagli, max_sezioni, max_pagine_lista, parole, silenzioso=True)
            except PortaleNonRaggiungibile as exc:
                host_giu.add(_host(url))
                rapporti.append({"stato": "errore", "pagine": 0, "sezioni": 0, "ricerche": [], "errori": [str(exc)[:200]],
                                 "note": "la pagina di partenza non si apre nemmeno dal PC"})
                continue
            rapporti.append(rap)
            for p in pg:
                pagine_c.setdefault(p["url"], p)
        rap = unisci_rapporti(rapporti)
        inviate = 0
        if pagine_c:
            sotto = cartella / "serie" / re.sub(r"[^A-Za-z0-9]+", "_", c["ente"])
            for f in scrivi(list(pagine_c.values()), c["siti"][0], sotto, per_file):
                try:
                    inviate += int(app.invia(regione, c["ente"], f, item_id=c["id"]).get("pagine", 0))
                except RuntimeError as exc:
                    rap["errori"] = [*rap["errori"], f"invio: {exc}"][:10]
        esiti[rap["stato"]] += 1
        print(f"      {rap['stato']}: {rap['pagine']} pagine lette, {inviate} inviate. {rap['note'][:110]}")
        app.rapporto(regione, [{"id": c["id"], **rap}])
        fatti.add(c["id"])
        stato_file.write_text(json.dumps(sorted(fatti)))
    return esiti


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", help="una pagina del portale (es. https://dgegovpa.it/Arluno/Albo/Albo); non serve con --bloccati")
    ap.add_argument("--bloccati", action="store_true",
                    help="legge dal PC TUTTI i comuni della regione che il server non riesce a leggere (serve --app); invia e manda il rapporto")
    ap.add_argument("--tutti", action="store_true", help="con --bloccati: anche i comuni che il server legge bene")
    ap.add_argument("--riparti", action="store_true", help="con --bloccati: salta i comuni già fatti in una esecuzione interrotta")
    ap.add_argument("--limite", type=int, help="con --bloccati: solo i primi N comuni (per una prova)")
    ap.add_argument("--out", default="monitor_pagine", help="cartella dei file da caricare nell'app")
    ap.add_argument("--max", type=int, default=None, help="massimo di pagine per comune (di default 400 per un comune, 150 con --bloccati)")
    ap.add_argument("--pausa", type=float, default=0.5, help="secondi tra una richiesta e l'altra")
    ap.add_argument("--max-pagine-lista", type=int, default=60, help="massimo di pagine per ogni elenco")
    ap.add_argument("--max-sezioni", type=int, default=30)
    ap.add_argument("--per-file", type=int, default=60)
    ap.add_argument("--senza-dettagli", action="store_true", help="non aprire il «Dettaglio» dei bandi")
    ap.add_argument("--cerca", help="parole da cercare nelle pagine di ricerca (delibere, atti…), separate da virgola; "
                                     "di default: " + ", ".join(PAROLE))
    ap.add_argument("--app", help="indirizzo dell'app (quello con cui la apri nel browser): invia le pagine direttamente")
    ap.add_argument("--comune", help="nome del comune, come nell'app (es. Arluno)")
    ap.add_argument("--regione", default="Lombardia")
    ap.add_argument("--email", default=os.environ.get("MONITOR_EMAIL"))
    ap.add_argument("--password", default=os.environ.get("MONITOR_PASSWORD"), help="meglio lasciarla vuota: la chiede lo script")
    ap.add_argument("--mostra-password", action="store_true", help="la password si vede mentre la scrivi (utile se non si capisce se scrive)")
    ap.add_argument("--github-token", default=os.environ.get("MONITOR_GITHUB_TOKEN"),
                    help="token personale GitHub, se la porta 8000 del Codespace è privata")
    a = ap.parse_args()
    if a.bloccati and not a.app:
        ap.error("--bloccati richiede --app (l'elenco dei comuni è nell'app)")
    if not a.bloccati and not a.url:
        ap.error("indica l'indirizzo del portale, oppure usa --bloccati")
    if not a.bloccati and bool(a.app) != bool(a.comune):
        ap.error("per l'invio diretto servono insieme --app e --comune")
    app = None
    if a.app:  # prima di scaricare: se l'accesso non va, lo si scopre subito e non dopo dieci minuti
        app = App(a.app, a.github_token)
        chiedi = input if a.mostra_password else getpass.getpass
        app.login(a.email or input("Email dell'app: ").strip(), a.password or chiedi("Password dell'app: "))
        print("Accesso all'app riuscito.")
    parole = [x.strip() for x in a.cerca.split(",") if x.strip()] if a.cerca else None
    if a.bloccati:
        assert app is not None
        esiti = lavora_elenco(app, a.regione, Path(a.out), tutti=a.tutti, riparti=a.riparti, limite=a.limite, massimo=a.max or 150, pausa=a.pausa,
                              dettagli=not a.senza_dettagli, max_sezioni=a.max_sezioni, max_pagine_lista=a.max_pagine_lista,
                              per_file=a.per_file, parole=parole)
        print(f"\nFinito: {esiti['ok']} letti, {esiti['non_riconosciuto']} con portale non riconosciuto, {esiti['errore']} non raggiungibili."
              "\nL'analisi continua nell'app (scheda Raccolta); l'esito di ogni comune è nella scheda Siti.")
        return
    try:
        pagine = scarica(a.url, a.max or 400, a.pausa, not a.senza_dettagli, a.max_sezioni, a.max_pagine_lista, parole)
    except PortaleNonRaggiungibile as exc:
        sys.exit(f"Non riesco ad aprire la pagina di partenza ({exc}): controlla l'indirizzo e la connessione.")
    files = scrivi(pagine, a.url, Path(a.out), a.per_file)
    print(f"\nScritti {len(files)} file in «{Path(a.out).resolve()}»:")
    for f in files:
        print(f"  {f.name}  ({f.stat().st_size // 1024} KB)")
    if app:
        print("\nInvio all'app…")
        if not invia_all_app(files, app, a.regione, a.comune):
            sys.exit("Nessuna pagina è stata accettata dall'app: i file restano nella cartella, puoi caricarli a mano.")
    else:
        print("\nOra caricali nell'app: Raccolta -> «Portale che blocca il server» -> scegli TUTTI i file, scrivi il comune, Analizza.")


if __name__ == "__main__":
    main()
