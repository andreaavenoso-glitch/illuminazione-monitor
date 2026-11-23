"""Referenti of a comune WITHOUT Claude: a free script that follows the checklist of the "referenti
comuni verificati" method as far as a program can.

What it does (the 12 steps, each reported as done / not done with the URLs checked):
 1 giunta / organi politici      5 scheda del responsabile tecnico   9  PEC (IPA, from the import)
 2 scheda del sindaco            6 Amm. Trasparente: organizzazione  10 elezioni / mandato
 3 scheda di ogni assessore      7 Amm. Trasparente: personale       11 stampa degli ultimi 6 mesi
 4 uffici LL.PP. / area tecnica  8 albo / decreti di nomina          12 riscontro incrociato

Names come from rules ("Sindaco: Mario Rossi", "Assessore ai LL.PP. ...") and are checked on the page text;
verificato / da confermare follow ``shared_models.referenti_logic`` (election date, 12 months, decree), and
the local press (Google News RSS, free) can downgrade a political name. Nothing is deduced: no e-mail is
rebuilt from a pattern, "nessuno ha la delega" is never written unless every assessore page was opened.
"""
from __future__ import annotations

import heapq
import re
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus, urlsplit

from app.collectors.main_content import main_text
from app.collectors.page_gate import safe_join
from app.collectors.referenti import looks_like_name, merge_people, verify_person
from app.collectors.rules_extract import extract_people_by_rules
from bs4 import BeautifulSoup
from shared_models.referenti_logic import election_date, freshness, has_decree, page_date

Fetch = Callable[[str], Awaitable[tuple[str, str | None]]]  # url -> (text, raw html or None)

PAGE_BUDGET = 60
MAX_DEPTH = 4

# (pattern, weight, tag): what a menu entry looks like on the way to the people
_LINKS: tuple[tuple[re.Pattern[str], int, str], ...] = tuple(
    (re.compile(p, re.I), w, t)
    for p, w, t in (
        (r"organi (di governo|politici|di indirizzo|istituzionali)|amministratori|amministrazione comunale|giunta|sindaco|assessor|politici", 30, "giunta"),
        (r"titolari di incarichi|incarichi politici|organizzazione|organigramma|articolazione degli uffici", 25, "organizzazione"),
        (r"lavori pubblici|area tecnica|settore tecnico|ufficio tecnico|uffici|manutenzion|patrimonio|ll\.? ?pp", 25, "uffici"),
        (r"personale|dirigenti|posizioni organizzative|responsabili|incarichi dirigenziali", 15, "personale"),
        (r"decret[io]|deleghe|nomina|albo", 15, "atti"),
        (r"^amministrazione$|amministrazione trasparente|trasparenza|uffici|unit[aà] organizzative", 12, "gateway"),
        (r"contatti|rubrica|telefon", 8, "contatti"),
    )
)
_NOT_PAGE = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".doc", ".docx", ".xls", ".xlsx", ".p7m")
_PRESS_SIGNAL = re.compile(
    r"rimpasto|dimission|dimess|revoca|nuovo assessore|nuova assessora|nomina(?:to|ta)? assessore|"
    r"vicesindaco|decadut|commissari|avvicendamento|lascia la giunta|azzerat",
    re.IGNORECASE,
)
STEPS = [
    "Giunta / organi politici", "Scheda del sindaco", "Scheda di ogni assessore", "Uffici LL.PP. / area tecnica",
    "Scheda del responsabile tecnico", "Amm. Trasparente: organizzazione", "Amm. Trasparente: personale",
    "Albo / decreti di nomina", "PEC (IPA)", "Elezioni e mandato", "Stampa ultimi 6 mesi", "Riscontro incrociato",
]


@dataclass
class Page:
    url: str
    text: str
    raw: str | None
    via: str  # the menu entry that led here
    tags: set[str]
    date: date | None = None


@dataclass
class Found:
    pages: list[Page] = field(default_factory=list)
    visited: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


_ROLE_IN_TEXT = re.compile(r"\b(sindac[oa]|assessor[ei]a?|vicesindaco|responsabile|dirigente)\b", re.I)
_PERSON_HREF = re.compile(r"sindaco|assessor|amministrator|giunta|persona|scheda|organi|politic", re.I)
# Platforms that host the Amministrazione Trasparente / albo of many comuni: a link to them is still "the site".
VENDOR_HOSTS = ("dgegovpa.it", "trasparenza-valutazione-merito.it", "halleyweb", "hypersicapp", "apkappa", "studiok",
                "municipiumapp", "wlp", "paleo", "cloud.comune")


