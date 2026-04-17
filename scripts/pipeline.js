/**
 * PIPELINE MONITORAGGIO PROCUREMENT – ILLUMINAZIONE PUBBLICA
 * Versione produzione – Node.js + GitHub Actions
 *
 * Architettura token-efficiente:
 *   Fase 1 – Raccolta:        4 connettori diretti API/RSS   (0 token)
 *   Fase 2 – Elaborazione:    normalizzazione/dedup/scoring  (0 token)
 *   Fase 3 – AI Haiku:        max 2 chiamate per run         (~700 token)
 *   Fase 4 – Output:          JSON + Markdown report         (0 token)
 */

import fetch    from "node-fetch";
import fs       from "fs";
import path     from "path";
import { fileURLToPath } from "url";

const __dir  = path.dirname(fileURLToPath(import.meta.url));
const ROOT   = path.resolve(__dir, "..");
const ISO    = new Date().toISOString().slice(0, 10);
const DT     = new Date().toLocaleDateString("it-IT", { day:"numeric", month:"long", year:"numeric" });
const DEV    = process.argv.includes("--dev");
const KEY    = process.env.ANTHROPIC_API_KEY || "";

if (!KEY) { console.error("❌ ANTHROPIC_API_KEY mancante"); process.exit(1); }

// ─── UTILITIES ────────────────────────────────────────────────────────────────
const log  = (msg) => console.log(`[${new Date().toTimeString().slice(0,8)}] ${msg}`);
const slp  = ms => new Promise(r => setTimeout(r, ms));

function parseDate(s) {
  if (!s || s === "n.d.") return null;
  const m = s.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (m) return new Date(+m[3], +m[2]-1, +m[1]);
  const d = new Date(s);
  return isNaN(d) ? null : d;
}
function daysUntil(s) {
  const d = parseDate(s);
  return d ? Math.ceil((d - new Date(ISO)) / 86400000) : null;
}
function ensureDir(p) { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); }

// ─── FASE 1: CONNETTORI UFFICIALI ─────────────────────────────────────────────

async function fetchANAC() {
  log("→ ANAC REST API /ricercaLotti …");
  const keywords = ["illuminazione pubblica","relamping LED","telegestione illuminazione","smart lighting"];
  const results  = [];

  for (const kw of keywords) {
    try {
      const url = `https://api.anticorruzione.it/api/v1/ricercaLotti?denominazione=${encodeURIComponent(kw)}&stato=pubblicato&page=0&pageSize=20`;
      const r   = await fetch(url, { headers: { Accept: "application/json" }, timeout: 10000 });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d   = await r.json();
      const items = (d.lotti || d.data || []);
      if (items.length) {
        log(`  ✓ ANAC "${kw}": ${items.length} lotti`);
        results.push(...items.map(x => ({
          ente:           x.denominazioneStazioneAppaltante || "n.d.",
          oggetto_raw:    x.oggetto || x.descrizione || "n.d.",
          importo_raw:    String(x.importoTotale || x.importo || 0),
          cig_raw:        x.cig || "n.d.",
          scadenza_raw:   x.dataScadenzaOfferta || "n.d.",
          procedura_raw:  x.modalitaRealizzazione || "n.d.",
          link_bando:     `https://www.anac.gov.it/bandi/${x.cig || ""}`,
          fonte_id:       "ANAC",
          regione:        x.regione || "n.d.",
          data_pub:       x.dataPubblicazione || ISO,
        })));
      }
      await slp(1000); // rispetta rate limit ANAC
    } catch (e) {
      log(`  ⚠ ANAC "${kw}": ${e.message}`);
    }
  }
  log(`✓ ANAC totale: ${results.length} record`);
  return results;
}

