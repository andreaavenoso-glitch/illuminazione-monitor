export type Source = {
  id: string;
  name: string;
  source_type: string;
  platform_type: string | null;
  base_url: string;
  sector_scope: string | null;
  priority: string;
  frequency: string;
  reliability_score: string;
  productivity_score: string;
  publication_model: string | null;
  source_priority_rank: number;
  active: boolean;
  last_checked_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Entity = {
  id: string;
  name: string;
  entity_type: string | null;
  region: string | null;
  province: string | null;
  municipality: string | null;
  notes: string | null;
};

export type WatchlistItem = {
  id: string;
  entity_id: string | null;
  source_id: string | null;
  url_gare: string | null;
  url_esiti: string | null;
  url_albo: string | null;
  url_trasparenza: string | null;
  url_determine: string | null;
  frequency: string;
  priority: string;
  reliability_score: string;
  productivity_score: string;
  publication_model: string | null;
  active: boolean;
  last_scan_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ProcurementRecord = {
  id: string;
  ente: string;
  descrizione: string | null;
  importo: string | null;
  regione: string | null;
  provincia: string | null;
  comune: string | null;
  cig: string | null;
  link_bando: string;
  stato_procedurale: string;
  tipo_novita: string;
  scadenza: string | null;
  data_pubblicazione: string | null;
  tipologia_gara_procedura: string | null;
  criterio: string | null;
  macrosettore: string;
  flag_concessione_ambito: string;
  flag_ppp_doppio_oggetto: string;
  flag_in_house_ambito: string;
  flag_om: string;
  flag_pre_gara: string;
  tag_tecnico: string | null;
  validation_level: string | null;
  reliability_index: string | null;
  is_weak_evidence: boolean;
  score_commerciale: number | null;
  priorita_commerciale: string | null;
  dedup_key: string | null;
  master_record_id: string | null;
  first_seen_at: string;
  last_seen_at: string;
};

export type Alert = {
  id: string;
  procurement_record_id: string | null;
  alert_type: string;
  severity: string;
  description: string;
  is_open: boolean;
  opened_at: string;
  closed_at: string | null;
};

export type DashboardKpi = {
  total_records: number;
  total_masters: number;
  gare_pubblicate: number;
  pre_gara: number;
  esito: number;
  rettifica: number;
  weak_evidence: number;
  priority_p1: number;
  priority_p2: number;
  priority_p3: number;
  priority_p4: number;
  alerts_open: number;
  valore_totale_eur: number;
  scadenze_imminenti: number;
  per_regione: Record<string, number>;
  per_stato: Record<string, number>;
  latest_report_date: string | null;
  latest_report_kpi: Record<string, unknown> | null;
};
