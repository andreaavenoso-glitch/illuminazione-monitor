"""Build the regional email digest. Pure (no DB, no network) so it is testable."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date

from shared_models.categories import GARA, MANIFESTAZIONE, PRE_GARA

SECTION_TITLES = {
    PRE_GARA: "Pre-gare (segnali prima del bando)",
    MANIFESTAZIONE: "Manifestazioni di interesse",
    GARA: "Gare pubblicate",
}
SECTION_ORDER = (PRE_GARA, MANIFESTAZIONE, GARA)


@dataclass(frozen=True)
class DigestItem:
    categoria: str
    ente: str
    descrizione: str
    link: str
    scadenza: date | None = None
    importo: float | None = None
    servizi: tuple[str, ...] = ()
    fonte_nazionale: bool = False


def _line(i: DigestItem) -> str:
    bits = [i.ente]
    if i.importo:
        bits.append(f"{i.importo:,.0f} EUR".replace(",", "."))
    if i.scadenza:
        bits.append(f"scadenza {i.scadenza.strftime('%d/%m/%Y')}")
    if i.servizi:
        bits.append("servizi: " + ", ".join(i.servizi))
    if i.fonte_nazionale:
        bits.append("da portale nazionale")
    return " | ".join(bits)


def build_digest(region: str, items: list[DigestItem], *, web_url: str) -> tuple[str, str, str]:
    """(subject, plain text, html) for one region. Items are grouped by the
    three categories, empty sections omitted."""
    by_cat = {c: [i for i in items if i.categoria == c] for c in SECTION_ORDER}
    counts = ", ".join(f"{len(by_cat[c])} {SECTION_TITLES[c].split(' (')[0].lower()}" for c in SECTION_ORDER if by_cat[c])
    subject = f"[{region}] {len(items)} novita illuminazione pubblica: {counts}"

    text = [f"Novita per {region}", ""]
    rows = ["<h2>Novit&agrave; per " + html.escape(region) + "</h2>"]
    for c in SECTION_ORDER:
        if not by_cat[c]:
            continue
        text.append(SECTION_TITLES[c].upper())
        rows.append(f"<h3>{html.escape(SECTION_TITLES[c])}</h3><ul>")
        for i in by_cat[c]:
            text.append(f"- {_line(i)}")
            text.append(f"  {i.descrizione[:240]}")
            text.append(f"  {i.link}")
            rows.append(
                f"<li><b>{html.escape(_line(i))}</b><br>{html.escape(i.descrizione[:240])}"
                f'<br><a href="{html.escape(i.link)}">{html.escape(i.link)}</a></li>'
            )
        text.append("")
        rows.append("</ul>")
    text.append(f"Vista regione: {web_url}/regions/{region}")
    rows.append(f'<p><a href="{html.escape(web_url)}/regions/{html.escape(region)}">Apri la vista della regione</a></p>')
    return subject, "\n".join(text), "".join(rows)


def parse_recipients(value: str | None) -> list[str]:
    if not value:
        return []
    out = []
    for part in value.replace(";", ",").split(","):
        p = part.strip()
        if p and "@" in p and p not in out:
            out.append(p)
    return out
