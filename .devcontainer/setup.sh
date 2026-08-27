#!/usr/bin/env bash
# Avvio automatico dell'app dentro un Codespace: build dei container, attesa
# che l'API sia pronta (alembic upgrade head gira dentro al comando di avvio
# del servizio "api" in docker-compose.yml, non qui), poi seed di watchlist e
# utente amministratore.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

set_env() {
  local key="$1" value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s#^${key}=.*#${key}=${value}#" .env
  else
    echo "${key}=${value}" >> .env
  fi
}

# ANTHROPIC_API_KEY ha nessun valore utilizzabile in .env.example (ci arriva
# vuoto -- ogni altra chiave li' ha un default di sviluppo gia' funzionante).
# Senza, ogni collector basato su IA (la scansione della watchlist e quasi
# tutti i portali e-procurement) restituisce silenziosamente 0 risultati pur
# segnalando "completato" -- confermato in produzione: il pannello di
# raccolta manuale mostrava "110 comuni scansionati, 0 validi" senza nessun
# errore visibile. Salva quello che l'utente ha eventualmente scritto a mano
# in .env prima che la sovrascrittura incondizionata qui sotto lo cancelli a
# ogni riesecuzione di questo script (rebuild del Codespace, o riavvio
# manuale dopo un git pull).
existing_anthropic_key=""
if [ -f .env ]; then
  existing_anthropic_key="$(grep '^ANTHROPIC_API_KEY=' .env | cut -d= -f2- || true)"
fi

# Sovrascrive sempre .env da .env.example: questo e' un ambiente di prova
# usa-e-getta, non un deploy persistente, e rieseguire questo script (es.
# dopo un git pull, o riavviando manualmente) deve poter correggere un .env
# rimasto con valori vecchi da un avvio precedente dello stesso Codespace.
cp .env.example .env

if [ -n "$existing_anthropic_key" ]; then
  set_env "ANTHROPIC_API_KEY" "$existing_anthropic_key"
fi

# In un Codespace il browser dell'utente NON e' dentro il container: le
# variabili che puntano ad "http://localhost:*" nel file .env.example sono
# pensate per l'uso in locale e vanno riscritte con gli indirizzi pubblici
# che GitHub assegna alle porte inoltrate (<nome-codespace>-<porta>.<dominio>),
# altrimenti il sito web prova a contattare il PC dell'utente e fallisce con
# "Failed to fetch". CODESPACE_NAME e GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN
# sono variabili d'ambiente che GitHub imposta automaticamente in ogni Codespace.
if [ -n "${CODESPACE_NAME:-}" ]; then
  domain="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  api_url="https://${CODESPACE_NAME}-8000.${domain}"
  web_url="https://${CODESPACE_NAME}-3000.${domain}"

  set_env "NEXT_PUBLIC_API_URL" "$api_url"
  set_env "CORS_ORIGINS" "$web_url"
fi

# docker-compose.yml monta /app/.next del servizio "web" come volume anonimo
# (serve a non far sparire la build di Next dietro al bind-mount del codice
# sorgente) — ma un volume anonimo sopravvive anche a un container ricreato
# da zero. Se NEXT_PUBLIC_API_URL cambia (es. rieseguendo questo script), la
# pagina di login continuerebbe a servire il bundle JS gia' compilato con il
# vecchio indirizzo finche' quella cache non viene buttata via esplicitamente.
docker compose rm -f -s -v web >/dev/null 2>&1 || true

echo "==> Costruzione e avvio dei servizi (puo' richiedere qualche minuto la prima volta)..."
# --force-recreate: se questo script viene rieseguito su container gia'
# esistenti (es. dopo un git pull nello stesso Codespace), forza la
# ricreazione così i container ripartono leggendo il nuovo .env invece di
# restare in piedi con le variabili d'ambiente della volta precedente.
docker compose up -d --build --force-recreate

echo "==> Attendo che l'API sia pronta..."
ready=""
for _ in $(seq 1 90); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    ready="1"
    break
  fi
  sleep 5
done

if [ -z "$ready" ]; then
  echo "L'API non ha risposto in tempo. Controlla i log con: docker compose logs api"
  exit 1
fi

echo "==> API pronta. Carico la watchlist (73 comuni lombardi + enti nazionali)..."
docker compose exec -T api python -m infra.scripts.seed_watchlist

echo "==> Creo l'utente amministratore..."
docker compose exec -T api python -m infra.scripts.seed_admin

# shellcheck disable=SC1091
admin_email="$(grep '^BOOTSTRAP_ADMIN_EMAIL=' .env | cut -d= -f2-)"
admin_password="$(grep '^BOOTSTRAP_ADMIN_PASSWORD=' .env | cut -d= -f2-)"

cat <<EOF

======================================================================
 Tutto pronto!
 Apri la scheda "PORTS" in basso nell'editor, trova la riga con la
 porta 3000 ("Dashboard — apri questa") e clicca sull'icona del
 mondo/globo per aprirla nel browser.

 Accedi con:
   email:    ${admin_email}
   password: ${admin_password}
 (credenziali di prova valide solo dentro questo Codespace temporaneo)
======================================================================
EOF

if ! grep -q '^ANTHROPIC_API_KEY=.\+' .env; then
  cat <<EOF

======================================================================
 ATTENZIONE: manca ANTHROPIC_API_KEY in .env.
 Senza questa chiave, la scansione dei comuni in watchlist e quasi
 tutti i portali e-procurement NON raccolgono nulla (0 risultati),
 pur segnalando "completato" -- nessun errore visibile.
 Prendine una su https://console.anthropic.com/settings/keys, poi
 aggiungi la riga "ANTHROPIC_API_KEY=sk-ant-..." in fondo a .env e
 riavvia i container con: docker compose up -d --force-recreate worker api
======================================================================
EOF
fi
