from datetime import UTC, datetime
from pathlib import Path

from infra.scripts.azzera_prove import history_path, summarize


def test_summary_makes_two_rounds_comparable():
    recs = [
        {"ente": "A", "tipo_novita": "pre_gara", "verifica_esito": None},
        {"ente": "A", "tipo_novita": "gara", "verifica_esito": "aperto"},
        {"ente": "B", "atto_tipo": "manifestazione_interesse", "verifica_esito": "chiuso"},
    ]
    refs = [{"ente": "A", "ruolo": "sindaco"}, {"ente": "A", "ruolo": "assessore"}, {"ente": "B", "ruolo": "sindaco"}]
    s = summarize(recs, refs)
    assert s["avvisi"] == 3 and s["enti_con_avvisi"] == 2
    assert s["per_tipo"] == {"pre_gara": 1, "gara": 1, "manifestazione_interesse": 1}
    assert s["per_verifica"]["non verificato"] == 1
    assert s["referenti"] == 3 and s["referenti_per_ruolo"] == {"sindaco": 2, "assessore": 1} and s["enti_con_referenti"] == 2


def test_history_file_name_is_dated_and_safe():
    p = history_path("Emilia-Romagna", datetime(2026, 11, 23, 21, 5, tzinfo=UTC), Path("/x"))
    assert p == Path("/x/20261123-2105_emilia-romagna.json")
    assert history_path("Valle d'Aosta", datetime(2026, 1, 2, 3, 4, tzinfo=UTC), Path("/x")).name == "20260102-0304_valle-d-aosta.json"
