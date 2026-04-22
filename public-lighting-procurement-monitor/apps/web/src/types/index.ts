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
  cig: string | null;
  link_bando: string;
  stato_procedurale: string;
  tipo_novita: string;
  scadenza: string | null;
  data_pubblicazione: string | null;
  flag_pre_gara: string;
  flag_om: string;
  flag_ppp_doppio_oggetto: string;
  is_weak_evidence: boolean;
  first_seen_at: string;
};
