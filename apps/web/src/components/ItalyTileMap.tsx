"use client";

import Link from "next/link";
import type { RegionSummary } from "@/lib/regions";

/** Tile-grid cartogram of Italy: one tile per region, placed roughly where it is; the shade says how many
 *  open opportunities it has. A common pattern for regional dashboards (readable at a glance, no map data). */
const GRID: Record<string, { c: number; r: number; code: string }> = {
  "Valle d'Aosta": { c: 0, r: 0, code: "VDA" },
  "Trentino-Alto Adige": { c: 2, r: 0, code: "TAA" },
  Piemonte: { c: 0, r: 1, code: "PIE" },
  Lombardia: { c: 1, r: 1, code: "LOM" },
  Veneto: { c: 2, r: 1, code: "VEN" },
  "Friuli-Venezia Giulia": { c: 3, r: 1, code: "FVG" },
  Liguria: { c: 0, r: 2, code: "LIG" },
  "Emilia-Romagna": { c: 1, r: 2, code: "EMR" },
  Toscana: { c: 1, r: 3, code: "TOS" },
  Marche: { c: 2, r: 3, code: "MAR" },
  Sardegna: { c: 0, r: 4, code: "SAR" },
  Lazio: { c: 1, r: 4, code: "LAZ" },
  Umbria: { c: 2, r: 4, code: "UMB" },
  Abruzzo: { c: 3, r: 4, code: "ABR" },
  Campania: { c: 2, r: 5, code: "CAM" },
  Molise: { c: 3, r: 5, code: "MOL" },
  Puglia: { c: 4, r: 5, code: "PUG" },
  Basilicata: { c: 3, r: 6, code: "BAS" },
  Calabria: { c: 3, r: 7, code: "CAL" },
  Sicilia: { c: 2, r: 8, code: "SIC" },
};

const TILE = 58;
const GAP = 6;

function shade(n: number, max: number): string {
  if (n <= 0) return "bg-neutral-100 text-neutral-400 dark:bg-neutral-800 dark:text-neutral-500";
  const q = n / Math.max(max, 1);
  if (q > 0.66) return "bg-brand-600 text-white";
  if (q > 0.33) return "bg-brand-500 text-white";
  if (q > 0.1) return "bg-brand-300 text-brand-900";
  return "bg-brand-200 text-brand-900";
}

export function ItalyTileMap({ regions }: { regions: RegionSummary[] }) {
  const byName = new Map(regions.map((r) => [r.region, r]));
  const totals = (r: RegionSummary) => r.pre_gara + r.manifestazione_interesse + r.gara;
  const max = Math.max(1, ...regions.map(totals));
  const cols = 5;
  const rows = 9;
  return (
    <div className="relative mx-auto" style={{ width: cols * (TILE + GAP), height: rows * (TILE + GAP) }}>
      {Object.entries(GRID).map(([name, g]) => {
        const r = byName.get(name);
        const n = r ? totals(r) : 0;
        return (
          <Link
            key={name}
            href={`/regions/${encodeURIComponent(name)}`}
            title={`${name}: ${n} opportunità${r?.enabled ? "" : " (regione spenta)"}`}
            className={`absolute flex flex-col items-center justify-center rounded-xl text-center transition hover:-translate-y-0.5 hover:shadow-lift ${shade(n, max)} ${
              r?.enabled ? "ring-2 ring-brand-300 dark:ring-brand-700" : "opacity-70"
            }`}
            style={{ left: g.c * (TILE + GAP), top: g.r * (TILE + GAP), width: TILE, height: TILE }}
          >
            <span className="text-[10px] font-semibold tracking-wide opacity-80">{g.code}</span>
            <span className="text-lg font-semibold leading-none">{n}</span>
          </Link>
        );
      })}
    </div>
  );
}
