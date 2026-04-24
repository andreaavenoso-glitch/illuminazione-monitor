FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /tmp/api-requirements.txt
RUN pip install -r /tmp/api-requirements.txt

COPY packages /packages
RUN pip install -e /packages/parsing_rules \
    && pip install -e /packages/scoring_engine \
    && pip install -e /packages/sector_dictionaries \
    && pip install -e /packages/shared_models \
    && pip install -e /packages/shared_schemas

COPY apps/api /app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
