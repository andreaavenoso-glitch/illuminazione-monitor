"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { usd, type UsageSummary } from "@/lib/usage";

/** Estimated spend on the Anthropic API, always in the header. */
export function UsageBadge() {
  const { data } = useQuery({
    queryKey: ["usage"],
    queryFn: () => api.get<UsageSummary>("/usage"),
    refetchInterval: 15000,
  });
  if (!data) return null;
  const b = data.budget;
  const low = b != null && b.remaining_usd < b.limit_usd * 0.1;
  return (
    <Link
      href="/usage"
      title={
        `Spesa stimata sull'API Anthropic (solo questa app, da quando esiste il contatore)\n` +
        `oggi ${usd(data.today.cost_usd)} · mese ${usd(data.month.cost_usd)} · totale ${usd(data.total.cost_usd)}` +
        (b ? `\nbudget del mese ${usd(b.limit_usd)}, residuo ${usd(b.remaining_usd)}` : "")
      }
      className={`rounded-full border px-2 py-0.5 text-xs hover:bg-neutral-100 dark:hover:bg-neutral-800 ${
        low ? "border-red-400 text-red-700" : "border-neutral-300 text-neutral-700 dark:border-neutral-700 dark:text-neutral-300"
      }`}
    >
      Claude oggi {usd(data.today.cost_usd)} · mese {usd(data.month.cost_usd)}
      {b && <> / {usd(b.limit_usd)}</>}
    </Link>
  );
}
