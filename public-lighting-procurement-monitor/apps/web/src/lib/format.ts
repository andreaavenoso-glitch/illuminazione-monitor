export function fmtEur(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "n.d.";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return "n.d.";
  return `€${n.toLocaleString("it-IT", { maximumFractionDigits: 0 })}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("it-IT");
}

export function fmtDateLong(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("it-IT", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const diff = d.getTime() - Date.now();
  return Math.ceil(diff / 86_400_000);
}
