export interface UsageWindow {
  cost_usd: number;
  calls: number;
  input_tokens: number;
  output_tokens: number;
}

export interface UsageSummary {
  today: UsageWindow;
  month: UsageWindow;
  total: UsageWindow;
  days: { day: string; cost_usd: number; calls: number }[];
  by_purpose: { name: string; cost_usd: number; calls: number }[];
  by_model: { name: string; cost_usd: number; calls: number }[];
  budget: { limit_usd: number; spent_usd: number; remaining_usd: number } | null;
  pricing: {
    model: string;
    input_per_mtok: number;
    output_per_mtok: number;
    model_in_table: boolean;
    table: Record<string, [number, number]>;
  };
}

export const PURPOSE_LABEL: Record<string, string> = {
  extract: "Lettura delle pagine (albi e trasparenza)",
  detail: "Dettaglio degli atti trovati",
  links: "Scelta dei link da seguire",
  collector: "Portali di gara",
};

/** Dollars with enough decimals to be meaningful for small amounts. */
export function usd(x: number): string {
  if (x === 0) return "$0.00";
  if (x < 0.01) return `$${x.toFixed(4)}`;
  return `$${x.toFixed(2)}`;
}
