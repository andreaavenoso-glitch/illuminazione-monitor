export type Categoria = "pre_gara" | "manifestazione_interesse" | "gara";

export const CATEGORIA_LABEL: Record<Categoria, string> = {
  pre_gara: "Pre-gare",
  manifestazione_interesse: "Manifestazioni di interesse",
  gara: "Gare",
};

export interface RegionSummary {
  region: string;
  enabled: boolean;
  recipients: string | null;
  last_digest_at: string | null;
  comuni: number;
  ok: number;
  failing: number;
  unchecked: number;
  regional_sites: number;
  pre_gara: number;
  manifestazione_interesse: number;
  gara: number;
  da_notificare: number;
}

export interface RegionComune {
  id: string;
  ente: string;
  provincia: string | null;
  tipo: string | null;
  siti: { ruolo: string; url: string }[];
  stato: "ok" | "failing" | "unchecked";
  last_error: string | null;
  consecutive_failures: number;
  last_scan_at: string | null;
  last_success_at: string | null;
  active: boolean;
}

export interface RegionSite {
  id: string;
  nome: string;
  url: string;
  ruolo: string | null;
  active: boolean;
  last_checked_at: string | null;
  ultimo_run: { status: string; errore: string | null; found: number; at: string } | null;
}

export interface RegionRecord {
  id: string;
  categoria: Categoria;
  ente: string;
  descrizione: string | null;
  link: string;
  scadenza: string | null;
  stato: string;
  first_seen_at: string;
  notificato: boolean;
  score: number | null;
}

export interface RegionDetail {
  region: string;
  enabled: boolean;
  recipients: string | null;
  last_digest_at: string | null;
  comuni: RegionComune[];
  siti_regionali: RegionSite[];
  records: RegionRecord[];
}

export interface Level1Source {
  id: string;
  nome: string;
  url: string;
  active: boolean;
  affidabilita: number;
  last_checked_at: string | null;
  raw_7gg: number;
  ultimo_run: { status: string; found: number; valid: number; errore: string | null; at: string } | null;
}

export interface Level1Overview {
  fonti: Level1Source[];
  record_assegnati_a_regione: number;
  record_senza_regione: number;
}

export const STATO_LABEL = { ok: "raggiungibile", failing: "non raggiungibile", unchecked: "non verificato" } as const;
export const STATO_CLASS = {
  ok: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  failing: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  unchecked: "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300",
} as const;
