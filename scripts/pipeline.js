/**
 * PIPELINE MONITORAGGIO PROCUREMENT – ILLUMINAZIONE PUBBLICA
 * v4.0 – Sistema multi-agente token-efficiente
 *
 * ARCHITETTURA:
 *   Fase 1 – Connettori diretti (0 token):
 *     - ANAC REST API (dataset appalti aperti)
 *     - TED API (bandi europei)
 *     - GURI RSS (Gazzetta Ufficiale, serie contratti)
 *     - Albo Pretorio scraper per enti in watchlist
 *     - Feed RSS stampa specializzata
 *   Fase 2 – Elaborazione deterministica (0 token):
 *     normalizzazione + deduplica + classificazione + scoring
 *   Fase 3 – Chiamate AI Haiku (2 sole):
 *     Call #1 – classifica ~20% record ambigui
 *     Call #2 – genera report giornaliero
 *   Fase 4 – Output + auto-arricchimento fonti + storico KPI
 */

import fetch from "node-fetch";
import fs    from "fs";
import path  from "path";
import { XMLParser } from "fast-xml-parser";
import { fileURLToPath } from "url";

// ── Costanti globali ─────────────────────────────────────────────────────────
const __dir = path.dirname(fileURLToPath(import.meta.url));
const ROOT  = path.resolve(__dir, "..");
const ISO   = new Date().toISOString().slice(0, 10);
const DT    = new Date().toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" });
const KEY   = process.env.ANTHROPIC_API_KEY || "";
const DEV   = process.argv.includes("--dev");

const STATE_DIR    = path.join(ROOT, "state");
const DOCS_DIR     = path.join(ROOT, "docs");
const REPORTS_DIR  = path.join(ROOT, "reports");
const WATCHLIST_FP = path.join(__dir, "watchlist.json");
const SOURCES_FP   = path.join(STATE_DIR, "sources.json");
const KPI_HIST_FP  = path.join(STATE_DIR, "kpi_history.json");
const SEEN_FP      = path.join(STATE_DIR, "seen.json");

const HTTP_TIMEOUT = 25000;
const UA           = "Mozilla/5.0 (compatible; IlluminazioneMonitor/4.0; +https://github.com/andreaavenoso-glitch/illuminazione-monitor)";

if (!KEY) { console.error("❌ ANTHROPIC_API_KEY mancante"); process.exit(1); }

// ── Utility ──────────────────────────────────────────────────────────────────
const log = (m) => console.log(`[${new Date().toTimeString().slice(0, 8)}] ${m}`);
const dbg = (m) => { if (DEV) console.log(`  · ${m}`); };
const slp = (ms) => new Promise((r) => setTimeout(r, ms));

function ensureDir(p) { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); }
function readJson(fp, fallback) {
  try { return JSON.parse(fs.readFileSync(fp, "utf8")); } catch { return fallback; }
}
function writeJson(fp, obj) {
  ensureDir(path.dirname(fp));
  fs.writeFileSync(fp, JSON.stringify(obj, null, 2), "utf8");
}
function parseDate(s) {
  if (!s || s === "n.d.") return null;
  const m = String(s).match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})/);
  if (m) return new Date(+m[3], +m[2] - 1, +m[1]);
  const d = new Date(s);
  return isNaN(d) ? null : d;
}
function daysUntil(s) {
  const d = parseDate(s);
  return d ? Math.ceil((d - new Date(ISO)) / 864e5) : null;
}
function parseImporto(v) {
  if (v == null) return 0;
  if (typeof v === "number") return v;
  const s = String(v).replace(/[€\s]/g, "").replace(/\.(?=\d{3})/g, "").replace(",", ".");
  const n = parseFloat(s);
  return isNaN(n) ? 0 : n;
}
function stripHtml(s) {
  return String(s || "").replace(/<[^>]+>/g, " ").replace(/&[a-z]+;/gi, " ").replace(/\s+/g, " ").trim();
}
function slug(s) {
  return String(s || "").toLowerCase().replace(/[àáä]/g, "a").replace(/[èéë]/g, "e").replace(/[ìíï]/g, "i").replace(/[òóö]/g, "o").replace(/[ùúü]/g, "u").replace(/[^a-z0-9]+/g, "-");
}

async function httpGet(url, opts = {}) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), opts.timeout || HTTP_TIMEOUT);
  try {
    const r = await fetch(url, {
      signal: ctrl.signal,
      headers: { "User-Agent": UA, "Accept": opts.accept || "*/*", ...(opts.headers || {}) },
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return opts.json ? await r.json() : await r.text();
  } finally { clearTimeout(to); }
}

// ── Chiamata API Anthropic (solo Haiku) ──────────────────────────────────────
async function callAI(prompt, opts = {}) {
  const {
    model = "claude-haiku-4-5-20251001",
    maxTokens = 1400,
  } = opts;

  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type":      "application/json",
      "x-api-key":         KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({ model, max_tokens: maxTokens, messages: [{ role: "user", content: prompt }] }),
  });
  const d = await r.json();
  if (d.error) throw new Error(`${d.error.type}: ${d.error.message}`);
  const text = (d.content || []).filter((b) => b.type === "text").map((b) => b.text).join("\n");
  const usage = d.usage || {};
  return { text, tokens: (usage.input_tokens || 0) + (usage.output_tokens || 0) };
}

