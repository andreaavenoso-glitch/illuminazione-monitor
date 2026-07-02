# Pinned to Debian 12 (bookworm) — Playwright's dependency installer doesn't
# yet recognize Debian 13 (trixie, the current "slim" default) and fails on
# renamed packages (ttf-unifont -> fonts-unifont, etc).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY apps/worker/requirements.txt /tmp/worker-requirements.txt
RUN pip install -r /tmp/worker-requirements.txt

# Playwright fallback: only used when a portal's plain-HTML fetch comes back
# too thin to be JS-rendered content. Installs Chromium + its OS deps.
RUN playwright install --with-deps chromium

COPY packages /packages
RUN pip install -e /packages/parsing_rules \
    && pip install -e /packages/scoring_engine \
    && pip install -e /packages/sector_dictionaries \
    && pip install -e /packages/shared_models \
    && pip install -e /packages/shared_schemas

COPY apps/worker /app

CMD ["celery", "-A", "app.celery_app", "worker", "--beat", "--loglevel=info"]
