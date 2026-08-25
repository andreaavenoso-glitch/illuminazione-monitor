#!/usr/bin/env bash
# Avvio automatico dell'app dentro un Codespace: build dei container, attesa
# che l'API sia pronta (alembic upgrade head gira dentro al comando di avvio
# del servizio "api" in docker-compose.yml, non qui), poi seed della watchlist.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

cp -n .env.example .env || true

echo "==> Costruzione e avvio dei servizi (puo' richiedere qualche minuto la prima volta)..."
docker compose up -d --build

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

cat <<'EOF'

======================================================================
 Tutto pronto!
 Apri la scheda "PORTS" in basso nell'editor, trova la riga con la
 porta 3000 ("Dashboard — apri questa") e clicca sull'icona del
 mondo/globo per aprirla nel browser.
======================================================================
EOF