_PARTICLES = {"di", "de", "del", "della", "dei", "degli", "da", "dal", "dalla", "van", "von", "d", "lo", "la", "le", "e"}
GENERIC_LINK = re.compile(
    r"^(vai( alla| a| al)?( pagina| scheda| sezione)?|leggi( tutto| di più| tutta| la scheda)?|scopri( di più)?|"
    r"maggiori informazioni|approfondisci|dettagli|altro|more|continua|visualizza|apri|accedi|clicca qui|qui)$",
    re.I,
)


def _title_case(text: str) -> bool:
    """A real name has a capital on every word ("Mario Rossi", "ROSSI MARIO"); "Note legali" does not."""
    toks = [t for t in re.split(r"[\s'’]+", text) if t and t.lower().strip(".") not in _PARTICLES]
    return bool(toks) and all(t[0].isupper() for t in toks)


def _context_text(a: Any) -> str:
    """For a link that says only "Vai alla pagina": the heading / title of the card it sits in."""
    node = a
    for _ in range(4):
        node = node.parent
        if node is None:
            break
        head = node.find(["h1", "h2", "h3", "h4", "h5", "h6", "strong"])
        if head and head.get_text(strip=True):
            return " ".join(head.get_text(" ", strip=True).split())
        txt = " ".join(node.get_text(" ", strip=True).split())
        if 3 < len(txt) <= 70:
            return txt
    return ""


_CARD_ROLE = re.compile(r"\b(vice ?sindaco|sindac[oa]|assessor[ea]|consigliere|consigliera|consigliere comunale)\b", re.I)
_PERSON_LINK_HREF = re.compile(r"persone|persona|scheda|amministrator|politic|/people/|/person/", re.I)


def card_text(a: Any) -> str:
    """The text of the card a link sits in: climb until a role word shows up (max 4 levels, ≤260 chars)."""
    node, best = a, ""
    for _ in range(4):
        node = node.parent
        if node is None:
            break
        txt = " ".join(node.get_text(" ", strip=True).split())
        if len(txt) > 260:
            break
        best = txt
        if _CARD_ROLE.search(txt):
            break
    return best


def _card_role(ctx: str) -> str | None:
    m = _CARD_ROLE.search(ctx)
    if not m:
        return None
    w = m.group(1).lower().replace(" ", "")
    if w.startswith("consigli"):
        return "consigliere"
    if w == "vicesindaco":
        return "assessore"
    return "sindaco" if w.startswith("sindac") else "assessore"


def people_from_cards(raw: str | None) -> list[dict[str, Any]]:
    """Name + role from the cards of an elenco page: <a>Mario Rossi</a> with "Sindaco" / "Assessore ..." in the
    same card. Consiglieri are left out; checked afterwards on the page text like every other person."""
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in BeautifulSoup(raw, "lxml").find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        bare = re.sub(r"(?i)\b(sindaco|sindaca|assessore|assessora|vicesindaco|dott\.?|dr\.?|ing\.?|arch\.?|avv\.?|geom\.?)\b", "", text)
        bare = " ".join(bare.split())
        if not (_PERSON_LINK_HREF.search(a["href"]) or _title_case(bare)) or not looks_like_name(bare) or not _title_case(bare):
            continue
        ctx = card_text(a)
        ruolo = _card_role(ctx)
        if ruolo not in ("sindaco", "assessore") or bare.lower() in seen:
            continue
        seen.add(bare.lower())
        out.append({"nome": bare, "ruolo": ruolo, "qualifica": ctx[:120], "email": None, "telefono": None, "citazione": ctx[:200]})
    return out


