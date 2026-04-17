/**
 * PIPELINE MONITORAGGIO PROCUREMENT – ILLUMINAZIONE PUBBLICA
 * v3.0 – Web search come fonte primaria (API ufficiali inaffidabili)
 * Costo stimato: ~$0.01/run · ~$0.30/mese
 */

import fetch  from "node-fetch";
import fs     from "fs";
import path   from "path";
import { fileURLToPath } from "url";

const __dir = path.dirname(fileURLToPath(import.meta.url));
const ROOT  = path.resolve(__dir, "..");
const ISO   = new Date().toISOString().slice(0,10);
const DT    = new Date().toLocaleDateString("it-IT",{day:"numeric",month:"long",year:"numeric"});
const KEY   = process.env.ANTHROPIC_API_KEY || "";

if (!KEY) { console.error("❌ ANTHROPIC_API_KEY mancante"); process.exit(1); }

const log = m => console.log(`[${new Date().toTimeString().slice(0,8)}] ${m}`);
const slp = ms => new Promise(r => setTimeout(r, ms));
function ensureDir(p){ if(!fs.existsSync(p)) fs.mkdirSync(p,{recursive:true}); }
function parseDate(s){
  if(!s||s==="n.d.")return null;
  const m=s.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if(m)return new Date(+m[3],+m[2]-1,+m[1]);
  const d=new Date(s); return isNaN(d)?null:d;
}
function daysUntil(s){ const d=parseDate(s); return d?Math.ceil((d-new Date(ISO))/864e5):null; }

// ── API Anthropic ─────────────────────────────────────────────────────────────

async function anthropic(messages, ws=false){
  const hdrs = {
    "Content-Type":      "application/json",
    "x-api-key":         KEY,
    "anthropic-version": "2023-06-01",
  };
  if(ws) hdrs["anthropic-beta"] = "web-search-2025-03-05";

  const body = {
    model:      "claude-haiku-4-5-20251001",
    max_tokens: 1000,
    messages,
  };
  if(ws) body.tools = [{type:"web_search_20250305", name:"web_search"}];

  const r = await fetch("https://api.anthropic.com/v1/messages",{
    method:"POST", headers:hdrs,
    body:JSON.stringify(body),
    timeout:45000,
  });
  const d = await r.json();
  if(d.error) throw new Error(d.error.message);
  const blocks = d.content||[];
  const wsUsed = blocks.some(b=>b.type==="tool_use");
  const text   = blocks.filter(b=>b.type==="text").map(b=>b.text).join("\n");
  return {text, wsUsed};
}

function pj(txt){
  if(!txt)return null;
  txt=txt.replace(/```[\w]*\n?|```/g,"").trim();
  try{return JSON.parse(txt);}catch{}
  const ai=txt.indexOf("["),aj=txt.lastIndexOf("]");
  if(ai>-1&&aj>ai){try{return JSON.parse(txt.slice(ai,aj+1));}catch{}}
  return null;
}

// ── FASE 1: raccolta via web search ───────────────────────────────────────────

const RECORD_SCHEMA = `[{"ente":"nome ente","oggetto_raw":"oggetto gara","importo_raw":"numero senza €","cig_raw":"CIG o n.d.","scadenza_raw":"dd/mm/yyyy o n.d.","procedura_raw":"aperta|negoziata|n.d.","link_bando":"url","fonte_id":"ANAC|TED|eproc|Albo","regione":"regione italiana","data_pub":"${ISO}","note_estrazione":"brevi note"}]`;

async function cercaGare(){
  log("→ [WS1] Cerca gare pubblicata su ANAC e portali e-procurement …");
  const {text, wsUsed} = await anthropic([{role:"user",content:
    `Cerca su ANAC (anticorruzione.it), portali e-procurement italiani (Sintel, STELLA, MEPA, siti comuni) le gare d'appalto per ILLUMINAZIONE PUBBLICA pubblicate negli ultimi 60 giorni. Keyword: "pubblica illuminazione" OR "relamping LED" OR "telegestione illuminazione" OR "illuminazione pubblica" OR "smart lighting". Trova almeno 5 gare reali con tutti i dettagli. Rispondi SOLO con JSON array valido:
${RECORD_SCHEMA}`
  }], true);
  log(`  web search: ${wsUsed?"attiva":"non attiva"}`);
  const j = pj(text);
  const arr = Array.isArray(j)?j:(j?[j]:[]);
  log(`✓ Gare ANAC/eproc: ${arr.length} record`);
  if(!arr.length) log(`  Preview risposta: ${text.slice(0,120)}`);
  return arr;
}

