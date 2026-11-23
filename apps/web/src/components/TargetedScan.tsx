"use client";

import { useMemo, useState } from "react";
import type { RegionComune } from "@/lib/regions";

const SEC_PER_COMUNE = 16; // measured: 10 comuni in 2m42s
const USD_PER_COMUNE = 0.009; // measured with Claude; 0 in rules mode

type Stato = "tutti" | "mai" | "errori" | "vecchi";

/** Targeted collection: filter the comuni (province, name, state) and pick exactly the ones to read. */
export function TargetedScan({
  comuni,
  busy,
  onStart,
  onClose,
}: {
  comuni: RegionComune[];
  busy: boolean;
  onStart: (ids: string[]) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const [prov, setProv] = useState<Set<string>>(new Set());
  const [stato, setStato] = useState<Stato>("tutti");
  const [picked, setPicked] = useState<Set<string>>(new Set());

  const province = useMemo(
    () => [...new Set(comuni.map((c) => c.provincia).filter((p): p is string => !!p))].sort(),
    [comuni],
  );
  const filtered = useMemo(() => {
    const week = Date.now() - 7 * 86_400_000;
    return comuni.filter((c) => {
      if (!c.active) return false;
      if (q && !c.ente.toLowerCase().includes(q.toLowerCase())) return false;
      if (prov.size && !(c.provincia && prov.has(c.provincia))) return false;
      if (stato === "mai" && c.last_scan_at) return false;
      if (stato === "errori" && c.stato !== "failing") return false;
      if (stato === "vecchi" && c.last_scan_at && Date.parse(c.last_scan_at) > week) return false;
      return true;
    });
  }, [comuni, q, prov, stato]);

  const toggle = (id: string) =>
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const n = picked.size;
  const minutes = Math.max(1, Math.round((n * SEC_PER_COMUNE) / 60));

  return (
    <section className="card space-y-3 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Raccolta mirata</h2>
        <button type="button" className="text-xs underline" onClick={onClose}>chiudi</button>
      </div>

      <div className="flex flex-wrap gap-2">
        <input
          className="min-w-[12rem] flex-1 rounded-lg border px-3 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-950"
          placeholder="Cerca un comune…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="rounded-lg border px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-950"
          value={stato}
          onChange={(e) => setStato(e.target.value as Stato)}
        >
          <option value="tutti">Tutti i comuni</option>
          <option value="mai">Mai letti</option>
          <option value="errori">Con siti non raggiungibili</option>
          <option value="vecchi">Non letti da 7 giorni</option>
        </select>
      </div>

      {province.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {province.map((p) => (
            <button key={p} type="button"
              onClick={() => setProv((s) => { const x = new Set(s); if (x.has(p)) x.delete(p); else x.add(p); return x; })}
              className={`chip border ${prov.has(p) ? "border-brand-500 bg-brand-50 text-brand-700" : "border-neutral-200 text-neutral-600 dark:border-neutral-700"}`}>
              {p}
            </button>
          ))}
          {prov.size > 0 && <button type="button" className="px-2 text-xs underline" onClick={() => setProv(new Set())}>tutte</button>}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-500">
        <span>{filtered.length} comuni corrispondono ai filtri</span>
        <span className="flex gap-3">
          <button type="button" className="underline" onClick={() => setPicked((p) => new Set([...p, ...filtered.map((c) => c.id)]))}>
            seleziona i {filtered.length} filtrati
          </button>
          <button type="button" className="underline" onClick={() => setPicked(new Set())}>nessuno</button>
        </span>
      </div>

      <ul className="max-h-64 divide-y overflow-y-auto rounded-lg border text-sm dark:divide-neutral-800 dark:border-neutral-800">
        {filtered.slice(0, 400).map((c) => (
          <li key={c.id}>
            <label className="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-neutral-50 dark:hover:bg-neutral-800">
              <input type="checkbox" checked={picked.has(c.id)} onChange={() => toggle(c.id)} />
              <span className="flex-1">{c.ente}</span>
              <span className="text-xs text-neutral-400">{c.provincia ?? ""}</span>
              <span className={`h-2 w-2 rounded-full ${c.stato === "ok" ? "bg-emerald-500" : c.stato === "failing" ? "bg-red-500" : "bg-neutral-300"}`}
                title={c.stato === "ok" ? "raggiungibile" : c.stato === "failing" ? (c.last_error ?? "errore") : "non verificato"} />
            </label>
          </li>
        ))}
        {filtered.length === 0 && <li className="p-3 text-neutral-500">Nessun comune con questi filtri.</li>}
        {filtered.length > 400 && <li className="p-2 text-center text-xs text-neutral-400">… altri {filtered.length - 400}: restringi i filtri</li>}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs text-neutral-500">
          {n} comuni scelti · circa {minutes} min · circa ${(n * USD_PER_COMUNE).toFixed(2)} con Claude (0 in modalità regole)
        </span>
        <button type="button" disabled={busy || n === 0}
          className="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          onClick={() => onStart([...picked])}>
          Avvia la raccolta di {n} comuni
        </button>
      </div>
    </section>
  );
}
