"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

type RecordRow = {
  id: string;
  ente: string;
  descrizione: string | null;
  importo: number | null;
  cig: string | null;
  link_bando: string;
  regione: string | null;
  scadenza: string | null;
  stato_procedurale: string;
  tipo_novita: string;
  score: number | null;
  priorita: string | null;
  is_weak_evidence: boolean;
};

type SourceRow = {
  source_id: string;
  source_name: string;
  status: string;
  records_found: number;
  records_valid: number;
  records_weak: number;
  error_message: string | null;
};

type AlertRow = {
  id: string;
  alert_type: string;
  severity: string;
  description: string;
  opened_at: string | null;
};

type DailyReport = {
  id: string;
  report_date: string;
  generated_at: string;
  total_new: number;
  total_updates: number;
  total_pregara: number;
  total_new_sources: number;
  report_json: {
    kpi: {
      total_new: number;
      total_updates: number;
      total_pregara: number;
      total_weak: number;
      total_p1: number;
      valore_totale_eur: number;
      total_sources_ok: number;
      total_sources_failed: number;
      total_anomalie_aperte: number;
    };
    nuove_gare: RecordRow[];
    aggiornamenti: RecordRow[];
    pre_gara: RecordRow[];
    evidenze_deboli: RecordRow[];
    fonti_interrogate: SourceRow[];
    anomalie_aperte: AlertRow[];
    markdown: string;
  };
};

function fmtEur(v: number | null | undefined): string {
  if (v == null) return "n.d.";
  return `€${v.toLocaleString("it-IT", { maximumFractionDigits: 0 })}`;
}

function RecordList({ title, rows }: { title: string; rows: RecordRow[] }) {
  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="text-lg font-semibold">
        {title}{" "}
        <span className="ml-2 rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
          {rows.length}
        </span>
      </h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-neutral-500">Nessun record.</p>
      ) : (
        <ul className="mt-3 space-y-2 text-sm">
          {rows.slice(0, 20).map((r) => (
            <li key={r.id} className="flex items-start justify-between gap-3 border-b border-neutral-100 pb-2 dark:border-neutral-800">
              <div className="flex-1">
                <div className="font-medium">{r.ente}</div>
                <div className="text-neutral-600 dark:text-neutral-400">
                  {r.descrizione ?? "—"}
                </div>
                <div className="mt-1 flex flex-wrap gap-2 text-xs text-neutral-500">
                  <span>{fmtEur(r.importo)}</span>
                  {r.scadenza && <span>· scad {new Date(r.scadenza).toLocaleDateString("it-IT")}</span>}
                  {r.cig && <span>· CIG {r.cig}</span>}
                  {r.regione && <span>· {r.regione}</span>}
                  <a href={r.link_bando} target="_blank" rel="noreferrer" className="text-sky-600 hover:underline">
                    apri →
                  </a>
                </div>
              </div>
              {r.priorita && (
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold text-white ${
                    r.priorita === "P1"
                      ? "bg-red-600"
                      : r.priorita === "P2"
                      ? "bg-orange-500"
                      : r.priorita === "P3"
                      ? "bg-amber-500"
                      : "bg-neutral-500"
                  }`}
                >
                  {r.priorita}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function DailyReportViewer() {
  const query = useQuery({
    queryKey: ["reports", "latest"],
    queryFn: () => api.get<DailyReport>("/reports/latest"),
    retry: false,
  });

  if (query.isLoading) return <div className="text-sm text-neutral-500">Caricamento…</div>;
  if (query.error) {
    const msg = query.error as Error;
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
        Nessun report ancora disponibile. Lancia manualmente il task con
        <code className="mx-1 rounded bg-amber-200 px-1 dark:bg-amber-800">POST /admin/rebuild-report/…</code>
        oppure attendi il cron giornaliero (07:00 UTC). {msg?.message && <span className="opacity-60">({msg.message})</span>}
      </div>
    );
  }

  const report = query.data!;
  const kpi = report.report_json.kpi;

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-sm text-neutral-500">Data report</p>
          <p className="text-xl font-semibold">{new Date(report.report_date).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
        </div>
        <p className="text-xs text-neutral-500">
          Generato il {new Date(report.generated_at).toLocaleString("it-IT")}
        </p>
      </header>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["Nuove gare", kpi.total_new],
          ["Aggiornamenti", kpi.total_updates],
          ["Pre-gara", kpi.total_pregara],
          ["Evidenze deboli", kpi.total_weak],
          ["Priorità P1", kpi.total_p1],
          ["Valore gare attive", fmtEur(kpi.valore_totale_eur)],
          ["Fonti ok / ko", `${kpi.total_sources_ok} / ${kpi.total_sources_failed}`],
          ["Anomalie aperte", kpi.total_anomalie_aperte],
        ].map(([label, value]) => (
          <div key={label as string} className="rounded-lg border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-900">
            <p className="text-xs uppercase text-neutral-500">{label}</p>
            <p className="mt-1 text-2xl font-bold">{value}</p>
          </div>
        ))}
      </section>

      <RecordList title="A. Nuove gare" rows={report.report_json.nuove_gare} />
      <RecordList title="B. Aggiornamenti" rows={report.report_json.aggiornamenti} />
      <RecordList title="C. Segnali pre-gara" rows={report.report_json.pre_gara} />
      <RecordList title="D. Evidenze deboli" rows={report.report_json.evidenze_deboli} />

      <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="text-lg font-semibold">Fonti interrogate</h2>
        {report.report_json.fonti_interrogate.length === 0 ? (
          <p className="mt-2 text-sm text-neutral-500">Nessun run nelle ultime 24h.</p>
        ) : (
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-500">
                <th className="pb-1">Fonte</th>
                <th className="pb-1">Stato</th>
                <th className="pb-1">Trovati</th>
                <th className="pb-1">Validi</th>
                <th className="pb-1">Deboli</th>
              </tr>
            </thead>
            <tbody>
              {report.report_json.fonti_interrogate.map((s) => (
                <tr key={s.source_id} className="border-t border-neutral-100 dark:border-neutral-800">
                  <td className="py-1">{s.source_name}</td>
                  <td className="py-1">
                    <span className={s.status === "success" ? "text-emerald-600" : s.status === "failed" ? "text-red-600" : "text-amber-600"}>
                      {s.status}
                    </span>
                  </td>
                  <td className="py-1">{s.records_found}</td>
                  <td className="py-1">{s.records_valid}</td>
                  <td className="py-1">{s.records_weak}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="text-lg font-semibold">Markdown</h2>
        <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded bg-neutral-50 p-3 text-xs text-neutral-700 dark:bg-neutral-950 dark:text-neutral-300">
          {report.report_json.markdown}
        </pre>
      </section>
    </div>
  );
}
