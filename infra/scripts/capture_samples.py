"""Dry run of the comuni scan, with NO Claude calls: fetch, gate, follow menus,
and save what was seen. Used to tune the fixed part of the reader (page gate,
section names, crawl depth) against real pages at zero API cost.

Run inside the worker container (it has the fetcher and Playwright):

    docker compose exec worker python -m infra.scripts.capture_samples \
        --region Puglia --limit 20 --out /workspace/infra/samples/puglia

One comune only (why did it produce nothing?):

    docker compose exec worker python -m infra.scripts.capture_samples \
        --region Lombardia --comune Arluno --out /workspace/infra/samples/arluno

Writes one .html per fetched page plus report.json and report.md. The pages
are public web pages; nothing from the database other than the comune name and
its URLs is written.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from pathlib import Path


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "x"


def summarize(reports: list[dict]) -> dict:
    """Aggregate numbers over the per-comune reports (pure, tested)."""
    s: Counter = Counter()
    templates: Counter = Counter()
    errors: Counter = Counter()
    for r in reports:
        s["comuni"] += 1
        if r.get("error"):
            s["unreachable"] += 1
            errors[r["error"]] += 1
            continue
        s["reachable"] += 1
        templates[r.get("template", "other")] += 1
        s[f"links_{r.get('links_source', 'none')}"] += 1
        pages = r.get("pages", [])
        s["pages"] += len(pages)
        s[f"stopped_by_{r.get('stopped_by', 'none')}"] += 1
        s["deepest_max"] = max(s["deepest_max"], r.get("deepest", 0))
        if any(p["gate"] != "skip" for p in pages):
            s["comuni_with_a_gated_page"] += 1
        if not pages:
            s["comuni_with_no_extra_page"] += 1
        for p in pages:
            s[f"gate_{p['gate']}"] += 1
    return {"counts": dict(s), "templates": dict(templates), "errors": dict(errors)}


async def run(region: str, limit: int, out: Path, concurrency: int = 3, comune: str | None = None) -> None:
    from app.collectors.adaptive_fetch import adaptive_fetch_result
    from app.collectors.albo_pretorio_llm import find_bandi_link
    from app.collectors.crawler import crawl
    from app.collectors.page_gate import (
        detect_template,
        discovered_platforms,
        gate_page,
        pick_section_links,
        same_site,
    )
    from app.collectors.sitemap import discover_sitemap_urls
    from app.config import get_worker_settings
    from app.db import SessionLocal
    from app.tasks.collect_watchlist import MAX_EXTRA_PAGES, select_sample
    from shared_models import Entity, WatchlistItem
    from shared_models.regions import normalize_region
    from sqlalchemy import or_, select

    settings = get_worker_settings()
    from shared_models.services import configure as configure_services
    from shared_models.services import parse_enabled

    configure_services(parse_enabled(settings.enabled_services))
    out.mkdir(parents=True, exist_ok=True)
    canonical = normalize_region(region)

    async def fetch(url: str, label: str, timeout: float = 60.0, variants: bool = True):
        return await adaptive_fetch_result(
            url, timeout=timeout, try_variants=variants, max_html_chars=settings.crawl_max_html_chars,
            playwright_min_chars=settings.smart_collector_playwright_min_chars,
            playwright_wait_ms=settings.smart_collector_playwright_wait_ms, label=label,
        )

    async with SessionLocal() as session:
        rows = (await session.execute(
            select(WatchlistItem, Entity)
            .join(Entity, WatchlistItem.entity_id == Entity.id)
            .where(WatchlistItem.active.is_(True),
                   or_(WatchlistItem.url_albo.is_not(None), WatchlistItem.url_trasparenza.is_not(None)))
        )).all()
    pairs = [(i, e) for i, e in rows if normalize_region(e.region) == canonical]
    if comune:  # one comune by name (substring, any case): diagnose why it produced nothing
        pairs = [(i, e) for i, e in pairs if comune.lower() in e.name.lower()]
        limit = max(1, len(pairs))
    sample = select_sample([i for i, _ in pairs], limit)
    by_id = {i.id: e for i, e in pairs}

    reports: list[dict] = []
    async def one(n: int, item) -> dict:
        ente = by_id[item.id].name
        start = item.url_trasparenza or item.url_albo
        base = f"{n:02d}-{slug(ente)}"
        print(f"[{n}/{len(sample)}] {ente}  {start}", flush=True)
        rep: dict = {"ente": ente, "start_url": start, "pages": []}
        first = await fetch(start, base)
        if not first.text:
            rep["error"] = first.error or "empty"
            return rep
        rep["final_url"] = first.url or start
        rep["template"] = detect_template(first.text)
        (out / f"{base}__00_start.html").write_text(first.text, encoding="utf-8")
        url = first.url or start

        sitemap = await discover_sitemap_urls(url)
        if sitemap:
            pages, rep["links_source"] = sitemap[:MAX_EXTRA_PAGES], "sitemap"
        else:
            labelled = [u for u in dict.fromkeys(
                [find_bandi_link(first.text, base_url=url),
                 *pick_section_links(first.text, base_url=url, limit=MAX_EXTRA_PAGES)]) if u and u != url]
            pages, rep["links_source"] = labelled[:MAX_EXTRA_PAGES], ("labels" if labelled else "none_would_ask_claude")

        pages_seen: list[dict] = []

        async def on_page(purl: str, html: str, depth: int, _base=base, pages_seen=pages_seen):
            g = gate_page(html, base_url=purl)
            pages_seen.append({
                "url": purl, "depth": depth, "chars": len(html), "gate": g.action,
                "template": g.template, "candidates": [c.title for c in g.candidates[:5]],
            })
            (out / f"{_base}__{len(pages_seen):02d}_d{depth}.html").write_text(html, encoding="utf-8")
            return g

        async def fetch_page(purl: str, _base=base, _start=url):
            own = same_site(purl, _start)
            return await fetch(purl, _base, timeout=60.0 if own else settings.crawl_external_timeout_s, variants=False)

        result = await crawl(
            start_url=url, start_html=first.text, seeds=pages, fetch=fetch_page, on_page=on_page,
            max_pages=settings.crawl_max_pages, max_depth=settings.crawl_max_depth,
            time_budget_s=settings.crawl_time_budget_s, delay_s=settings.crawl_delay_s,
        )
        rep["pages"] = pages_seen
        rep["unreadable"] = [{"url": v.url, "error": v.error} for v in result.visits if v.action == "unreadable"]
        rep["stopped_by"] = result.stopped_by
        rep["platforms_found"] = discovered_platforms([v.url for v in result.visits], url)
        rep["deepest"] = max(v.depth for v in result.visits)
        return rep

    sem = asyncio.Semaphore(max(1, concurrency))

    async def guarded(n: int, item) -> dict:
        async with sem:
            try:
                return await one(n, item)
            except Exception as exc:  # noqa: BLE001  one bad site must not stop the dry run
                print(f"   ERRORE su {by_id[item.id].name}: {type(exc).__name__}: {exc}", flush=True)
                return {"ente": by_id[item.id].name, "error": f"crash: {type(exc).__name__}", "pages": []}

    reports = list(await asyncio.gather(*(guarded(n, i) for n, i in enumerate(sample, 1))))

    platforms: Counter = Counter()
    for r in reports:
        for host in r.get("platforms_found", {}):
            platforms[host] += 1
    summary = summarize(reports)
    summary["platforms_found"] = dict(platforms.most_common())
    (out / "report.json").write_text(json.dumps({"summary": summary, "comuni": reports}, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# Dry run scansione comuni (senza Claude)", "", f"Regione: {canonical}, comuni: {len(reports)}", "",
             "```", json.dumps(summary, ensure_ascii=False, indent=1), "```", ""]
    for r in reports:
        lines.append(
            f"- **{r['ente']}** — {r.get('error') or r.get('template')} — pagine: {len(r['pages'])} — "
            f"profondita max: {r.get('deepest', '-')} — stop: {r.get('stopped_by', '-')} — link: {r.get('links_source', '-')}"
        )
        for p in r["pages"]:
            lines.append(f"    - d{p['depth']} {p['gate']} {p['url']} {p.get('candidates', '')}")
        for host, purl in r.get("platforms_found", {}).items():
            lines.append(f"    - PIATTAFORMA ESTERNA {host} {purl}")
        for u in r.get("unreadable", []):
            lines.append(f"    - ILLEGGIBILE {u['error']} {u['url']}")
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\nSalvato in {out} (report.md, report.json e le pagine .html)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", required=True)
    ap.add_argument("--concurrency", type=int, default=3, help="comuni letti in parallelo")
    ap.add_argument("--comune", help="solo il comune che contiene questo nome (es. Arluno)")
    a = ap.parse_args()
    asyncio.run(run(a.region, a.limit, Path(a.out), a.concurrency, a.comune))


if __name__ == "__main__":
    main()
