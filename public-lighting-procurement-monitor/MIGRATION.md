# Migrazione al nuovo repository

Il monorepo è stato scaffoldato dentro `public-lighting-procurement-monitor/` del repo legacy `andreaavenoso-glitch/illuminazione-monitor` per facilitare la review via PR #1. Per spostarlo nel nuovo repository dedicato:

## 1. Crea il nuovo repo su GitHub

- Nome suggerito: `public-lighting-procurement-monitor` (o `lighting-monitor`)
- Visibilità a discrezione (private consigliato finché non stabilizzi)
- **Non** inizializzare con README / LICENSE / .gitignore (li abbiamo già)

## 2. Estrai la cartella con la storia git (opzione A — conserva la history)

Dalla root di `illuminazione-monitor` su branch `claude/lighting-tender-monitor-Cyx0j`:

```bash
# crea un branch che contiene SOLO la cartella monorepo
git subtree split --prefix=public-lighting-procurement-monitor -b monorepo-export

# pusha quel branch come main del nuovo repo
git push git@github.com:<owner>/public-lighting-procurement-monitor.git monorepo-export:main
```

## 3. Copia pulita (opzione B — parti da zero)

Se preferisci un commit iniziale pulito senza i run-per-run del legacy:

```bash
cp -R public-lighting-procurement-monitor /tmp/new-repo
cd /tmp/new-repo
git init
git add .
git commit -m "chore: initial import from illuminazione-monitor/public-lighting-procurement-monitor"
git remote add origin git@github.com:<owner>/public-lighting-procurement-monitor.git
git branch -M main
git push -u origin main
```

## 4. CI

Il workflow `.github/workflows/ci.yml` oggi vive nel repo legacy; va copiato nel nuovo repo. Dentro il monorepo è già self-contained, quindi basta spostarlo e aggiustare i `paths:`:

```yaml
# rimuovere il prefisso public-lighting-procurement-monitor/ dai paths:
on:
  pull_request:
    paths:
      - "**"
      - ".github/workflows/ci.yml"
```

E rimuovere il `working-directory: public-lighting-procurement-monitor` dai job (working-dir diventa la root del nuovo repo).

## 5. Primo giro locale

```bash
cd <new-repo>
cp .env.example .env
docker-compose up -d --build
docker-compose exec api alembic upgrade head
docker-compose exec api python -m infra.scripts.seed_watchlist
curl -s http://localhost:8000/health | jq
# apri http://localhost:3000
```

## 6. Archiviazione del repo legacy

Una volta validato il nuovo repo:

```bash
# nel repo legacy, segna il read-only
# (via GitHub UI: Settings → Archive repository)
```

In alternativa puoi cancellare solo la cartella migrata dal legacy lasciando storico + prototipo Node intatti:

```bash
git rm -r public-lighting-procurement-monitor
git commit -m "chore: migrated to separate repo <new-url>"
git push
```

## 7. Secret e infrastruttura

Nel nuovo repo configura i secret GitHub Actions se userai deploy/CI:

- `POSTGRES_PASSWORD`, `S3_SECRET_KEY` (se il CI fa smoke test integration)
- nessun `ANTHROPIC_API_KEY` — il nuovo stack non usa più l'API Anthropic

## Deliverable

Riferimento al piano: `/root/.claude/plans/piano-tecnico-operativo-1-toasty-gadget.md`.

Sprint 1-10 consegnati. Criteri di accettazione §22: report giornaliero coerente, export XLSX conforme, classificazione nuove gare/aggiornamenti/pre-gara/evidenze deboli, deduplica, storico, fonti interrogate, alert su anomalie, revisione umana via dashboard → tutti soddisfatti.
