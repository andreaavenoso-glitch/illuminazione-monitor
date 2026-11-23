"""Email each enabled region's referents the records they have not seen yet.

Runs at the end of the daily chain (after normalize/score), so records found
at national level (TED, ANAC...) and those scraped from the region's comuni
arrive in one message per region. A record is marked ``notified_at`` only if
the email actually went out; with SMTP unset nothing is marked, so enabling
email later sends what accumulated.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from app.celery_app import celery_app
from app.config import WorkerSettings, get_worker_settings
from app.db import SessionLocal
from app.digest import DigestItem, build_digest, parse_recipients
from shared_models import ProcurementRecord, RegionSettings
from shared_models.categories import categorize_record
from shared_models.relevance import APERTO, MAX_AGE_DAYS, act_signature, collapse_duplicates, record_state
from sqlalchemy import and_, or_, select

log = logging.getLogger(__name__)

MAX_ITEMS_PER_EMAIL = 100


def _send(settings: WorkerSettings, *, to: list[str], subject: str, text: str, html: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = ", ".join(to)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


async def _run(region: str | None = None) -> dict:
    settings = get_worker_settings()
    out: dict = {"regions": {}}
    async with SessionLocal() as session:
        stmt = select(RegionSettings).where(RegionSettings.enabled.is_(True))
        if region:
            stmt = select(RegionSettings).where(RegionSettings.region == region)
        for rs in (await session.execute(stmt)).scalars().all():
            recipients = parse_recipients(rs.recipients)
            if not recipients:
                out["regions"][rs.region] = "no_recipients"
                continue
            now_utc = datetime.now(tz=UTC)
            recs = (
                await session.execute(
                    select(ProcurementRecord)
                    .where(
                        ProcurementRecord.regione == rs.region,
                        ProcurementRecord.notified_at.is_(None),
                        ProcurementRecord.master_record_id.is_(None),
                        # An expired deadline is noise; without a deadline, only recent notices.
                        or_(
                            ProcurementRecord.scadenza >= now_utc,
                            and_(
                                ProcurementRecord.scadenza.is_(None),
                                or_(
                                    ProcurementRecord.data_pubblicazione.is_(None),
                                    ProcurementRecord.data_pubblicazione >= now_utc - timedelta(days=MAX_AGE_DAYS),
                                ),
                            ),
                        ),
                    )
                    .order_by(ProcurementRecord.first_seen_at.desc())
                    .limit(MAX_ITEMS_PER_EMAIL)
                )
            ).scalars().all()
            items: list[tuple[ProcurementRecord, DigestItem]] = []
            # Several copies of one act (albo, transparency page, news): one line.
            deduped = collapse_duplicates(
                list(recs),
                lambda r: act_signature(r.ente, r.descrizione),
                lambda r: (r.scadenza is not None, len(r.descrizione or "")),
            )
            for r in deduped:
                cat = categorize_record(r)
                if cat is None or record_state(
                    cat, r.scadenza, r.data_pubblicazione, r.link_bando, r.verifica_esito, cig=r.cig
                )[0] != APERTO:
                    continue
                items.append((r, DigestItem(
                    categoria=cat, ente=r.ente, descrizione=r.descrizione or "",
                    link=r.link_bando,
                    scadenza=r.scadenza.date() if r.scadenza else None,
                    importo=float(r.importo) if r.importo else None,
                    servizi=tuple(k for k in (r.servizio or "").split(",") if k),
                )))
            if not items:
                out["regions"][rs.region] = "nothing_new"
                continue
            if not settings.smtp_host:
                log.warning("digest.smtp_not_configured", extra={"region": rs.region, "items": len(items)})
                out["regions"][rs.region] = f"smtp_not_configured ({len(items)} in attesa)"
                continue
            subject, text, html = build_digest(rs.region, [i for _, i in items], web_url=settings.web_base_url)
            try:
                await asyncio.to_thread(_send, settings, to=recipients, subject=subject, text=text, html=html)
            except Exception as exc:  # noqa: BLE001
                log.exception("digest.send_failed", extra={"region": rs.region})
                out["regions"][rs.region] = f"send_failed: {type(exc).__name__}"
                continue
            now = datetime.now(tz=UTC)
            for r, _ in items:
                r.notified_at = now
            rs.last_digest_at = now
            await session.commit()
            out["regions"][rs.region] = f"sent {len(items)}"
    return out


@celery_app.task(name="app.tasks.send_region_digests.send_region_digests")
def send_region_digests(region: str | None = None) -> dict:
    return asyncio.run(_run(region))
