"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ClaudeStatusBanner } from "@/components/ClaudeStatusBanner";
import { MenuItem, RegionTabs, type TabDef } from "@/components/RegionTabs";
import { ScanView } from "@/components/ScanView";
import { getToken, getUser, hasRole } from "@/lib/auth";
import {
  CATEGORIA_LABEL,
  STATO_CLASS,
  STATO_LABEL,
  type Categoria,
  SERVIZIO_LABEL,
  type RegionDetail,
  RUOLO_LABEL,
} from "@/lib/regions";

type Tab = Categoria | "siti" | "scan" | "verifica";

const ERROR_LABELS: Record<string, string> = {
  http_404: "pagina non trovata (404)",
  http_403: "accesso bloccato (403)",
  dns: "dominio inesistente",
  ssl: "certificato non valido",
  timeout: "nessuna risposta (timeout)",
  empty: "pagina vuota",
  connect: "connessione rifiutata",
  reset: "connessione interrotta dal server (probabile blocco)",
  redirect: "troppi reindirizzamenti",
  protocol: "risposta non valida dal server",
  error: "errore non classificato (vedi log)",
};

function fmt(d: string | null): string {
  return d ? new Date(d).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—";
}

export default function RegionPage() {
  const params = useParams<{ region: string }>();
  const region = decodeURIComponent(params.region);
  const qc = useQueryClient();
  const admin = hasRole(getUser(), "admin");
  const [tab, setTab] = useState<Tab>("pre_gara");
  const [recipients, setRecipients] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [showExpired, setShowExpired] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["region", region, showExpired],
    queryFn: () => api.get<RegionDetail>(`/regions/${encodeURIComponent(region)}${showExpired ? "?scadute=true" : ""}`),
    refetchInterval: 20000,
  });

  const save = useMutation({
    mutationFn: (body: { enabled?: boolean; recipients?: string }) =>
      api.patch(`/regions/${encodeURIComponent(region)}`, body),
    onSuccess: () => {
      setRecipients(null);
      qc.invalidateQueries({ queryKey: ["region", region] });
      qc.invalidateQueries({ queryKey: ["regions"] });
    },
  });
  const toggleSite = useMutation({
    mutationFn: (v: { id: string; active: boolean }) =>
      api.patch(`/regions/${encodeURIComponent(region)}/sites/${v.id}`, { active: v.active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["region", region] }),
  });
  const collect = useMutation({
    mutationFn: (opts?: { limit?: number; resume?: boolean }) => {
      const q = new URLSearchParams();
      if (opts?.limit) q.set("limit", String(opts.limit));
      if (opts?.resume) q.set("resume", "true");
      const qs = q.toString();
      return api.post(`/regions/${encodeURIComponent(region)}/collect${qs ? `?${qs}` : ""}`);
    },
    onSuccess: (_d, opts) => {
      setTab("scan");
      setMessage(
        opts?.limit
          ? `Prova avviata su ${opts.limit} comuni (prima quelli mai scansionati). Segui l'avanzamento qui sotto.`
          : opts?.resume
            ? "Ripresa avviata: salta i comuni già letti nelle ultime 24 ore, poi siti regionali, normalizzazione e punteggio. Segui l'avanzamento qui sotto."
            : "Raccolta avviata: prima i comuni, poi siti regionali, normalizzazione e punteggio. Segui l'avanzamento qui sotto.",
      );
    },
    onError: (e: Error) => setMessage(`Errore: ${e.message}`),
  });
  const processNow = useMutation({
    mutationFn: () => api.post(`/regions/${encodeURIComponent(region)}/process`),
    onSuccess: () => {
      setMessage("Elaborazione avviata: i record già raccolti compaiono nei tab tra circa un minuto (la pagina si aggiorna da sola).");
    },
    onError: (e: Error) => setMessage(`Errore: ${e.message}`),
  });
  const verify = useMutation({
    mutationFn: () => api.post(`/regions/${encodeURIComponent(region)}/verify`),
    onSuccess: () => {
      setMessage(
        "Verifica avviata: apro il link di ogni avviso senza scadenza (pagina o PDF) e leggo la data. Ci vuole qualche minuto; la pagina si aggiorna da sola.",
      );
    },
    onError: (e: Error) => setMessage(`Errore: ${e.message}`),
  });
  const referenti = useMutation({
    mutationFn: (recordId: string) =>
      api.post<{ task_id: string; ente: string }>(`/regions/${encodeURIComponent(region)}/records/${recordId}/referenti`),
    onSuccess: async (d) => {
      setMessage(`Ricerca referenti di ${d.ente} avviata: leggo il documento e le pagine di giunta e uffici tecnici (1-2 minuti)…`);
      // Wait for the real outcome instead of leaving the user guessing.
      for (let i = 0; i < 80; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        try {
          const st = await api.get<{ status: string; result?: { trovati?: number; pagine?: number; proposte?: number; metodo?: string; error?: string; lacune?: string[]; stampa?: string }; error?: string }>(
            `/admin/task-status/${d.task_id}`,
          );
          if (st.status === "SUCCESS") {
            const r = st.result ?? {};
            setMessage(
              r.error
                ? `Referenti: ${r.error}`
                : r.trovati
                  ? `Referenti di ${d.ente}: trovati ${r.trovati} (metodo: ${r.metodo ?? "?"}, fonti controllate: ${r.pagine ?? "?"}).${r.lacune?.length ? ` Lacune: ${r.lacune.slice(0, 3).join("; ")}.` : ""}${r.stampa ? ` Stampa: ${r.stampa}` : ""}`
                  : `Referenti di ${d.ente}: nessun nome trovato (pagine lette: ${r.pagine ?? 0}, proposte lette dal testo: ${r.proposte ?? 0}, metodo: ${r.metodo ?? "?"}). I siti senza una pagina di giunta leggibile vanno guardati a mano.`,
            );
            qc.invalidateQueries({ queryKey: ["region", region] });
            return;
          }
          if (st.status === "FAILURE") {
            setMessage(`Ricerca referenti fallita: ${(st.error ?? "errore sconosciuto").slice(0, 300)}`);
            return;
          }
        } catch {
          /* keep waiting */
        }
      }
      setMessage("La ricerca referenti sta richiedendo più del previsto: controlla i log del worker (docker compose logs worker).");
    },
    onError: (e: Error) => setMessage(`Errore: ${e.message}`),
  });
  const digest = useMutation({
    mutationFn: () => api.post(`/regions/${encodeURIComponent(region)}/send-digest`),
    onSuccess: () =>
      setMessage(
        "Invio richiesto. Se il server di posta (SMTP) non è configurato la mail non parte e i record restano in attesa.",
      ),
    onError: (e: Error) => setMessage(`Errore: ${e.message}`),
  });

  const download = async (path: string, filename: string) => {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const token = getToken();
    const res = await fetch(`${base}/regions/${encodeURIComponent(region)}/${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      setMessage(`Esportazione non riuscita (${res.status})`);
      return;
    }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };
  const downloadCsv = () => download("records.csv", `record_${region}.csv`);

  const daysLeft = (d: string | null): number | null =>
    d ? Math.ceil((Date.parse(d) - Date.now()) / 86_400_000) : null;

  if (isLoading) return <p className="text-sm text-neutral-500">Caricamento…</p>;
  if (error || !data) return <p className="text-sm text-red-600">Regione non trovata.</p>;

  const byCat = (c: Categoria) => data.records.filter((r) => r.categoria === c);
  const failing = data.comuni.filter((c) => c.stato === "failing").length;
  const tabs: TabDef<Tab>[] = [
    { key: "pre_gara", label: CATEGORIA_LABEL.pre_gara, n: byCat("pre_gara").length, group: "opportunita", tone: "sky" },
    { key: "manifestazione_interesse", label: CATEGORIA_LABEL.manifestazione_interesse, n: byCat("manifestazione_interesse").length, group: "opportunita", tone: "violet" },
    { key: "gara", label: CATEGORIA_LABEL.gara, n: byCat("gara").length, group: "opportunita", tone: "emerald" },
    { key: "verifica", label: "Da verificare", n: data.da_verificare?.length ?? 0, group: "lavoro", tone: "amber" },
    { key: "siti", label: "Siti", n: data.comuni.length + data.siti_regionali.length, group: "lavoro", tone: "neutral" },
    { key: "scan", label: "Raccolta", group: "lavoro", tone: "neutral" },
  ];

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <Link href="/regions" className="text-xs text-neutral-500 hover:underline">← Regioni</Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">
            {data.region}{" "}
            <span className={`ml-2 rounded-full px-2 py-0.5 align-middle text-xs ${data.enabled ? "bg-emerald-100 text-emerald-800" : "bg-neutral-200 text-neutral-600"}`}>
              {data.enabled ? "attiva" : "spenta"}
            </span>
          </h1>
          {admin && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <button type="button" disabled={collect.isPending}
                className="rounded-lg bg-neutral-900 px-4 py-1.5 font-medium text-white shadow-sm hover:bg-neutral-700 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
                title="Rilegge tutti i comuni della regione"
                onClick={() => collect.mutate(undefined)}>
                Raccogli ora
              </button>
              <button type="button" disabled={collect.isPending}
                className="rounded-lg border px-3 py-1.5 hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800"
                title="Salta i comuni già letti nelle ultime 24 ore: per riprendere una raccolta interrotta senza rifare e ripagare quelli già fatti"
                onClick={() => collect.mutate({ resume: true })}>
                Riprendi
              </button>
              <button type="button" disabled={collect.isPending}
                className="rounded-lg border px-3 py-1.5 hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800"
                title="Scansiona solo 10 comuni: per verificare che tutto funzioni senza spendere un giro intero"
                onClick={() => collect.mutate({ limit: 10 })}>
                Prova con 10 comuni
              </button>
              <details className="relative">
                <summary className="cursor-pointer list-none rounded-lg border px-3 py-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800">
                  Altro ▾
                </summary>
                <div className="absolute right-0 z-20 mt-2 w-60 space-y-0.5 rounded-lg border bg-white p-1.5 text-left shadow-lg dark:border-neutral-700 dark:bg-neutral-900">
                  <MenuItem onClick={() => processNow.mutate()} disabled={processNow.isPending}
                    hint="Elabora i dati già raccolti senza rileggere i siti">Elabora ora</MenuItem>
                  <MenuItem onClick={() => digest.mutate()} disabled={digest.isPending}
                    hint="Invia ai referenti email i nuovi avvisi">Invia email ora</MenuItem>
                  <hr className="my-1 dark:border-neutral-700" />
                  <MenuItem onClick={downloadCsv} hint="Tutti i record, anche quelli scaduti (segnati)">Scarica CSV</MenuItem>
                  <MenuItem onClick={() => download("referenti.xlsx", `referenti_${region}.xlsx`)}
                    hint="Indice e un foglio per provincia, da condividere">Referenti (xlsx)</MenuItem>
                  <MenuItem onClick={() => download("referenti.xlsx?interno=true", `referenti_${region}_interno.xlsx`)}
                    hint="Con affidabilità, azione, fonti e motivi (uso interno)">Referenti interno</MenuItem>
                  <hr className="my-1 dark:border-neutral-700" />
                  <MenuItem onClick={() => save.mutate({ enabled: !data.enabled })}
                    hint={data.enabled ? "Smette di raccogliere e notificare" : "Include la regione nelle raccolte"}>
                    {data.enabled ? "Spegni regione" : "Attiva regione"}
                  </MenuItem>
                </div>
              </details>
            </div>
          )}
        </div>
        <ClaudeStatusBanner />
        {data.ultimo_scan?.errore && !/Claude non disponibile|credit balance|usage limits/i.test(data.ultimo_scan.errore) && (
          <p className="rounded border border-red-300 bg-red-50 p-2 text-xs text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100">
            Ultima raccolta ({fmt(data.ultimo_scan.at)}) non riuscita: {data.ultimo_scan.errore.slice(0, 300)}
          </p>
        )}
        {message && <p className="rounded bg-sky-50 p-2 text-xs text-sky-900 dark:bg-sky-950 dark:text-sky-100">{message}</p>}
        <div className="text-xs text-neutral-600 dark:text-neutral-400">
          Referenti email:{" "}
          {recipients === null ? (
            <>
              <b>{data.recipients ?? "nessuno"}</b>
              {admin && (
                <button type="button" className="ml-2 underline" onClick={() => setRecipients(data.recipients ?? "")}>
                  modifica
                </button>
              )}
            </>
          ) : (
            <span className="inline-flex gap-2">
              <input value={recipients} onChange={(e) => setRecipients(e.target.value)}
                placeholder="mail1@x.it, mail2@x.it"
                className="w-72 rounded border px-2 py-0.5 dark:bg-neutral-900" />
              <button type="button" className="underline" onClick={() => save.mutate({ recipients })}>salva</button>
              <button type="button" className="underline" onClick={() => setRecipients(null)}>annulla</button>
            </span>
          )}
          {" · "}ultima email: {fmt(data.last_digest_at)}
          {failing > 0 && <> · <span className="text-red-600">{failing} comuni con siti non raggiungibili</span></>}
        </div>
      </header>

      <RegionTabs tabs={tabs} active={tab} onSelect={setTab} />

      {tab === "scan" ? (
        <ScanView region={region} />
      ) : tab === "verifica" ? (
        <ul className="space-y-3">
          <li className="text-xs text-neutral-500">
            Avvisi in attesa di lettura del documento: per gare e manifestazioni serve una scadenza letta nel documento e successiva
            alla verifica; per le pre-gare serve la data dell'atto. Finché non è confermata non compaiono nelle liste né nelle email. {admin && (
              <button type="button" className="underline" disabled={verify.isPending} onClick={() => verify.mutate()}>
                Verifica ora (apre i link e legge la scadenza)
              </button>
            )}
          </li>
          {(data.da_verificare ?? []).length === 0 && <li className="text-sm text-neutral-500">Nessun avviso da verificare.</li>}
          {(data.da_verificare ?? []).map((r) => (
            <li key={r.id} className="rounded border p-3 text-sm dark:border-neutral-800">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <b>{r.ente}</b>
                <span className="text-xs text-neutral-500">
                  {CATEGORIA_LABEL[r.categoria]} · visto il {fmt(r.first_seen_at)}
                  {r.scadenza && ` · scadenza indicata nella lista: ${fmt(r.scadenza).split(",")[0]} (non confermata dal documento)`}
                  {r.verificato && " · letto il documento, nessuna conferma"}
                </span>
              </div>
              <p className="mt-1">{r.descrizione}</p>
              <a href={r.link} target="_blank" rel="noreferrer" className="text-xs text-sky-700 underline">apri il documento</a>
            </li>
          ))}
        </ul>
      ) : tab !== "siti" ? (
        <ul className="space-y-3">
          {data.scadute_nascoste > 0 && (
            <li className="text-xs text-neutral-500">
              {data.scadute_nascoste} avvisi con scadenza passata (o molto vecchi) nascosti.{" "}
              <button type="button" className="underline" onClick={() => setShowExpired(true)}>mostra</button>
            </li>
          )}
          {showExpired && (
            <li className="text-xs text-neutral-500">
              Stai vedendo anche gli avvisi scaduti.{" "}
              <button type="button" className="underline" onClick={() => setShowExpired(false)}>nascondili</button>
            </li>
          )}
          {byCat(tab).length === 0 && (
            <li className="text-sm text-neutral-500">
              Nessun elemento negli ultimi 60 giorni.
            </li>
          )}
          {byCat(tab).map((r) => (
            <li key={r.id} className="rounded border p-3 text-sm dark:border-neutral-800">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <b>{r.ente}</b>
                <span className="text-xs text-neutral-500">
                  visto il {fmt(r.first_seen_at)}
                  {r.scadenza && (
                    <>
                      {" "}· {r.scaduto ? <span className="text-red-700">scaduto il {fmt(r.scadenza).split(",")[0]}</span> : (
                        <span className="font-medium text-amber-700 dark:text-amber-300">
                          scade il {fmt(r.scadenza).split(",")[0]} (tra {daysLeft(r.scadenza)} giorni)
                        </span>
                      )}
                    </>
                  )}
                  {r.scaduto && !r.scadenza && <span className="text-red-700"> · molto vecchio</span>}
                  {r.data_non_verificata && <span className="text-amber-700"> · data non verificata</span>}
                  {r.notificato ? " · email inviata" : " · email in attesa"}
                </span>
              </div>
              {r.servizi.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {r.servizi.map((k) => (
                    <span key={k} className="rounded-full bg-sky-100 px-2 py-0.5 text-[11px] text-sky-900 dark:bg-sky-950 dark:text-sky-200">
                      {SERVIZIO_LABEL[k] ?? k}
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-1 text-neutral-700 dark:text-neutral-300">{(r.descrizione ?? "").slice(0, 300)}</p>
              <a href={r.link} target="_blank" rel="noreferrer" className="mt-1 inline-block break-all text-xs text-sky-700 underline dark:text-sky-300">
                {r.link}
              </a>
              <div className="mt-2 border-t pt-2 text-xs dark:border-neutral-800">
                {r.referenti_sintesi && (r.referenti ?? []).length > 0 && (
                  <p className="mb-1 text-neutral-600 dark:text-neutral-400">
                    Affidabilità <b>{r.referenti_sintesi.etichetta}</b> ({r.referenti_sintesi.affidabilita_pct}%) · {r.referenti_sintesi.azione}
                    {" · "}
                    <a className="underline" href={r.referenti_sintesi.stampa_url} target="_blank" rel="noreferrer"
                      title="Cerca sulla stampa degli ultimi 6 mesi rimpasti o cambi di assessore">
                      controlla la stampa
                    </a>
                  </p>
                )}
                {(r.referenti ?? []).length > 0 ? (
                  <ul className="space-y-1">
                    {r.referenti.map((p) => (
                      <li key={`${p.ruolo}-${p.nome}`}>
                        <b>{RUOLO_LABEL[p.ruolo]}</b>: {p.nome}
                        {p.qualifica && <span className="text-neutral-500"> ({p.qualifica})</span>}
                        {p.email && <> · <a className="text-sky-700 underline" href={`mailto:${p.email}`}>{p.email}</a></>}
                        {p.telefono && <> · {p.telefono}</>}
                        {p.stato === "da_confermare" && (
                          <span className="ml-1 rounded bg-amber-100 px-1 text-amber-900" title={p.motivo ?? undefined}>
                            da confermare{p.motivo ? `: ${p.motivo}` : ""}
                          </span>
                        )}
                        {" "}<a className="text-neutral-500 underline" href={p.fonte_url} target="_blank" rel="noreferrer" title={p.citazione ?? "fonte"}>fonte</a>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-neutral-500">Referenti non ancora cercati.</span>
                )}
                {admin && (
                  <button type="button" className="ml-2 underline" disabled={referenti.isPending}
                    onClick={() => referenti.mutate(r.id)}>
                    {(r.referenti ?? []).length > 0 ? "aggiorna referenti" : "Trova referenti"}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="space-y-6">
          <section>
            <h2 className="mb-2 font-semibold">Siti regionali ({data.siti_regionali.length})</h2>
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-neutral-500"><tr><th className="py-1">Sito</th><th>Ruolo</th><th>Ultimo controllo</th><th>Esito</th><th></th></tr></thead>
              <tbody>
                {data.siti_regionali.map((s) => (
                  <tr key={s.id} className="border-t dark:border-neutral-800">
                    <td className={`py-1.5 ${s.active ? "" : "opacity-70"}`}>
                      <a href={s.url} target="_blank" rel="noreferrer" className="underline">{s.nome}</a>
                      {s.scoperto_da && (
                        <div className="text-xs text-amber-700 dark:text-amber-300" title={s.scoperto_da.comuni.join(", ")}>
                          scoperto da {s.scoperto_da.count} {s.scoperto_da.count === 1 ? "comune" : "comuni"}
                          {!s.active && " · da approvare"}
                        </div>
                      )}
                    </td>
                    <td>{s.ruolo ?? "—"}</td>
                    <td>{fmt(s.last_checked_at)}</td>
                    <td>
                      {s.ultimo_run == null ? <span className={`rounded-full px-2 py-0.5 text-xs ${STATO_CLASS.unchecked}`}>non verificato</span>
                        : s.ultimo_run.status === "failed"
                          ? <span className={`rounded-full px-2 py-0.5 text-xs ${STATO_CLASS.failing}`} title={s.ultimo_run.errore ?? ""}>errore</span>
                          : <span className={`rounded-full px-2 py-0.5 text-xs ${STATO_CLASS.ok}`}>letto ({s.ultimo_run.found} trovati)</span>}
                    </td>
                    <td>
                      {admin && (
                        <button type="button" className="rounded border px-2 py-0.5 text-xs hover:bg-neutral-100 dark:hover:bg-neutral-800"
                          onClick={() => toggleSite.mutate({ id: s.id, active: !s.active })}>
                          {s.active ? "Disattiva" : "Attiva"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {data.siti_regionali.length === 0 && <tr><td colSpan={5} className="py-2 text-neutral-500">Nessun sito regionale nel catalogo per questa regione.</td></tr>}
              </tbody>
            </table>
          </section>
          <section>
            <h2 className="mb-2 font-semibold">Comuni ({data.comuni.length})</h2>
            {data.comuni.length === 0 && (
              <p className="text-sm text-neutral-500">
                Nessun comune caricato. Importa l&apos;elenco da IPA: <code>python -m infra.scripts.import_ipa --region &quot;{data.region}&quot; --file amministrazioni.csv</code>
              </p>
            )}
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-neutral-500"><tr><th className="py-1">Comune</th><th>Siti da leggere</th><th>Stato</th></tr></thead>
              <tbody>
                {data.comuni.map((c) => (
                  <tr key={c.id} className={`border-t align-top dark:border-neutral-800 ${c.active ? "" : "opacity-60"}`}>
                    <td className="py-1.5">{c.ente}{c.provincia && <span className="text-xs text-neutral-500"> ({c.provincia})</span>}</td>
                    <td className="space-y-0.5">
                      {c.siti.length === 0 && <span className="text-xs text-neutral-500">nessun indirizzo noto (inattivo)</span>}
                      {c.siti.map((s) => (
                        <div key={s.url} className="text-xs"><span className="text-neutral-500">{s.ruolo}: </span>
                          <a href={s.url} target="_blank" rel="noreferrer" className="break-all underline">{s.url}</a></div>
                      ))}
                    </td>
                    <td>
                      <span className={`rounded-full px-2 py-0.5 text-xs ${STATO_CLASS[c.stato]}`}>{STATO_LABEL[c.stato]}</span>
                      {c.stato === "failing" && <div className="mt-0.5 text-xs text-red-700 dark:text-red-300">{c.last_error ? (ERROR_LABELS[c.last_error] ?? c.last_error) : "errore"} · {c.consecutive_failures}× di fila</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </div>
  );
}