async function cercaTED(){
  log("→ [WS2] Cerca bandi sopra soglia UE su TED/GUUE …");
  await slp(3000);
  const {text, wsUsed} = await anthropic([{role:"user",content:
    `Cerca su TED (ted.europa.eu) i bandi europei italiani per illuminazione pubblica pubblicati negli ultimi 60 giorni. Cerca "pubblica illuminazione" e "street lighting" con paese Italia. Trova 3-4 bandi reali. Rispondi SOLO con JSON array valido:
${RECORD_SCHEMA}`
  }], true);
  log(`  web search: ${wsUsed?"attiva":"non attiva"}`);
  const j = pj(text);
  const arr = Array.isArray(j)?j:(j?[j]:[]);
  log(`✓ TED: ${arr.length} record`);
  return arr;
}

async function cercaPreGara(){
  log("→ [WS3] Cerca segnali pre-gara su albi pretori e stampa …");
  await slp(3000);
  const {text, wsUsed} = await anthropic([{role:"user",content:
    `Cerca delibere di Giunta, determine dirigenziali, programmi triennali LL.PP. 2024-2026 di comuni e province italiani su illuminazione pubblica, relamping LED, smart city lighting. Cerca anche notizie recenti su Infobuildenergia, Quotidiano Energia. Trova 2-3 segnali pre-gara reali. Rispondi SOLO con JSON array valido (aggiungi "atto_tipo":"delibera|determina|ptlp" e "pre_gara_forza":"forte|debole"):
${RECORD_SCHEMA}`
  }], true);
  log(`  web search: ${wsUsed?"attiva":"non attiva"}`);
  const j = pj(text);
  const arr = Array.isArray(j)?j:(j?[j]:[]);
  log(`✓ Pre-gara: ${arr.length} segnali`);
  return arr;
}

// ── FASE 2: elaborazione deterministica ───────────────────────────────────────

const KW_IN=["illuminazione pubblica","pubblica illuminazione","relamping","telegestione","telecontrollo","smart lighting","riqualificazione illuminazione","pali illuminazione","global service illuminazione","accordo quadro illuminazione"];
const KW_EX=["illuminazione interna","impianto elettrico generico","facility management","climatizzazione"];

