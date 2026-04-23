from collections import Counter
from datetime import UTC, datetime, timedelta

from app.core.database import get_session
from app.schemas.dashboard import DashboardKpi
from fastapi import APIRouter, Depends
from shared_models import Alert, DailyReport, ProcurementRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/kpi", response_model=DashboardKpi)
async def dashboard_kpi(session: AsyncSession = Depends(get_session)) -> DashboardKpi:
    records = list((await session.execute(select(ProcurementRecord))).scalars().all())
    masters = [r for r in records if r.master_record_id is None]

    stato_counter = Counter(r.stato_procedurale for r in masters if r.stato_procedurale)
    regione_counter = Counter(r.regione for r in masters if r.regione)

    priority_counter = Counter(r.priorita_commerciale for r in masters if r.priorita_commerciale)

    valore = sum(
        float(r.importo)
        for r in masters
        if r.importo is not None and r.stato_procedurale == "GARA PUBBLICATA"
    )

    now = datetime.now(tz=UTC)
    horizon = now + timedelta(days=7)
    scadenze_imminenti = sum(
        1
        for r in masters
        if r.scadenza is not None
        and r.scadenza >= now
        and r.scadenza <= horizon
        and r.stato_procedurale == "GARA PUBBLICATA"
    )

    open_alerts = (
        await session.execute(select(Alert).where(Alert.is_open.is_(True)))
    ).scalars().all()

    latest_report = (
        await session.execute(
            select(DailyReport).order_by(DailyReport.report_date.desc()).limit(1)
        )
    ).scalar_one_or_none()

    return DashboardKpi(
        total_records=len(records),
        total_masters=len(masters),
        gare_pubblicate=stato_counter.get("GARA PUBBLICATA", 0),
        pre_gara=stato_counter.get("PRE-GARA", 0),
        esito=stato_counter.get("ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA", 0),
        rettifica=stato_counter.get("RETTIFICA-PROROGA-CHIARIMENTI", 0),
        weak_evidence=sum(1 for r in records if r.is_weak_evidence),
        priority_p1=priority_counter.get("P1", 0),
        priority_p2=priority_counter.get("P2", 0),
        priority_p3=priority_counter.get("P3", 0),
        priority_p4=priority_counter.get("P4", 0),
        alerts_open=len(list(open_alerts)),
        valore_totale_eur=round(valore, 2),
        scadenze_imminenti=scadenze_imminenti,
        per_regione=dict(regione_counter.most_common(10)),
        per_stato=dict(stato_counter),
        latest_report_date=latest_report.report_date.isoformat() if latest_report else None,
        latest_report_kpi=latest_report.report_json.get("kpi") if latest_report else None,
    )
