# Public Lighting Procurement Monitor

Full-stack monitor per il procurement dell'illuminazione pubblica italiana.

## Architettura (modular monolith)

```
apps/
  api/          FastAPI + SQLAlchemy (async) + Alembic
  worker/       Celery + beat, collector TED/ANAC/GURI
  web/          Next.js 14 (App Router) + Tailwind + react-query
packages/
  parsing_rules/        keywords, regex CIG/CUP/CPV, date, importo, perimeter
  scoring_engine/       scoring commerciale (Sprint 6)
  sector_dictionaries/  tag tecnici (LED, telegestione, …)
  shared_models/        SQLAlchemy Base + 10 tabelle condivise tra api e worker
  shared_schemas/       pydantic di interscambio
infra/
  docker/       Dockerfile api/worker/web
  scripts/      seed_watchlist.py
```

## Avvio locale

```bash
cp .env.example .env
docker-compose up -d --build
docker-compose exec api alembic upgrade head
docker-compose exec api python -m infra.scripts.seed_watchlist
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

## Smoke test Sprint 1-3

```bash
# health
curl -s http://localhost:8000/health | jq

# CRUD base
curl -s http://localhost:8000/sources | jq 'length'     # ≥ 15
curl -s http://localhost:8000/watchlist | jq 'length'   # ≥ 38
curl -s http://localhost:8000/entities | jq 'length'    # ≥ 37

# lancio collector
curl -X POST http://localhost:8000/admin/run-daily-monitor
docker-compose logs -f worker   # guardare TED/ANAC/GURI

# job_runs
docker-compose exec db psql -U postgres -d lighting_monitor -c \
  "SELECT job_name, status, records_found, records_valid FROM job_runs ORDER BY started_at DESC LIMIT 10;"

# unit test
docker-compose exec api pytest /packages/../tests/unit -v
```

## Migrazione verso il nuovo repo

Questo monorepo è stato scaffoldato dentro `illuminazione-monitor/public-lighting-procurement-monitor/` per comodità. Per estrarlo:

```bash
git subtree split --prefix=public-lighting-procurement-monitor -b monorepo-export
# poi: crea nuovo repo su GitHub e push del branch monorepo-export
```

Oppure `cp -r public-lighting-procurement-monitor /tmp/new && cd /tmp/new && git init`.

## Legacy disabilitato

Il vecchio pipeline Node (`scripts/pipeline.js`) e il workflow `.github/workflows/daily-run.yml` del repo padre sono stati messi in pausa (file rinominato in `.disabled`). Il nuovo cron viene gestito da Celery beat nel servizio `worker` (default 05:00 UTC, fuso `Europe/Rome`).

## Roadmap

Vedi `/root/.claude/plans/piano-tecnico-operativo-1-toasty-gadget.md` per sprint 4-10.