async function fetchTED() {
  log("→ TED/GUUE REST API /v3/notices/search …");
  const results = [];
  try {
    const url = "https://api.ted.europa.eu/v3/notices/search?" + new URLSearchParams({
      q:           "illuminazione pubblica OR pubblica illuminazione OR smart lighting",
      countryCode: "IT",
      limit:       "20",
      fields:      "title,buyer,estimatedValue,deadlineForTender,procedureType,noticeId,publicationDate",
    });
    const r = await fetch(url, { headers: { Accept: "application/json" }, timeout: 12000 });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const items = (d.notices || d.results || []);
    log(`✓ TED: ${items.length} notice sopra soglia UE`);
    results.push(...items.map(x => ({
      ente:          (x.buyer || {}).officialName || (x.buyer || {}).name || "n.d.",
      oggetto_raw:   (x.title || {}).text || x.subject || "n.d.",
      importo_raw:   String(x.estimatedValue || 0),
      cig_raw:       "n.d.",
      scadenza_raw:  x.deadlineForTender || "n.d.",
      procedura_raw: x.procedureType || "n.d.",
      link_bando:    `https://ted.europa.eu/notice/${x.noticeId || ""}`,
      fonte_id:      "TED",
      regione:       "n.d.",
      data_pub:      x.publicationDate || ISO,
    })));
  } catch (e) {
    log(`⚠ TED: ${e.message} (nessun record TED in questo run)`);
  }
  return results;
}

async function fetchGURI() {
  log("→ GURI RSS feed …");
  const results = [];
  const KW = ["illuminazione pubblica","relamping","telegestione","smart lighting","pali illuminazione"];
  try {
    // Usa un proxy RSS-to-JSON pubblico (rss2json o similar)
    const rssUrl  = "https://www.gazzettaufficiale.it/rss/contratti.xml";
    const apiUrl  = `https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(rssUrl)}`;
    const r       = await fetch(apiUrl, { timeout: 10000 });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d       = await r.json();
    const items   = (d.items || []).filter(x => KW.some(k => (x.title || "").toLowerCase().includes(k)));
    log(`✓ GURI: ${items.length} atti pertinenti`);
    results.push(...items.map(x => ({
      ente:          "n.d.",
      oggetto_raw:   x.title || "n.d.",
      importo_raw:   "n.d.",
      cig_raw:       "n.d.",
      scadenza_raw:  "n.d.",
      procedura_raw: "n.d.",
      link_bando:    x.link || "n.d.",
      fonte_id:      "GURI",
      regione:       "n.d.",
      data_pub:      (x.pubDate || "").slice(0, 10) || ISO,
      note_estrazione: x.description ? x.description.slice(0, 120) : "",
    })));
  } catch (e) {
    log(`⚠ GURI: ${e.message}`);
  }
  return results;
}

