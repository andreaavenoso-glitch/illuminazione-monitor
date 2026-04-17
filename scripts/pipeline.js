/**
 * PIPELINE MONITORAGGIO PROCUREMENT – ILLUMINAZIONE PUBBLICA
 * v2.1 – Fix: x-api-key header, ANAC/TED corretti, guard 0 record
 */
 
import fetch   from "node-fetch";
import fs      from "fs";
import path    from "path";
import { fileURLToPath } from "url";
 
const __dir = path.dirname(fileURLToPath(import.meta.url));
const ROOT  = path.resolve(__dir, "..");
const ISO   = new Date().toISOString().slice(0, 10);
const DT    = new Date().toLocaleDateString("it-IT", { day:"numeric", month:"long", year:"numeric" });
const KEY   = process.env.ANTHROPIC_API_KEY || "";
 
if (!KEY) { console.error("❌ ANTHROPIC_API_KEY mancante"); process.exit(1); }
 
const log = (msg) => console.log(`[${new Date().toTimeString().slice(0,8)}] ${msg}`);
const slp = ms => new Promise(r => setTimeout(r, ms));
function ensureDir(p) { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); }
function parseDate(s) {
  if (!s || s === "n.d.") return null;
  const m = s.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (m) return new Date(+m[3], +m[2]-1, +m[1]);
  const d = new Date(s); return isNaN(d) ? null : d;
}
function daysUntil(s) { const d=parseDate(s); return d?Math.ceil((d-new Date(ISO))/86400000):null; }
 
// FASE 1: Connettori
 
async function fetchANAC() {
  log("→ ANAC …");
  const results = [];
  const kws = ["illuminazione pubblica","relamping LED","telegestione illuminazione","pubblica illuminazione"];
  for (const kw of kws) {
    const urls = [
      `https://api.anticorruzione.it/api/v1/ricercaLotti?q=${encodeURIComponent(kw)}&page=0&pageSize=10`,
      `https://api.anticorruzione.it/api/v1/ricercaLotti?denominazione=${encodeURIComponent(kw)}&page=0&pageSize=10`,
    ];
    for (const url of urls) {
      try {
        const r = await fetch(url, { headers:{ Accept:"application/json","User-Agent":"IlluminazioneMonitor/2.1" }, timeout:12000 });
        if (!r.ok) continue;
        const d = await r.json();
        const items = d.lotti||d.data||d.results||d.content||[];
        if (items.length) {
          log(`  ✓ ANAC "${kw}": ${items.length} lotti`);
          results.push(...items.map(x=>({
            ente: x.denominazioneStazioneAppaltante||x.ente||"n.d.",
            oggetto_raw: x.oggetto||x.descrizione||"n.d.",
            importo_raw: String(x.importoTotale||x.importo||0),
            cig_raw: x.cig||"n.d.",
            scadenza_raw: x.dataScadenzaOfferta||"n.d.",
            procedura_raw: x.modalitaRealizzazione||"n.d.",
            link_bando: x.cig?`https://www.anticorruzione.it/-/bandi-e-contratti-detail?id=${x.cig}`:"n.d.",
            fonte_id:"ANAC", regione: x.regione||"n.d.", data_pub: x.dataPubblicazione||ISO,
          })));
          break;
        }
      } catch {}
    }
    await slp(800);
  }
  log(`✓ ANAC totale: ${results.length}`);
  return results;
}
 
