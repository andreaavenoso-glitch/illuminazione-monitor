"""Import the comuni of one region from the IPA open data (indicepa.gov.it)
into entities + watchlist_items, with the "Amministrazione Trasparente" link
every PA must publish (D.Lgs. 33/2013) as the site to scan.

Download the "Amministrazioni" dataset (CSV) from https://indicepa.gov.it
(Open Data) and pass it with --file, or give a direct link with --url.

Usage (inside the api container):
    python -m infra.scripts.import_ipa --region Puglia --file /workspace/amministrazioni.csv
    python -m infra.scripts.import_ipa --region Puglia --url https://...

Idempotent: a comune already on the watchlist is left untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import re
from decimal import Decimal

# IPA column names vary slightly between releases: accept the known spellings.
_ALIASES = {
    "name": ("Denominazione_ente", "denominazione_ente", "Denominazione ente", "des_amm"),
    "tipo": ("Tipologia", "tipologia", "Tipologia_istat", "tipologia_istat"),
    "comune": ("Comune", "comune"),
    "provincia": ("Provincia", "provincia", "Sigla_provincia"),
    "regione": ("Regione", "regione"),
    "sito": ("Sito_istituzionale", "sito_istituzionale"),
    "trasparenza": (
        "Link_Amministrazione_Trasparente", "link_amministrazione_trasparente",
        "Amministrazione_trasparente", "Link_amministrazione_trasparente",
    ),
}


def _norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _pick(row: dict, key: str) -> str:
    """First non-empty value among the known spellings of a column. Matching
    ignores case, spaces and underscores, since IPA's xlsx and txt releases
    don't spell the headers identically."""
    norm = {_norm_col(k): v for k, v in row.items() if k}
    for alias in _ALIASES[key]:
        v = norm.get(_norm_col(alias))
        if v and str(v).strip() and str(v).strip().lower() not in ("nan", "none"):
            return str(v).strip()
    return ""


def xlsx_to_text(path: str) -> str:
    """First sheet of an .xlsx as tab-separated text (header row first), so
    the same parser handles IPA's xlsx, txt and csv releases."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    lines = []
    for row in ws.iter_rows(values_only=True):
        lines.append("\t".join("" if c is None else str(c).replace("\t", " ").replace("\n", " ") for c in row))
    return "\n".join(lines)


def _clean_url(url: str) -> str | None:
    url = url.strip()
    if not url:
        return None
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


def parse_ipa_rows(text: str, region: str) -> list[dict]:
    """Comuni of ``region`` from the IPA CSV text: name, province, site,
    trasparenza URL. Skips other regions and non-comune bodies."""
    from shared_models.regions import normalize_region

    target = normalize_region(region)
    first = text.lstrip("﻿").split("\n", 1)[0]
    delim = ";" if first.count(";") > first.count(",") else ("\t" if first.count("\t") > first.count(",") else ",")
    out: list[dict] = []
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=delim):
        if normalize_region(_pick(row, "regione")) != target:
            continue
        tipo = _pick(row, "tipo").lower()
        name = _pick(row, "name")
        if "comuni" not in tipo and not name.lower().startswith("comune di"):
            continue
        out.append({
            "name": name,
            "provincia": _pick(row, "provincia") or None,
            "sito": _clean_url(_pick(row, "sito")),
            "trasparenza": _clean_url(_pick(row, "trasparenza")),
        })
    return out


async def run(region: str, text: str) -> None:
    from app.core.database import SessionLocal
    from shared_models import Entity, WatchlistItem
    from shared_models.regions import normalize_region
    from sqlalchemy import select

    canonical = normalize_region(region)
    rows = parse_ipa_rows(text, region)
    if text.lstrip("\ufeff").lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        print("Il file scaricato e' una pagina web, non un elenco di dati: l'indirizzo non e' quello "
              "del dataset. Scarica il file a mano da indicepa.gov.it (Open Data -> dataset "
              "'Amministrazioni') e usa --file.")
        return
    if not rows:
        header = text.lstrip("\ufeff").split("\n", 1)[0][:300]
        print(f"Nessun comune trovato per {canonical}. Colonne del file: {header}")
        return
    new_e = new_w = no_url = 0
    async with SessionLocal() as session:
        for r in rows:
            ent = (await session.execute(
                select(Entity).where(Entity.name == r["name"], Entity.region == canonical)
            )).scalar_one_or_none()
            if ent is None:
                ent = Entity(name=r["name"], region=canonical, province=r["provincia"],
                             municipality=r["name"], entity_type="comune")
                session.add(ent)
                await session.flush()
                new_e += 1
            if (await session.execute(
                select(WatchlistItem).where(WatchlistItem.entity_id == ent.id)
            )).scalar_one_or_none():
                continue
            # IPA's txt release has no "Amministrazione Trasparente" column:
            # fall back to the comune's own home page, from which the scan
            # looks for the "Bandi di gara e contratti" section by itself.
            url = r["trasparenza"] or r["sito"]
            if not r["trasparenza"]:
                no_url += 1
            session.add(WatchlistItem(
                entity_id=ent.id, url_trasparenza=url, frequency="daily", priority="B",
                reliability_score=Decimal("0.70"), publication_model="html_scraping",
                active=bool(url),
            ))
            new_w += 1
        await session.commit()
    print(f"import_ipa {canonical}: comuni nel file={len(rows)} nuovi_enti={new_e} "
          f"nuovi_siti={new_w} senza_link_trasparenza={no_url} (usata la home del sito)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--file")
    g.add_argument("--url")
    a = ap.parse_args()
    if a.file and a.file.lower().endswith((".xlsx", ".xlsm")):
        text = xlsx_to_text(a.file)
    elif a.file:
        with open(a.file, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    else:
        import httpx
        text = httpx.get(a.url, follow_redirects=True, timeout=120).text
    asyncio.run(run(a.region, text))


if __name__ == "__main__":
    main()