function pj(txt) {
  if (!txt) return null;
  txt = txt.replace(/```[\w]*\n?|```/g, "").trim();
  try { return JSON.parse(txt); } catch {}
  const ai = txt.indexOf("["), aj = txt.lastIndexOf("]");
  if (ai > -1 && aj > ai) { try { return JSON.parse(txt.slice(ai, aj + 1)); } catch {} }
  const oi = txt.indexOf("{"), oj = txt.lastIndexOf("}");
  if (oi > -1 && oj > oi) { try { return JSON.parse(txt.slice(oi, oj + 1)); } catch {} }
  return null;
}

// ── Perimetro tematico ───────────────────────────────────────────────────────
const KW_IN = [
  "illuminazione pubblica", "pubblica illuminazione", "relamping", "telegestione",
  "telecontrollo", "smart lighting", "smart city", "riqualificazione illuminazione",
  "pali illuminazione", "global service illuminazione", "accordo quadro illuminazione",
  "efficientamento energetico illuminazione", "led illuminazione", "punti luce",
  "impianti illuminazione", "lampione", "lampioni", "street lighting",
  "public lighting", "luce pubblica", "illuminazione stradale",
  "manutenzione illuminazione", "gestione illuminazione", "concessione illuminazione",
];
const KW_EX = [
  "illuminazione interna", "impianto elettrico generico", "facility management",
  "climatizzazione", "illuminazione votiva", "illuminazione scenica",
  "illuminazione domestica", "lampada da tavolo",
];
const CPV_LIGHT = [
  "34928500", "34928510", "34928520", "34928530",
  "45316110", "45316000", "45316100",
  "50232000", "50232100", "50232110",
  "31500000", "31520000", "31527200", "31527260",
  "31518000", "31518100", "31518200", "31518600",
  "71314100", "71323100",
];

// ── AGENTE 1 · Connettore ANAC (dataset appalti) ─────────────────────────────
async function agenteAnac() {
  log("→ Agente 1 · ANAC dataset appalti");
  const out = [];
  const endpoints = [
    "https://dati.anticorruzione.it/opendata/api/v1/rest/dataset/ocds-appalti-ordinari-2024/dataset",
    "https://dati.anticorruzione.it/opendata/api/v1/rest/dataset/ocds-appalti-ordinari-2025/dataset",
    "https://dati.anticorruzione.it/opendata/api/v1/rest/dataset/ocds-appalti-ordinari-2026/dataset",
  ];
  for (const url of endpoints) {
    try {
      dbg(`ANAC → ${url}`);
      const data = await httpGet(url, { json: true, timeout: 20000 });
      const items = Array.isArray(data) ? data : (data.releases || data.records || data.data || []);
      for (const it of items.slice(0, 200)) {
        const t = it.tender || it;
        const obj = String(t.title || t.oggetto || "").toLowerCase();
        const cpvHit = (t.mainProcurementCategory || t.classification?.id || "").toString();
        const kwHit = KW_IN.some((k) => obj.includes(k));
        const cpvOk = CPV_LIGHT.some((c) => cpvHit.startsWith(c));
        if (!kwHit && !cpvOk) continue;
        out.push({
          ente:         it.buyer?.name || t.procuringEntity?.name || "n.d.",
          oggetto_raw:  t.title || t.oggetto || "n.d.",
          importo_raw:  t.value?.amount || t.importo || 0,
          cig_raw:      it.ocid?.replace(/^ocds-\w+-/, "") || t.cig || "n.d.",
          scadenza_raw: t.tenderPeriod?.endDate || t.dataScadenza || "n.d.",
          procedura_raw: t.procurementMethod || t.procedura || "n.d.",
          link_bando:   t.documents?.[0]?.url || it.url || "https://dati.anticorruzione.it",
          fonte_id:     "ANAC",
          regione:      it.buyer?.address?.region || t.regione || "n.d.",
          data_pub:     t.datePublished || it.date || ISO,
          note_estrazione: "connettore ANAC diretto",
        });
      }
      log(`  ✓ ANAC ${url.split("/").slice(-2, -1)}: ${items.length} totali, +${out.length} in perimetro`);
    } catch (e) {
      dbg(`ANAC errore ${url}: ${e.message}`);
    }
  }
  log(`✓ Agente ANAC: ${out.length} record`);
  return out;
}

