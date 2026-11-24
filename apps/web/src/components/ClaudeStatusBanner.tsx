"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface ClaudeStatus {
  ok: boolean | null;
  error: string | null;
  checked_at: string | null;
}

/** Live state of Claude. While it is down the API probes it every ~90 s, so this goes away by itself
 *  once the credit is back. */
export function useClaudeStatus() {
  return useQuery({
    queryKey: ["claude-status"],
    queryFn: () => api.get<ClaudeStatus>("/claude"),
    refetchInterval: 30000,
  });
}

function shortReason(error: string | null): string {
  if (!error) return "";
  if (/credit balance/i.test(error)) return "credito dell'API Anthropic esaurito";
  if (/usage limit|spend limit|quota/i.test(error)) return "limite di spesa raggiunto";
  if (/chiave|api key|authentication|permission/i.test(error)) return "chiave API non valida o assente";
  return error.slice(0, 160);
}

export function ClaudeStatusBanner() {
  const { data } = useClaudeStatus();
  if (!data || data.ok !== false) return null;
  return (
    <p className="rounded border border-red-300 bg-red-50 p-2 text-xs text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100">
      <b>Claude non disponibile</b>: {shortReason(data.error)}. La raccolta prosegue con le regole gratuite. Questo avviso
      sparisce da solo quando il credito è di nuovo attivo (controllo automatico ogni 1-2 minuti).
    </p>
  );
}

/** Small pill for the header, visible on every page while Claude is down. */
export function ClaudeDownPill() {
  const { data } = useClaudeStatus();
  if (!data || data.ok !== false) return null;
  return (
    <span
      className="rounded-full border border-red-400 bg-red-50 px-2 py-0.5 text-xs text-red-800"
      title={shortReason(data.error)}
    >
      Claude non disponibile
    </span>
  );
}
