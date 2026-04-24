# Illuminazione Pubblica Monitor

> **Nota — transizione in corso**: il prototipo Node descritto in questo README è stato **archiviato**. Il workflow giornaliero `.github/workflows/daily-run.yml` è disabilitato (`.yml.disabled`) a partire da Sprint 1 del nuovo sistema. Il nuovo stack full-stack (FastAPI + Celery + Postgres + Redis + MinIO + Next.js) vive in [`public-lighting-procurement-monitor/`](./public-lighting-procurement-monitor) ed è pensato per essere migrato in un repository separato (`git subtree split --prefix=public-lighting-procurement-monitor`). Sotto viene documentato il prototipo solo come riferimento storico.

---

Sistema automatico di monitoraggio procurement illuminazione pubblica italiana.
**Architettura token-efficiente**: connettori diretti API ufficiali + solo 2 chiamate AI Haiku per run.

---

## Setup in 5 minuti

### 1. Fork / crea il repository su GitHub

```bash
git clone https://github.com/TUO-USERNAME/illuminazione-monitor
cd illuminazione-monitor
```

### 2. Aggiungi il secret API

In GitHub → Settings → Secrets and variables → Actions → New repository secret:

```
Name:  ANTHROPIC_API_KEY
Value: sk-ant-XXXXXXXXXXXXXXXX
```

### 3. Abilita GitHub Pages

In GitHub → Settings → Pages:
- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/dashboard`

La dashboard sarà live su: `https://TUO-USERNAME.github.io/illuminazione-monitor`

### 4. Prima esecuzione manuale

In GitHub → Actions → "Pipeline Illuminazione Pubblica" → Run workflow

Il run crea automaticamente:
- `dashboard/illuminazione.json` — dataset completo
- `reports/report-YYYY-MM-DD.md` — report giornaliero

Da quel momento il cron giornaliero alle 06:00 (ora di Roma) parte automaticamente.

---

## Struttura del progetto

```
illuminazione-monitor/
├── .github/
│   └── workflows/
│       └── daily-run.yml      # GitHub Actions cron
├── scripts/
│   ├── pipeline.js            # Pipeline principale Node.js
│   └── watchlist.json         # Lista enti da monitorare
├── dashboard/
│   ├── index.html             # Dashboard statica
│   └── illuminazione.json     # Dataset (aggiornato automaticamente)
├── reports/
│   └── report-YYYY-MM-DD.md  # Report giornalieri
├── package.json
└── .env.example
```

---

## Architettura token-efficiente

| Fase | Operazione | Token AI |
|---|---|---|
| 1 — Raccolta | ANAC REST API + TED API + GURI RSS + Albo scraper | **0** |
| 2 — Elaborazione | Normalizzazione + Deduplica + Classificazione det. + Scoring | **0** |
| 3 — AI Haiku | Call #1: classifica ~20% record ambigui | ~300 |
| 3 — AI Haiku | Call #2: genera report giornaliero | ~400 |
| 4 — Output | JSON + Markdown | **0** |
| **Totale per run** | | **~700 token** |

**Risparmio vs architettura con web search**: ~87% in meno.

---

## Personalizzazione

### Aggiungere enti alla watchlist

Modifica `scripts/watchlist.json`:

```json
[
  { "ente": "Comune di X", "url": "https://www.comune.x.it/albo", "regione": "Lombardia" },
  ...
]
```

### Modificare le keyword del perimetro

In `scripts/pipeline.js`, linea ~80:

```js
const KW_IN = [
  "illuminazione pubblica",
  "relamping LED",
  // aggiungi qui
];
const KW_EX = [
  "illuminazione interna",
  // aggiungi qui
];
```

### Cambiare l'orario del run

In `.github/workflows/daily-run.yml`:

```yaml
schedule:
  - cron: '0 5 * * *'  # 05:00 UTC = 06:00 Roma CET
```

---

## Esecuzione locale

```bash
npm install
export ANTHROPIC_API_KEY=sk-ant-XXXXXXXXX
npm run run

# Modalità dev (output verbose)
npm run dev
```

---

## Output

### illuminazione.json

```json
{
  "last_updated": "2026-04-13T06:31:00Z",
  "schema_version": "4.0",
  "records": [...],
  "kpi_oggi": {
    "record_totali": 14,
    "gare_attive": 8,
    "pre_gara": 3,
    "priorita_p1": 4,
    "valore_totale_eur": 94500000,
    "ai_calls": 2,
    "token_stimati": 700
  },
  "gare_scadenza_imminente": [...],
  "per_stato": { "GARA PUBBLICATA": 8, "PRE-GARA": 3, ... },
  "per_regione": { "Lombardia": 4, "Lazio": 3, ... }
}
```

### report-YYYY-MM-DD.md

Report Markdown strutturato con sezioni A/B/C e cruscotto finale, generato da Claude Haiku.

---

## Costi stimati

Con abbonamento Claude Pro (uso API separato):

| Voce | Costo |
|---|---|
| ~700 token/run × 30 run/mese = 21.000 token | ~$0.02/mese |
| GitHub Actions (public repo) | Gratis |
| GitHub Pages | Gratis |
| **Totale infrastruttura** | **~$0.02/mese** |

---

## Troubleshooting

**Il run fallisce con "ANTHROPIC_API_KEY mancante"**
→ Verifica che il secret sia configurato in GitHub → Settings → Secrets

**JSON non aggiornato dopo il run**
→ Controlla che GitHub Actions abbia i permessi `contents: write` (già configurato nel workflow)

**ANAC API restituisce errore CORS**
→ Normale in browser locale. Nel pipeline Node.js le chiamate funzionano correttamente.

**La dashboard mostra "Errore caricamento"**
→ Esegui almeno un run manuale prima per creare `illuminazione.json`