async function fetchTED() {
  log("→ TED …");
  const results = [];
  try {
    const r = await fetch("https://api.ted.europa.eu/v3/notices/search", {
      method:"POST",
      headers:{ "Content-Type":"application/json", Accept:"application/json" },
      body: JSON.stringify({
        query:"illuminazione pubblica OR pubblica illuminazione OR smart lighting",
        filters:{ countryOfBuyer:["IT"] },
        limit:20, page:1,
      }),
      timeout:15000,
    });
    if (r.ok) {
      const d = await r.json();
      const items = d.notices||d.results||[];
      if (items.length) {
        log(`✓ TED: ${items.length} notice`);
        results.push(...items.map(x=>({
          ente: (x.buyer||{}).officialName||(x.buyer||{}).name||"n.d.",
          oggetto_raw: (x.title||{}).text||x.subject||x.title||"n.d.",
          importo_raw: String(x.estimatedValue||x.totalValue||0),
          cig_raw:"n.d.", scadenza_raw: x.deadlineForTender||"n.d.",
          procedura_raw: x.procedureType||"n.d.",
          link_bando: x.noticeId?`https://ted.europa.eu/udl?uri=TED:NOTICE:${x.noticeId}:TEXT:IT:HTML`:"n.d.",
          fonte_id:"TED", regione:"n.d.", data_pub: x.publicationDate||ISO,
        })));
      }
    } else log(`  ⚠ TED: HTTP ${r.status}`);
  } catch(e) { log(`  ⚠ TED: ${e.message}`); }
  log(`✓ TED totale: ${results.length}`);
  return results;
}
 
async function fetchGURI() {
  log("→ GURI …");
  const results = [];
  const KW = ["illuminazione pubblica","relamping","telegestione","smart lighting"];
  try {
    const rssUrl = "https://www.gazzettaufficiale.it/rss/contratti.xml";
    const r = await fetch(`https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(rssUrl)}`, { timeout:12000 });
    if (r.ok) {
      const d = await r.json();
      const items = (d.items||[]).filter(x=>KW.some(k=>(x.title||"").toLowerCase().includes(k)));
      if (items.length) {
        log(`✓ GURI: ${items.length} atti`);
        results.push(...items.map(x=>({
          ente:"n.d.", oggetto_raw: x.title||"n.d.", importo_raw:"n.d.",
          cig_raw:"n.d.", scadenza_raw:"n.d.", procedura_raw:"n.d.",
          link_bando: x.link||"n.d.", fonte_id:"GURI", regione:"n.d.",
          data_pub:(x.pubDate||"").slice(0,10)||ISO,
          note_estrazione:(x.description||"").slice(0,120),
        })));
      }
    }
  } catch(e) { log(`  ⚠ GURI: ${e.message}`); }
  log(`✓ GURI totale: ${results.length}`);
  return results;
}
 
// FASE 2: Pipeline deterministica
 
const KW_IN = ["illuminazione pubblica","pubblica illuminazione","relamping","telegestione","telecontrollo","smart lighting","riqualificazione illuminazione","pali illuminazione","global service illuminazione","accordo quadro illuminazione"];
const KW_EX = ["illuminazione interna","impianto elettrico generico","facility management","climatizzazione"];
 
function normalize(r,i) {
  const obj=(r.oggetto_raw||r.oggetto||"").toLowerCase(),all=JSON.stringify(r).toLowerCase();
  if(!KW_IN.some(k=>obj.includes(k)))return null;
  if(KW_EX.some(k=>obj.includes(k)))return null;
  const pnrr=/pnrr|pnc|react[\s.-]?eu/.test(all),ppp=/ppp|concessione|project[\s.-]?fin/.test(obj+" "+(r.procedura_raw||""));
  const imp=parseFloat(String(r.importo_raw||0).replace(/[€\s]/g,"").replace(/\.(?=\d{3})/g,"").replace(",","."))||0;
  const cig=(r.cig_raw||"n.d.").trim().toUpperCase(),cigOk=/^[A-Z0-9]{8,10}$/.test(cig);
  const tags=[];
  if(/led|relamp/.test(obj))tags.push("LED");if(/telegest/.test(obj))tags.push("telegestione");
  if(/telecontr/.test(obj))tags.push("telecontrollo");if(/smart[\s-]?light/.test(obj))tags.push("smart lighting");
  if(/global[\s-]?serv/.test(obj))tags.push("global service");if(/accordo[\s-]?quad/.test(obj))tags.push("accordo quadro");
  if(/manuten|gestione/.test(obj))tags.push("manutenzione");if(pnrr)tags.push("PNRR");if(ppp)tags.push("PPP");
  if(imp>5538000)tags.push("sopra soglia UE");
  return {
    record_id:`R-${ISO}-${String(i+1).padStart(4,"0")}`,
    ente:(r.ente||"n.d.").trim(),oggetto:(r.oggetto_raw||r.oggetto||"n.d.").replace(/\s+/g," ").trim(),
    importo_iva_escl:imp||"n.d.",importo_stimato:!imp,cig:cigOk?cig:"n.d.",
    data_scadenza:r.scadenza_raw||"n.d.",data_pubblicazione:r.data_pub||ISO,
    procedura:r.procedura_raw||"n.d.",fonte_principale:r.fonte_id||"n.d.",
    link_bando:r.link_bando||"n.d.",regione:r.regione||"n.d.",
    atto_tipo:r.atto_tipo||null,pre_gara_forza:r.pre_gara_forza||null,
    flag_pnrr:pnrr,flag_ppp:ppp,flag_sopra_soglia_ue:imp>5538000,flag_anomalia:false,
    tag_tecnico:tags,livello_validazione:cigOk?"L3":"L2",confidence_score:cigOk?.85:.65,
    last_updated_at:new Date().toISOString(),note_operative:r.note_estrazione||"",storico_eventi:[],
  };
}
 
