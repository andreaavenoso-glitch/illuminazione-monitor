"""History of the collection runs and their comparison (depth, pages, records, cost).

Pure functions over ScanRun / ScanItem rows (anything with the same attributes), tested without a database.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


def run_summary(run: Any, items: list[Any], cost: float | None) -> dict:
    done = [i for i in items if i.status in ("done", "error")]
    read = [i for i in items if (i.pages_read or 0) > 0]
    deepest = [i.deepest or 0 for i in read]
    end = run.ended_at or run.heartbeat_at
    return {
        "id": str(run.id),
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "status": run.status,
        "durata_s": max(0.0, (end - run.started_at).total_seconds()) if end and run.started_at else None,
        "comuni": len(items),
        "comuni_letti": len(done),
        "errori": sum(1 for i in items if i.status == "error"),
        "pagine": sum(i.pages_read or 0 for i in items),
        "pagine_saltate": sum(i.pages_skipped or 0 for i in items),
        "profondita_max": max(deepest, default=0),
        "profondita_media": round(sum(deepest) / len(deepest), 2) if deepest else 0.0,
        "record_trovati": sum(i.records_found or 0 for i in items),
        "chiamate_claude": sum(i.claude_calls or 0 for i in items),
        "costo_usd": round(float(cost or 0), 4),
        "config": run.config or {},
        "istogramma_profondita": dict(sorted(Counter(deepest).items())),
        "fermate_per": dict(Counter(i.stopped_by for i in read if i.stopped_by)),
    }


def _row(i: Any | None) -> dict | None:
    if i is None:
        return None
    return {
        "pagine": i.pages_read or 0, "profondita": i.deepest or 0, "record": i.records_found or 0,
        "claude": i.claude_calls or 0, "stato": i.status, "fermata_per": i.stopped_by, "errore": i.error,
    }


def compare_runs(items_a: list[Any], items_b: list[Any]) -> dict:
    """Per comune, run A against run B, with the differences (B - A); comuni present in one run only are
    listed too. ``totali`` sums the comuni present in BOTH, so the comparison is like for like."""
    a = {i.ente: i for i in items_a}
    b = {i.ente: i for i in items_b}
    rows = []
    tot = {"pagine": [0, 0], "record": [0, 0], "profondita_somma": [0, 0], "comuni": 0}
    for ente in sorted(set(a) | set(b)):
        ra, rb = _row(a.get(ente)), _row(b.get(ente))
        diff = None
        if ra and rb:
            diff = {k: rb[k] - ra[k] for k in ("pagine", "profondita", "record")}
            tot["comuni"] += 1
            tot["pagine"][0] += ra["pagine"]
            tot["pagine"][1] += rb["pagine"]
            tot["record"][0] += ra["record"]
            tot["record"][1] += rb["record"]
            tot["profondita_somma"][0] += ra["profondita"]
            tot["profondita_somma"][1] += rb["profondita"]
        rows.append({"ente": ente, "a": ra, "b": rb, "diff": diff})
    n = tot["comuni"] or 1
    return {
        "righe": rows,
        "totali": {
            "comuni_in_comune": tot["comuni"],
            "pagine": tot["pagine"], "record": tot["record"],
            "profondita_media": [round(tot["profondita_somma"][0] / n, 2), round(tot["profondita_somma"][1] / n, 2)],
        },
        "solo_a": sum(1 for r in rows if r["a"] and not r["b"]),
        "solo_b": sum(1 for r in rows if r["b"] and not r["a"]),
        "migliorati": sum(1 for r in rows if r["diff"] and (r["diff"]["record"] > 0 or r["diff"]["profondita"] > 0)),
    }


def describe_config_diff(a: dict, b: dict) -> list[str]:
    """What changed between the settings of two runs, in words."""
    out = []
    for k, label in (
        ("crawl_max_pages", "pagine massime"), ("crawl_max_depth", "profondità massima"),
        ("crawl_time_budget_s", "tempo di esplorazione (s)"), ("extraction_mode", "estrazione"), ("tipo", "tipo di raccolta"),
    ):
        if a.get(k) != b.get(k):
            out.append(f"{label}: {a.get(k, 'n/d')} → {b.get(k, 'n/d')}")
    return out

