"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { WatchlistItem, Entity } from "@/types";
import { SourceBadge } from "./SourceBadge";

type RowWithEntity = WatchlistItem & { entity?: Entity };

export function WatchlistTable() {
  const watchlistQuery = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.get<WatchlistItem[]>("/watchlist"),
  });

  const entitiesQuery = useQuery({
    queryKey: ["entities"],
    queryFn: () => api.get<Entity[]>("/entities"),
  });

  if (watchlistQuery.isLoading || entitiesQuery.isLoading) {
    return <div className="text-sm text-neutral-500">Caricamento…</div>;
  }
  if (watchlistQuery.error || entitiesQuery.error) {
    const msg = (watchlistQuery.error ?? entitiesQuery.error) as Error;
    return <div className="text-sm text-red-600">Errore: {msg.message}</div>;
  }

  const entitiesById = new Map((entitiesQuery.data ?? []).map((e) => [e.id, e]));
  const rows: RowWithEntity[] = (watchlistQuery.data ?? []).map((w) => ({
    ...w,
    entity: w.entity_id ? entitiesById.get(w.entity_id) : undefined,
  }));

  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
      <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
        <thead className="bg-neutral-50 dark:bg-neutral-950/50">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-neutral-500">Ente</th>
            <th className="px-4 py-3 text-left font-medium text-neutral-500">Regione</th>
            <th className="px-4 py-3 text-left font-medium text-neutral-500">Priorità</th>
            <th className="px-4 py-3 text-left font-medium text-neutral-500">URL albo</th>
            <th className="px-4 py-3 text-left font-medium text-neutral-500">Attivo</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/40">
              <td className="px-4 py-2 font-medium">{r.entity?.name ?? "—"}</td>
              <td className="px-4 py-2 text-neutral-600">{r.entity?.region ?? "—"}</td>
              <td className="px-4 py-2">
                <SourceBadge priority={r.priority} />
              </td>
              <td className="max-w-[320px] truncate px-4 py-2 text-xs text-neutral-500">
                {r.url_albo ? (
                  <a href={r.url_albo} target="_blank" rel="noreferrer" className="hover:underline">
                    {r.url_albo}
                  </a>
                ) : (
                  "—"
                )}
              </td>
              <td className="px-4 py-2">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${
                    r.active ? "bg-emerald-500" : "bg-neutral-400"
                  }`}
                />
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={5} className="px-4 py-8 text-center text-neutral-500">
                Nessun elemento. Esegui <code>seed_watchlist.py</code>.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
