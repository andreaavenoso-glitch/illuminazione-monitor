# Public Lighting Procurement Monitor

Full-stack monitor per il procurement dell'illuminazione pubblica italiana.
Acquisisce ogni giorno da fonti ufficiali (ANAC, TED, GURI) e portali
e-procurement (ASMECOMM, Traspare, Tuttogare, SATER, START Toscana, …),
normalizza, deduplica, classifica, genera report e alimenta una dashboard
con alert e anomalie.

## Architettura (modular monolith)

```
apps/
  api/          FastAPI + SQLAlchemy (async) + Alembic
  worker/       Celery + beat, collector TED/ANAC/GURI + eproc portals
  web/          Next.js 14 (App Router) + Tailwind + react-query
packages/
  parsing_rules/        keywords, regex CIG/CUP/CPV, date, importo, perimeter
  scoring_engine/       scoring commerciale (§10)
  sector_dictionaries/  tag tecnici (LED, telegestione, smart lighting, …)
  shared_models/        SQLAlchemy Base + 10 tabelle condivise api ↔ worker
  shared_schemas/       pydantic di interscambio
infra/
  docker/       Dockerfile api/worker/web
  scripts/      seed_watchlist.py
tests/          unit + integration
```

## Avvio locale

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m infra.scripts.seed_watchlist
```

Endpoint:

| Servizio | URL |
| --- | --- |
| API | http://localhost:8000 |
| Docs OpenAPI | http://localhost:8000/docs |
| Web | http://localhost:3000 |
| MinIO console | http://localhost:9001 |
| Postgres | localhost:5432 |
| Redis | localhost:6379 |

## Pipeline giornaliera (Celery beat, fuso Europe/Rome)

```
05:00  collect_official_sources       (TED, ANAC, GURI)
05:30  collect_eproc_portals          (ASMECOMM, Traspare, Tuttogare, SATER, START Toscana)
06:00  normalize_records              (raw → procurement_records)
06:30  score_and_dedupe               (scoring + dedup master/duplicati)
07:00  generate_daily_report          (JSON + Markdown in daily_reports)
07:30  detect_anomalies               (proroghe, revoche, ricorsi, stallo)
```

## Smoke test

```bash
# health
curl -s http://localhost:8000/health | jq

# CRUD base
curl -s http://localhost:8000/sources | jq 'length'
curl -s http://localhost:8000/watchlist | jq 'length'

# trigger manuali
curl -X POST http://localhost:8000/admin/run-daily-monitor
curl -X POST http://localhost:8000/admin/normalize-records
curl -X POST http://localhost:8000/admin/score-and-dedupe
curl -X POST http://localhost:8000/admin/rebuild-report/$(date +%Y-%m-%d)
curl -X POST http://localhost:8000/admin/detect-anomalies
curl -X POST "http://localhost:8000/admin/run-backfill?days=7"

# unit test (121 test)
pytest tests/unit -v
```

## Export

```
GET /records/export/xlsx?priorita=P1
GET /records/export/csv?regione=Toscana
GET /records/export/json?only_masters=true
```

## Dashboard frontend

- `/` — KPI live + top P1 + breakdown per regione/stato
- `/records` — tabella filtrata (regione, stato, priorità, flag, importo, …)
- `/records/[id]` — scheda completa
- `/reports` — report giornaliero
- `/alerts` — anomalie aperte con close action
- `/weak-evidence` — record §9.1 falliti
- `/admin/watchlist` — 38 enti + 15 sources

## Schema DB

10 tabelle (spec §5) + `job_runs` + indici: `sources`, `entities`,
`watchlist_items`, `raw_records`, `procurement_records`, `record_events`,
`alerts`, `documents`, `daily_reports`, `job_runs`. 3 migration Alembic
(`0001_baseline`, `0002_core_tables`, `0003_scoring_columns`).

## Roadmap completata

Sprint 1-10 del piano originale (vedi `/root/.claude/plans/…`):
fondazione tecnica, modello dati, collector ufficiali, collector fascia A,
normalizzazione, scoring/dedup, daily report, dashboard, export/documents,
anomaly engine + backfill. 121 unit test green, ruff clean.
