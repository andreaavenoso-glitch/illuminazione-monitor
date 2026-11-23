"""End-to-end test of the FREE parts (no Claude, no cost) on real sites, to see the real limits.

For each site: crawl + page gate, avvisi extracted by rules, the hunt for the deadline (page -> attachments ->
PDF), and the referenti script with its 12-step checklist. Writes report.md / report.json with a section
"Limitazioni rilevate": what the script could not do and why, so it can be improved where it matters.

Large test over a sample (see campione.py), with the documentation analysis and the reference of known referenti:
    docker compose exec -T worker python -m infra.scripts.prova_siti --campione /workspace/infra/prove/campione.csv --analisi \
        --oro /workspace/infra/scripts/data/oro_referenti_lombardia.csv --concorrenza 3 --out /workspace/infra/prove/grande
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
from urllib.parse import urlsplit


def limitations(sites: list[dict], failures: dict | None = None) -> list[str]:
    """What the free script could not do, in words (pure, tested)."""
    out: list[str] = []
    blocked = [s["ente"] for s in sites if s.get("error") and ("403" in s["error"] or "blocc" in s["error"].lower())]
    if blocked:
        out.append("Il sito blocca l'accesso automatico (403) — " + ", ".join(blocked)
                   + ": da qui non si legge. Alternative: piattaforme regionali/nazionali o verifica manuale.")
    throttled = [s["ente"] for s in sites if s.get("error") and "429" in s["error"]]
    if throttled:
        out.append("Il sito limita le richieste (429) — " + ", ".join(throttled[:8])
                   + ": l'indirizzo di questo server è in attesa. Non è un errore del sito: riprovare più tardi "
                   "(da qualche minuto a un'ora) e con meno comuni insieme.")
    blocked = blocked + throttled
    unreachable = [s["ente"] for s in sites if s.get("error") and s["ente"] not in blocked]
    if unreachable:
        out.append(f"Siti non leggibili ({len(unreachable)}): " + ", ".join(unreachable[:8]) + " — errore di rete o pagina vuota.")
    full = sum(s.get("pages_full", 0) for s in sites)
    if full:
        out.append(f"{full} pagine nominano i servizi ma non hanno un elenco riconoscibile: le regole non le leggono "
                   "(servirebbe Claude o un lettore dedicato alla piattaforma).")
    stops = Counter(s["stopped_by"] for s in sites if s.get("stopped_by"))
    if stops.get("pages") or stops.get("time"):
        out.append(f"Esplorazione fermata dal budget (pagine {stops.get('pages', 0)}, tempo {stops.get('time', 0)}): "
                   "potrebbero restare pagine utili non lette.")
    bad_hosts: Counter = Counter()
    for (host, _kind), n in (failures or {}).items():
        bad_hosts[host] += n
    if bad_hosts:
        top = ", ".join(f"{h} ({n})" for h, n in bad_hosts.most_common(8))
        out.append("Indirizzi non raggiungibili da questo server (piattaforme di albo/trasparenza che bloccano o "
                   "interrompono le connessioni): " + top)
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


def riepilogo(sites: list[dict], gold: list[dict] | None = None) -> dict:
    """Aggregate numbers over the sites, in total and per size class: the measure of how well each of the four
    parts works (detection, deadline hunt, referenti, documentation analysis). Pure, tested."""
    from collections import defaultdict

    def pct(a: int, b: int) -> float:
        return round(100 * a / b, 1) if b else 0.0

    def block(group: list[dict]) -> dict:
        ok = [x for x in group if not x.get("error")]
        recs = [r for x in ok for r in x.get("records", [])]
        hunts = [h for x in ok for h in x.get("hunts", [])]
        ana = [a for x in ok for a in x.get("analisi", [])]
        ref_sites = [x for x in ok if "referenti" in x]
        roles = lambda x, r: any(p["ruolo"] == r for p in x["referenti"])  # noqa: E731
        fields: dict[str, int] = defaultdict(int)
        for a in ana:
            for k in a.get("campi", []):
                fields[k] += 1
        return {
            "siti": len(group), "letti": len(ok), "letti_pct": pct(len(ok), len(group)),
            "bloccati": sum(1 for x in group if x.get("error") and "403" in x["error"]),
            "pagine_medie": round(sum(x.get("pages", 0) for x in ok) / max(len(ok), 1), 1),
            "siti_con_avvisi_pct": pct(sum(1 for x in ok if x.get("records")), len(ok)),
            "avvisi": len(recs),
            "avvisi_per_categoria": dict(Counter(r["categoria"] for r in recs)),
            "scadenza": {"cercate": len(hunts), "trovate": sum(1 for h in hunts if h["deadline"]),
                         "trovate_pct": pct(sum(1 for h in hunts if h["deadline"]), len(hunts))},
            "referenti": {
                "siti": len(ref_sites),
                "con_sindaco_pct": pct(sum(1 for x in ref_sites if roles(x, "sindaco")), len(ref_sites)),
                "con_assessore_pct": pct(sum(1 for x in ref_sites if roles(x, "assessore")), len(ref_sites)),
                "con_tecnico_pct": pct(sum(1 for x in ref_sites if roles(x, "responsabile_tecnico")), len(ref_sites)),
                "checklist_media": round(sum(sum(1 for c in x["checklist"] if c["ok"]) for x in ref_sites) / max(len(ref_sites), 1), 1),
            },
            "analisi": {"documenti_analizzati": len(ana), "campi_trovati_pct": {k: pct(v, len(ana)) for k, v in sorted(fields.items())}},
        }

    by_f: dict[str, list[dict]] = defaultdict(list)
    for x in sites:
        by_f[x.get("fascia") or "n/d"].append(x)
    out = {"totale": block(sites), "per_fascia": {f: block(g) for f, g in sorted(by_f.items())}}
    if gold:
        found = hits = 0
        per_ente = []
        for g_ente in sorted({g["ente"] for g in gold}):
            site = next((x for x in sites if g_ente.lower() in x["ente"].lower() or x["ente"].lower() in g_ente.lower()), None)
            if not site or "referenti" not in site:
                continue
            names = " ".join(p["nome"].lower() for p in site["referenti"])
            want = [g for g in gold if g["ente"] == g_ente]
            ok_n = sum(1 for g in want if g["cognome"].lower() in names)
            found += len(want)
            hits += ok_n
            per_ente.append({"ente": g_ente, "attesi": len(want), "trovati": ok_n})
        out["riferimento_referenti"] = {"attesi": found, "trovati": hits, "recall_pct": pct(hits, found), "per_ente": per_ente}
    return out


async def run(
    sites: list[tuple[str, str, str]], out: Path, max_hunt: int, concurrency: int = 3, analisi: bool = False,
    gold: list[dict] | None = None,
) -> None:
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
    from app.collectors.doc_fields import extract_fields

    async def one(ente: str, start: str, fascia: str) -> dict:
        print(f"== {ente}  {start}", flush=True)
        rep: dict = {"ente": ente, "start": start, "fascia": fascia, "pages": 0, "pages_full": 0, "records": [],
                     "hunts": [], "analisi": []}
        first = await adaptive_fetch_result(
            start, timeout=60, try_variants=True, max_html_chars=settings.crawl_max_html_chars,
            playwright_min_chars=settings.smart_collector_playwright_min_chars,
            playwright_wait_ms=settings.smart_collector_playwright_wait_ms, label="prova",
        )
        if not first.text:
            rep["error"] = first.error or "pagina vuota"
            return rep
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

        # the same starting points as the real scan: sitemap, else the "Bandi di gara" link and the section names
        from app.collectors.albo_pretorio_llm import find_bandi_link
        from app.collectors.page_gate import pick_section_links
        from app.collectors.sitemap import discover_sitemap_urls

        seeds = await discover_sitemap_urls(url)
        if seeds:
            seeds = seeds[:8]
        else:
            seeds = [u for u in dict.fromkeys([find_bandi_link(first.text, base_url=url),
                                               *pick_section_links(first.text, base_url=url, limit=8)]) if u and u != url]
        rep["seeds"] = seeds
        res = await crawl(
            start_url=url, start_html=first.text, seeds=seeds, fetch=fetch_page, on_page=on_page,
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
        todo = [r for r in rep["records"] if r["categoria"] in STRICT_CATEGORIES][:max_hunt]
        for r in todo:
            h = await hunt_deadline(r["url"], lambda u, d: fetch_doc(u, d, settings))
            row_dl = r["scadenza_in_riga"]
            rep["hunts"].append({"url": r["url"], "deadline": str(h.deadline) if h.deadline else row_dl,
                                 "docs": len(h.docs), "reason": h.reason, "notes": [d.note for d in h.docs if d.note],
                                 "trail": h.trail(), "in_riga": bool(row_dl)})
            if analisi:  # documentation analysis on the same documents the hunt read
                fields = extract_fields([(urlsplit(d.url).path.rsplit("/", 1)[-1] or d.url, d.text) for d in h.docs if d.text], today)
                rep["analisi"].append({"url": r["url"], "documenti": len(h.docs), "campi": sorted(fields),
                                       "valori": {k: v["valore"] for k, v in fields.items()}})
        async def sfetch(u: str):
            return await _script_fetch(u, settings)
        try:
            ref = await search_referenti(ente, [url], sfetch, _fetch_press, pec=None, today=today)
            rep["referenti"] = [{"ruolo": p["ruolo"], "nome": p["nome"], "stato": p["stato"], "motivo": p.get("motivo"),
                                 "email": p.get("email"), "fonte": p["fonte_url"]} for p in ref["people"]]
            rep["checklist"] = ref["checklist"]
            rep["referenti_pagine"] = ref["urls"]
            from app.collectors.referenti_script import menu_links

            rep["menu_visti"] = [(sc, t, u) for sc, u, t, _ in sorted(menu_links(first.raw if hasattr(first, "raw") and first.raw else first.text, url), reverse=True)[:15]]
            rep["elezione"] = str(ref["elezione"] or "")
            rep["stampa"] = ref["stampa"]
        except Exception as exc:  # noqa: BLE001
            rep["referenti_errore"] = f"{type(exc).__name__}: {exc}"
        return rep

    sem = asyncio.Semaphore(max(1, concurrency))

    async def guarded(ente: str, start: str, fascia: str) -> dict:
        async with sem:
            try:
                return await one(ente, start, fascia)
            except Exception as exc:  # noqa: BLE001 - one bad site must not stop the whole test
                return {"ente": ente, "start": start, "fascia": fascia, "error": f"crash: {type(exc).__name__}: {exc}",
                        "records": [], "hunts": [], "analisi": []}

    reports: list[dict] = list(await asyncio.gather(*(guarded(*x) for x in sites)))

    from app.collectors.adaptive_fetch import FAILURES

    lim = limitations(reports, FAILURES)
    riep = riepilogo(reports, gold)
    (out / "report.json").write_text(json.dumps({"riepilogo": riep, "limitazioni": lim, "siti": reports}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md = [f"# Prova gratuita dei siti ({datetime.now(tz=UTC):%d/%m/%Y %H:%M}) — {len(reports)} comuni", "", "## Riepilogo", ""]
    t = riep["totale"]
    md += [
        f"- 1) Rilevamento: siti letti {t['letti']}/{t['siti']} ({t['letti_pct']}%), bloccati 403: {t['bloccati']}, "
        f"con avvisi: {t['siti_con_avvisi_pct']}%, avvisi totali {t['avvisi']} {t['avvisi_per_categoria']}",
        f"- 2) Scadenza (gare/manifestazioni): trovata in {t['scadenza']['trovate']}/{t['scadenza']['cercate']} ({t['scadenza']['trovate_pct']}%)",
        f"- 3) Referenti: sindaco {t['referenti']['con_sindaco_pct']}%, assessore {t['referenti']['con_assessore_pct']}%, "
        f"tecnico {t['referenti']['con_tecnico_pct']}%, checklist media {t['referenti']['checklist_media']}/12",
    ]
    if analisi:
        md.append(f"- 4) Analisi documentazione: {t['analisi']['documenti_analizzati']} avvisi; campi trovati (%): {t['analisi']['campi_trovati_pct']}")
    if "riferimento_referenti" in riep:
        rr = riep["riferimento_referenti"]
        md.append(f"- Confronto col riferimento (cognomi noti): {rr['trovati']}/{rr['attesi']} ({rr['recall_pct']}%)")
    md += ["", "| fascia | siti | letti % | avvisi/sito | scadenza % | sindaco % | assessore % | tecnico % |", "|---|---|---|---|---|---|---|---|"]
    for f, b in riep["per_fascia"].items():
        md.append(f"| {f} | {b['siti']} | {b['letti_pct']} | {round(b['avvisi'] / max(b['letti'], 1), 1)} | {b['scadenza']['trovate_pct']} | "
                  f"{b['referenti']['con_sindaco_pct']} | {b['referenti']['con_assessore_pct']} | {b['referenti']['con_tecnico_pct']} |")
    md += ["", "## Limitazioni rilevate", ""]
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
        if s.get("seeds") is not None:
            md.append(f"- punti di partenza dell'esplorazione: {len(s['seeds'])} " + (", ".join(x[-50:] for x in s["seeds"][:4])))
        if "referenti" in s:
            md.append(f"- pagine lette per i referenti: {len(s.get('referenti_pagine', []))}")
            for u in s.get("referenti_pagine", [])[:12]:
                md.append(f"    - {u}")
            md.append("- voci di menu viste dallo script (punteggio, testo):")
            for sc, t, u in s.get("menu_visti", []):
                md.append(f"    - {sc} {t[:40]} -> {u[:80]}")
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
    ap.add_argument("--campione", help="CSV prodotto da campione.py (nome;url;regione;provincia;fascia)")
    ap.add_argument("--concorrenza", type=int, default=3, help="siti provati in parallelo")
    ap.add_argument("--analisi", action="store_true", help="analizza anche la documentazione degli avvisi trovati")
    ap.add_argument("--oro", help="CSV di riferimento dei referenti (ente;cognome;ruolo)")
    a = ap.parse_args()
    sites: list[tuple[str, str, str]] = []
    for x in a.sito:
        n, u = x.split("=", 1)
        sites.append((n, u, "n/d"))
    if a.campione:
        import csv

        if not Path(a.campione).exists():
            print(f"File del campione non trovato: {a.campione}\nCrealo prima con:\n"
                  "  docker compose exec -T api python -m infra.scripts.campione --region Lombardia --n 60 "
                  f"--ipa /workspace/infra/amministrazioni.txt --out {a.campione}")
            return
        with open(a.campione, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                sites.append((r["nome"], r["url"], r.get("fascia") or "n/d"))
    gold = None
    if a.oro:
        import csv

        with open(a.oro, encoding="utf-8-sig", newline="") as f:
            gold = list(csv.DictReader(f, delimiter=";"))
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
                    sites.append((ent.name, u, "n/d"))
    if not sites:
        print("Nessun sito: usa --region/--comune oppure --sito Nome=url")
        return
    await run(sites, Path(a.out), a.max_hunt, a.concorrenza, a.analisi, gold)


if __name__ == "__main__":
    asyncio.run(main())
