"""Level 2 (one box per region) and Level 1 (national sources overview)."""
from datetime import UTC, datetime, timedelta

from app.auth import current_user, require_role
from app.core.database import get_session
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from shared_models import (
    Entity,
    JobRun,
    ProcurementRecord,
    RawRecord,
    RegionSettings,
    Source,
    User,
    WatchlistItem,
)
from shared_models.categories import CATEGORIES, categorize
from shared_models.regions import REGIONS, normalize_region
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
level1_router = APIRouter()

RECENT_DAYS = 60


class RegionSettingsUpdate(BaseModel):
    enabled: bool | None = None
    recipients: str | None = None


def _health(item: WatchlistItem) -> str:
    if item.last_scan_at is None:
        return "unchecked"
    if (item.consecutive_failures or 0) > 0:
        return "failing"
    # Scanned before health tracking existed: nothing confirms it was readable.
    return "ok" if item.last_success_at else "unchecked"


def _canonical(region: str) -> str:
    r = normalize_region(region)
    if r is None:
        raise HTTPException(status_code=404, detail="Regione sconosciuta")
    return r


async def _settings_map(session: AsyncSession) -> dict[str, RegionSettings]:
    rows = (await session.execute(select(RegionSettings))).scalars().all()
    return {r.region: r for r in rows}


async def _get_or_create_settings(session: AsyncSession, region: str) -> RegionSettings:
    rs = await session.get(RegionSettings, region)
    if rs is None:
        rs = RegionSettings(region=region, enabled=False)
        session.add(rs)
        await session.flush()
    return rs


def _record_category(r: ProcurementRecord) -> str | None:
    return categorize(
        stato_procedurale=r.stato_procedurale,
        text=f"{r.descrizione or ''} {r.tipologia_gara_procedura or ''}",
        flag_pre_gara=r.flag_pre_gara,
        atto_tipo=r.atto_tipo,
    )


async def _recent_records(session: AsyncSession, region: str | None = None):
    since = datetime.now(tz=UTC) - timedelta(days=RECENT_DAYS)
    stmt = select(ProcurementRecord).where(
        ProcurementRecord.first_seen_at >= since,
        ProcurementRecord.master_record_id.is_(None),
    )
    if region:
        stmt = stmt.where(ProcurementRecord.regione == region)
    else:
        stmt = stmt.where(ProcurementRecord.regione.is_not(None))
    return (await session.execute(stmt.order_by(ProcurementRecord.first_seen_at.desc()))).scalars().all()


