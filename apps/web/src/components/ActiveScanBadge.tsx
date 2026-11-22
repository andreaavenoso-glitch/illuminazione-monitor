"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface ActiveScan {
  region: string | null;
  total: number;
  done: number;
}

/** Shown in the header while a scan is running, whatever page is open. */
export function ActiveScanBadge() {
  const { data } = useQuery({
    queryKey: ["active-scans"],
    queryFn: () => api.get<ActiveScan[]>("/regions/scans/active"),
    refetchInterval: 10000,
  });
  if (!data || data.length === 0) return null;
  return (
    <>
      {data.map((s, i) => (
        <Link
          key={`${s.region ?? "tutte"}-${i}`}
          href={s.region ? `/regions/${encodeURIComponent(s.region)}` : "/regions"}
          className="animate-pulse rounded-full border border-blue-400 bg-blue-50 px-2 py-0.5 text-xs text-blue-800"
          title="Scansione in corso: clicca per vedere l'avanzamento"
        >
          Scansione {s.region ?? "tutte le regioni"} {s.done}/{s.total}
        </Link>
      ))}
    </>
  );
}