// Albo Pretorio: lista enti in watchlist da file JSON configurabile
async function fetchAlbo() {
  log("→ Albo Pretorio watchlist …");
  const watchlistPath = path.join(ROOT, "scripts", "watchlist.json");
  let watchlist = [];
  try {
    watchlist = JSON.parse(fs.readFileSync(watchlistPath, "utf8"));
    log(`  Watchlist: ${watchlist.length} enti`);
  } catch {
    log("  ⚠ watchlist.json non trovato – usa watchlist di default");
    watchlist = [
      { ente: "Comune di Roma",     url: "https://www.comune.roma.it/albo" },
      { ente: "Comune di Milano",   url: "https://www.comune.milano.it/albo" },
      { ente: "Comune di Napoli",   url: "https://www.comune.napoli.it/albo" },
      { ente: "Comune di Torino",   url: "https://www.comune.torino.it/appalti" },
      { ente: "Comune di Bologna",  url: "https://www.comune.bologna.it/albo" },
      { ente: "Comune di Firenze",  url: "https://www.comune.fi.it/albo" },
      { ente: "Comune di Venezia",  url: "https://www.comune.venezia.it/albo" },
      { ente: "Comune di Palermo",  url: "https://www.comune.palermo.it/albo" },
      { ente: "Comune di Genova",   url: "https://www.comune.genova.it/albo" },
      { ente: "Comune di Bari",     url: "https://www.comune.bari.it/albo" },
    ];
  }

  const KW  = ["illuminazione","relamping","led","telegestione","smart lighting","pali"];
  const KWX = ["illuminazione interna","impianto elettrico","facility"];
  const results = [];

  for (const entry of watchlist) {
    try {
      const r    = await fetch(entry.url, { timeout: 8000, headers: { "User-Agent": "Mozilla/5.0 (compatible; IlluminazioneMonitor/1.0)" } });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const html = await r.text();
      // Estrai tutti i titoli di atti (testo tra tag <a> o <td>)
      const matches = [...html.matchAll(/<(?:a|td|li)[^>]*>([^<]{10,200})<\/(?:a|td|li)>/gi)]
        .map(m => m[1].replace(/\s+/g, " ").trim())
        .filter(t => KW.some(k => t.toLowerCase().includes(k)))
        .filter(t => !KWX.some(k => t.toLowerCase().includes(k)));

      for (const title of matches.slice(0, 3)) {
        results.push({
          ente:          entry.ente,
          oggetto_raw:   title,
          importo_raw:   "n.d.",
          cig_raw:       "n.d.",
          scadenza_raw:  "n.d.",
          procedura_raw: "n.d.",
          link_bando:    entry.url,
          fonte_id:      "Albo Pretorio",
          regione:       entry.regione || "n.d.",
          data_pub:      ISO,
          atto_tipo:     /delibera/.test(title.toLowerCase()) ? "delibera" : /determina/.test(title.toLowerCase()) ? "determina" : null,
          pre_gara_forza: null,
        });
      }
      await slp(500);
    } catch (e) {
      log(`  ⚠ Albo ${entry.ente}: ${e.message}`);
    }
  }
  log(`✓ Albo Pretorio: ${results.length} atti trovati`);
  return results;
}

// ─── FASE 2: PIPELINE DETERMINISTICA ──────────────────────────────────────────

const KW_IN  = ["illuminazione pubblica","pubblica illuminazione","relamping","telegestione","telecontrollo","smart lighting","riqualificazione illuminazione","pali illuminazione","global service illuminazione","accordo quadro illuminazione"];
const KW_EX  = ["illuminazione interna","impianto elettrico generico","facility management","climatizzazione"];

