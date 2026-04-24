const CLASSES: Record<string, string> = {
  A: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  B: "bg-sky-100 text-sky-800 ring-sky-200",
  C: "bg-amber-100 text-amber-800 ring-amber-200",
};

export function SourceBadge({ priority }: { priority: string }) {
  const cls = CLASSES[priority] ?? "bg-neutral-100 text-neutral-700 ring-neutral-200";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}
    >
      {priority}
    </span>
  );
}
