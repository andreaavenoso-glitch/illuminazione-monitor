import type { ReactNode } from "react";

export function KpiCard({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
  hint?: string;
}) {
  const border = {
    neutral: "border-neutral-200 dark:border-neutral-800",
    success: "border-emerald-300 dark:border-emerald-800",
    warning: "border-amber-300 dark:border-amber-800",
    danger: "border-red-300 dark:border-red-800",
  }[tone];
  return (
    <div className={`rounded-lg border bg-white p-4 dark:bg-neutral-900 ${border}`}>
      <p className="text-xs uppercase tracking-wide text-neutral-500">{label}</p>
      <p className="mt-2 text-2xl font-bold leading-none">{value}</p>
      {hint && <p className="mt-1 text-xs text-neutral-500">{hint}</p>}
    </div>
  );
}
