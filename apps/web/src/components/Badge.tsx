const STATO_CLASSES: Record<string, string> = {
  "GARA PUBBLICATA": "bg-sky-100 text-sky-800 ring-sky-200",
  "PRE-GARA": "bg-amber-100 text-amber-800 ring-amber-200",
  "RETTIFICA-PROROGA-CHIARIMENTI": "bg-purple-100 text-purple-800 ring-purple-200",
  "ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA": "bg-emerald-100 text-emerald-800 ring-emerald-200",
};

export function StatoBadge({ value }: { value: string | null }) {
  if (!value) return <span className="text-xs text-neutral-400">—</span>;
  const cls = STATO_CLASSES[value] ?? "bg-neutral-100 text-neutral-700 ring-neutral-200";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}>
      {value}
    </span>
  );
}

const PRIO_CLASSES: Record<string, string> = {
  P1: "bg-red-600 text-white",
  P2: "bg-orange-500 text-white",
  P3: "bg-amber-500 text-white",
  P4: "bg-neutral-500 text-white",
};

export function PriorityBadge({ value }: { value: string | null }) {
  if (!value) return <span className="text-xs text-neutral-400">—</span>;
  const cls = PRIO_CLASSES[value] ?? "bg-neutral-400 text-white";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`}>
      {value}
    </span>
  );
}

export function SeverityBadge({ value }: { value: string }) {
  const cls =
    value === "high" || value === "critical"
      ? "bg-red-100 text-red-800 ring-red-200"
      : value === "medium"
      ? "bg-amber-100 text-amber-800 ring-amber-200"
      : "bg-neutral-100 text-neutral-700 ring-neutral-200";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}>
      {value}
    </span>
  );
}