def person_from_page(pg_url: str, text: str, raw: str | None) -> dict[str, Any] | None:
    """A person's own page ("/persone/mario-rossi"): the name is the page title, the role is written in the first
    lines ("Sindaco", "Assessore ai lavori pubblici"). Consiglieri and everybody else are left out."""
    if not raw or not _PERSON_LINK_HREF.search(pg_url):
        return None
    soup = BeautifulSoup(raw, "lxml")
    h1 = soup.find("h1")
    name = " ".join(h1.get_text(" ", strip=True).split()) if h1 else ""
    bare = " ".join(re.sub(r"(?i)\b(sindaco|sindaca|assessore|assessora|vicesindaco|dott\.?|dr\.?|ing\.?|arch\.?|avv\.?|geom\.?)\b", "", name).split())
    if not bare or not looks_like_name(bare) or not _title_case(bare):
        return None
    # the role is written in the CENTRAL part of the page, right after the name: the menu of the site ("Organi di
    # governo: Sindaco, Giunta, Consiglio") would give "Sindaco" to everybody
    central = main_text(raw) or " ".join(text.split())
    idx = central.find(bare)
    head = central[idx: idx + 500] if idx >= 0 else central[:500]
    ruolo = _card_role(head)
    if ruolo not in ("sindaco", "assessore"):
        return None
    return {"nome": bare, "ruolo": ruolo, "qualifica": head[:120], "email": None, "telefono": None, "citazione": head[:200]}


def score_link(text: str, href: str, person_ok: bool = False) -> tuple[int, set[str]]:
    """How promising a link is on the way to the people, and what kind of page it leads to. A link whose text
    merely LOOKS like a name ("Animali Domestici") is a person's page only when it is listed on a giunta /
    organi page, or says so itself (role word, "sindaco" in the address): otherwise every two-word menu entry
    would eat the page budget."""
    t = " ".join(text.lower().split())
    if not t or len(t) > 70 or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return 0, set()
    if href.lower().split("?")[0].endswith(_NOT_PAGE):
        return 0, set()
    score, tags = 0, set()
    for rx, w, tag in _LINKS:
        if rx.search(t) or rx.search(href.lower().split("?")[0].rsplit("/", 1)[-1]):
            score = max(score, w)
            tags.add(tag)
    # a person's own page: the link text is a name, possibly with the role in front/behind
    bare = re.sub(r"(?i)\b(sindaco|sindaca|assessore|assessora|vicesindaco|dott\.?|dr\.?|ing\.?|arch\.?|avv\.?|geom\.?)\b", "", text)
    if looks_like_name(" ".join(bare.split())) and _title_case(bare) and (person_ok or _ROLE_IN_TEXT.search(text) or _PERSON_HREF.search(href)):
        evidence = bool(_ROLE_IN_TEXT.search(text) or _PERSON_HREF.search(href))
        score, tags = max(score, 40 if evidence else 20), tags | {"scheda"}  # no role seen: after giunta / uffici
    return score, tags


def menu_links(raw: str, base: str, parent_tags: set[str] | None = None) -> list[tuple[int, str, str, set[str]]]:
    host = urlsplit(base).netloc
    person_ok = bool(parent_tags and parent_tags & {"giunta", "organizzazione", "scheda"})
    out: dict[str, tuple[int, str, str, set[str]]] = {}
    for a in BeautifulSoup(raw, "lxml").find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        if GENERIC_LINK.match(text):
            text = _context_text(a) or text
        sc, tags = score_link(text, a["href"].strip(), person_ok)
        if sc <= 0:
            continue
        if "scheda" in tags:  # on an elenco: sindaco / assessori first, consiglieri last
            role = _card_role(card_text(a))
            sc = 60 if role in ("sindaco", "assessore") else (5 if role == "consigliere" else sc)
        url = safe_join(base, a["href"].strip())
        if not url:
            continue
        other = urlsplit(url).netloc
        if other != host and not (sc >= 25 and any(v in other for v in VENDOR_HOSTS)):
            continue
        url = url.split("#")[0]
        if url not in out or out[url][0] < sc:
            out[url] = (sc, url, text, tags)
    return list(out.values())


async def crawl(starts: list[str], fetch: Fetch, *, budget: int = PAGE_BUDGET) -> Found:
    """Best-first walk of the comune's own site towards giunta, uffici, trasparenza, atti."""
    found = Found()
    heap: list[tuple[int, int, str, str, int, set[str]]] = []
    seen: set[str] = set()
    n = 0
    for u in starts:
        heapq.heappush(heap, (-100, n, u, "home", 0, {"home"}))
        n += 1
    while heap and len(found.pages) < budget:
        neg, _, url, via, depth, tags = heapq.heappop(heap)
        if url in seen:
            continue
        seen.add(url)
        text, raw = await fetch(url)
        if not text:
            found.failed.append(url)
            continue
        found.visited.append(url)
        found.pages.append(Page(url, text, raw, via, tags, page_date(text)))
        if raw and depth < MAX_DEPTH:
            for sc, u, anchor, t in menu_links(raw, url, tags):
                if u not in seen:
                    heapq.heappush(heap, (-sc - (0 if depth else 5), n, u, anchor, depth + 1, t))
                    n += 1
    return found


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^\w@.]+", " ", s.lower()).split())


