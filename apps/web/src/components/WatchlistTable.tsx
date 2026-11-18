"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { WatchlistItem, Entity } from "@/types";
import { SourceBadge } from "./SourceBadge";

type RowWithEntity = WatchlistItem & { entity?: Entity };

// Why a fetch failed, in words a reader can act on. The kinds come from the
// worker (classify_fetch_error): an address that 404s or doesn't resolve is
// probably wrong and worth correcting; a 403 means the site blocks us, so a
// different address wouldn't help.
const ERROR_LABELS: Record<string, string> = {
  http_404: "pagina non trovata (404)",
  http_403: "accesso bloccato (403)",
  dns: "dominio inesistente",
  ssl: "certificato non valido",
  timeout: "nessuna risposta (timeout)",
  empty: "pagina vuota",
};

function errorLabel(kind: string | null): string {
  if (!kind) return "errore";
  if (ERROR_LABELS[kind]) return ERROR_LABELS[kind];
  if (kind.startsWith("http_")) return `errore ${kind.slice(5)}`;
  return "errore";
}

type Health = "ok" | "failing" | "unchecked";

function healthOf(r: WatchlistItem): Health {
  if (!r.last_scan_at) return "unchecked";
  if (r.consecutive_failures > 0) return "failing";
  // Scanned before health tracking existed: nothing confirms it was readable.
  if (!r.last_success_at) return "unchecked";
  return "ok";
}

function HealthBadge({ r }: { r: WatchlistItem }) {
  const health = healthOf(r);
  if (health === "ok") {
    return (
      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
        raggiungibile
      </span>
    );
  }
  if (health === "failing") {
    const never = !r.last_success_at;
    return (
      <span
        title={r.last_error ?? undefined}
        className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-800 dark:bg-red-950 dark:text-red-200"
      >
        {errorLabel(r.last_error)}
        {" · "}
        {never ? "mai letta" : `${r.consecutive_failures} scansioni`}
      </span>
    );
  }
  return (
    <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300">
      da verificare
    </span>
  );
}

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

  const failing = rows.filter((r) => r.active && healthOf(r) === "failing").length;
  const scanned = rows.filter((r) => r.active && healthOf(r) !== "unchecked").length;

  return (
    <div className="space-y-3">
      {scanned > 0 && (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          {failing === 0
            ? `Tutte le ${scanned} fonti scansionate sono raggiungibili.`
            : `${failing} fonti su ${scanned} scansionate non sono raggiungibili: controlla gli indirizzi segnati in rosso.`}
        </p>
      )}
    <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
      <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
        <thead className="bg-neutral-50 dark:bg-neutral-950/50">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-neutral-500">Ente</th>
            <th className="px-4 py-3 text-left font-medium text-neutral-500">Regione</th>
            <th className="px-4 py-3 text-left font-medium text-neutral-500">Priorità</th>
            <th className="px-4 py-3 text-left font-medium text-neutral-500">URL monitorata</th>
            <th className="px-4 py-3 text-left font-medium text-neutral-500">Stato</th>
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
                ) : r.url_trasparenza ? (
                  <a href={r.url_trasparenza} target="_blank" rel="noreferrer" className="hover:underline">
                    {r.url_trasparenza}
                    <span className="ml-1 text-neutral-400">(trasparenza)</span>
                  </a>
                ) : (
                  "—"
                )}
              </td>
              <td className="px-4 py-2">
                <HealthBadge r={r} />
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
              <td colSpan={6} className="px-4 py-8 text-center text-neutral-500">
                Nessun elemento. Esegui <code>seed_watchlist.py</code>.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
    </div>
  );
}