// ── AGENTE 2 · Connettore TED (bandi UE) ─────────────────────────────────────
async function agenteTed() {
  log("→ Agente 2 · TED bandi europei");
  const out = [];
  const url = "https://api.ted.europa.eu/v3/notices/search";
  const body = {
    query: `(classification-cpv IN (${CPV_LIGHT.map((c) => `"${c}"`).join(",")})) AND (place-of-performance = "ITA") AND (publication-date >= today(-60))`,
    fields: [
      "publication-number", "notice-title", "buyer-name", "buyer-city",
      "buyer-country", "total-value", "deadline-receipt-tender-date-lot",
      "procedure-type", "links", "publication-date", "cpv",
    ],
    limit: 60,
    scope: "ACTIVE",
    onlyLatestVersions: true,
  };
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "User-Agent": UA, "Accept": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const notices = data.notices || data.results || [];
    for (const n of notices) {
      const title = n["notice-title"]?.ita || n["notice-title"]?.eng || n["notice-title"] || "n.d.";
      out.push({
        ente:          n["buyer-name"]?.[0] || "n.d.",
        oggetto_raw:   typeof title === "object" ? Object.values(title)[0] : title,
        importo_raw:   n["total-value"]?.[0]?.value || 0,
        cig_raw:       n["publication-number"] || "n.d.",
        scadenza_raw:  n["deadline-receipt-tender-date-lot"]?.[0] || "n.d.",
        procedura_raw: n["procedure-type"] || "n.d.",
        link_bando:    n.links?.pdf?.ita || n.links?.html?.ita || `https://ted.europa.eu/en/notice/-/detail/${n["publication-number"]}`,
        fonte_id:      "TED",
        regione:       n["buyer-city"]?.[0] || "n.d.",
        data_pub:      n["publication-date"] || ISO,
        note_estrazione: "connettore TED diretto",
      });
    }
    log(`✓ Agente TED: ${out.length} record`);
  } catch (e) {
    log(`  ⚠ TED errore: ${e.message} – provo fallback RSS`);
    try {
      const rss = await httpGet("https://ted.europa.eu/en/rss/latest", { timeout: 15000 });
      const parser = new XMLParser({ ignoreAttributes: false });
      const j = parser.parse(rss);
      const items = j?.rss?.channel?.item || [];
      for (const it of items.slice(0, 30)) {
        const title = stripHtml(it.title);
        if (!KW_IN.some((k) => title.toLowerCase().includes(k))) continue;
        out.push({
          ente: "n.d.", oggetto_raw: title, importo_raw: 0, cig_raw: "n.d.",
          scadenza_raw: "n.d.", procedura_raw: "n.d.", link_bando: it.link || "",
          fonte_id: "TED", regione: "n.d.", data_pub: it.pubDate || ISO,
          note_estrazione: "TED RSS fallback",
        });
      }
      log(`✓ TED RSS fallback: ${out.length} record`);
    } catch (e2) { log(`  ✗ TED fallback fallito: ${e2.message}`); }
  }
  return out;
}

// ── AGENTE 3 · Connettore GURI (Gazzetta Ufficiale) ─────────────────────────
async function agenteGuri() {
  log("→ Agente 3 · GURI Gazzetta Ufficiale contratti");
  const out = [];
  const feeds = [
    "https://www.gazzettaufficiale.it/rss/S_C.xml",
    "https://www.gazzettaufficiale.it/rss/S_5.xml",
    "https://www.gazzettaufficiale.it/rss/serie_generale.xml",
  ];
  const parser = new XMLParser({ ignoreAttributes: false });
  for (const url of feeds) {
    try {
      const xml = await httpGet(url, { timeout: 15000, accept: "application/rss+xml" });
      const j = parser.parse(xml);
      const items = j?.rss?.channel?.item || j?.feed?.entry || [];
      const arr = Array.isArray(items) ? items : [items];
      for (const it of arr) {
        const title = stripHtml(it.title?.["#text"] || it.title);
        const desc  = stripHtml(it.description || it.summary);
        const low   = (title + " " + desc).toLowerCase();
        if (!KW_IN.some((k) => low.includes(k))) continue;
        if (KW_EX.some((k) => low.includes(k))) continue;
        out.push({
          ente:          "Gazzetta Ufficiale",
          oggetto_raw:   title,
          importo_raw:   0,
          cig_raw:       "n.d.",
          scadenza_raw:  "n.d.",
          procedura_raw: "n.d.",
          link_bando:    it.link || it.guid || url,
          fonte_id:      "GURI",
          regione:       "n.d.",
          data_pub:      it.pubDate || it.published || ISO,
          note_estrazione: "GURI RSS",
        });
      }
      dbg(`GURI ${url}: cumulativo ${out.length}`);
    } catch (e) { dbg(`GURI errore ${url}: ${e.message}`); }
  }
  log(`✓ Agente GURI: ${out.length} record`);
  return out;
}