function dedup(arr) {
  const seen=new Map(),out=[];let rm=0;
  for(const r of arr){const ib=typeof r.importo_iva_escl==="number"?Math.round(r.importo_iva_escl/50000)*50000:"x";const k=r.cig&&r.cig!=="n.d."?"cig:"+r.cig:"eo:"+r.ente.slice(0,28).toLowerCase()+"|"+r.oggetto.slice(0,38).toLowerCase()+"|"+ib;if(seen.has(k))rm++;else{seen.set(k,1);out.push(r);}}
  return{out,rm};
}
 
function classifyDet(r) {
  const a=(r.oggetto||"").toLowerCase()+" "+(r.note_operative||"").toLowerCase();
  if(r.atto_tipo)return{s:"PRE-GARA",t:"segnale_pre_gara"};
  if(/esito|aggiudic|revoca|deserta|annullat/.test(a))return{s:"ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA",t:"nuovo_oggi"};
  if(/proroga|rettifica|chiariment/.test(a))return{s:"RETTIFICA-PROROGA-CHIARIMENTI",t:"aggiornamento_gara_nota"};
  if(r.cig!=="n.d."&&r.link_bando!=="n.d.")return{s:"GARA PUBBLICATA",t:"nuovo_oggi"};
  if(r.confidence_score<.70)return{s:"GARA PUBBLICATA",t:"evidenza_debole"};
  return null;
}
 
function scoreRecord(r) {
  let s=0;const imp=typeof r.importo_iva_escl==="number"?r.importo_iva_escl:0;
  if(imp>10e6)s+=35;else if(imp>5e6)s+=28;else if(imp>2e6)s+=20;else if(imp>1e6)s+=14;else if(imp>5e5)s+=8;else s+=3;
  const st=r.stato_procedurale||"";
  if(st==="GARA PUBBLICATA")s+=25;else if(st.startsWith("RETTIFICA"))s+=20;else if(st==="PRE-GARA")s+=r.pre_gara_forza==="forte"?20:8;else if(st.startsWith("ESITO"))s+=10;
  const d=daysUntil(r.data_scadenza);
  if(d!==null){if(d<=3)s+=20;else if(d<=7)s+=15;else if(d<=15)s+=10;else if(d<=30)s+=5;}
  if(r.flag_ppp)s+=8;if(r.flag_pnrr)s+=6;if(r.flag_sopra_soglia_ue)s+=4;
  if((r.tag_tecnico||[]).some(t=>/accordo|global/.test(t)))s+=3;
  let p="P4";
  if(s>=70||(imp>5e6&&st==="GARA PUBBLICATA")||(d!==null&&d>=0&&d<=2))p="P1";
  else if(s>=50)p="P2";else if(s>=30)p="P3";
  return{...r,score_commerciale:s,priorita_commerciale:p};
}
 
// FASE 3: AI – FIX CRITICO: aggiunto x-api-key header
 