function normalize(r, i) {
  const obj = (r.oggetto_raw || r.oggetto || "").toLowerCase();
  const all  = JSON.stringify(r).toLowerCase();

  // Filtro perimetro
  if (!KW_IN.some(k => obj.includes(k))) return null;
  if (KW_EX.some(k => obj.includes(k)))   return null;

  const pnrr   = /pnrr|pnc|react[\s.-]?eu|m2c3/.test(all);
  const ppp    = /ppp|concessione|project[\s.-]?fin/.test(obj + " " + (r.procedura_raw || ""));
  const rawI   = String(r.importo_raw || 0).replace(/[€\s]/g,"").replace(/\.(?=\d{3})/g,"").replace(",",".");
  const imp    = parseFloat(rawI) || 0;
  const cig    = (r.cig_raw || "n.d.").trim().toUpperCase();
  const cigOk  = /^[A-Z0-9]{8,10}$/.test(cig);

  const tags = [];
  if (/led|relamp/.test(obj))       tags.push("LED");
  if (/telegest/.test(obj))          tags.push("telegestione");
  if (/telecontr/.test(obj))         tags.push("telecontrollo");
  if (/smart[\s-]?light/.test(obj))  tags.push("smart lighting");
  if (/global[\s-]?serv/.test(obj))   tags.push("global service");
  if (/accordo[\s-]?quad/.test(obj))  tags.push("accordo quadro");
  if (/manuten|gestione/.test(obj))   tags.push("manutenzione");
  if (/proroga/.test(obj))            tags.push("proroga");
  if (pnrr)           tags.push("PNRR");
  if (ppp)            tags.push("PPP");
  if (imp > 5538000)  tags.push("sopra soglia UE");

  return {
    record_id:            `R-${ISO}-${String(i+1).padStart(4,"0")}`,
    ente:                 (r.ente || "n.d.").trim(),
    oggetto:              (r.oggetto_raw || r.oggetto || "n.d.").replace(/\s+/g," ").trim(),
    importo_iva_escl:     imp || "n.d.",
    importo_stimato:      !imp,
    cig:                  cigOk ? cig : "n.d.",
    data_scadenza:        r.scadenza_raw || r.data_scadenza || "n.d.",
    data_pubblicazione:   r.data_pub || ISO,
    procedura:            r.procedura_raw || r.procedura || "n.d.",
    fonte_principale:     r.fonte_id || "n.d.",
    link_bando:           r.link_bando || "n.d.",
    regione:              r.regione || "n.d.",
    atto_tipo:            r.atto_tipo || null,
    pre_gara_forza:       r.pre_gara_forza || null,
    flag_pnrr:            pnrr,
    flag_ppp:             ppp,
    flag_sopra_soglia_ue: imp > 5538000,
    flag_anomalia:        false,
    tag_tecnico:          tags,
    livello_validazione:  cigOk ? "L3" : "L2",
    confidence_score:     cigOk ? 0.85 : 0.65,
    last_updated_at:      new Date().toISOString(),
    note_operative:       r.note_estrazione || "",
    storico_eventi:       [],
  };
}

function dedup(arr) {
  const seen = new Map(), out = []; let rm = 0;
  for (const r of arr) {
    const ib = typeof r.importo_iva_escl === "number"
      ? Math.round(r.importo_iva_escl / 50000) * 50000 : "x";
    const k  = r.cig && r.cig !== "n.d."
      ? "cig:" + r.cig
      : "eo:" + r.ente.slice(0,28).toLowerCase() + "|" + r.oggetto.slice(0,38).toLowerCase() + "|" + ib;
    if (seen.has(k)) rm++;
    else { seen.set(k, 1); out.push(r); }
  }
  return { out, rm };
}

function classifyDet(r) {
  const a = (r.oggetto || "").toLowerCase() + " " + (r.note_operative || "").toLowerCase();
  if (r.atto_tipo)                                         return { s:"PRE-GARA",                            t:"segnale_pre_gara" };
  if (/esito|aggiudic|revoca|deserta|annullat/.test(a))   return { s:"ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA", t:"nuovo_oggi" };
  if (/proroga|rettifica|chiariment/.test(a))             return { s:"RETTIFICA-PROROGA-CHIARIMENTI",        t:"aggiornamento_gara_nota" };
  if (r.cig !== "n.d." && r.link_bando !== "n.d.")        return { s:"GARA PUBBLICATA",                     t:"nuovo_oggi" };
  if (r.confidence_score < 0.70)                          return { s:"GARA PUBBLICATA",                     t:"evidenza_debole" };
  return null;
}

function scoreRecord(r) {
  let s = 0;
  const imp = typeof r.importo_iva_escl === "number" ? r.importo_iva_escl : 0;
  if (imp>10e6)s+=35; else if(imp>5e6)s+=28; else if(imp>2e6)s+=20;
  else if(imp>1e6)s+=14; else if(imp>5e5)s+=8; else s+=3;

  const st = r.stato_procedurale || "";
  if (st==="GARA PUBBLICATA")s+=25;
  else if(st.startsWith("RETTIFICA"))s+=20;
  else if(st==="PRE-GARA")s+=r.pre_gara_forza==="forte"?20:8;
  else if(st.startsWith("ESITO"))s+=10;

  const d = daysUntil(r.data_scadenza);
  if (d!==null){if(d<=3)s+=20;else if(d<=7)s+=15;else if(d<=15)s+=10;else if(d<=30)s+=5;}
  if (r.flag_ppp)s+=8; if(r.flag_pnrr)s+=6; if(r.flag_sopra_soglia_ue)s+=4;
  if ((r.tag_tecnico||[]).some(t=>/accordo|global/.test(t)))s+=3;

  let p = "P4";
  if (s>=70||(imp>5e6&&st==="GARA PUBBLICATA")||(d!==null&&d>=0&&d<=2)) p="P1";
  else if(s>=50)p="P2"; else if(s>=30)p="P3";
  return { ...r, score_commerciale:s, priorita_commerciale:p };
}