// ── AGENTE 4 · Scraper Albo Pretorio degli enti in watchlist ────────────────
async function agenteAlbo(watchlist) {
  log(`→ Agente 4 · Scraper Albo Pretorio (${watchlist.length} enti)`);
  const out = [];
  const CHUNK = 8;
  for (let i = 0; i < watchlist.length; i += CHUNK) {
    const batch = watchlist.slice(i, i + CHUNK);
    const results = await Promise.allSettled(batch.map(async (w) => {
      try {
        const html = await httpGet(w.url, { timeout: 12000 });
        const text = stripHtml(html).toLowerCase();
        const found = [];
        for (const kw of KW_IN) {
          const idx = text.indexOf(kw);
          if (idx === -1) continue;
          const ctx = text.slice(Math.max(0, idx - 80), Math.min(text.length, idx + 200));
          if (KW_EX.some((k) => ctx.includes(k))) continue;
          found.push({ kw, ctx });
          if (found.length >= 3) break;
        }
        for (const f of found) {
          out.push({
            ente:          w.ente,
            oggetto_raw:   f.ctx.slice(0, 140),
            importo_raw:   0,
            cig_raw:       "n.d.",
            scadenza_raw:  "n.d.",
            procedura_raw: "n.d.",
            link_bando:    w.url,
            fonte_id:      "Albo",
            regione:       w.regione || "n.d.",
            data_pub:      ISO,
            note_estrazione: `albo scraper: match "${f.kw}"`,
          });
        }
      } catch (e) { dbg(`Albo ${w.ente}: ${e.message}`); }
    }));
    dbg(`Albo batch ${i / CHUNK + 1}: ${results.filter((r) => r.status === "fulfilled").length}/${batch.length} ok, cumulativo ${out.length}`);
  }
  log(`✓ Agente Albo: ${out.length} record`);
  return out;
}

// ── AGENTE 5 · Feed stampa specializzata / notizie di settore ───────────────
async function agenteStampa() {
  log("→ Agente 5 · Stampa specializzata (segnali pre-gara)");
  const out = [];
  const feeds = [
    "https://www.infobuildenergia.it/feed/",
    "https://www.quotidianoenergia.it/rss/QE",
    "https://www.edilportale.com/rss/news.xml",
    "https://www.appaltiecontratti.it/feed/",
    "https://www.lucedintorno.it/feed/",
  ];
  const parser = new XMLParser({ ignoreAttributes: false });
  for (const url of feeds) {
    try {
      const xml = await httpGet(url, { timeout: 12000, accept: "application/rss+xml" });
      const j = parser.parse(xml);
      const items = j?.rss?.channel?.item || j?.feed?.entry || [];
      const arr = Array.isArray(items) ? items : [items];
      for (const it of arr.slice(0, 40)) {
        const title = stripHtml(it.title?.["#text"] || it.title);
        const desc  = stripHtml(it.description || it.summary || it.content);
        const low   = (title + " " + desc).toLowerCase();
        if (!KW_IN.some((k) => low.includes(k))) continue;
        if (KW_EX.some((k) => low.includes(k))) continue;
        const forte = /delibera|determina|aggiudica|approva|bando|gara/.test(low);
        out.push({
          ente:          "Stampa di settore",
          oggetto_raw:   title,
          importo_raw:   0,
          cig_raw:       "n.d.",
          scadenza_raw:  "n.d.",
          procedura_raw: "n.d.",
          link_bando:    it.link || it.guid || url,
          fonte_id:      "Stampa",
          regione:       "n.d.",
          data_pub:      it.pubDate || it.published || ISO,
          atto_tipo:     /delibera|determina/.test(low) ? "delibera" : "notizia",
          pre_gara_forza: forte ? "forte" : "debole",
          note_estrazione: `stampa RSS · ${new URL(url).hostname}`,
        });
      }
    } catch (e) { dbg(`Stampa errore ${url}: ${e.message}`); }
  }
  log(`✓ Agente Stampa: ${out.length} record`);
  return out;
}

// ── AGENTE 6 · Auto-arricchimento fonti (scoperta nuovi enti) ───────────────
function agenteAutoEnrich(records, watchlist) {
  log("→ Agente 6 · Auto-arricchimento watchlist");
  const known = new Set(watchlist.map((w) => slug(w.ente)));
  const scoperti = new Map();
  for (const r of records) {
    const ente = (r.ente || "").trim();
    if (!ente || ente === "n.d." || ente.length < 4) continue;
    const s = slug(ente);
    if (known.has(s)) continue;
    const cur = scoperti.get(s) || { ente, url: r.link_bando, regione: r.regione, count: 0 };
    cur.count++;
    scoperti.set(s, cur);
  }
  const nuovi = [...scoperti.values()].filter((x) => x.count >= 2 && x.url && x.url.startsWith("http"))
    .map((x) => ({ ente: x.ente, url: x.url, regione: x.regione || "n.d.", added_on: ISO, auto_discovered: true }));
  if (nuovi.length) log(`  ✓ Scoperti ${nuovi.length} nuovi enti (auto-aggiunti alla watchlist)`);
  return nuovi;
}

