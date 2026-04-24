"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtEur } from "@/lib/format";
import type { DashboardKpi, ProcurementRecord } from "@/types";
import { KpiCard } from "./KpiCard";
import { PriorityBadge, StatoBadge } from "./Badge";

export function HomeDashboard() {
  const kpiQuery = useQuery({
    queryKey: ["dashboard", "kpi"],
    queryFn: () => api.get<DashboardKpi>("/dashboard/kpi"),
  });

  const topQuery = useQuery({
    queryKey: ["records", "top"],
    queryFn: () =>
      api.get<ProcurementRecord[]>(
        "/records?only_masters=true&priorita=P1&limit=10"
      ),
  });

  if (kpiQuery.isLoading) {
    return <div className="text-sm text-neutral-500">Caricamento…</div>;
  }
  if (kpiQuery.error) {
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-100">
        Errore KPI: {(kpiQuery.error as Error).message}
      </div>
    );
  }

  const kpi = kpiQuery.data!;
  const top = topQuery.data ?? [];

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard label="Gare pubblicate" value={kpi.gare_pubblicate} tone="success" />
        <KpiCard label="Pre-gara" value={kpi.pre_gara} tone="warning" />
        <KpiCard
          label="Scadenza ≤ 7gg"
          value={kpi.scadenze_imminenti}
          tone={kpi.scadenze_imminenti > 0 ? "warning" : "neutral"}
        />
        <KpiCard
          label="Anomalie aperte"
          value={kpi.alerts_open}
          tone={kpi.alerts_open > 0 ? "danger" : "success"}
        />
        <KpiCard label="Priorità P1" value={kpi.priority_p1} tone="danger" />
        <KpiCard label="Priorità P2" value={kpi.priority_p2} />
        <KpiCard label="Valore gare attive" value={fmtEur(kpi.valore_totale_eur)} />
        <KpiCard
          label="Evidenze deboli"
          value={kpi.weak_evidence}
          hint="Record senza dati minimi §9.1"
        />
      </section>

      <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Top opportunità P1</h2>
          <Link href="/records?priorita=P1" className="text-sm text-sky-600 hover:underline">
            Tutte →
          </Link>
        </div>
        {topQuery.isLoading ? (
          <p className="mt-2 text-sm text-neutral-500">Caricamento…</p>
        ) : top.length === 0 ? (
          <p className="mt-2 text-sm text-neutral-500">
            Nessun record P1 al momento. Avvia il pipeline con
            <code className="mx-1 rounded bg-neutral-100 px-1 dark:bg-neutral-800">POST /admin/run-daily-monitor</code>.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
            {top.map((r) => (
              <li key={r.id} className="flex items-start justify-between gap-3 py-2">
                <div className="flex-1">
                  <Link href={`/records/${r.id}`} className="font-medium hover:underline">
                    {r.ente}
                  </Link>
                  <div className="text-xs text-neutral-500">{r.descrizione ?? "—"}</div>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-neutral-500">
                    <span>{fmtEur(r.importo)}</span>
                    {r.regione && <span>· {r.regione}</span>}
                    {r.cig && <span>· CIG {r.cig}</span>}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <PriorityBadge value={r.priorita_commerciale ?? null} />
                  <StatoBadge value={r.stato_procedurale} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
          <h3 className="font-semibold">Per regione</h3>
          <ul className="mt-2 space-y-1 text-sm text-neutral-700 dark:text-neutral-300">
            {Object.entries(kpi.per_regione).length === 0 ? (
              <li className="text-neutral-500">Nessun record.</li>
            ) : (
              Object.entries(kpi.per_regione).map(([k, v]) => (
                <li key={k} className="flex justify-between">
                  <span>{k}</span>
                  <span className="font-mono">{v}</span>
                </li>
              ))
            )}
          </ul>
        </div>
        <div className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
          <h3 className="font-semibold">Per stato</h3>
          <ul className="mt-2 space-y-1 text-sm text-neutral-700 dark:text-neutral-300">
            {Object.entries(kpi.per_stato).length === 0 ? (
              <li className="text-neutral-500">Nessun record.</li>
            ) : (
              Object.entries(kpi.per_stato).map(([k, v]) => (
                <li key={k} className="flex justify-between">
                  <span className="truncate">{k}</span>
                  <span className="font-mono">{v}</span>
                </li>
              ))
            )}
          </ul>
        </div>
      </section>

      {kpi.latest_report_date && (
        <p className="text-center text-xs text-neutral-500">
          Ultimo report: {kpi.latest_report_date} —{" "}
          <Link href="/reports" className="underline">
            vai al report →
          </Link>
        </p>
      )}
    </div>
  );
}
