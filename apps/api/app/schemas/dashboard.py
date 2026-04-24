from typing import Any

from pydantic import BaseModel


class DashboardKpi(BaseModel):
    total_records: int
    total_masters: int
    gare_pubblicate: int
    pre_gara: int
    esito: int
    rettifica: int
    weak_evidence: int
    priority_p1: int
    priority_p2: int
    priority_p3: int
    priority_p4: int
    alerts_open: int
    valore_totale_eur: float
    scadenze_imminenti: int
    per_regione: dict[str, int]
    per_stato: dict[str, int]
    latest_report_date: str | None
    latest_report_kpi: dict[str, Any] | None
