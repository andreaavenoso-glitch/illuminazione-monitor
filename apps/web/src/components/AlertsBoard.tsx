"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtDateLong } from "@/lib/format";
import type { Alert } from "@/types";
import { SeverityBadge } from "./Badge";

export function AlertsBoard() {
  const [showClosed, setShowClosed] = useState(false);
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ["alerts", { showClosed }],
    queryFn: () =>
      api.get<Alert[]>(`/alerts?is_open=${showClosed ? "false" : "true"}&limit=200`),
  });

  const closeMutation = useMutation({
    mutationFn: (id: string) => api.patch<Alert>(`/alerts/${id}/close`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={showClosed}
          onChange={(e) => setShowClosed(e.target.checked)}
        />
        Mostra alert chiuse
      </label>
      {query.isLoading ? (
        <div className="text-sm text-neutral-500">Caricamento…</div>
      ) : query.error ? (
        <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-100">
          Errore: {(query.error as Error).message}
        </div>
      ) : (query.data ?? []).length === 0 ? (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-100">
          Nessuna alert {showClosed ? "chiusa" : "aperta"}.
        </div>
      ) : (
        <ul className="space-y-2">
          {(query.data ?? []).map((a) => (
            <li
              key={a.id}
              className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <SeverityBadge value={a.severity} />
                    <span className="text-sm font-medium">{a.alert_type}</span>
                  </div>
                  <p className="mt-1 text-sm text-neutral-700 dark:text-neutral-300">
                    {a.description}
                  </p>
                  <p className="mt-1 text-xs text-neutral-500">
                    Aperta il {fmtDateLong(a.opened_at)}
                    {a.closed_at && ` · chiusa il ${fmtDateLong(a.closed_at)}`}
                    {a.procurement_record_id && (
                      <>
                        {" · "}
                        <Link
                          href={`/records/${a.procurement_record_id}`}
                          className="text-sky-600 hover:underline"
                        >
                          vai al record →
                        </Link>
                      </>
                    )}
                  </p>
                </div>
                {a.is_open && (
                  <button
                    type="button"
                    onClick={() => closeMutation.mutate(a.id)}
                    disabled={closeMutation.isPending}
                    className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
                  >
                    Chiudi
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
