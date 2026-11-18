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

## Prova rapida senza installare nulla (GitHub Codespaces)

Non serve Docker né essere amministratore del proprio PC: dalla pagina del
repository su github.com, bottone verde **Code → Codespaces → Create
codespace on main**. Il Codespace costruisce ed avvia da solo tutti i
servizi e carica la watchlist (vedi `.devcontainer/`); ci vogliono alcuni
minuti la prima volta. Quando è pronto, apri la scheda **PORTS** in basso e
clicca sull'icona del mondo sulla riga della porta 3000 per aprire la
dashboard nel browser. Pensato per una prova temporanea (rientra nel piano
gratuito di GitHub Codespaces per uso limitato), non per l'uso in produzione
continuativo — per quello vedi l'avvio locale/server qui sotto.

## Avvio locale

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m infra.scripts.seed_watchlist
docker compose exec api python -m infra.scripts.seed_regions
```

Il seed carica anche la watchlist di 73 comuni lombardi target per l'illuminazione
pubblica da `infra/scripts/data/comuni_lombardia_illuminazione.csv` — per
aggiungerne o modificarne, basta editare quel CSV e rilanciare il seed (è
idempotente: le entità già presenti non vengono duplicate). Tutti e 73 hanno
un `url_albo`/`url_trasparenza` valorizzato e vengono scansionati da subito; per
29 di essi l'URL è stato reperito via ricerca web (non tramite apertura diretta
della pagina) e va quindi considerato da verificare — è segnalato nel campo
`note` del CSV e nelle note dell'entità in `/admin/watchlist`. Per correggere
un URL sbagliato: `PATCH /watchlist/{id}` (endpoint API, non ancora esposto
come form nella dashboard — vedi `/admin/watchlist` per la sola consultazione).

### Struttura per regioni

- **Livello 1** (`/level1`): portali nazionali (TED, ANAC, GURI...), solo analisi e verifica delle fonti. Consip è fuori.
  I record trovati vengono assegnati a una regione (regione esplicita, codice NUTS di TED, ente già in watchlist,
  regione citata nel testo) e compaiono nel suo riquadro.
- **Livello 2** (`/regions`): un riquadro per regione con pre-gare, manifestazioni di interesse e gare, e la vista
  dei siti (siti regionali del catalogo + comuni con tutti i loro indirizzi e lo stato di raggiungibilità).
  Solo le regioni *attive* vengono raccolte e notificate (di partenza: Lombardia e Puglia, modificabile dalla UI o con
  `ENABLED_REGIONS` al seed).
- **Email ai referenti**: a fine pipeline giornaliera, una mail per regione con le novità non ancora notificate.
  Destinatari modificabili per regione; servono le variabili `SMTP_*` (vedi `.env.example`): senza server di posta
  nulla parte e i record restano in attesa.
- **Comuni di una regione**: `python -m infra.scripts.import_ipa --region Puglia --file amministrazioni.csv`
  (dataset "Amministrazioni" di IPA, indicepa.gov.it; accetta xlsx, txt con tabulazione e csv) importa i comuni con il link a Amministrazione Trasparente.
- **Lettura dei siti dei comuni:** prima un filtro fisso (`app/collectors/page_gate.py`): una pagina senza parole
  chiave di illuminazione o PPP non arriva mai a Claude; per le altre va solo l'elenco dei link che corrispondono;
  una pagina invariata dall'ultima analisi riuscita non viene riletta. Le sezioni di Amministrazione Trasparente si
  trovano prima per nome (D.Lgs. 33/2013) e solo se manca si chiede a Claude. I contatori (pagine saltate,
  invariate, inviate a Claude, piattaforme rilevate) sono nel risultato del task e nel log
  (`docker compose logs worker | grep collect_watchlist.stats`).
- **Siti regionali scoperti in automatico:** quando la visita di un comune porta a una piattaforma di gara esterna
  (provinciale, regionale o di un fornitore, per esempio il PortaleAppalti di una Provincia), il sito viene salvato tra
  i siti della regione del comune, **spento e da approvare**, con l'elenco dei comuni che vi rimandano. Dalla pagina
  della regione, tab "Siti", un amministratore lo attiva o lo disattiva.
- **Servizi cercati:** non solo l'illuminazione pubblica. Il catalogo (`packages/shared_models/shared_models/services.py`,
  ricavato dalle schede dei servizi A2A Illuminazione Pubblica) ha 11 servizi, ciascuno con le sue parole chiave:
  illuminazione pubblica, artistica, piste ciclabili e passaggi pedonali, semafori, videosorveglianza, relamping ed
  efficientamento di edifici e scuole, fotovoltaico e comunità energetiche, ricarica EV, 5G, digital advertising,
  smart city. Si attivano con `ENABLED_SERVICES` (vuoto = tutti). Il filtro delle pagine, le istruzioni a Claude e il
  controllo di pertinenza usano i servizi attivi; ogni avviso riporta i servizi di cui parla.
- **Vista dell'avanzamento** (pagina della regione, tab "Raccolta"): barra di avanzamento con ora di fine stimata, una
  linea del tempo con una barra per comune (da quando inizia a quando finisce la lettura), il segnale di Claude per
  comune (chiamato N volte, non chiamato, errore) e un avviso rosso se l'API di Claude non è disponibile. Si aggiorna
  ogni 3 secondi mentre la raccolta gira. I dati sono in `scan_runs` e `scan_items`.
- I siti regionali del catalogo sono in `infra/scripts/data/siti_regionali.json` (candidati da verificare).

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
- `/admin/watchlist` — 38 enti nazionali + 73 comuni lombardi (illuminazione pubblica) + 15 sources

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
