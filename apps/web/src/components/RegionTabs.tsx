"use client";

import type { ReactNode } from "react";

export interface TabDef<K extends string> {
  key: K;
  label: string;
  n?: number;
  group: "opportunita" | "lavoro";
  tone: string; // sky | violet | emerald | amber | neutral
}

const TONES: Record<string, { dot: string; on: string; badge: string }> = {
  sky: { dot: "bg-sky-500", on: "border-sky-500 bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-100", badge: "bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-100" },
  violet: { dot: "bg-violet-500", on: "border-violet-500 bg-violet-50 text-violet-900 dark:bg-violet-950 dark:text-violet-100", badge: "bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-100" },
  emerald: { dot: "bg-emerald-500", on: "border-emerald-500 bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100", badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-100" },
  amber: { dot: "bg-amber-500", on: "border-amber-500 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100", badge: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-100" },
  neutral: { dot: "bg-neutral-400", on: "border-neutral-500 bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100", badge: "bg-neutral-200 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-100" },
};

function Pill<K extends string>({ t, active, onSelect }: { t: TabDef<K>; active: boolean; onSelect: (k: K) => void }) {
  const tone = TONES[t.tone] ?? TONES.neutral;
  const alert = t.tone === "amber" && (t.n ?? 0) > 0;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => onSelect(t.key)}
      className={`flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm transition ${
        active
          ? `${tone.on} font-medium shadow-sm`
          : "border-transparent text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${tone.dot} ${alert && !active ? "animate-pulse" : ""}`} />
      {t.label}
      {t.n !== undefined && (
        <span className={`min-w-[1.5rem] rounded-full px-1.5 py-0.5 text-center text-xs font-semibold ${active || alert ? tone.badge : "bg-neutral-100 text-neutral-500 dark:bg-neutral-800"}`}>
          {t.n}
        </span>
      )}
    </button>
  );
}

/** Opportunities (pre-gara / manifestazioni / gare) on the left, working tabs on the right;
 *  scrolls sideways on a phone instead of wrapping. */
export function RegionTabs<K extends string>({
  tabs,
  active,
  onSelect,
}: {
  tabs: TabDef<K>[];
  active: K;
  onSelect: (k: K) => void;
}) {
  const opp = tabs.filter((t) => t.group === "opportunita");
  const work = tabs.filter((t) => t.group === "lavoro");
  return (
    <nav
      role="tablist"
      className="sticky top-0 z-10 -mx-1 flex items-center gap-2 overflow-x-auto bg-neutral-50/90 px-1 py-2 backdrop-blur dark:bg-neutral-950/90"
    >
      <div className="flex shrink-0 gap-1 rounded-full bg-white p-1 shadow-sm ring-1 ring-neutral-200 dark:bg-neutral-900 dark:ring-neutral-800">
        {opp.map((t) => <Pill key={t.key} t={t} active={t.key === active} onSelect={onSelect} />)}
      </div>
      <span className="mx-1 h-6 w-px shrink-0 bg-neutral-300 dark:bg-neutral-700" aria-hidden />
      <div className="flex shrink-0 gap-1">
        {work.map((t) => <Pill key={t.key} t={t} active={t.key === active} onSelect={onSelect} />)}
      </div>
    </nav>
  );
}

export function MenuItem({
  children,
  onClick,
  hint,
  disabled,
}: {
  children: ReactNode;
  onClick: () => void;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="block w-full rounded-md px-3 py-1.5 text-left hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800"
    >
      <span className="text-sm">{children}</span>
      {hint && <span className="block text-[11px] leading-tight text-neutral-500">{hint}</span>}
    </button>
  );
}
