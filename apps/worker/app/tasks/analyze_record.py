"""Preliminary analysis of the documentation of one notice: read the page and its attached documents,
store them (Document rows with their text) and extract the fields by rules. Free; Claude can be added later
for the fields rules cannot read."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, date, datetime
from uuid import UUID

from app.celery_app import celery_app
from app.collectors.doc_collect import LIVELLI, collect_docs
from app.collectors.doc_fields import extract_fields
from app.db import SessionLocal
from app.tasks.verify_records import _fetch_plain
from shared_models import AnalisiRecord, Document, ProcurementRecord
from shared_models.categories import categorize_record
from shared_models.pregara import pregara_tipi
from shared_models.riclassifica import is_higher, verdetto_da_documenti
from sqlalchemy import select

log = logging.getLogger(__name__)


CATEGORIA_LABEL = {"manifestazione_interesse": "manifestazione di interesse", "gara": "gara", "pre_gara": "pre-gara"}


def applica_analisi(rec, attached: list[tuple[str, str]], fields: dict, profondita: str, today: date, now: datetime) -> list[str]:
    """What the analysis of the documents changes on the notice itself (pure on ``rec``, tested without a database):

    * the category: a heading that is a call for interest or a tender moves a pre-gara to its box (never down);
    * the deadline read in the documents: written on the notice (a deep analysis replaces the one of the listing,
      a base one only fills it in), so that the notice is confirmed (open) or expired (noise gone);
    * an outcome / award / revocation: the notice is closed.
    Returns the notes, in words, of what changed.
    """
    notes: list[str] = []
    current = categorize_record(rec)
    v = verdetto_da_documenti(attached)
    if v.categoria and is_higher(v.categoria, current):
        rec.categoria_analisi = v.categoria
        notes.append(f"riclassificato in {CATEGORIA_LABEL[v.categoria]}: {v.motivo}")
    if v.chiuso:
        rec.verifica_esito, rec.verified_at = "chiuso", now
        rec.verifica_nota = f"Chiuso dall'analisi dei documenti: {v.motivo}"
        return notes + [rec.verifica_nota]
    found = fields.get("scadenza")
    if not found:
        if notes or (current in ("manifestazione_interesse", "gara") or rec.categoria_analisi):
            rec.verifica_nota = "Scadenza non trovata nei documenti letti" + (f" ({profondita})" if profondita else "")
            notes.append(rec.verifica_nota)
        return notes
    doc_deadline = date.fromisoformat(str(found["valore"])[:10])
    existing = rec.scadenza.date() if isinstance(rec.scadenza, datetime) else rec.scadenza
    ora = (fields.get("ora_scadenza") or {}).get("valore")
    if existing is None or profondita == "approfondita":
        hh, mm = (int(x) for x in str(ora).split(":")) if ora else (23, 59)
        rec.scadenza = datetime(doc_deadline.year, doc_deadline.month, doc_deadline.day, hh, mm, tzinfo=UTC)
        effective = doc_deadline
        what = f"Scadenza {doc_deadline:%d/%m/%Y}{f' ore {ora}' if ora else ''} letta in {found.get('fonte') or 'un documento'} (analisi {profondita})"
    else:
        effective = existing
        what = (f"Scadenza dell'elenco {existing:%d/%m/%Y} (il documento dice {doc_deadline:%d/%m/%Y}: "
                "«Approfondisci documentazione» la allinea)") if existing != doc_deadline else f"Scadenza {existing:%d/%m/%Y} confermata dal documento"
    rec.verifica_esito = "aperto" if effective >= today else "chiuso"
    rec.verified_at, rec.verifica_nota = now, what + ("" if effective >= today else ": già passata")
    notes.append(rec.verifica_nota)
    return notes


async def analyze(record_id: UUID, profondita: str = "base") -> dict:
    livello = LIVELLI.get(profondita, LIVELLI["base"])
    profondita = profondita if profondita in LIVELLI else "base"
    async with SessionLocal() as s:
        rec = await s.get(ProcurementRecord, record_id)
        if rec is None:
            return {"error": "record non trovato"}
        link, ente, descrizione = rec.link_bando, rec.ente, rec.descrizione or ""
    collected, why = await collect_docs(link, _fetch_plain, livello)
    readable = [d for d in collected if d.text]
    today = datetime.now(tz=UTC).date()
    fields = extract_fields([(d.name, d.text) for d in readable], today)
    # the kind of pre-gara signal, from the title and from what the documents say
    tipi = pregara_tipi(descrizione + " " + " ".join(d.text[:4000] for d in readable))
    if tipi:
        fields["pregara_tipi"] = {"valore": tipi, "fonte": "titolo e documenti", "contesto": ""}
    documenti = [
        {"url": d.url, "nome": d.name, "caratteri": len(d.text), "letto": bool(d.text), "livello": d.depth}
        for d in collected
    ]
    async with SessionLocal() as s:
        for d in readable:
            checksum = hashlib.sha256(d.text.encode("utf-8")).hexdigest()
            exists = (
                await s.execute(
                    select(Document).where(Document.procurement_record_id == record_id, Document.checksum == checksum)
                )
            ).scalar_one_or_none()
            if exists is None:
                s.add(Document(
                    procurement_record_id=record_id, filename=d.name, storage_url=d.url, text_content=d.text,
                    checksum=checksum,
                    mime_type="application/pdf" if d.url.lower().split("?")[0].endswith(".pdf") else "text/html",
                ))
        row = (
            await s.execute(select(AnalisiRecord).where(AnalisiRecord.procurement_record_id == record_id))
        ).scalar_one_or_none()
        if row is None:
            row = AnalisiRecord(procurement_record_id=record_id)
            s.add(row)
        # a deep analysis is never replaced by a later base one
        if not (row.profondita == "approfondita" and profondita == "base"):
            row.documenti, row.campi, row.profondita = documenti, fields, profondita
            row.metodo, row.eseguita_il = "regole", datetime.now(tz=UTC)
        # what the documents say about the notice itself: its box, its deadline, whether it is already over
        rec = await s.get(ProcurementRecord, record_id)
        changes = applica_analisi(
            rec, [(d.name, d.text) for d in readable if d.depth > 0], fields, profondita, today, datetime.now(tz=UTC),
        ) if rec is not None and readable else []
        await s.commit()
    log.info("analyze_record ente=%s livello=%s documenti=%d letti=%d campi=%d stop=%s",
             ente, profondita, len(collected), len(readable), len(fields), why)
    return {"ente": ente, "profondita": profondita, "documenti": len(collected), "letti": len(readable),
            "campi": len(fields), "stop": why, "modifiche": changes}


@celery_app.task(name="app.tasks.analyze_record.analyze_record", soft_time_limit=900, time_limit=960)
def analyze_record(record_id: str, profondita: str = "base") -> dict:
    return asyncio.run(analyze(UUID(record_id), profondita))