@router.get("")
async def list_regions(
    _: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    settings = await _settings_map(session)
    items = (
        await session.execute(
            select(WatchlistItem, Entity.region).outerjoin(Entity, WatchlistItem.entity_id == Entity.id)
        )
    ).all()
    sources = (
        await session.execute(
            select(Source.regione, func.count()).where(Source.regione.is_not(None)).group_by(Source.regione)
        )
    ).all()
    src_count = {r: n for r, n in sources}

    per: dict[str, dict] = {
        r: {
            "region": r,
            "enabled": settings[r].enabled if r in settings else False,
            "recipients": settings[r].recipients if r in settings else None,
            "last_digest_at": settings[r].last_digest_at if r in settings else None,
            "comuni": 0, "ok": 0, "failing": 0, "unchecked": 0,
            "regional_sites": src_count.get(r, 0),
            "pre_gara": 0, "manifestazione_interesse": 0, "gara": 0, "da_notificare": 0,
        }
        for r in REGIONS
    }
    for item, region in items:
        r = normalize_region(region)
        if r:
            per[r]["comuni"] += 1
            per[r][_health(item)] += 1
    for rec in await _recent_records(session):
        r = normalize_region(rec.regione)
        cat = _record_category(rec)
        if r and cat:
            per[r][cat] += 1
            if rec.notified_at is None:
                per[r]["da_notificare"] += 1
    # Active regions first, then alphabetical.
    return sorted(per.values(), key=lambda x: (not x["enabled"], x["region"]))


@router.get("/{region}")
async def region_detail(
    region: str, _: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict:
    region = _canonical(region)
    rs = await session.get(RegionSettings, region)
    rows = (
        await session.execute(
            select(WatchlistItem, Entity)
            .join(Entity, WatchlistItem.entity_id == Entity.id)
            .order_by(Entity.name)
        )
    ).all()
    comuni = [
        {
            "id": str(item.id),
            "ente": ent.name,
            "provincia": ent.province,
            "tipo": ent.entity_type,
            "siti": [
                {"ruolo": ruolo, "url": url}
                for ruolo, url in (
                    ("albo", item.url_albo), ("trasparenza", item.url_trasparenza),
                    ("gare", item.url_gare), ("esiti", item.url_esiti),
                    ("determine", item.url_determine),
                )
                if url
            ],
            "stato": _health(item),
            "last_error": item.last_error,
            "consecutive_failures": item.consecutive_failures or 0,
            "last_scan_at": item.last_scan_at,
            "last_success_at": item.last_success_at,
            "active": item.active,
        }
        for item, ent in rows
        if normalize_region(ent.region) == region
    ]
    # Problems first, then the ones already read, then the rest (stable, so
    # each group stays alphabetical): the trial run touches a few comuni out
    # of hundreds and they would otherwise be lost in the list.
    order = {"failing": 0, "ok": 1, "unchecked": 2}
    comuni.sort(key=lambda c: order[c["stato"]])
    sources = (
        await session.execute(select(Source).where(Source.regione == region).order_by(Source.name))
    ).scalars().all()
    last_runs: dict = {}
    for s in sources:
        j = (
            await session.execute(
                select(JobRun).where(JobRun.source_id == s.id).order_by(JobRun.started_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if j:
            last_runs[s.id] = {
                "status": j.status, "errore": j.error_message, "found": j.records_found, "at": j.started_at,
            }
    records = []
    for rec in await _recent_records(session, region):
        cat = _record_category(rec)
        if cat is None:
            continue
        records.append({
            "id": str(rec.id), "categoria": cat, "ente": rec.ente,
            "descrizione": rec.descrizione, "link": rec.link_bando,
            "scadenza": rec.scadenza, "stato": rec.stato_procedurale,
            "first_seen_at": rec.first_seen_at, "notificato": rec.notified_at is not None,
            "score": rec.score_commerciale,
        })
    return {
        "region": region,
        "enabled": rs.enabled if rs else False,
        "recipients": rs.recipients if rs else None,
        "last_digest_at": rs.last_digest_at if rs else None,
        "comuni": comuni,
        "siti_regionali": [
            {"id": str(s.id), "nome": s.name, "url": s.base_url, "ruolo": s.ruolo,
             "active": s.active, "last_checked_at": s.last_checked_at,
             "ultimo_run": last_runs.get(s.id)}
            for s in sources
        ],
        "records": records[:300],
        "categorie": list(CATEGORIES),
    }


@router.patch("/{region}")
async def update_region(
    region: str,
    payload: RegionSettingsUpdate,
    _: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    region = _canonical(region)
    rs = await _get_or_create_settings(session, region)
    data = payload.model_dump(exclude_unset=True)
    if data.get("enabled") is not None:
        rs.enabled = data["enabled"]
    if "recipients" in data:
        rs.recipients = (data["recipients"] or "").strip() or None
    await session.commit()
    return {"region": region, "enabled": rs.enabled, "recipients": rs.recipients}


@router.post("/{region}/collect")
async def collect_region(
    region: str,
    limit: int | None = Query(None, ge=1, le=500, description="Trial run: scan at most this many comuni"),
    _: User = Depends(require_role("admin")),
) -> dict:
    from app.services.admin_service import dispatch_region_scan

    region = _canonical(region)
    return {"status": "dispatched", "region": region, "limit": limit, **dispatch_region_scan(region, limit)}


@router.post("/{region}/send-digest")
async def send_digest(region: str, _: User = Depends(require_role("admin"))) -> dict:
    from app.services.admin_service import dispatch_region_digest

    region = _canonical(region)
    return {"status": "dispatched", "region": region, "task_id": dispatch_region_digest(region)}


@level1_router.get("")
async def level1_overview(
    _: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict:
    """Level 1: what the national portals gave us and whether to trust it.
    Analysis only: it does not own any tender list (those live per region)."""
    since = datetime.now(tz=UTC) - timedelta(days=7)
    sources = (
        await session.execute(
            select(Source)
            .where(Source.regione.is_(None), Source.source_type == "official")
            .order_by(Source.name)
        )
    ).scalars().all()
    raw_counts = dict(
        (
            await session.execute(
                select(RawRecord.source_id, func.count())
                .where(RawRecord.fetched_at >= since)
                .group_by(RawRecord.source_id)
            )
        ).all()
    )
    out = []
    for s in sources:
        last = (
            await session.execute(
                select(JobRun).where(JobRun.source_id == s.id).order_by(JobRun.started_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        out.append({
            "id": str(s.id), "nome": s.name, "url": s.base_url, "active": s.active,
            "affidabilita": float(s.reliability_score), "last_checked_at": s.last_checked_at,
            "raw_7gg": raw_counts.get(s.id, 0),
            "ultimo_run": None if last is None else {
                "status": last.status, "found": last.records_found, "valid": last.records_valid,
                "errore": last.error_message, "at": last.started_at,
            },
        })
    routed = len(await _recent_records(session))
    unrouted = (
        await session.execute(
            select(func.count()).select_from(ProcurementRecord).where(
                ProcurementRecord.regione.is_(None), ProcurementRecord.master_record_id.is_(None)
            )
        )
    ).scalar_one()
    return {"fonti": out, "record_assegnati_a_regione": routed, "record_senza_regione": unrouted}