def people_from_pages(pages: list[Page], today: date, elezione: date | None) -> list[tuple[dict[str, Any], str]]:
    """(person, url) for every name the rules find on a page, checked on that page's text; the freshness
    rules decide verificato / da_confermare."""
    out: list[tuple[dict[str, Any], str]] = []
    for pg in pages:
        own = person_from_page(pg.url, pg.text, pg.raw)
        for prop in extract_people_by_rules(pg.text) + people_from_cards(pg.raw) + ([own] if own else []):
            chk = verify_person(prop, pg.text)
            if not chk:
                continue
            pos = _norm(pg.text).find(_norm(chk["nome"]).split()[-1])
            window = _norm(pg.text)[max(0, pos - 300): pos + 300] if pos >= 0 else ""
            ok, motivo = freshness(chk["ruolo"], pg.date, elezione, has_decree(window), today)
            chk = {**chk, "data_fonte": pg.date, "elezione_data": elezione, "motivo": None}
            if chk["stato"] != "verificato":
                chk["motivo"] = "ruolo non scritto accanto al nome"
            elif not ok:
                chk["stato"], chk["motivo"] = "da_confermare", motivo
            out.append((chk, pg.url))
    return out


def attach_contacts(people: list[dict[str, Any]], pages: list[Page], domain_hint: str) -> None:
    """An e-mail / phone found on the SAME page as a person, preferring the comune's own domain; never
    rebuilt from a pattern."""
    for p in people:
        if p.get("email") and p.get("telefono"):
            continue
        for pg in pages:
            if pg.url != p["fonte_url"]:
                continue
            n_people = sum(1 for q in people if q["fonte_url"] == p["fonte_url"])
            if n_people != 1:  # several people on a page: contacts only if next to the name (rules did)
                break
            emails = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", pg.text)
            emails = [e for e in emails if domain_hint in e.lower()] or emails
            if emails and not p.get("email"):
                p["email"] = emails[0]
            break


# --- press ----------------------------------------------------------------------------------------
def press_url(ente: str) -> str:
    q = quote_plus(f'"{ente}" giunta OR assessore OR sindaco OR "lavori pubblici" when:6m')
    return f"https://news.google.com/rss/search?q={q}&hl=it&gl=IT&ceid=IT:it"


def parse_press(xml: str, today: date) -> list[tuple[date, str, str]]:
    """(date, title, link) of the articles of the last 6 months that talk about changes in the giunta."""
    out: list[tuple[date, str, str]] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        try:
            d = parsedate_to_datetime(item.findtext("pubDate") or "").date()
        except (TypeError, ValueError):
            continue
        if today - d <= timedelta(days=183) and _PRESS_SIGNAL.search(title):
            out.append((d, title, (item.findtext("link") or "").strip()))
    return sorted(out, reverse=True)


def apply_press(people: list[dict[str, Any]], signals: list[tuple[date, str, str]]) -> None:
    """A political name whose surname appears in a recent article about changes is only da_confermare."""
    for p in people:
        if p["ruolo"] not in ("sindaco", "assessore") or p["stato"] != "verificato":
            continue
        surname = _norm(p["nome"]).split()[-1]
        for d, title, _ in signals:
            if surname in _norm(title):
                p["stato"] = "da_confermare"
                p["motivo"] = f"stampa del {d:%d/%m/%Y}: {title[:110]}"
                break