async function aiCall(prompt) {
  const r = await fetch("https://api.anthropic.com/v1/messages",{
    method:"POST",
    headers:{
      "Content-Type":"application/json",
      "x-api-key": KEY,
      "anthropic-version":"2023-06-01",
    },
    body:JSON.stringify({ model:"claude-haiku-4-5-20251001", max_tokens:1000, messages:[{role:"user",content:prompt}] }),
    timeout:30000,
  });
  const d=await r.json();
  if(d.error)throw new Error(d.error.message);
  return(d.content||[]).filter(b=>b.type==="text").map(b=>b.text).join("\n");
}
 
function parseJson(txt) {
  if(!txt)return null;txt=txt.replace(/```[\w]*\n?|```/g,"").trim();
  try{return JSON.parse(txt);}catch{}
  const ai=txt.indexOf("["),aj=txt.lastIndexOf("]");
  if(ai>-1&&aj>ai){try{return JSON.parse(txt.slice(ai,aj+1));}catch{}}
  return null;
}
 
async function aiClassify(amb) {
  if(!amb.length){log("  ▷ Nessun ambiguo – call #1 saltata");return[];}
  log(`→ AI call #1: classifica ${amb.length} record …`);
  const out=[];
  for(let i=0;i<amb.length;i+=8){
    const batch=amb.slice(i,i+8),pay=batch.map(r=>({id:r.record_id,e:r.ente.slice(0,20),o:r.oggetto.slice(0,55),c:r.cig}));
    try{const txt=await aiCall(`Classifica procurement illuminazione pubblica italiana.\nSTATI: GARA PUBBLICATA|PRE-GARA|RETTIFICA-PROROGA-CHIARIMENTI|ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA\nTIPI: nuovo_oggi|segnale_pre_gara|aggiornamento_gara_nota|evidenza_debole\nInput: ${JSON.stringify(pay)}\nOutput JSON solo: [{"record_id":"...","stato_procedurale":"...","tipo_novita":"..."}]`);const j=parseJson(txt);if(Array.isArray(j))out.push(...j);}catch(e){log(`  ⚠ Batch err: ${e.message}`);}
    await slp(2000);
  }
  log(`  ✓ AI classify: ${out.length}/${amb.length}`);
  return out;
}
 
async function aiReport(scored) {
  log("→ AI call #2: report …");
  const fE=v=>v&&v!=="n.d."?"€"+Number(v).toLocaleString("it-IT"):"n.d.";
  const top=scored.slice().sort((a,b)=>b.score_commerciale-a.score_commerciale).slice(0,8);
  const nG=scored.filter(r=>r.stato_procedurale==="GARA PUBBLICATA").length;
  const nPr=scored.filter(r=>r.stato_procedurale==="PRE-GARA").length;
  const nP1=scored.filter(r=>r.priorita_commerciale==="P1").length;
  const totV=scored.reduce((a,r)=>a+(typeof r.importo_iva_escl==="number"?r.importo_iva_escl:0),0);
  const gareStr=top.length?top.map(r=>`[${r.priorita_commerciale}] ${r.ente} | ${r.oggetto.slice(0,50)} | ${fE(r.importo_iva_escl)} | ${r.stato_procedurale} | scad:${r.data_scadenza}`).join("\n"):"Nessuna gara trovata in questo run.";
  const txt=await aiCall(`Scrivi report giornaliero Markdown per monitoraggio procurement illuminazione pubblica italiana.\nGare: ${gareStr}\nKPI: gare=${nG}, pre=${nPr}, P1=${nP1}, tot=${scored.length}, €${(totV/1e6).toFixed(1)}M, data=${DT}\nStruttura (max 300 parole):\n# Report · Illuminazione pubblica · ${DT}\n## A. Nuove gare\n## B. Pre-gara\n## C. Osservazioni\n## Cruscotto\n|KPI|Valore|\n|---|---|\n|Gare|${nG}|\n|Pre-gara|${nPr}|\n|P1|${nP1}|\n|Totale|${scored.length}|`);
  log(`  ✓ Report: ${txt.length} char`);
  return txt;
}
 
// MAIN
 
