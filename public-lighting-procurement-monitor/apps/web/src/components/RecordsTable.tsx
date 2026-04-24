"use client";

import Link from "next/link";
import { PriorityBadge, StatoBadge } from "./Badge";
import { fmtDate, fmtEur } from "@/lib/format";
import type { ProcurementRecord } from "@/types";

export function RecordsTable({ records }: { records: ProcurementRecord[] }) {
  if (records.length === 0) {
    return (
      <div className="rounded-lg border border-neutral-200 bg-white p-6 text-sm text-neutral-500 dark:border-neutral-800 dark:bg-neutral-900">
        Nessun record corrisponde ai filtri.
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
            <th className="px-3 py-2 text-right font-medium text-neutral-500">Importo</th>
            <th className="px-3 py-2 text-left font-medium text-neutral-500">Stato</th>
            <th className="px-3 py-2 text-center font-medium text-neutral-500">Prio</th>
            <th className="px-3 py-2 text-left font-medium text-neutral-500">Scadenza</th>
            <th className="px-3 py-2 text-left font-medium text-neutral-500">Regione</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
          {records.map((r) => (
            <tr key={r.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/40">
              <td className="px-3 py-2 font-medium">
                <Link href={`/records/${r.id}`} className="hover:underline">
                  {r.ente}
                </Link>
              </td>
              <td className="max-w-xs truncate px-3 py-2 text-neutral-700 dark:text-neutral-300" title={r.descrizione ?? ""}>
                {r.descrizione ?? "—"}
              </td>
              <td className="px-3 py-2 text-right font-mono text-neutral-700 dark:text-neutral-300">
                {fmtEur(r.importo)}
              </td>
              <td className="px-3 py-2">
                <StatoBadge value={r.stato_procedurale} />
              </td>
              <td className="px-3 py-2 text-center">
                <PriorityBadge value={r.priorita_commerciale ?? null} />
              </td>
              <td className="px-3 py-2 text-neutral-700 dark:text-neutral-300">{fmtDate(r.scadenza)}</td>
              <td className="px-3 py-2 text-neutral-500">{r.regione ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