# --- the whole search --------------------------------------------------------------------------------
def build_checklist(
    found: Found, people: list[dict[str, Any]], pec: str | None, elezione: date | None, press_ok: bool, press_n: int
) -> list[dict[str, Any]]:
    by_tag: dict[str, list[str]] = {}
    for pg in found.pages:
        for t in pg.tags:
            by_tag.setdefault(t, []).append(pg.url)
    roles = {r: [p for p in people if p["ruolo"] == r] for r in ("sindaco", "assessore", "responsabile_tecnico")}
    scheda = by_tag.get("scheda", [])
    two_pages = any(sum(1 for pg in found.pages if _norm(q["nome"]) in _norm(pg.text)) >= 2 for q in people)
    done: list[tuple[bool, list[str], str]] = [
        (bool(by_tag.get("giunta")) and bool(roles["sindaco"] or roles["assessore"]), by_tag.get("giunta", [])[:4], ""),
        (any(p.get("email") or p.get("telefono") for p in roles["sindaco"]) or bool(scheda and roles["sindaco"]), scheda[:2], ""),
        (bool(roles["assessore"]) and len(scheda) >= len(roles["assessore"]), scheda[:6],
         "" if roles["assessore"] else "nessun assessore trovato: non si puo' dire che nessuno abbia la delega"),
        (bool(by_tag.get("uffici")), by_tag.get("uffici", [])[:4], ""),
        (bool(roles["responsabile_tecnico"]), [p["fonte_url"] for p in roles["responsabile_tecnico"]][:2], ""),
        (bool(by_tag.get("organizzazione")), by_tag.get("organizzazione", [])[:3], ""),
        (bool(by_tag.get("personale")), by_tag.get("personale", [])[:3], ""),
        (bool(by_tag.get("atti")), by_tag.get("atti", [])[:3], "decreti letti solo se linkati dal menu"),
        (bool(pec), [], "da IPA" if pec else "PEC non presente nei dati IPA importati"),
        (elezione is not None, [], "" if elezione else "data non trovata sul sito: verificare su Eligendo / Anagrafe amministratori"),
        (press_ok, [], f"{press_n} articoli su cambi di giunta" if press_ok else "RSS non raggiungibile: controllo manuale"),
        (two_pages, [], "almeno un nome su due pagine" if two_pages else "nessun nome confermato da una seconda pagina"),
    ]
    return [{"n": i + 1, "passo": STEPS[i], "ok": ok, "urls": urls, "nota": note} for i, (ok, urls, note) in enumerate(done)]


async def search_referenti(
    ente: str, starts: list[str], fetch: Fetch, fetch_press: Callable[[str], Awaitable[str]],
    *, pec: str | None, today: date,
) -> dict[str, Any]:
    found = await crawl(starts, fetch)
    texts = [pg.text for pg in found.pages]
    elezione = max((e for t in texts if (e := election_date(t, today))), default=None)
    people_raw = people_from_pages(found.pages, today, elezione)
    people = merge_people(people_raw)
    host = urlsplit(starts[0]).netloc if starts else ""
    attach_contacts(people, found.pages, max(host.split("."), key=len, default=""))  # e.g. "scanzanojonico"
    try:
        xml = await fetch_press(press_url(ente))
    except Exception:  # noqa: BLE001
        xml = ""
    signals = parse_press(xml, today) if xml else []
    apply_press(people, signals)
    checklist = build_checklist(found, people, pec, elezione, bool(xml), len(signals))
    lacune: list[str] = []
    ruoli = {p["ruolo"] for p in people}
    for r, label in (("sindaco", "sindaco"), ("assessore", "assessore con delega LL.PP."), ("responsabile_tecnico", "responsabile tecnico")):
        if r not in ruoli:
            lacune.append(f"{label}: non trovato nelle {len(found.pages)} pagine lette")
    for p in people:
        if p["stato"] != "verificato":
            lacune.append(f"{p['nome']} ({p['ruolo']}): {p.get('motivo') or 'da confermare'}")
    if found.failed:
        lacune.append(f"pagine non apribili: {', '.join(found.failed[:3])}")
    missing = [str(s["n"]) for s in checklist if not s["ok"]]
    if missing:
        lacune.append("checklist incompleta, passi non riusciti: " + ", ".join(missing))
    stampa = (
        f"{len(signals)} articoli su cambi di giunta negli ultimi 6 mesi: " + "; ".join(t[:80] for _, t, _ in signals[:2])
        if signals else ("nessun articolo su cambi di giunta" if xml else "non controllata (RSS non raggiungibile)")
    )
    mandato = date(elezione.year + 5, elezione.month, min(elezione.day, 28)) if elezione else None
    return {
        "people": people, "pec": pec, "elezione": elezione, "mandato_scadenza": mandato,
        "checklist": checklist, "lacune": lacune, "stampa": stampa, "urls": found.visited,
        "press": [(str(d), t, link) for d, t, link in signals],
    }
