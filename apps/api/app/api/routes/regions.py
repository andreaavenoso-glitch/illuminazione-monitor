"""Level 2 (one box per region) and Level 1 (national sources overview)."""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.auth import current_user, require_role
from app.core.database import get_session
from app.services.scan_view import scan_summary
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from shared_models import (
    ApiUsage,
    Entity,
    JobRun,
    ProcurementRecord,
    RawRecord,
    RegionSettings,
    ScanItem,
    ScanRun,
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


class SiteUpdate(BaseModel):
    active: bool


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
    last_scan = (
        await session.execute(
            select(JobRun).where(JobRun.job_name == "collect_watchlist_albo")
            .order_by(JobRun.started_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
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
            "servizi": [k for k in (rec.servizio or "").split(",") if k],
        })
    return {
        "region": region,
        "enabled": rs.enabled if rs else False,
        "recipients": rs.recipients if rs else None,
        "last_digest_at": rs.last_digest_at if rs else None,
        "ultimo_scan": None if last_scan is None else {
            "status": last_scan.status, "errore": last_scan.error_message,
            "at": last_scan.started_at, "trovati": last_scan.records_found,
        },
        "comuni": comuni,
        "siti_regionali": [
            {"id": str(s.id), "nome": s.name, "url": s.base_url, "ruolo": s.ruolo,
             "active": s.active, "last_checked_at": s.last_checked_at,
             "scoperto_da": s.discovered_from,
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


@router.get("/{region}/scan")
async def region_scan(
    region: str, _: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict | None:
    """Per-comune progress of the latest scan that covered this region: the
    region's own run, or the latest all-regions run (daily), whichever is newer."""
    region = _canonical(region)
    own = (
        await session.execute(
            select(ScanRun).where(ScanRun.region == region).order_by(ScanRun.started_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    general = (
        await session.execute(
            select(ScanRun).where(ScanRun.region.is_(None)).order_by(ScanRun.started_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    run = max((r for r in (own, general) if r is not None), key=lambda r: r.started_at, default=None)
    if run is None:
        return None
    items = list((await session.execute(select(ScanItem).where(ScanItem.run_id == run.id))).scalars().all())
    if run.region is None:
        # An all-regions run: keep this region's comuni only.
        rows = (
            await session.execute(
                select(ScanItem.id, Entity.region)
                .join(WatchlistItem, ScanItem.item_id == WatchlistItem.id)
                .join(Entity, WatchlistItem.entity_id == Entity.id)
                .where(ScanItem.run_id == run.id)
            )
        ).all()
        keep = {i for i, r in rows if normalize_region(r) == region}
        items = [i for i in items if i.id in keep]
    cost_rows = (
        await session.execute(
            select(ApiUsage.scan_item_id, func.coalesce(func.sum(ApiUsage.cost_usd), 0))
            .where(ApiUsage.run_id == run.id)
            .group_by(ApiUsage.scan_item_id)
        )
    ).all()
    costs = {sid: float(c) for sid, c in cost_rows if sid is not None}
    run_cost = sum(float(c) for _, c in cost_rows)
    return scan_summary(run, items, datetime.now(tz=UTC), costs=costs, run_cost=run_cost)


@router.patch("/{region}/sites/{source_id}")
async def update_site(
    region: str,
    source_id: UUID,
    payload: SiteUpdate,
    _: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Approve (activate) or switch off a regional site, e.g. one the crawl of
    the comuni discovered."""
    region = _canonical(region)
    src = await session.get(Source, source_id)
    if src is None or src.regione != region:
        raise HTTPException(status_code=404, detail="Sito non trovato in questa regione")
    src.active = payload.active
    await session.commit()
    return {"id": str(src.id), "active": src.active}


@router.post("/{region}/collect")
async def collect_region(
    region: str,
    limit: int | None = Query(None, ge=1, le=500, description="Trial run: scan at most this many comuni"),
    resume: bool = Query(False, description="Skip the comuni already read in the last 24 hours"),
    _: User = Depends(require_role("admin")),
) -> dict:
    from app.services.admin_service import dispatch_region_scan

    region = _canonical(region)
    hours = 24.0 if resume else None
    return {
        "status": "dispatched", "region": region, "limit": limit, "resume": resume,
        **dispatch_region_scan(region, limit, hours),
    }


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
