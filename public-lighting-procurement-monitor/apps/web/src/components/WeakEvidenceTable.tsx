"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { ProcurementRecord } from "@/types";

export function WeakEvidenceTable() {
  const query = useQuery({
    queryKey: ["records", "weak"],
    queryFn: () =>
      api.get<ProcurementRecord[]>(
        "/records?limit=200&only_masters=false"
      ),
  });

  if (query.isLoading) return <div className="text-sm text-neutral-500">Caricamento…</div>;
  if (query.error) {
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-100">
        Errore: {(query.error as Error).message}
      </div>
    );
  }

  const rows = (query.data ?? []).filter((r) => r.is_weak_evidence);
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-100">
        Nessuna evidenza debole. Tutti i record hanno i campi minimi richiesti.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
      <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
        <thead className="bg-neutral-50 dark:bg-neutral-950/50">
          <tr>
            <th className="px-3 py-2 text-left font-medium text-neutral-500">Ente</th>
            <th className="px-3 py-2 text-left font-medium text-neutral-500">Oggetto</th>
            <th className="px-3 py-2 text-left font-medium text-neutral-500">Reliability</th>
            <th className="px-3 py-2 text-left font-medium text-neutral-500">Visto</th>
            <th className="px-3 py-2 text-left font-medium text-neutral-500">Bando</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/40">
              <td className="px-3 py-2 font-medium">
                <Link href={`/records/${r.id}`} className="hover:underline">
                  {r.ente}
                </Link>
              </td>
              <td className="max-w-md truncate px-3 py-2 text-neutral-700 dark:text-neutral-300" title={r.descrizione ?? ""}>
                {r.descrizione ?? "—"}
              </td>
              <td className="px-3 py-2 text-neutral-500">{r.reliability_index ?? "—"}</td>
              <td className="px-3 py-2 text-neutral-500">{fmtDate(r.first_seen_at)}</td>
              <td className="px-3 py-2">
                <a
                  href={r.link_bando}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sky-600 hover:underline"
                >
                  apri →
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