// ── FASE 2: normalizzazione + deduplica + classificazione + scoring ─────────
function normalize(r, i) {
  const obj = (r.oggetto_raw || r.oggetto || "").toLowerCase();
  const all = JSON.stringify(r).toLowerCase();
  if (!KW_IN.some((k) => obj.includes(k))) return null;
  if (KW_EX.some((k) => obj.includes(k))) return null;
  const pnrr = /pnrr|pnc|react[\s.-]?eu|fondi europei|next[\s.-]?generation/.test(all);
  const ppp  = /ppp|concessione|project[\s.-]?fin|partenariato/.test(obj + " " + (r.procedura_raw || ""));
  const imp  = parseImporto(r.importo_raw);
  const cig  = String(r.cig_raw || "n.d.").trim().toUpperCase();
  const cigOk = /^[A-Z0-9]{8,10}$/.test(cig);
  const tags = [];
  if (/led|relamp/.test(obj)) tags.push("LED");
  if (/telegest/.test(obj))   tags.push("telegestione");
  if (/telecontr/.test(obj))  tags.push("telecontrollo");
  if (/smart[\s-]?light|smart[\s-]?city/.test(obj)) tags.push("smart lighting");
  if (/global[\s-]?serv/.test(obj)) tags.push("global service");
  if (/accordo[\s-]?quad/.test(obj)) tags.push("accordo quadro");
  if (/manuten|gestione/.test(obj))  tags.push("manutenzione");
  if (/proroga/.test(obj))    tags.push("proroga");
  if (/efficient/.test(obj))  tags.push("efficientamento");
  if (pnrr) tags.push("PNRR");
  if (ppp)  tags.push("PPP");
  if (imp > 5538000) tags.push("sopra soglia UE");
  return {
    record_id:         `R-${ISO}-${String(i + 1).padStart(4, "0")}`,
    ente:              (r.ente || "n.d.").trim(),
    oggetto:           (r.oggetto_raw || r.oggetto || "n.d.").replace(/\s+/g, " ").trim(),
    importo_iva_escl:  imp || "n.d.",
    importo_stimato:   !imp,
    cig:               cigOk ? cig : "n.d.",
    data_scadenza:     r.scadenza_raw || "n.d.",
    data_pubblicazione: r.data_pub || ISO,
    procedura:         r.procedura_raw || "n.d.",
    fonte_principale:  r.fonte_id || "n.d.",
    link_bando:        r.link_bando || "n.d.",
    regione:           r.regione || "n.d.",
    atto_tipo:         r.atto_tipo || null,
    pre_gara_forza:    r.pre_gara_forza || null,
    flag_pnrr:         pnrr,
    flag_ppp:          ppp,
    flag_sopra_soglia_ue: imp > 5538000,
    flag_anomalia:     false,
    tag_tecnico:       tags,
    livello_validazione: cigOk ? "L3" : "L2",
    confidence_score:  cigOk ? 0.85 : 0.65,
    last_updated_at:   new Date().toISOString(),
    note_operative:    r.note_estrazione || "",
    storico_eventi:    [],
  };
}

function dedup(arr) {
  const seen = new Map();
  const out = [];
  let rm = 0;
  for (const r of arr) {
    const ib = typeof r.importo_iva_escl === "number" ? Math.round(r.importo_iva_escl / 50000) * 50000 : "x";
    const k = r.cig && r.cig !== "n.d."
      ? "cig:" + r.cig
      : "eo:" + r.ente.slice(0, 28).toLowerCase() + "|" + r.oggetto.slice(0, 38).toLowerCase() + "|" + ib;
    if (seen.has(k)) rm++; else { seen.set(k, 1); out.push(r); }
  }
  return { out, rm };
}

function classifyDet(r) {
  const a = (r.oggetto || "").toLowerCase() + " " + (r.note_operative || "").toLowerCase();
  if (r.atto_tipo && r.atto_tipo !== "notizia") return { s: "PRE-GARA", t: "segnale_pre_gara" };
  if (/esito|aggiudic|revoca|deserta|annullat/.test(a))       return { s: "ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA", t: "nuovo_oggi" };
  if (/proroga|rettifica|chiariment/.test(a))                 return { s: "RETTIFICA-PROROGA-CHIARIMENTI",       t: "aggiornamento_gara_nota" };
  if (r.cig !== "n.d." && r.link_bando !== "n.d.")            return { s: "GARA PUBBLICATA",                     t: "nuovo_oggi" };
  if (r.confidence_score < 0.70)                              return { s: "GARA PUBBLICATA",                     t: "evidenza_debole" };
  return null;
}

