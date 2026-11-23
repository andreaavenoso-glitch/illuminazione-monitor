"""Storico delle raccolte e confronto tra due raccolte (profondita', pagine, record)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS

from app.services.scan_history import compare_runs, describe_config_diff, run_summary

T0 = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)


def item(ente, pages, deepest, records, status="done", stopped=None, claude=1):
    return NS(ente=ente, pages_read=pages, pages_skipped=0, deepest=deepest, records_found=records, claude_calls=claude,
              status=status, stopped_by=stopped, error=None)


def test_run_summary_metrics():
    run = NS(id="r1", started_at=T0, ended_at=T0 + timedelta(minutes=10), heartbeat_at=None, status="done",
             config={"crawl_max_depth": 5})
    items = [item("A", 20, 3, 2, stopped="exhausted"), item("B", 8, 2, 0), item("C", 0, 0, 0, status="error")]
    s = run_summary(run, items, 0.1234)
    assert s["comuni"] == 3 and s["comuni_letti"] == 3 and s["errori"] == 1
    assert s["pagine"] == 28 and s["profondita_max"] == 3 and s["profondita_media"] == 2.5
    assert s["record_trovati"] == 2 and s["costo_usd"] == 0.1234 and s["durata_s"] == 600
    assert s["istogramma_profondita"] == {2: 1, 3: 1} and s["fermate_per"] == {"exhausted": 1}


def test_compare_runs_like_for_like():
    a = [item("A", 20, 3, 0), item("B", 8, 2, 1), item("OnlyA", 5, 1, 0)]
    b = [item("A", 40, 6, 3), item("B", 8, 2, 1), item("OnlyB", 9, 2, 1)]
    c = compare_runs(a, b)
    rows = {r["ente"]: r for r in c["righe"]}
    assert rows["A"]["diff"] == {"pagine": 20, "profondita": 3, "record": 3}
    assert rows["B"]["diff"] == {"pagine": 0, "profondita": 0, "record": 0}
    assert rows["OnlyA"]["b"] is None and rows["OnlyB"]["a"] is None and rows["OnlyA"]["diff"] is None
    assert c["solo_a"] == 1 and c["solo_b"] == 1 and c["migliorati"] == 1
    t = c["totali"]
    assert t["comuni_in_comune"] == 2 and t["pagine"] == [28, 48] and t["record"] == [1, 4]  # only comuni in both
    assert t["profondita_media"] == [2.5, 4.0]


def test_config_diff_in_words():
    d = describe_config_diff(
        {"crawl_max_pages": 20, "crawl_max_depth": 5, "extraction_mode": "auto"},
        {"crawl_max_pages": 40, "crawl_max_depth": 6, "extraction_mode": "auto"},
    )
    assert d == ["pagine massime: 20 → 40", "profondità massima: 5 → 6"]
    assert describe_config_diff({}, {}) == []