// ─── FASE 3: AI (MAX 2 CHIAMATE HAIKU) ────────────────────────────────────────

async function aiCall(prompt) {
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method:  "POST",
    headers: { "Content-Type":"application/json", "anthropic-version":"2023-06-01" },
    body: JSON.stringify({
      model:      "claude-haiku-4-5-20251001",
      max_tokens: 1000,
      messages:   [{ role:"user", content:prompt }],
    }),
  });
  const d = await r.json();
  if (d.error) throw new Error(d.error.message);
  return (d.content||[]).filter(b=>b.type==="text").map(b=>b.text).join("\n");
}

function parseJson(txt) {
  txt = txt.replace(/```[\w]*\n?|```/g,"").trim();
  try { return JSON.parse(txt); } catch {}
  const ai=txt.indexOf("["),aj=txt.lastIndexOf("]");
  if (ai>-1&&aj>ai) { try{return JSON.parse(txt.slice(ai,aj+1));}catch{} }
  return null;
}

async function aiClassify(ambigui) {
  if (!ambigui.length) { log("  ▷ Nessun ambiguo – call #1 saltata (0 token)"); return []; }
  log(`→ AI Haiku call #1: classifica ${ambigui.length} record ambigui …`);

  // Batch da 8 per stare nei 1000 token di risposta
  const out = [];
  for (let i=0; i<ambigui.length; i+=8) {
    const batch = ambigui.slice(i,i+8);
    const pay   = batch.map(r=>({id:r.record_id,e:r.ente.slice(0,20),o:r.oggetto.slice(0,55),c:r.cig}));
    try {
      const txt = await aiCall(
        `Classifica procurement illuminazione pubblica italiana.
STATI: GARA PUBBLICATA|PRE-GARA|RETTIFICA-PROROGA-CHIARIMENTI|ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA
TIPI: nuovo_oggi|segnale_pre_gara|aggiornamento_gara_nota|evidenza_debole
Input: ${JSON.stringify(pay)}
Output JSON solo: [{"record_id":"...","stato_procedurale":"...","tipo_novita":"..."}]`
      );
      const j = parseJson(txt);
      if (Array.isArray(j)) out.push(...j);
    } catch(e) { log(`  ⚠ Batch classify err: ${e.message}`); }
    await slp(2000); // rate limit
  }
  log(`  ✓ AI classify: ${out.length}/${ambigui.length} classificati`);
  return out;
}