function normalize(r,i){
  const obj=(r.oggetto_raw||r.oggetto||"").toLowerCase(), all=JSON.stringify(r).toLowerCase();
  if(!KW_IN.some(k=>obj.includes(k)))return null;
  if(KW_EX.some(k=>obj.includes(k)))return null;
  const pnrr=/pnrr|pnc|react[\s.-]?eu/.test(all);
  const ppp=/ppp|concessione|project[\s.-]?fin/.test(obj+" "+(r.procedura_raw||""));
  const imp=parseFloat(String(r.importo_raw||0).replace(/[€\s]/g,"").replace(/\.(?=\d{3})/g,"").replace(",","."))||0;
  const cig=(r.cig_raw||"n.d.").trim().toUpperCase();
  const cigOk=/^[A-Z0-9]{8,10}$/.test(cig);
  const tags=[];
  if(/led|relamp/.test(obj))tags.push("LED");
  if(/telegest/.test(obj))tags.push("telegestione");
  if(/telecontr/.test(obj))tags.push("telecontrollo");
  if(/smart[\s-]?light/.test(obj))tags.push("smart lighting");
  if(/global[\s-]?serv/.test(obj))tags.push("global service");
  if(/accordo[\s-]?quad/.test(obj))tags.push("accordo quadro");
  if(/manuten|gestione/.test(obj))tags.push("manutenzione");
  if(/proroga/.test(obj))tags.push("proroga");
  if(pnrr)tags.push("PNRR"); if(ppp)tags.push("PPP");
  if(imp>5538000)tags.push("sopra soglia UE");
  return {
    record_id:`R-${ISO}-${String(i+1).padStart(4,"0")}`,
    ente:(r.ente||"n.d.").trim(),
    oggetto:(r.oggetto_raw||r.oggetto||"n.d.").replace(/\s+/g," ").trim(),
    importo_iva_escl:imp||"n.d.", importo_stimato:!imp,
    cig:cigOk?cig:"n.d.",
    data_scadenza:r.scadenza_raw||"n.d.",
    data_pubblicazione:r.data_pub||ISO,
    procedura:r.procedura_raw||"n.d.",
    fonte_principale:r.fonte_id||"n.d.",
    link_bando:r.link_bando||"n.d.",
    regione:r.regione||"n.d.",
    atto_tipo:r.atto_tipo||null, pre_gara_forza:r.pre_gara_forza||null,
    flag_pnrr:pnrr, flag_ppp:ppp, flag_sopra_soglia_ue:imp>5538000,
    flag_anomalia:false, tag_tecnico:tags,
    livello_validazione:cigOk?"L3":"L2",
    confidence_score:cigOk?.85:.65,
    last_updated_at:new Date().toISOString(),
    note_operative:r.note_estrazione||"", storico_eventi:[],
  };
}

function dedup(arr){
  const seen=new Map(),out=[];let rm=0;
  for(const r of arr){
    const ib=typeof r.importo_iva_escl==="number"?Math.round(r.importo_iva_escl/50000)*50000:"x";
    const k=r.cig&&r.cig!=="n.d."?"cig:"+r.cig:"eo:"+r.ente.slice(0,28).toLowerCase()+"|"+r.oggetto.slice(0,38).toLowerCase()+"|"+ib;
    if(seen.has(k))rm++; else{seen.set(k,1);out.push(r);}
  }
  return{out,rm};
}

function classifyDet(r){
  const a=(r.oggetto||"").toLowerCase()+" "+(r.note_operative||"").toLowerCase();
  if(r.atto_tipo)return{s:"PRE-GARA",t:"segnale_pre_gara"};
  if(/esito|aggiudic|revoca|deserta|annullat/.test(a))return{s:"ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA",t:"nuovo_oggi"};
  if(/proroga|rettifica|chiariment/.test(a))return{s:"RETTIFICA-PROROGA-CHIARIMENTI",t:"aggiornamento_gara_nota"};
  if(r.cig!=="n.d."&&r.link_bando!=="n.d.")return{s:"GARA PUBBLICATA",t:"nuovo_oggi"};
  if(r.confidence_score<.70)return{s:"GARA PUBBLICATA",t:"evidenza_debole"};
  return null;
}

function scoreRecord(r){
  let s=0;
  const imp=typeof r.importo_iva_escl==="number"?r.importo_iva_escl:0;
  if(imp>10e6)s+=35;else if(imp>5e6)s+=28;else if(imp>2e6)s+=20;
  else if(imp>1e6)s+=14;else if(imp>5e5)s+=8;else s+=3;
  const st=r.stato_procedurale||"";
  if(st==="GARA PUBBLICATA")s+=25;
  else if(st.startsWith("RETTIFICA"))s+=20;
  else if(st==="PRE-GARA")s+=r.pre_gara_forza==="forte"?20:8;
  else if(st.startsWith("ESITO"))s+=10;
  const d=daysUntil(r.data_scadenza);
  if(d!==null){if(d<=3)s+=20;else if(d<=7)s+=15;else if(d<=15)s+=10;else if(d<=30)s+=5;}
  if(r.flag_ppp)s+=8;if(r.flag_pnrr)s+=6;if(r.flag_sopra_soglia_ue)s+=4;
  if((r.tag_tecnico||[]).some(t=>/accordo|global/.test(t)))s+=3;
  let p="P4";
  if(s>=70||(imp>5e6&&st==="GARA PUBBLICATA")||(d!==null&&d>=0&&d<=2))p="P1";
  else if(s>=50)p="P2";else if(s>=30)p="P3";
  return{...r,score_commerciale:s,priorita_commerciale:p};
}

