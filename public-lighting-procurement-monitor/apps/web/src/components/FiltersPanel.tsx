"use client";

import type { ChangeEvent } from "react";

export type RecordFilters = {
  q: string;
  regione: string;
  stato: string;
  priorita: string;
  tipoNovita: string;
  onlyMasters: boolean;
  minImporto: string;
  flagPpp: string;
  flagOm: string;
  flagPreGara: string;
};

export const EMPTY_FILTERS: RecordFilters = {
  q: "",
  regione: "",
  stato: "",
  priorita: "",
  tipoNovita: "",
  onlyMasters: true,
  minImporto: "",
  flagPpp: "",
  flagOm: "",
  flagPreGara: "",
};

const STATI = [
  "GARA PUBBLICATA",
  "PRE-GARA",
  "RETTIFICA-PROROGA-CHIARIMENTI",
  "ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA",
];

const TIPI_NOVITA = [
  "Nuovo oggi",
  "Nuovo emerso oggi ma pubblicato prima",
  "Aggiornamento gara nota",
  "Segnale pre-gara",
];

export function FiltersPanel({
  value,
  onChange,
  regions,
}: {
  value: RecordFilters;
  onChange: (next: RecordFilters) => void;
  regions: string[];
}) {
  const update = <K extends keyof RecordFilters>(k: K, v: RecordFilters[K]) =>
    onChange({ ...value, [k]: v });
  const text = (k: keyof RecordFilters) => (e: ChangeEvent<HTMLInputElement>) =>
    update(k, e.target.value as never);
  const sel = (k: keyof RecordFilters) => (e: ChangeEvent<HTMLSelectElement>) =>
    update(k, e.target.value as never);

  return (
    <details className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900" open>
      <summary className="cursor-pointer text-sm font-medium text-neutral-700 dark:text-neutral-200">
        Filtri
      </summary>
      <div className="mt-3 grid gap-3 md:grid-cols-4">
        <div>
          <label className="text-xs text-neutral-500">Cerca</label>
          <input
            type="text"
            value={value.q}
            onChange={text("q")}
            placeholder="ente, oggetto, CIG"
            className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-950"
          />
        </div>
        <div>
          <label className="text-xs text-neutral-500">Regione</label>
          <select value={value.regione} onChange={sel("regione")} className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-950">
            <option value="">Tutte</option>
            {regions.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-neutral-500">Stato procedurale</label>
          <select value={value.stato} onChange={sel("stato")} className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-950">
            <option value="">Tutti</option>
            {STATI.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-neutral-500">Priorità</label>
          <select value={value.priorita} onChange={sel("priorita")} className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-950">
            <option value="">Tutte</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
            <option value="P4">P4</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-neutral-500">Tipo novità</label>
          <select value={value.tipoNovita} onChange={sel("tipoNovita")} className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-950">
            <option value="">Tutti</option>
            {TIPI_NOVITA.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-neutral-500">Importo minimo (€)</label>
          <input
            type="number"
            value={value.minImporto}
            onChange={text("minImporto")}
            placeholder="es. 500000"
            className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-950"
          />
        </div>
        <div>
          <label className="text-xs text-neutral-500">Flag PPP</label>
          <select value={value.flagPpp} onChange={sel("flagPpp")} className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-950">
            <option value="">—</option>
            <option value="Yes">Sì</option>
            <option value="No">No</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-neutral-500">Flag O&amp;M</label>
          <select value={value.flagOm} onChange={sel("flagOm")} className="mt-1 w-full rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-950">
            <option value="">—</option>
            <option value="Yes">Sì</option>
            <option value="No">No</option>
          </select>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={value.onlyMasters}
            onChange={(e) => update("onlyMasters", e.target.checked)}
          />
          Solo master (nascondi duplicati)
        </label>
        <button
          onClick={() => onChange(EMPTY_FILTERS)}
          type="button"
          className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
        >
          Reset
        </button>
      </div>
    </details>
  );
}