async function aiReport(scored) {
  log("→ AI Haiku call #2: generazione report …");
  const fE  = v => v&&v!=="n.d." ? "€"+Number(v).toLocaleString("it-IT") : "n.d.";
  const top  = scored.slice().sort((a,b)=>b.score_commerciale-a.score_commerciale).slice(0,8);
  const nG   = scored.filter(r=>r.stato_procedurale==="GARA PUBBLICATA").length;
  const nPr  = scored.filter(r=>r.stato_procedurale==="PRE-GARA").length;
  const nP1  = scored.filter(r=>r.priorita_commerciale==="P1").length;
  const nAn  = scored.filter(r=>r.flag_anomalia).length;
  const totV = scored.reduce((a,r)=>a+(typeof r.importo_iva_escl==="number"?r.importo_iva_escl:0),0);

  const txt = await aiCall(
    `Scrivi il report giornaliero Markdown per monitoraggio procurement illuminazione pubblica italiana.

Gare principali (ordinate per score commerciale):
${top.map(r=>`[${r.priorita_commerciale}] ${r.ente} | ${r.oggetto.slice(0,50)} | ${fE(r.importo_iva_escl)} | ${r.stato_procedurale} | scad:${r.data_scadenza} | tags:${(r.tag_tecnico||[]).slice(0,3).join(",")} | fonte:${r.fonte_principale}`).join("\n")}

KPI run: gare_attive=${nG}, pre_gara=${nPr}, P1=${nP1}, anomalie=${nAn}, tot_record=${scored.length}, valore_tot=€${(totV/1e6).toFixed(1)}M, data=${DT}

STRUTTURA OBBLIGATORIA (max 400 parole):
# Report monitoraggio · Illuminazione pubblica · ${DT}

## A. Nuove gare / avvisi / esiti
(elenca le gare GARA PUBBLICATA e ESITO più rilevanti con importo e scadenza)

## B. Segnali pre-gara
(elenca i PRE-GARA con ente, oggetto, forza del segnale)

## C. Osservazioni rilevanti
(PPP, PNRR, sopra soglia UE, anomalie, scadenze imminenti)

## Cruscotto finale
| KPI | Valore |
|-----|--------|
| Gare attive | ${nG} |
| Segnali pre-gara | ${nPr} |
| Priorità P1 | ${nP1} |
| Record totali | ${scored.length} |
| Valore monitorato | €${(totV/1e6).toFixed(1)}M |
| Anomalie aperte | ${nAn} |`
  );
  log(`  ✓ Report: ${txt.length} caratteri`);
  return txt;
}

// ─── FASE 4: OUTPUT ───────────────────────────────────────────────────────────

function buildJson(scored, runLog) {
  const perStato={}, perReg={};
  scored.forEach(r=>{
    perStato[r.stato_procedurale||"n.d."]=(perStato[r.stato_procedurale||"n.d."]||0)+1;
    if(r.regione&&r.regione!=="n.d.")perReg[r.regione]=(perReg[r.regione]||0)+1;
  });
  const totVal = scored.reduce((a,r)=>a+(typeof r.importo_iva_escl==="number"?r.importo_iva_escl:0),0);
  return {
    last_updated:    new Date().toISOString(),
    schema_version:  "4.0",
    records:         scored,
    kpi_oggi: {
      record_totali:    scored.length,
      gare_attive:      scored.filter(r=>r.stato_procedurale==="GARA PUBBLICATA").length,
      pre_gara:         scored.filter(r=>r.stato_procedurale==="PRE-GARA").length,
      priorita_p1:      scored.filter(r=>r.priorita_commerciale==="P1").length,
      anomalie_aperte:  scored.filter(r=>r.flag_anomalia).length,
      valore_totale_eur: totVal,
      durata_run_s:     runLog.durata_s,
      ai_calls:         runLog.ai_calls,
      token_stimati:    runLog.token_stimati,
    },
    gare_scadenza_imminente: scored.filter(r=>{
      const d=daysUntil(r.data_scadenza);
      return d!==null && d>=0 && d<=7;
    }),
    anomalie_aperte: scored.filter(r=>r.flag_anomalia),
    per_stato:       perStato,
    per_regione:     perReg,
  };
}

// ─── MAIN ─────────────────────────────────────────────────────────────────────