async function main() {
  const t0=Date.now();
  log("═══════════════════════════════════════════════");
  log(` PIPELINE ILLUMINAZIONE v2.1 – ${ISO}`);
  log("═══════════════════════════════════════════════");
 
  log("\n▶ FASE 1 — Raccolta");
  const [anacData,tedData,guriData]=await Promise.all([fetchANAC(),fetchTED(),fetchGURI()]);
  const raw=[...anacData,...tedData,...guriData];
  log(`\n▷ Grezzi: ${raw.length} (ANAC:${anacData.length} TED:${tedData.length} GURI:${guriData.length})`);
 
  log("\n▶ FASE 2 — Elaborazione");
  const normed=raw.map((r,i)=>normalize(r,i)).filter(Boolean);
  log(`✓ Normalizzazione: ${normed.length}/${raw.length}`);
  const{out,rm}=dedup(normed);if(rm)log(`✓ Deduplica: rimossi ${rm}`);log(`✓ Unici: ${out.length}`);
  const pre=[],amb=[];out.forEach(r=>{const c=classifyDet(r);c?pre.push({...r,stato_procedurale:c.s,tipo_novita:c.t}):amb.push(r);});
  const detPct=out.length>0?Math.round(pre.length/out.length*100):0;
  log(`✓ Classificazione det: ${pre.length} (${detPct}%) | AI: ${amb.length}`);
 
  log("\n▶ FASE 3 — AI Haiku");
  let aiCalls=0,classified=[...pre];
  if(amb.length){const aiRes=await aiClassify(amb);aiCalls++;const mp=new Map(aiRes.map(c=>[c.record_id,c]));amb.forEach(r=>{const c=mp.get(r.record_id);if(!c)classified.push({...r,stato_procedurale:"GARA PUBBLICATA",tipo_novita:"nuovo_oggi"});else classified.push({...r,stato_procedurale:c.stato_procedurale,tipo_novita:c.tipo_novita});});}
  const scored=classified.map(scoreRecord);
  const nP1=scored.filter(r=>r.priorita_commerciale==="P1").length;
  if(scored.length>0)log(`✓ Scoring: P1=${nP1} P2=${scored.filter(r=>r.priorita_commerciale==="P2").length} P3=${scored.filter(r=>r.priorita_commerciale==="P3").length}`);
  else log("▷ 0 record – scoring saltato");
  const report=await aiReport(scored);aiCalls++;
 
  log("\n▶ FASE 4 — Output");
  const elapsed=Math.floor((Date.now()-t0)/1000);
  const perSt={},perRg={};scored.forEach(r=>{perSt[r.stato_procedurale||"n.d."]=(perSt[r.stato_procedurale||"n.d."]||0)+1;if(r.regione&&r.regione!=="n.d.")perRg[r.regione]=(perRg[r.regione]||0)+1;});
  const totVal=scored.reduce((a,r)=>a+(typeof r.importo_iva_escl==="number"?r.importo_iva_escl:0),0);
  const json={last_updated:new Date().toISOString(),schema_version:"2.1",records:scored,kpi_oggi:{record_totali:scored.length,gare_attive:scored.filter(r=>r.stato_procedurale==="GARA PUBBLICATA").length,pre_gara:scored.filter(r=>r.stato_procedurale==="PRE-GARA").length,priorita_p1:nP1,anomalie_aperte:0,valore_totale_eur:totVal,durata_run_s:elapsed,ai_calls:aiCalls},gare_scadenza_imminente:scored.filter(r=>{const d=daysUntil(r.data_scadenza);return d!==null&&d>=0&&d<=7;}),anomalie_aperte:[],per_stato:perSt,per_regione:perRg};
  ensureDir(path.join(ROOT,"docs"));ensureDir(path.join(ROOT,"reports"));
  fs.writeFileSync(path.join(ROOT,"docs","illuminazione.json"),JSON.stringify(json,null,2),"utf8");
  fs.writeFileSync(path.join(ROOT,"reports",`report-${ISO}.md`),report,"utf8");
  log(`✓ JSON: docs/illuminazione.json (${scored.length} record)`);
  log(`✓ Report: reports/report-${ISO}.md`);
  log(`\n════════════════════════════════════════`);
  log(` COMPLETATA — ${elapsed}s — ${scored.length} record — €${(totVal/1e6).toFixed(1)}M`);
  log(`════════════════════════════════════════\n`);
}
 
main().catch(e=>{console.error("❌ Errore critico:",e);process.exit(1);});
