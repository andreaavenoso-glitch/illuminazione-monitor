#!/usr/bin/env bash
# Comandi corti, pensati per scriverli da telefono nel terminale del Codespace.
#
#   bash aggiorna.sh           scarica gli aggiornamenti e riavvia tutto
#   bash aggiorna.sh claude    prova se Claude risponde (costa pochi centesimi)
#   bash aggiorna.sh stato     stato dei servizi e ultima raccolta
#   bash aggiorna.sh ko [--prova] [--applica]   diagnosi e recupero siti non raggiungibili
set -u
cd "$(dirname "$0")"

app_url() {
  if [ -n "${CODESPACE_NAME:-}" ] && [ -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]; then
    echo "https://${CODESPACE_NAME}-3000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  else
    echo "http://localhost:3000"
  fi
}

case "${1:-aggiorna}" in
  aggiorna)
    echo "==> 1/5 Scarico gli aggiornamenti..."
    if ! git pull; then
      echo "git pull non e' riuscito (modifiche locali?). Copia qui sopra l'errore e mandamelo."
      exit 1
    fi
    echo "==> 2/5 Avvio i servizi fermi (se il Codespace era spento)..."
    docker compose up -d
    echo "==> 3/5 Ricreo API e worker (rileggono il file .env, ad esempio la chiave Claude) e riavvio il sito..."
    # "restart" NON rilegge .env: una chiave appena aggiunta resterebbe ignorata.
    # Se requirements.txt del worker e' cambiato (nuova libreria), l'immagine va ricostruita.
    req_hash=$(sha1sum apps/worker/requirements.txt | cut -d' ' -f1)
    if [ "$(cat .worker_requirements.sha 2>/dev/null)" != "$req_hash" ]; then
      echo "    nuove librerie per il worker: ricostruisco l'immagine (qualche minuto)..."
      docker compose build worker && echo "$req_hash" > .worker_requirements.sha
    fi
    docker compose up -d --force-recreate api worker
    docker compose restart web
    echo "==> 4/5 Aspetto che l'API risponda (fino a 2 minuti)..."
    ok=0
    for _ in $(seq 1 40); do
      if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then ok=1; break; fi
      sleep 3
    done
    if [ "$ok" = 1 ]; then
      echo "==> 5/5 Carico comuni, regioni, siti e utente (non cancella nulla, serve se il database e' nuovo)..."
      for seed in seed_watchlist seed_regions seed_admin; do
        docker compose exec -T api python -m infra.scripts.$seed || echo "($seed non riuscito: incolla l'errore)"
      done
      echo
      echo "Pronto. Apri: $(app_url)/regions"
    else
      echo "L'API non ha risposto in tempo. Ultime righe del suo log:"
      docker compose logs api --tail 20
      exit 1
    fi
    ;;
  claude)
    docker compose exec -T worker python -m infra.scripts.check_extraction
    ;;
  ko)
    shift
    docker compose exec -T worker python -m infra.scripts.siti_ko "$@"
    ;;
  stato)
    docker compose ps
    echo
    echo "--- Ultime righe della raccolta ---"
    docker compose logs worker --since 90m 2>/dev/null \
      | grep -E "collect_watchlist\.(scope|stats|claude_unavailable)|collect_watchlist_albo.*succeeded|claude_error" \
      | tail -12
    echo
    echo "Comuni letti nell'ultima ora: $(docker compose logs worker --since 60m 2>/dev/null | grep -c 'collect_watchlist.crawl')"
    echo "App: $(app_url)/regions"
    ;;
  *)
    echo "Uso: bash aggiorna.sh [aggiorna|claude|stato|ko]"
    exit 2
    ;;
esac