// ── FASE 3: report ────────────────────────────────────────────────────────────

async function generateReport(scored){
  log("→ [WS4] Generazione report …");
  const fE=v=>v&&v!=="n.d."?"€"+Number(v).toLocaleString("it-IT"):"n.d.";
  const top=scored.slice().sort((a,b)=>b.score_commerciale-a.score_commerciale).slice(0,8);
  const nG=scored.filter(r=>r.stato_procedurale==="GARA PUBBLICATA").length;
  const nPr=scored.filter(r=>r.stato_procedurale==="PRE-GARA").length;
  const nP1=scored.filter(r=>r.priorita_commerciale==="P1").length;
  const totV=scored.reduce((a,r)=>a+(typeof r.importo_iva_escl==="number"?r.importo_iva_escl:0),0);
  const gareStr=top.length
    ?top.map(r=>`[${r.priorita_commerciale}] ${r.ente} | ${r.oggetto.slice(0,50)} | ${fE(r.importo_iva_escl)} | ${r.stato_procedurale} | scad:${r.data_scadenza} | fonte:${r.fonte_principale}`).join("\n")
    :"Nessuna gara trovata oggi.";
  const {text} = await anthropic([{role:"user",content:
    `Scrivi report giornaliero Markdown per monitoraggio procurement illuminazione pubblica italiana.
Gare trovate:
${gareStr}
KPI: gare=${nG}, pre=${nPr}, P1=${nP1}, tot=${scored.length}, €${(totV/1e6).toFixed(1)}M, data=${DT}
Struttura (max 320 parole):
# Report · Illuminazione pubblica · ${DT}
## A. Nuove gare
## B. Pre-gara
## C. Osservazioni rilevanti
## Cruscotto
|KPI|Valore|
|---|---|
|Gare attive|${nG}|
|Pre-gara|${nPr}|
|Priorità P1|${nP1}|
|Record totali|${scored.length}|
|Valore monitorato|€${(totV/1e6).toFixed(1)}M|`
  }]);
  log(`  ✓ Report: ${text.length} char`);
  return text;
}

// ── MAIN ──────────────────────────────────────────────────────────────────────