function scoreRecord(r) {
  let s = 0;
  const imp = typeof r.importo_iva_escl === "number" ? r.importo_iva_escl : 0;
  if      (imp > 10e6) s += 35;
  else if (imp > 5e6)  s += 28;
  else if (imp > 2e6)  s += 20;
  else if (imp > 1e6)  s += 14;
  else if (imp > 5e5)  s += 8;
  else                 s += 3;
  const st = r.stato_procedurale || "";
  if      (st === "GARA PUBBLICATA")       s += 25;
  else if (st.startsWith("RETTIFICA"))     s += 20;
  else if (st === "PRE-GARA")              s += r.pre_gara_forza === "forte" ? 20 : 8;
  else if (st.startsWith("ESITO"))         s += 10;
  const d = daysUntil(r.data_scadenza);
  if (d !== null) {
    if      (d <= 3)  s += 20;
    else if (d <= 7)  s += 15;
    else if (d <= 15) s += 10;
    else if (d <= 30) s += 5;
  }
  if (r.flag_ppp)             s += 8;
  if (r.flag_pnrr)            s += 6;
  if (r.flag_sopra_soglia_ue) s += 4;
  if ((r.tag_tecnico || []).some((t) => /accordo|global/.test(t))) s += 3;
  let p = "P4";
  if      (s >= 70 || (imp > 5e6 && st === "GARA PUBBLICATA") || (d !== null && d >= 0 && d <= 2)) p = "P1";
  else if (s >= 50) p = "P2";
  else if (s >= 30) p = "P3";
  return { ...r, score_commerciale: s, priorita_commerciale: p };
}

// ── AGENTE 7 · Classificatore AI Haiku (record ambigui) ─────────────────────
async function agenteClassifierAI(ambigui) {
  if (!ambigui.length) return { assegnati: [], tokens: 0 };
  log(`→ Agente 7 · Classificatore AI Haiku (${ambigui.length} record ambigui)`);
  const pay = ambigui.map((r) => ({ id: r.record_id, e: r.ente.slice(0, 20), o: r.oggetto.slice(0, 55) }));
  const { text, tokens } = await callAI(
    `Classifica record procurement illuminazione pubblica italiana.
STATI ammessi: GARA PUBBLICATA | PRE-GARA | RETTIFICA-PROROGA-CHIARIMENTI | ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA
TIPI ammessi:  nuovo_oggi | segnale_pre_gara | aggiornamento_gara_nota | evidenza_debole

Input (id, ente, oggetto):
${JSON.stringify(pay)}

Rispondi SOLO con JSON array (nessun testo attorno):
[{"record_id":"...","stato_procedurale":"...","tipo_novita":"..."}]`,
    { maxTokens: 900 }
  );
  const j = pj(text);
  const mp = new Map((Array.isArray(j) ? j : []).map((c) => [c.record_id, c]));
  const assegnati = ambigui.map((r) => {
    const c = mp.get(r.record_id);
    return c
      ? { ...r, stato_procedurale: c.stato_procedurale, tipo_novita: c.tipo_novita }
      : { ...r, stato_procedurale: "GARA PUBBLICATA", tipo_novita: "nuovo_oggi" };
  });
  log(`  ✓ AI Haiku classifier: ${tokens} token`);
  return { assegnati, tokens };
}

// ── AGENTE 8 · Reporter AI Haiku ────────────────────────────────────────────
async function agenteReporterAI(scored, kpi) {
  log("→ Agente 8 · Reporter AI Haiku");
  const fE = (v) => v && v !== "n.d." ? "€" + Number(v).toLocaleString("it-IT") : "n.d.";
  const top = scored.slice().sort((a, b) => b.score_commerciale - a.score_commerciale).slice(0, 8);
  const gareStr = top.length
    ? top.map((r) => `[${r.priorita_commerciale}] ${r.ente} | ${r.oggetto.slice(0, 55)} | ${fE(r.importo_iva_escl)} | ${r.stato_procedurale} | scad:${r.data_scadenza}`).join("\n")
    : "Nessuna gara trovata oggi.";
  const { text, tokens } = await callAI(
    `Scrivi un report giornaliero Markdown sul procurement dell'illuminazione pubblica italiana.

Top gare rilevate:
${gareStr}

KPI: gare attive=${kpi.gare_attive}, pre-gara=${kpi.pre_gara}, P1=${kpi.priorita_p1}, totale=${kpi.record_totali}, valore=€${(kpi.valore_totale_eur / 1e6).toFixed(1)}M

Struttura obbligatoria (max 350 parole, tono professionale, in italiano):
# Report · Illuminazione pubblica · ${DT}
## A. Nuove gare pubblicate
## B. Segnali pre-gara
## C. Osservazioni rilevanti (rischi, opportunità, trend)
## Cruscotto
|KPI|Valore|
|---|---|
|Gare attive|${kpi.gare_attive}|
|Pre-gara|${kpi.pre_gara}|
|Priorità P1|${kpi.priorita_p1}|
|Record totali|${kpi.record_totali}|
|Valore monitorato|€${(kpi.valore_totale_eur / 1e6).toFixed(1)}M|`,
    { maxTokens: 1400 }
  );
  log(`  ✓ AI Haiku reporter: ${tokens} token, ${text.length} char`);
  return { text, tokens };
}

