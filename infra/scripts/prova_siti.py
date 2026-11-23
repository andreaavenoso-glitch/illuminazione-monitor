"""End-to-end test of the FREE parts (no Claude, no cost) on real sites, to see the real limits.

For each site: crawl + page gate, avvisi extracted by rules, the hunt for the deadline (page -> attachments ->
PDF), and the referenti script with its 12-step checklist. Writes report.md / report.json with a section
"Limitazioni rilevate": what the script could not do and why, so it can be improved where it matters.

By watchlist (needs the database):
    docker compose exec -T worker python -m infra.scripts.prova_siti --region Basilicata --comune Scanzano --out /workspace/infra/prove/scanzano
Direct, no database (name=url, repeatable):
    docker compose exec -T worker python -m infra.scripts.prova_siti --sito "Comune di Arluno=https://www.comune.arluno.mi.it" --out /workspace/infra/prove/arluno
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def limitations(sites: list[dict]) -> list[str]:
    """What the free script could not do, in words (pure, tested)."""
    out: list[str] = []
    unreachable = [s["ente"] for s in sites if s.get("error")]
    if unreachable:
        out.append(f"Siti non leggibili ({len(unreachable)}): " + ", ".join(unreachable[:8]) + " — blocco o errore di rete.")
    full = sum(s.get("pages_full", 0) for s in sites)
    if full:
        out.append(f"{full} pagine nominano i servizi ma non hanno un elenco riconoscibile: le regole non le leggono "
                   "(servirebbe Claude o un lettore dedicato alla piattaforma).")
    stops = Counter(s["stopped_by"] for s in sites if s.get("stopped_by"))
    if stops.get("pages") or stops.get("time"):
        out.append(f"Esplorazione fermata dal budget (pagine {stops.get('pages', 0)}, tempo {stops.get('time', 0)}): "
                   "potrebbero restare pagine utili non lette.")
    reasons = Counter()
    for s in sites:
        for h in s.get("hunts", []):
            if not h.get("deadline"):
                reasons[h.get("reason") or "n/d"] += 1
                for n in h.get("notes", []):
                    reasons[n] += 1
    for why, n in reasons.most_common(6):
        out.append(f"Scadenza non trovata ({n}): {why}")
    for s in sites:
        missing = [c["passo"] for c in s.get("checklist", []) if not c["ok"]]
        if missing:
            out.append(f"Referenti {s['ente']}: passi non riusciti — " + "; ".join(missing[:5]))
    return out or ["Nessuna limitazione rilevata su questi siti."]


async def run(sites: list[tuple[str, str]], out: Path, max_hunt: int) -> None:
    from app.collectors.adaptive_fetch import adaptive_fetch_result
    from app.collectors.crawler import crawl
    from app.collectors.deadline_hunt import hunt_deadline
    from app.collectors.page_gate import gate_page, same_site
    from app.collectors.referenti_script import search_referenti
    from app.collectors.rules_extract import extract_records_by_rules
    from app.config import get_worker_settings
    from app.tasks.find_referenti import _fetch_press, _script_fetch
    from app.tasks.verify_records import fetch_doc
    from shared_models.categories import categorize
    from shared_models.relevance import STRICT_CATEGORIES, today_utc
    from shared_models.services import configure as configure_services
    from shared_models.services import parse_enabled

    settings = get_worker_settings()
    configure_services(parse_enabled(settings.enabled_services))
    out.mkdir(parents=True, exist_ok=True)
    today = today_utc()
    reports: list[dict] = []

    for ente, start in sites:
        print(f"== {ente}  {start}", flush=True)
        rep: dict = {"ente": ente, "start": start, "pages": 0, "pages_full": 0, "records": [], "hunts": []}
        first = await adaptive_fetch_result(
            start, timeout=60, try_variants=True, max_html_chars=settings.crawl_max_html_chars,
            playwright_min_chars=settings.smart_collector_playwright_min_chars,
            playwright_wait_ms=settings.smart_collector_playwright_wait_ms, label="prova",
        )
        if not first.text:
            rep["error"] = first.error or "pagina vuota"
            reports.append(rep)
            continue
        url = first.url or start
        cands: list = []
        gates = Counter()

        async def on_page(purl: str, html: str, depth: int, cands=cands, gates=gates):
            g = gate_page(html, base_url=purl)
            gates[g.action] += 1
            cands.extend(g.candidates)
            return g

        async def fetch_page(purl: str, _start=url):
            own = same_site(purl, _start)
            return await adaptive_fetch_result(
                purl, timeout=60.0 if own else settings.crawl_external_timeout_s, try_variants=False,
                max_html_chars=settings.crawl_max_html_chars,
                playwright_min_chars=settings.smart_collector_playwright_min_chars,
                playwright_wait_ms=settings.smart_collector_playwright_wait_ms, label="prova",
            )

        res = await crawl(
            start_url=url, start_html=first.text, seeds=[], fetch=fetch_page, on_page=on_page,
            max_pages=settings.crawl_max_pages, max_depth=settings.crawl_max_depth,
            time_budget_s=settings.crawl_time_budget_s, delay_s=settings.crawl_delay_s,
        )
        gates[gate_page(first.text, base_url=url).action] += 1
        rep.update(pages=len(res.visits) + 1, stopped_by=res.stopped_by, pages_full=gates["full"],
                   gate=dict(gates), deepest=max((v.depth for v in res.visits), default=0))
        recs = extract_records_by_rules(cands, ente=ente, today=today)
        for r in recs:
            cat = categorize(stato_procedurale="PRE-GARA", text=f"{r['title']} {r['body']}", atto_tipo=r["atto_tipo"],
                             has_deadline=bool(r["scadenza"]))
            rep["records"].append({"titolo": r["title"][:140], "tipo": r["atto_tipo"], "categoria": cat,
                                   "scadenza_in_riga": r["scadenza"], "url": r["url"]})
        todo = [r for r in rep["records"] if r["categoria"] in STRICT_CATEGORIES and not r["scadenza_in_riga"]][:max_hunt]
        for r in todo:
            h = await hunt_deadline(r["url"], lambda u, d: fetch_doc(u, d, settings))
            rep["hunts"].append({"url": r["url"], "deadline": str(h.deadline) if h.deadline else None,
                                 "docs": len(h.docs), "reason": h.reason, "notes": [d.note for d in h.docs if d.note],
                                 "trail": h.trail()})
        async def sfetch(u: str):
            return await _script_fetch(u, settings)
        try:
            ref = await search_referenti(ente, [url], sfetch, _fetch_press, pec=None, today=today)
            rep["referenti"] = [{"ruolo": p["ruolo"], "nome": p["nome"], "stato": p["stato"], "motivo": p.get("motivo"),
                                 "email": p.get("email"), "fonte": p["fonte_url"]} for p in ref["people"]]
            rep["checklist"] = ref["checklist"]
            rep["elezione"] = str(ref["elezione"] or "")
            rep["stampa"] = ref["stampa"]
        except Exception as exc:  # noqa: BLE001
            rep["referenti_errore"] = f"{type(exc).__name__}: {exc}"
        reports.append(rep)

    lim = limitations(reports)
    (out / "report.json").write_text(json.dumps({"limitazioni": lim, "siti": reports}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md = [f"# Prova gratuita dei siti ({datetime.now(tz=UTC):%d/%m/%Y %H:%M})", "", "## Limitazioni rilevate", ""]
    md += [f"- {x}" for x in lim] + [""]
    for s in reports:
        md.append(f"## {s['ente']}  ({s['start']})")
        if s.get("error"):
            md += [f"- NON LEGGIBILE: {s['error']}", ""]
            continue
        md.append(f"- pagine {s['pages']}, profondità {s.get('deepest')}, stop: {s.get('stopped_by')}, filtro: {s.get('gate')}")
        md.append(f"- avvisi trovati dalle regole: {len(s['records'])}")
        for r in s["records"][:25]:
            md.append(f"    - [{r['categoria']}] {r['titolo']} (scadenza in riga: {r['scadenza_in_riga'] or '—'})")
        for h in s["hunts"]:
            md.append(f"- scadenza {h['url'][:70]}: {h['deadline'] or 'NON TROVATA'} — {h['trail'][:200]}")
        if "referenti" in s:
            md.append(f"- referenti: {len(s['referenti'])} (checklist {sum(1 for c in s['checklist'] if c['ok'])}/12; elezioni {s['elezione'] or 'n/d'})")
            for p in s["referenti"]:
                md.append(f"    - {p['ruolo']}: {p['nome']} [{p['stato']}] {p.get('motivo') or ''}")
        md.append("")
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:60]))
    print(f"\nSalvato in {out}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--region")
    ap.add_argument("--comune")
    ap.add_argument("--sito", action="append", default=[], help="Nome=url (senza database)")
    ap.add_argument("--max-hunt", type=int, default=15, help="avvisi per cui cercare la scadenza")
    a = ap.parse_args()
    sites: list[tuple[str, str]] = [tuple(x.split("=", 1)) for x in a.sito]  # type: ignore[misc]
    if a.region:
        from app.db import SessionLocal
        from shared_models import Entity, WatchlistItem
        from shared_models.regions import normalize_region
        from sqlalchemy import select

        async with SessionLocal() as s:
            rows = (await s.execute(select(WatchlistItem, Entity).join(Entity, WatchlistItem.entity_id == Entity.id)
                                    .where(WatchlistItem.active.is_(True)))).all()
        for item, ent in rows:
            if normalize_region(ent.region) == normalize_region(a.region) and (not a.comune or a.comune.lower() in ent.name.lower()):
                u = item.url_trasparenza or item.url_albo
                if u:
                    sites.append((ent.name, u))
    if not sites:
        print("Nessun sito: usa --region/--comune oppure --sito Nome=url")
        return
    await run(sites, Path(a.out), a.max_hunt)


if __name__ == "__main__":
    asyncio.run(main())
