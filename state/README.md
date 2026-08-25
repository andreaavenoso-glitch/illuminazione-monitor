# state/

Directory di stato persistente della pipeline. **Aggiornata automaticamente** ad ogni run — non modificare manualmente.

| File | Contenuto |
|---|---|
| `sources.json` | Registry delle fonti attive e conteggio record per fonte all'ultimo run |
| `kpi_history.json` | Storico KPI giornalieri (ultimi 180 run), usato per i grafici trend in dashboard |
| `seen.json` | Deduplica cross-run: tiene traccia di CIG/record già visti per calcolare "novità" |
