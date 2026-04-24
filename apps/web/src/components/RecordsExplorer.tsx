"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ProcurementRecord } from "@/types";
import { ExportButtons } from "./ExportButtons";
import { RecordsTable } from "./RecordsTable";
import { EMPTY_FILTERS, FiltersPanel, type RecordFilters } from "./FiltersPanel";

const ITALIAN_REGIONS = [
  "Abruzzo",
  "Basilicata",
  "Calabria",
  "Campania",
  "Emilia-Romagna",
  "Friuli-VG",
  "Lazio",
  "Liguria",
  "Lombardia",
  "Marche",
  "Molise",
  "Piemonte",
  "Puglia",
  "Sardegna",
  "Sicilia",
  "Toscana",
  "Trentino-Alto Adige",
  "Umbria",
  "Valle d'Aosta",
  "Veneto",
];

function buildQueryString(filters: RecordFilters): string {
  const p = new URLSearchParams();
  if (filters.q) p.set("q", filters.q);
  if (filters.regione) p.set("regione", filters.regione);
  if (filters.stato) p.set("stato_procedurale", filters.stato);
  if (filters.priorita) p.set("priorita", filters.priorita);
  if (filters.tipoNovita) p.set("tipo_novita", filters.tipoNovita);
  if (filters.minImporto) p.set("min_importo", filters.minImporto);
  if (filters.flagPpp) p.set("flag_ppp_doppio_oggetto", filters.flagPpp);
  if (filters.flagOm) p.set("flag_om", filters.flagOm);
  if (filters.flagPreGara) p.set("flag_pre_gara", filters.flagPreGara);
  if (filters.onlyMasters) p.set("only_masters", "true");
  p.set("limit", "200");
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

export function RecordsExplorer() {
  const [filters, setFilters] = useState<RecordFilters>(EMPTY_FILTERS);
  const query = useQuery({
    queryKey: ["records", "list", filters],
    queryFn: () => api.get<ProcurementRecord[]>(`/records${buildQueryString(filters)}`),
  });

  const regions = useMemo(() => ITALIAN_REGIONS, []);

  return (
    <div className="space-y-4">
      <FiltersPanel value={filters} onChange={setFilters} regions={regions} />
      {query.isLoading ? (
        <div className="text-sm text-neutral-500">Caricamento…</div>
      ) : query.error ? (
        <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-100">
          Errore: {(query.error as Error).message}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-neutral-500">{query.data?.length ?? 0} record</p>
            <ExportButtons queryString={buildQueryString(filters)} />
          </div>
          <RecordsTable records={query.data ?? []} />
        </>
      )}
    </div>
  );
}