// ── MAIN – Orchestrazione multi-agente ──────────────────────────────────────
async function main() {
  const t0 = Date.now();
  ensureDir(STATE_DIR);
  ensureDir(DOCS_DIR);
  ensureDir(REPORTS_DIR);

  log("═══════════════════════════════════════════════");
  log(` PIPELINE ILLUMINAZIONE v4.0 – ${ISO}`);
  log(" Multi-agente · connettori diretti + 2 call Haiku");
  log("═══════════════════════════════════════════════");

  const watchlist = readJson(WATCHLIST_FP, []);
  log(`▷ Watchlist: ${watchlist.length} enti monitorati`);

  // ── FASE 1: Raccolta parallela via agenti connettori ──
  log("\n▶ FASE 1 — Raccolta multi-fonte (agenti in parallelo)");
  const [anacData, tedData, guriData, alboData, stampaData] = await Promise.all([
    agenteAnac().catch((e) => { log(`  ✗ ANAC: ${e.message}`); return []; }),
    agenteTed().catch((e) => { log(`  ✗ TED: ${e.message}`); return []; }),
    agenteGuri().catch((e) => { log(`  ✗ GURI: ${e.message}`); return []; }),
    agenteAlbo(watchlist).catch((e) => { log(`  ✗ Albo: ${e.message}`); return []; }),
    agenteStampa().catch((e) => { log(`  ✗ Stampa: ${e.message}`); return []; }),
  ]);
  const raw = [...anacData, ...tedData, ...guriData, ...alboData, ...stampaData];
  log(`\n▷ Grezzi totali: ${raw.length}  (ANAC:${anacData.length} TED:${tedData.length} GURI:${guriData.length} Albo:${alboData.length} Stampa:${stampaData.length})`);

  // ── FASE 2: Elaborazione deterministica ──
  log("\n▶ FASE 2 — Elaborazione deterministica");
  const normed = raw.map((r, i) => normalize(r, i)).filter(Boolean);
  log(`✓ Nel perimetro: ${normed.length}/${raw.length}`);
  const { out, rm } = dedup(normed);
  if (rm) log(`✓ Deduplica: rimossi ${rm}`);
  log(`✓ Record unici: ${out.length}`);

  const pre = [], amb = [];
  out.forEach((r) => {
    const c = classifyDet(r);
    if (c) pre.push({ ...r, stato_procedurale: c.s, tipo_novita: c.t });
    else amb.push(r);
  });
  log(`✓ Classificati deterministicamente: ${pre.length} · ambigui per AI: ${amb.length}`);

  // ── FASE 3: AI Haiku (call #1: classifier) ──
  let classified = [...pre];
  let tokensClass = 0;
  if (amb.length > 0) {
    try {
      await slp(1500);
      const { assegnati, tokens } = await agenteClassifierAI(amb);
      classified = classified.concat(assegnati);
      tokensClass = tokens;
    } catch (e) {
      log(`  ⚠ Classifier AI errore: ${e.message}`);
      amb.forEach((r) => classified.push({ ...r, stato_procedurale: "GARA PUBBLICATA", tipo_novita: "nuovo_oggi" }));
    }
  }
  const scored = classified.map(scoreRecord);
  const nP1 = scored.filter((r) => r.priorita_commerciale === "P1").length;
  const nP2 = scored.filter((r) => r.priorita_commerciale === "P2").length;
  const nP3 = scored.filter((r) => r.priorita_commerciale === "P3").length;
  log(`✓ Scoring: P1=${nP1} P2=${nP2} P3=${nP3} P4=${scored.length - nP1 - nP2 - nP3}`);

  // ── KPI ──
  const nGare = scored.filter((r) => r.stato_procedurale === "GARA PUBBLICATA").length;
  const nPreg = scored.filter((r) => r.stato_procedurale === "PRE-GARA").length;
  const totVal = scored.reduce((a, r) => a + (typeof r.importo_iva_escl === "number" ? r.importo_iva_escl : 0), 0);
  const kpi = {
    record_totali:     scored.length,
    gare_attive:       nGare,
    pre_gara:          nPreg,
    priorita_p1:       nP1,
    priorita_p2:       nP2,
    priorita_p3:       nP3,
    valore_totale_eur: totVal,
    ai_calls:          0,
    token_stimati:     0,
    fonti_attive:      new Set(scored.map((r) => r.fonte_principale)).size,
  };

  // ── FASE 3: AI Haiku (call #2: reporter) ──
  log("\n▶ FASE 3 — Generazione report");
  let report = `# Report · Illuminazione pubblica · ${DT}\n\nNessuna gara rilevata oggi.`;
  let tokensRep = 0;
  try {
    await slp(1500);
    const { text, tokens } = await agenteReporterAI(scored, kpi);
    report = text;
    tokensRep = tokens;
  } catch (e) { log(`  ⚠ Reporter errore: ${e.message}`); }

  kpi.ai_calls = (amb.length > 0 ? 1 : 0) + 1;
  kpi.token_stimati = tokensClass + tokensRep;

  // ── FASE 4: Auto-arricchimento watchlist ──
  log("\n▶ FASE 4 — Auto-arricchimento fonti");
  const nuoviEnti = agenteAutoEnrich(scored, watchlist);
  if (nuoviEnti.length) {
    const merged = [...watchlist, ...nuoviEnti];
    writeJson(WATCHLIST_FP, merged);
    log(`  ✓ Watchlist aggiornata: ${watchlist.length} → ${merged.length}`);
  }

  // ── FASE 5: Storico KPI + tracking record visti ──
  const kpiHist = readJson(KPI_HIST_FP, []);
  kpiHist.push({ date: ISO, ...kpi, durata_run_s: Math.floor((Date.now() - t0) / 1000) });
  const kpiTrim = kpiHist.slice(-180);
  writeJson(KPI_HIST_FP, kpiTrim);

  const seen = readJson(SEEN_FP, {});
  scored.forEach((r) => {
    const k = r.cig !== "n.d." ? r.cig : (slug(r.ente).slice(0, 20) + "-" + slug(r.oggetto).slice(0, 30));
    if (!seen[k]) seen[k] = { first_seen: ISO, ente: r.ente, oggetto: r.oggetto.slice(0, 80) };
    seen[k].last_seen = ISO;
  });
  writeJson(SEEN_FP, seen);

  // ── Sources registry ──
  const sources = readJson(SOURCES_FP, { updated: null, list: [] });
  sources.updated = new Date().toISOString();
  sources.list = [
    { id: "ANAC",   count: anacData.length,   type: "REST API" },
    { id: "TED",    count: tedData.length,    type: "REST API + RSS fallback" },
    { id: "GURI",   count: guriData.length,   type: "RSS Gazzetta Ufficiale" },
    { id: "Albo",   count: alboData.length,   type: `scraper (${watchlist.length} enti)` },
    { id: "Stampa", count: stampaData.length, type: "RSS stampa settore" },
  ];
  writeJson(SOURCES_FP, sources);

  // ── FASE 6: Output finale ──
  log("\n▶ FASE 6 — Output");
  const elapsed = Math.floor((Date.now() - t0) / 1000);
  const perSt = {}, perRg = {}, perFonte = {};
  scored.forEach((r) => {
    perSt[r.stato_procedurale || "n.d."] = (perSt[r.stato_procedurale || "n.d."] || 0) + 1;
    if (r.regione && r.regione !== "n.d.") perRg[r.regione] = (perRg[r.regione] || 0) + 1;
    perFonte[r.fonte_principale] = (perFonte[r.fonte_principale] || 0) + 1;
  });
  const json = {
    last_updated:   new Date().toISOString(),
    schema_version: "4.0",
    records:        scored,
    kpi_oggi: {
      ...kpi,
      durata_run_s: elapsed,
      fonte:        "multi_agent_direct",
    },
    gare_scadenza_imminente: scored.filter((r) => {
      const d = daysUntil(r.data_scadenza);
      return d !== null && d >= 0 && d <= 7;
    }),
    anomalie_aperte: scored.filter((r) => r.flag_anomalia),
    per_stato:  perSt,
    per_regione: perRg,
    per_fonte:  perFonte,
    fonti_attive: sources.list,
    storico_kpi: kpiTrim.slice(-30),
  };

  writeJson(path.join(DOCS_DIR, "illuminazione.json"), json);
  fs.writeFileSync(path.join(REPORTS_DIR, `report-${ISO}.md`), report, "utf8");

  log(`✓ docs/illuminazione.json (${scored.length} record)`);
  log(`✓ reports/report-${ISO}.md`);
  log(`✓ state/kpi_history.json (${kpiTrim.length} run)`);
  log(`✓ state/sources.json (${sources.list.length} fonti)`);
  log("\n════════════════════════════════════════════");
  log(` COMPLETATA – ${elapsed}s – ${scored.length} record – €${(totVal / 1e6).toFixed(1)}M`);
  log(` AI: ${kpi.ai_calls} call · ~${kpi.token_stimati} token`);
  log("════════════════════════════════════════════\n");
}

main().catch((e) => { console.error("❌ Errore critico:", e); process.exit(1); });