async function main(){
  const t0=Date.now();
  log("═══════════════════════════════════════════════");
  log(` PIPELINE ILLUMINAZIONE v3.0 – ${ISO}`);
  log("═══════════════════════════════════════════════");
  log(" Fonte dati: Claude web search (API ufficiali inaffidabili)");

  // FASE 1
  log("\n▶ FASE 1 — Raccolta via web search (3 chiamate)");
  const [gareData, tedData, pregaraData] = await Promise.all([
    cercaGare(),
    cercaTED(),
    cercaPreGara(),
  ]);
  const raw=[...gareData,...tedData,...pregaraData];
  log(`\n▷ Totale grezzi: ${raw.length}`);

  // FASE 2
  log("\n▶ FASE 2 — Elaborazione deterministica");
  const normed=raw.map((r,i)=>normalize(r,i)).filter(Boolean);
  log(`✓ Nel perimetro: ${normed.length}/${raw.length}`);
  const{out,rm}=dedup(normed);
  if(rm)log(`✓ Deduplica: rimossi ${rm}`);
  log(`✓ Unici: ${out.length}`);

  const pre=[],amb=[];
  out.forEach(r=>{const c=classifyDet(r);c?pre.push({...r,stato_procedurale:c.s,tipo_novita:c.t}):amb.push(r);});
  log(`✓ Classificazione det: ${pre.length} | ambigui: ${amb.length}`);

  // Classificazione AI solo se ci sono ambigui
  let classified=[...pre];
  let aiClassCalls=0;
  if(amb.length>0){
    log("→ Classificazione AI ambigui …");
    await slp(2000);
    try{
      const pay=amb.map(r=>({id:r.record_id,e:r.ente.slice(0,20),o:r.oggetto.slice(0,55),c:r.cig}));
      const {text}=await anthropic([{role:"user",content:
        `Classifica questi record procurement illuminazione pubblica.
STATI: GARA PUBBLICATA|PRE-GARA|RETTIFICA-PROROGA-CHIARIMENTI|ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA
TIPI: nuovo_oggi|segnale_pre_gara|aggiornamento_gara_nota|evidenza_debole
Input: ${JSON.stringify(pay)}
Output JSON solo: [{"record_id":"...","stato_procedurale":"...","tipo_novita":"..."}]`
      }]);
      aiClassCalls++;
      const j=pj(text);
      const mp=new Map((Array.isArray(j)?j:[]).map(c=>[c.record_id,c]));
      amb.forEach(r=>{const c=mp.get(r.record_id);classified.push(c?{...r,stato_procedurale:c.stato_procedurale,tipo_novita:c.tipo_novita}:{...r,stato_procedurale:"GARA PUBBLICATA",tipo_novita:"nuovo_oggi"});});
      log(`  ✓ Classificati: ${j?.length||0}/${amb.length}`);
    }catch(e){
      log(`  ⚠ Classificazione AI err: ${e.message} — fallback deterministico`);
      amb.forEach(r=>classified.push({...r,stato_procedurale:"GARA PUBBLICATA",tipo_novita:"nuovo_oggi"}));
    }
  }

  const scored=classified.map(scoreRecord);
  const nP1=scored.filter(r=>r.priorita_commerciale==="P1").length;
  log(`✓ Scoring: P1=${nP1} P2=${scored.filter(r=>r.priorita_commerciale==="P2").length} P3=${scored.filter(r=>r.priorita_commerciale==="P3").length}`);

  // FASE 3
  log("\n▶ FASE 3 — Report");
  let report=`# Report · Illuminazione pubblica · ${DT}\n\n${scored.length===0?"Nessuna gara trovata oggi.":"Run completato."}`;
  try{ report=await generateReport(scored); }
  catch(e){ log(`⚠ Report err: ${e.message}`); }

  // FASE 4
  log("\n▶ FASE 4 — Output");
  const elapsed=Math.floor((Date.now()-t0)/1000);
  const perSt={},perRg={};
  scored.forEach(r=>{perSt[r.stato_procedurale||"n.d."]=(perSt[r.stato_procedurale||"n.d."]||0)+1;if(r.regione&&r.regione!=="n.d.")perRg[r.regione]=(perRg[r.regione]||0)+1;});
  const totVal=scored.reduce((a,r)=>a+(typeof r.importo_iva_escl==="number"?r.importo_iva_escl:0),0);
  const json={
    last_updated:new Date().toISOString(), schema_version:"3.0", records:scored,
    kpi_oggi:{record_totali:scored.length,gare_attive:scored.filter(r=>r.stato_procedurale==="GARA PUBBLICATA").length,pre_gara:scored.filter(r=>r.stato_procedurale==="PRE-GARA").length,priorita_p1:nP1,valore_totale_eur:totVal,durata_run_s:elapsed,ai_calls:3+aiClassCalls+1,fonte:"web_search"},
    gare_scadenza_imminente:scored.filter(r=>{const d=daysUntil(r.data_scadenza);return d!==null&&d>=0&&d<=7;}),
    anomalie_aperte:[],per_stato:perSt,per_regione:perRg,
  };
  ensureDir(path.join(ROOT,"docs")); ensureDir(path.join(ROOT,"reports"));
  fs.writeFileSync(path.join(ROOT,"docs","illuminazione.json"),JSON.stringify(json,null,2),"utf8");
  fs.writeFileSync(path.join(ROOT,"reports",`report-${ISO}.md`),report,"utf8");
  log(`✓ docs/illuminazione.json (${scored.length} record)`);
  log(`✓ reports/report-${ISO}.md`);
  log(`\n════════════════════════════════════════`);
  log(` COMPLETATA — ${elapsed}s — ${scored.length} record — €${(totVal/1e6).toFixed(1)}M`);
  log("════════════════════════════════════════\n");
}

main().catch(e=>{console.error("❌ Errore critico:",e);process.exit(1);});
