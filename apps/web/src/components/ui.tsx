"use client";

import type { ReactNode } from "react";

/** Small line icons (no dependency): 24x24, stroke currentColor. */
const PATHS: Record<string, string> = {
  bulb: "M9 18h6M10 21h4M12 3a6 6 0 00-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0012 3z",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7l1-8z",
  flag: "M5 21V4m0 0h11l-2 4 2 4H5",
  hand: "M7 11V6a1.5 1.5 0 013 0v4m0-1V4.5a1.5 1.5 0 013 0V10m0-.5V6a1.5 1.5 0 013 0v7a7 7 0 01-7 7h-1a6 6 0 01-5-3l-2-3.5a1.5 1.5 0 012.4-1.7L7 14",
  check: "M9 12l2 2 4-4M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  clock: "M12 6v6l4 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  alert: "M12 9v4m0 4h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",
  users: "M17 20v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2M10 10a4 4 0 100-8 4 4 0 000 8zM21 20v-2a4 4 0 00-3-3.9M16 2.1a4 4 0 010 7.8",
  globe: "M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  mail: "M3 7l9 6 9-6M5 5h14a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2z",
  doc: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  building: "M4 21V5l8-3 8 3v16M9 21v-4h6v4M8 9h.01M12 9h.01M16 9h.01M8 13h.01M12 13h.01M16 13h.01",
};

export function Icon({ name, className = "h-5 w-5" }: { name: keyof typeof PATHS | string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      className={className} aria-hidden>
      <path d={PATHS[name] ?? PATHS.doc} />
    </svg>
  );
}

export const TONE = {
  sky: { bg: "bg-sky-50 dark:bg-sky-950/60", fg: "text-sky-700 dark:text-sky-300", solid: "bg-sky-500", ring: "ring-sky-200 dark:ring-sky-900", hex: "#0ea5e9", border: "border-l-sky-500" },
  violet: { bg: "bg-violet-50 dark:bg-violet-950/60", fg: "text-violet-700 dark:text-violet-300", solid: "bg-violet-500", ring: "ring-violet-200 dark:ring-violet-900", hex: "#8b5cf6", border: "border-l-violet-500" },
  emerald: { bg: "bg-emerald-50 dark:bg-emerald-950/60", fg: "text-emerald-700 dark:text-emerald-300", solid: "bg-emerald-500", ring: "ring-emerald-200 dark:ring-emerald-900", hex: "#10b981", border: "border-l-emerald-500" },
  amber: { bg: "bg-amber-50 dark:bg-amber-950/60", fg: "text-amber-700 dark:text-amber-300", solid: "bg-amber-500", ring: "ring-amber-200 dark:ring-amber-900", hex: "#f59e0b", border: "border-l-amber-500" },
  red: { bg: "bg-red-50 dark:bg-red-950/60", fg: "text-red-700 dark:text-red-300", solid: "bg-red-500", ring: "ring-red-200 dark:ring-red-900", hex: "#ef4444", border: "border-l-red-500" },
  brand: { bg: "bg-brand-50 dark:bg-brand-900/40", fg: "text-brand-700 dark:text-brand-200", solid: "bg-brand-500", ring: "ring-brand-200 dark:ring-brand-800", hex: "#6366f1", border: "border-l-brand-500" },
  neutral: { bg: "bg-neutral-100 dark:bg-neutral-800", fg: "text-neutral-700 dark:text-neutral-300", solid: "bg-neutral-400", ring: "ring-neutral-200 dark:ring-neutral-700", hex: "#a3a3a3", border: "border-l-neutral-300" },
} as const;
export type Tone = keyof typeof TONE;

/** Big-number tile with an icon (clickable when ``onClick`` is given). */
export function KpiTile({
  label, value, icon, tone = "brand", hint, onClick, active,
}: {
  label: string; value: ReactNode; icon: string; tone?: Tone; hint?: ReactNode; onClick?: () => void; active?: boolean;
}) {
  const t = TONE[tone];
  const body = (
    <div className={`card flex h-full items-center gap-3 p-4 text-left transition ${onClick ? "hover:-translate-y-0.5 hover:shadow-lift" : ""} ${active ? `ring-2 ${t.ring}` : ""}`}>
      <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${t.bg} ${t.fg}`}>
        <Icon name={icon} className="h-6 w-6" />
      </span>
      <span className="min-w-0">
        <span className="block text-2xl font-semibold leading-none tracking-tight">{value}</span>
        <span className="mt-1 block truncate text-xs text-neutral-500">{label}</span>
        {hint && <span className="block text-[11px] text-neutral-400">{hint}</span>}
      </span>
    </div>
  );
  return onClick ? <button type="button" onClick={onClick} className="block h-full w-full">{body}</button> : body;
}

/** Horizontal stacked bar: segments proportional to their value. */
export function StackedBar({
  parts, height = "h-2.5", empty = "Nessun dato",
}: { parts: { label: string; value: number; tone: Tone }[]; height?: string; empty?: string }) {
  const total = parts.reduce((a, p) => a + p.value, 0);
  if (total === 0) return <div className={`${height} w-full rounded-full bg-neutral-100 dark:bg-neutral-800`} title={empty} />;
  return (
    <div className={`flex ${height} w-full overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800`}>
      {parts.filter((p) => p.value > 0).map((p) => (
        <div key={p.label} className={TONE[p.tone].solid} style={{ width: `${(100 * p.value) / total}%` }} title={`${p.label}: ${p.value}`} />
      ))}
    </div>
  );
}

/** Donut chart with a centre label. */
export function Donut({
  parts, size = 132, center,
}: { parts: { label: string; value: number; tone: Tone }[]; size?: number; center?: ReactNode }) {
  const total = parts.reduce((a, p) => a + p.value, 0);
  const r = 46;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg viewBox="0 0 120 120" width={size} height={size} className="-rotate-90">
        <circle cx="60" cy="60" r={r} fill="none" stroke="currentColor" strokeWidth="14" className="text-neutral-100 dark:text-neutral-800" />
        {total > 0 && parts.filter((p) => p.value > 0).map((p) => {
          const len = (p.value / total) * c;
          const el = (
            <circle key={p.label} cx="60" cy="60" r={r} fill="none" stroke={TONE[p.tone].hex} strokeWidth="14"
              strokeDasharray={`${Math.max(len - 2, 0)} ${c}`} strokeDashoffset={-offset} strokeLinecap="round" />
          );
          offset += len;
          return el;
        })}
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{center}</div>
    </div>
  );
}

/** Days left to a deadline as a coloured badge. */
export function Countdown({ iso }: { iso: string | null }) {
  if (!iso) return <span className="chip bg-neutral-100 text-neutral-500 dark:bg-neutral-800">scadenza non indicata</span>;
  const days = Math.ceil((Date.parse(iso) - Date.now()) / 86_400_000);
  const tone: Tone = days < 0 ? "red" : days <= 7 ? "red" : days <= 21 ? "amber" : "emerald";
  const t = TONE[tone];
  return (
    <span className={`chip ${t.bg} ${t.fg}`}>
      <Icon name="clock" className="h-3.5 w-3.5" />
      {days < 0 ? "scaduta" : days === 0 ? "scade oggi" : `${days} gg alla scadenza`}
    </span>
  );
}
