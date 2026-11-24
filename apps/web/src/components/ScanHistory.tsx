"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { StackedBar, TONE } from "@/components/ui";
import { usd } from "@/lib/usage";

interface RunSummary {
  id: string;
  started_at: string;
  status: string;
  durata_s: number | null;
  comuni: number;
  comuni_letti: number;
  errori: number;
  pagine: number;
  profondita_max: number;
  profondita_media: number;
  record_trovati: number;
  chiamate_claude: number;
  costo_usd: number;
  config: Record<string, string | number>;
  istogramma_profondita: Record<string, number>;
  fermate_per: Record<string, number>;
}
interface Side { pagine: number; profondita: number; record: number; stato: string; fermata_per: string | null }
interface Compare {
  righe: { ente: string; a: Side | null; b: Side | null; diff: { pagine: number; profondita: number; record: number } | null }[];
  totali: { comuni_in_comune: number; pagine: number[]; record: number[]; profondita_media: number[] };
  solo_a: number;
  solo_b: number;
  migliorati: number;
  config_diff: string[];
}

const fmt = (d: string) => new Date(d).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
const dur = (s: number | null) => (s == null ? "—" : s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m` : `${Math.round(s / 60)} min`);
const delta = (n: number) => (n === 0 ? <span className="text-neutral-400">=</span> : <span className={n > 0 ? "text-emerald-600" : "text-red-600"}>{n > 0 ? "+" : ""}{n}</span>);
const TIPO: Record<string, string> = { completa: "completa", mirata: "mirata", prova: "prova", ripresa: "ripresa" };

function Histogram({ h }: { h: Record<string, number> }) {
  const levels = Object.keys(h).map(Number).sort((a, b) => a - b);
  if (levels.length === 0) return <span className="text-[11px] text-neutral-400">—</span>;
  const max = Math.max(...Object.values(h));
  return (
    <div className="flex h-8 items-end gap-0.5" title="Comuni per livello di profondità raggiunto">
      {levels.map((l) => (
        <div key={l} className="flex flex-col items-center">
          <div className="w-3 rounded-t bg-brand-400" style={{ height: `${Math.max(3, (28 * h[String(l)]) / max)}px` }} title={`livello ${l}: ${h[String(l)]} comuni`} />
          <span className="text-[8px] text-neutral-400">{l}</span>
        </div>
      ))}
    </div>
  );
}

/** History of the collection runs: depth, pages, records, cost and settings, with a like-for-like comparison. */
export function ScanHistory({ region }: { region: string }) {
  const [sel, setSel] = useState<string[]>([]);
  const runs = useQuery({
    queryKey: ["scan-history", region],
    queryFn: () => api.get<RunSummary[]>(`/regions/${encodeURIComponent(region)}/scans`),
  });
  const [a, b] = sel.length === 2 ? [...sel].sort((x, y) => (runs.data!.findIndex((r) => r.id === y) - runs.data!.findIndex((r) => r.id === x))) : [null, null];
  const cmp = useQuery({
    queryKey: ["scan-compare", region, a, b],
    queryFn: () => api.get<Compare>(`/regions/${encodeURIComponent(region)}/scans/compare?a=${a}&b=${b}`),
    enabled: !!a && !!b,
  });
  const toggle = (id: string) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s.slice(-1), id]));
  const data = runs.data ?? [];
  const maxRec = Math.max(1, ...data.map((r) => r.record_trovati));

  return (
    <section className="space-y-4">
      <p className="text-xs text-neutral-500">
        Ogni raccolta lascia le sue misure: pagine lette, profondità raggiunta, record trovati, costo e impostazioni usate.
        Scegli <b>due raccolte</b> per confrontarle comune per comune.
      </p>
      {runs.isLoading && <p className="text-sm text-neutral-500">Caricamento…</p>}
      {data.length === 0 && !runs.isLoading && <p className="text-sm text-neutral-500">Nessuna raccolta registrata per questa regione.</p>}

      {data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border dark:border-neutral-800">
          <table className="w-full min-w-[960px] text-left text-sm">
            <thead className="bg-neutral-100 text-xs uppercase text-neutral-500 dark:bg-neutral-900">
              <tr>
                <th className="p-2" />
                <th className="p-2">Quando</th>
                <th className="p-2">Tipo</th>
                <th className="p-2">Comuni</th>
                <th className="p-2">Pagine</th>
                <th className="p-2">Profondità</th>
                <th className="p-2">Livelli</th>
                <th className="p-2">Record trovati</th>
                <th className="p-2">Costo</th>
                <th className="p-2">Durata</th>
                <th className="p-2">Impostazioni</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} className={`border-t align-top dark:border-neutral-800 ${sel.includes(r.id) ? "bg-brand-50 dark:bg-brand-900/20" : ""}`}>
                  <td className="p-2"><input type="checkbox" checked={sel.includes(r.id)} onChange={() => toggle(r.id)} aria-label="confronta" /></td>
                  <td className="p-2 whitespace-nowrap">{fmt(r.started_at)}<div className="text-[11px] text-neutral-400">{r.status}</div></td>
                  <td className="p-2">{TIPO[String(r.config?.tipo)] ?? "—"}</td>
                  <td className="p-2">{r.comuni_letti}/{r.comuni}{r.errori > 0 && <div className="text-[11px] text-red-600">{r.errori} errori</div>}</td>
                  <td className="p-2">{r.pagine}</td>
                  <td className="p-2">media <b>{r.profondita_media}</b><div className="text-[11px] text-neutral-400">max {r.profondita_max}</div></td>
                  <td className="p-2"><Histogram h={r.istogramma_profondita} /></td>
                  <td className="p-2">
                    <b>{r.record_trovati}</b>
                    <div className="mt-1 h-1.5 w-20 overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
                      <div className="h-full rounded-full bg-emerald-500" style={{ width: `${(100 * r.record_trovati) / maxRec}%` }} />
                    </div>
                  </td>
                  <td className="p-2">{usd(r.costo_usd)}<div className="text-[11px] text-neutral-400">{r.chiamate_claude} chiamate</div></td>
                  <td className="p-2">{dur(r.durata_s)}</td>
                  <td className="p-2 text-[11px] text-neutral-500">
                    {r.config?.crawl_max_pages ? <>{r.config.crawl_max_pages} pag · prof. {r.config.crawl_max_depth} · {r.config.extraction_mode}</> : "n/d (prima dello storico)"}
                    {Object.keys(r.fermate_per).length > 0 && <div>stop: {Object.entries(r.fermate_per).map(([k, v]) => `${k} ${v}`).join(", ")}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {sel.length === 1 && <p className="text-xs text-neutral-500">Scegli una seconda raccolta per il confronto.</p>}
      {cmp.data && (
        <div className="card space-y-3 p-4">
          <h3 className="text-sm font-semibold">Confronto (stessi comuni: {cmp.data.totali.comuni_in_comune})</h3>
          {cmp.data.config_diff.length > 0 ? (
            <p className="text-xs text-neutral-600 dark:text-neutral-300">Impostazioni cambiate: {cmp.data.config_diff.join(" · ")}</p>
          ) : (
            <p className="text-xs text-neutral-500">Impostazioni identiche (o non registrate per una delle due).</p>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            {([["Pagine lette", cmp.data.totali.pagine], ["Record trovati", cmp.data.totali.record], ["Profondità media", cmp.data.totali.profondita_media]] as const).map(([l, v]) => (
              <div key={l} className="rounded-xl bg-neutral-50 p-3 dark:bg-neutral-800/50">
                <div className="text-xs text-neutral-500">{l}</div>
                <div className="text-xl font-semibold">{v[0]} → {v[1]} <span className="text-sm">{delta(Math.round((v[1] - v[0]) * 100) / 100)}</span></div>
                <StackedBar height="h-1.5" parts={[{ label: "prima", value: Number(v[0]), tone: "neutral" }, { label: "dopo", value: Number(v[1]), tone: "brand" }]} />
              </div>
            ))}
          </div>
          <p className="text-xs text-neutral-500">
            {cmp.data.migliorati} comuni migliorati (più record o più profondità) · {cmp.data.solo_a} solo nella prima · {cmp.data.solo_b} solo nella seconda
          </p>
          <div className="max-h-96 overflow-y-auto rounded-lg border dark:border-neutral-800">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-neutral-100 text-neutral-500 dark:bg-neutral-900">
                <tr><th className="p-2">Comune</th><th className="p-2">Pagine</th><th className="p-2">Profondità</th><th className="p-2">Record</th></tr>
              </thead>
              <tbody>
                {cmp.data.righe
                  .filter((r) => r.diff && (r.diff.pagine || r.diff.profondita || r.diff.record))
                  .sort((x, y) => (y.diff!.record - x.diff!.record) || (y.diff!.profondita - x.diff!.profondita))
                  .map((r) => (
                    <tr key={r.ente} className="border-t dark:border-neutral-800">
                      <td className="p-2">{r.ente}</td>
                      <td className="p-2">{r.a!.pagine} → {r.b!.pagine} {delta(r.diff!.pagine)}</td>
                      <td className="p-2">{r.a!.profondita} → {r.b!.profondita} {delta(r.diff!.profondita)}</td>
                      <td className="p-2">{r.a!.record} → {r.b!.record} {delta(r.diff!.record)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-neutral-400">Sono elencati solo i comuni che differiscono. <span className={TONE.emerald.fg}>Verde</span> = più di prima.</p>
        </div>
      )}
    </section>
  );
}