async function main() {
  const t0 = Date.now();
  log("═══════════════════════════════════════════════");
  log(` PIPELINE ILLUMINAZIONE – ${ISO}`);
  log("═══════════════════════════════════════════════");

  // ── FASE 1 ──
  log("\n▶ FASE 1 — Raccolta (0 token AI)");
  const [anacData, tedData, guriData, alboData] = await Promise.all([
    fetchANAC(),
    fetchTED(),
    fetchGURI(),
    fetchAlbo(),
  ]);
  const raw = [...anacData, ...tedData, ...guriData, ...alboData];
  log(`\n▷ Record grezzi totali: ${raw.length}`);

  // ── FASE 2 ──
  log("\n▶ FASE 2 — Elaborazione deterministica (0 token AI)");

  const normed = raw.map((r,i)=>normalize(r,i)).filter(Boolean);
  log(`✓ Normalizzazione: ${normed.length}/${raw.length} record nel perimetro`);

  const { out, rm } = dedup(normed);
  if (rm) log(`✓ Deduplica: rimossi ${rm} duplicati`);
  log(`✓ Unici: ${out.length} record`);

  const pre=[], amb=[];
  out.forEach(r=>{
    const c=classifyDet(r);
    if(c) pre.push({...r,stato_procedurale:c.s,tipo_novita:c.t});
    else  amb.push(r);
  });
  const detCoverage = Math.round(pre.length/out.length*100);
  log(`✓ Classificazione det: ${pre.length} record (${detCoverage}% copertura) | AI ambigui: ${amb.length}`);

  // ── FASE 3 ──
  log("\n▶ FASE 3 — AI Haiku (max 2 chiamate)");
  let aiCalls=0, tokenStimati=0;

  let classified = [...pre];
  if (amb.length > 0) {
    const aiRes = await aiClassify(amb);
    aiCalls++;
    tokenStimati += amb.length * 30 + 200; // stima
    const mp = new Map(aiRes.map(c=>[c.record_id,c]));
    amb.forEach(r=>{
      const c=mp.get(r.record_id);
      if(!c) classified.push({...r,stato_procedurale:"GARA PUBBLICATA",tipo_novita:"nuovo_oggi"});
      else   classified.push({...r,stato_procedurale:c.stato_procedurale,tipo_novita:c.tipo_novita});
    });
  }

  const scored = classified.map(scoreRecord);
  const nP1    = scored.filter(r=>r.priorita_commerciale==="P1").length;
  log(`✓ Scoring: P1=${nP1} P2=${scored.filter(r=>r.priorita_commerciale==="P2").length} P3=${scored.filter(r=>r.priorita_commerciale==="P3").length} P4=${scored.filter(r=>r.priorita_commerciale==="P4").length}`);

  const report = await aiReport(scored);
  aiCalls++; tokenStimati += 600;

  // ── FASE 4 ──
  log("\n▶ FASE 4 — Output");
  const elapsed = Math.floor((Date.now()-t0)/1000);
  const runLog  = { durata_s:elapsed, ai_calls:aiCalls, token_stimati:tokenStimati };
  const json    = buildJson(scored, runLog);

  ensureDir(path.join(ROOT,"docs"));
  ensureDir(path.join(ROOT,"reports"));

  const jsonPath   = path.join(ROOT,"docs","illuminazione.json");
  const reportPath = path.join(ROOT,"reports",`report-${ISO}.md`);

  fs.writeFileSync(jsonPath,   JSON.stringify(json, null, 2), "utf8");
  fs.writeFileSync(reportPath, report, "utf8");

  const totVal = scored.reduce((a,r)=>a+(typeof r.importo_iva_escl==="number"?r.importo_iva_escl:0),0);
  log(`✓ JSON:   docs/illuminazione.json (${scored.length} record)`);
  log(`✓ Report: reports/report-${ISO}.md`);
  log(`\n════════════════════════════════════════`);
  log(` COMPLETATA — ${elapsed}s — ${scored.length} record — €${(totVal/1e6).toFixed(1)}M`);
  log(` AI calls: ${aiCalls} — Token stimati: ~${tokenStimati}`);
  log("════════════════════════════════════════\n");
}

main().catch(e => { console.error("❌ Errore critico:", e); process.exit(1); });
