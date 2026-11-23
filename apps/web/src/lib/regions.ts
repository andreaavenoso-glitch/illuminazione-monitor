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
  scoperto_da: { comuni: string[]; count: number } | null;
  ultimo_run: { status: string; errore: string | null; found: number; at: string } | null;
}

export interface Referente {
  nome: string;
  ruolo: "sindaco" | "assessore" | "responsabile_tecnico" | "rup" | "ente";
  qualifica: string | null;
  email: string | null;
  telefono: string | null;
  fonte_url: string;
  citazione: string | null;
  stato: "verificato" | "da_confermare";
  verified_at: string;
  data_fonte?: string | null;
  elezione_data?: string | null;
  motivo?: string | null;
}

export interface ReferentiSintesi {
  affidabilita_pct: number;
  etichetta: "certo" | "probabile" | "ipotetico";
  azione: string;
  stampa_url: string;
}

export const RUOLO_LABEL: Record<Referente["ruolo"], string> = {
  sindaco: "Sindaco",
  assessore: "Assessore",
  responsabile_tecnico: "Responsabile tecnico",
  rup: "RUP",
  ente: "PEC ente",
};

export interface PassoChecklist {
  n: number;
  passo: string;
  ok: boolean;
  urls: string[];
  nota: string;
}

export interface RicercaReferenti {
  metodo: string;
  passi: PassoChecklist[];
  passi_ok: number;
  lacune: string[];
  stampa: string | null;
  elezione_data: string | null;
  mandato_scadenza: string | null;
  eseguita_il: string;
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
  scaduto: boolean;
  data_non_verificata?: boolean;
  servizi: string[];
  referenti: Referente[];
  referenti_sintesi?: ReferentiSintesi;
  ricerca?: RicercaReferenti | null;
}

export const SERVIZIO_LABEL: Record<string, string> = {
  illuminazione_pubblica: "Illuminazione pubblica",
  illuminazione_artistica: "Illuminazione artistica",
  piste_ciclabili_pedonali: "Piste ciclabili e pedonali",
  semafori: "Semafori",
  videosorveglianza: "Videosorveglianza",
  relamping_edifici: "Edifici pubblici e scuole",
  fotovoltaico_cer: "Fotovoltaico e CER",
  ricarica_ev: "Ricarica EV",
  connettivita_5g: "5G e telecomunicazioni",
  digital_advertising: "Digital advertising",
  smart_city: "Smart city",
};

export interface RecordDaVerificare {
  id: string;
  categoria: Categoria;
  ente: string;
  descrizione: string;
  link: string;
  first_seen_at: string | null;
  verificato: boolean;
  scadenza?: string | null;
  servizi: string[];
}

export interface RegionDetail {
  scadute_nascoste: number;
  da_verificare: RecordDaVerificare[];
  ultimo_scan: { status: string; errore: string | null; at: string; trovati: number } | null;
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

export interface ScanItemView {
  ente: string;
  status: "queued" | "running" | "done" | "error" | "skipped" | "interrupted";
  started_at: string | null;
  ended_at: string | null;
  duration_s: number | null;
  pages_read: number;
  pages_skipped: number;
  claude_calls: number;
  claude_errors: number;
  cost_usd: number | null;
  records_found: number;
  deepest: number;
  stopped_by: string | null;
  error: string | null;
}

export interface ScanRunView {
  id: string;
  region: string | null;
  status: "running" | "done" | "failed" | "interrupted";
  started_at: string;
  ended_at: string | null;
  elapsed_s: number;
  eta_s: number | null;
  total: number;
  done: number;
  running: number;
  interrupted: number;
  errors: number;
  queued: number;
  limit: number | null;
  error: string | null;
  cost_usd: number | null;
  claude: { status: "unused" | "ok" | "down" | "rules"; error: string | null; calls: number; call_errors: number };
  items: ScanItemView[];
}
