"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ClaudeStatusBanner } from "@/components/ClaudeStatusBanner";
import { Countdown, Icon, KpiTile, StackedBar, TONE, type Tone } from "@/components/ui";
import { MenuItem, RegionTabs, type TabDef } from "@/components/RegionTabs";
import { EmailDraftBox } from "@/components/EmailDraftBox";
import { LavorazioneView } from "@/components/LavorazioneView";
import { ReferentiTable } from "@/components/ReferentiTable";
import { TargetedScan } from "@/components/TargetedScan";
import { ScanHistory } from "@/components/ScanHistory";
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
  type Referente,
  type ReferentiRiga,
} from "@/lib/regions";

type Tab = Categoria | "siti" | "scan" | "verifica" | "referenti" | "storico" | "lavorazione";

const CAT_TONE: Record<Categoria, Tone> = { pre_gara: "sky", manifestazione_interesse: "violet", gara: "emerald" };

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
  const [draft, setDraft] = useState<{ id: string; oggetto: string; corpo: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [targeted, setTargeted] = useState(false);
  const [onlyConfirmed, setOnlyConfirmed] = useState(false);

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
                  ? `Referenti di ${d.ente}: trovati ${r.trovati} (metodo: ${r.metodo ?? "?"}, fonti controllate: ${r.pagine ?? "?"}).${r.lacune?.length ? ` Lacune: ${r.lacune.slice(0, 2).map((x) => x.slice(0, 120)).join("; ")}…` : ""}${r.stampa ? ` Stampa: ${r.stampa.slice(0, 120)}` : ""} Dettagli nella checklist della scheda.`
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
  const trackTask = async (taskId: string, label: string) => {
    for (let i = 0; i < 2400; i++) {
      await new Promise((r) => setTimeout(r, 4000));
      try {
        const st = await api.get<{ status: string; result?: { trovati?: number; error?: string; enti?: number; con_sindaco?: number }; error?: string }>(
          `/admin/task-status/${taskId}`,
        );
        if (st.status === "SUCCESS") {
          const r = st.result ?? {};
          setMessage(
            r.error
              ? `${label}: ${r.error}`
              : r.enti !== undefined
                ? `${label}: cercati ${r.enti} comuni, con almeno un nome trovato: ${r.con_sindaco ?? 0}.`
                : `${label}: trovati ${r.trovati ?? 0} nomi.`,
          );
          qc.invalidateQueries({ queryKey: ["region", region] });
          return;
        }
        if (st.status === "FAILURE") {
          setMessage(`${label} fallita: ${(st.error ?? "errore").slice(0, 200)}`);
          return;
        }
      } catch {
        /* keep waiting */
      }
    }
  };
  const activeScans = useQuery({
    queryKey: ["active-scans"],
    queryFn: () => api.get<{ region: string | null; total: number; done: number }[]>("/regions/scans/active"),
    refetchInterval: 5000,
  });
  const running = (activeScans.data ?? []).some((a) => a.region === region || a.region === null);
  const stop = useMutation({
    mutationFn: () => api.post<{ stopped: boolean }>(`/regions/${encodeURIComponent(region)}/stop`),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["active-scans"] });
      setMessage(
        d.stopped
          ? "Stop richiesto: finisco i comuni in corso (fino a qualche minuto), salto gli altri e poi elaboro quello che ho già raccolto."
          : "Nessuna raccolta in corso per questa regione.",
      );
    },
    onError: (e: Error) => setMessage(`Errore: ${e.message}`),
  });
  const collectSelected = useMutation({
    mutationFn: (ids: string[]) =>
      api.post<{ comuni: number }>(`/regions/${encodeURIComponent(region)}/collect-selected`, { ids }),
    onSuccess: (d) => {
      setTargeted(false);
      setTab("scan");
      setMessage(`Raccolta mirata avviata su ${d.comuni} comuni. Segui l'avanzamento qui sotto.`);
    },
    onError: (e: Error) => setMessage(`Errore: ${e.message}`),
  });
  const prepareEmail = useMutation({
    mutationFn: (recordId: string) =>
      api.get<{ oggetto: string; corpo: string }>(`/regions/${encodeURIComponent(region)}/records/${recordId}/email`),
    onSuccess: (d, recordId) => {
      setDraft({ id: recordId, ...d });
      setCopied(false);
    },
    onError: (e: Error) => setMessage(`Errore: ${e.message}`),
  });
  const decide = useMutation({
    mutationFn: (v: { id: string; stato: "selezionata" | "scartata" | "nessuna" }) =>
      api.post(`/regions/${encodeURIComponent(region)}/records/${v.id}/lavorazione`, { stato: v.stato }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["region", region] }),
    onError: (e: Error) => setMessage(`Errore: ${e.message}`),
  });
  const [busyId, setBusyId] = useState<string | null>(null);
  const pacchetto = useMutation({
    mutationFn: (v: { id: string; profondita?: "base" | "approfondita" }) =>
      api.post<{ task_id: string; ente: string; profondita: string }>(
        `/regions/${encodeURIComponent(region)}/records/${v.id}/pacchetto${v.profondita ? `?profondita=${v.profondita}` : ""}`,
      ),
    onMutate: (v) => setBusyId(v.id),
    onSuccess: async (d, v) => {
      setMessage(`Pacchetto di ${d.ente}: leggo i documenti (${d.profondita}) e cerco i referenti…`);
      await trackTask(d.task_id, `Pacchetto di ${d.ente}`);
      setBusyId((cur) => (cur === v.id ? null : cur));
    },
    onError: (e: Error, v) => {
      setBusyId((cur) => (cur === v.id ? null : cur));
      setMessage(`Errore: ${e.message}`);
    },
  });
  const analizza = useMutation({
    mutationFn: (v: { id: string; profondita?: "base" | "approfondita" }) =>
      api.post<{ task_id: string; ente: string }>(
        `/regions/${encodeURIComponent(region)}/records/${v.id}/analizza?profondita=${v.profondita ?? "base"}`,
      ),
    onSuccess: async (d) => {
      setMessage(`Analisi della documentazione di ${d.ente} avviata: leggo la pagina e gli allegati…`);
      for (let i = 0; i < 80; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        try {
          const st = await api.get<{ status: string; result?: { documenti?: number; letti?: number; campi?: number; error?: string }; error?: string }>(
            `/admin/task-status/${d.task_id}`,
          );
          if (st.status === "SUCCESS") {
            const r = st.result ?? {};
            setMessage(
              r.error
                ? `Analisi: ${r.error}`
                : `Analisi di ${d.ente}: ${r.letti ?? 0} documenti letti su ${r.documenti ?? 0}, ${r.campi ?? 0} dati estratti (vedi la scheda).`,
            );
            qc.invalidateQueries({ queryKey: ["region", region] });
            return;
          }
          if (st.status === "FAILURE") {
            setMessage(`Analisi fallita: ${(st.error ?? "errore").slice(0, 200)}`);
            return;
          }
        } catch {
          /* keep waiting */
        }
      }
    },
    onError: (e: Error) => setMessage(`Errore: ${e.message}`),
  });
  const referentiEnte = useMutation({
    mutationFn: (ente: string) =>
      api.post<{ task_id: string }>(`/regions/${encodeURIComponent(region)}/referenti/ente?ente=${encodeURIComponent(ente)}`),
    onSuccess: (d, ente) => {
      setMessage(`Ricerca referenti di ${ente} avviata…`);
      void trackTask(d.task_id, `Referenti di ${ente}`);
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

  const byCat = (c: Categoria) => data.records.filter((r) => r.categoria === c && (!onlyConfirmed || r.confermato !== false));
  const confirmedIn = (c: Categoria) => data.records.filter((r) => r.categoria === c && r.confermato !== false).length;
  const allIn = (c: Categoria) => data.records.filter((r) => r.categoria === c).length;
  const failing = data.comuni.filter((c) => c.stato === "failing").length;
  const tabs: TabDef<Tab>[] = [
    { key: "pre_gara", label: CATEGORIA_LABEL.pre_gara, n: allIn("pre_gara"), group: "opportunita", tone: "sky" },
    { key: "manifestazione_interesse", label: CATEGORIA_LABEL.manifestazione_interesse, n: allIn("manifestazione_interesse"), group: "opportunita", tone: "violet" },
    { key: "gara", label: CATEGORIA_LABEL.gara, n: allIn("gara"), group: "opportunita", tone: "emerald" },
    { key: "lavorazione", label: "Lavorazione", n: data.records.filter((r) => r.lavorazione?.stato === "selezionata").length, group: "lavoro", tone: "emerald" },
    { key: "referenti", label: "Referenti", n: (data.referenti_comuni ?? []).filter((r) => r.cercato).length, group: "lavoro", tone: "violet" },
    { key: "verifica", label: "Da verificare", n: data.da_verificare?.length ?? 0, group: "lavoro", tone: "amber" },
    { key: "siti", label: "Siti", n: data.comuni.length + data.siti_regionali.length, group: "lavoro", tone: "neutral" },
    { key: "scan", label: "Raccolta", group: "lavoro", tone: "neutral" },
    { key: "storico", label: "Storico", group: "lavoro", tone: "neutral" },
  ];

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <Link href="/regions" className="text-xs text-neutral-500 hover:text-brand-600">← Tutte le regioni</Link>
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-gradient-to-r from-brand-600 to-sky-500 p-5 text-white shadow-lift">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{data.region}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-white/85">
              <span className={`chip ${data.enabled ? "bg-white/20 text-white" : "bg-black/20 text-white"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${data.enabled ? "bg-emerald-300" : "bg-neutral-300"}`} />
                {data.enabled ? "attiva" : "spenta"}
              </span>
              <span>{data.comuni.length} comuni · {failing > 0 ? `${failing} con siti non raggiungibili` : "tutti i siti letti senza errori"}</span>
            </p>
          </div>
          {admin && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <button type="button" disabled={collect.isPending}
                className="rounded-lg bg-white px-4 py-1.5 font-semibold text-brand-700 shadow-sm hover:bg-brand-50 disabled:opacity-50"
                title="Rilegge tutti i comuni della regione"
                onClick={() => collect.mutate(undefined)}>
                Raccogli ora
              </button>
              <button type="button" disabled={collect.isPending}
                className="rounded-lg border border-white/40 px-3 py-1.5 hover:bg-white/15 disabled:opacity-50"
                title="Salta i comuni già letti nelle ultime 24 ore: per riprendere una raccolta interrotta senza rifare e ripagare quelli già fatti"
                onClick={() => collect.mutate({ resume: true })}>
                Riprendi
              </button>
              <button type="button" disabled={collect.isPending}
                className="rounded-lg border border-white/40 px-3 py-1.5 hover:bg-white/15 disabled:opacity-50"
                title="Scansiona solo 10 comuni: per verificare che tutto funzioni senza spendere un giro intero"
                onClick={() => collect.mutate({ limit: 10 })}>
                Prova con 10 comuni
              </button>
              <button type="button" disabled={collect.isPending}
                className="rounded-lg border border-white/40 px-3 py-1.5 hover:bg-white/15 disabled:opacity-50"
                title="Scegli esattamente quali comuni leggere (per provincia, nome, stato)"
                onClick={() => setTargeted((v) => !v)}>
                Raccolta mirata
              </button>
              {running && (
                <button type="button" disabled={stop.isPending}
                  className="animate-pulse rounded-lg bg-red-500 px-3 py-1.5 font-semibold text-white shadow-sm hover:bg-red-600 disabled:opacity-50"
                  title="Ferma la raccolta in corso: i comuni già letti restano salvati"
                  onClick={() => stop.mutate()}>
                  ■ Ferma raccolta
                </button>
              )}
              <details className="relative">
                <summary className="cursor-pointer list-none rounded-lg border border-white/40 px-3 py-1.5 hover:bg-white/15">
                  Altro ▾
                </summary>
                <div className="absolute right-0 z-20 mt-2 w-60 space-y-0.5 rounded-xl border bg-white p-1.5 text-left text-neutral-900 shadow-lg dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100">
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
        {targeted && (
          <TargetedScan comuni={data.comuni} busy={collectSelected.isPending}
            onStart={(ids) => collectSelected.mutate(ids)} onClose={() => setTargeted(false)} />
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

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile label="Pre-gare" hint={`${confirmedIn("pre_gara")} con data confermata`} value={allIn("pre_gara")} icon="bolt" tone="sky" onClick={() => setTab("pre_gara")} active={tab === "pre_gara"} />
        <KpiTile label="Manifestazioni di interesse" hint={`${confirmedIn("manifestazione_interesse")} con scadenza confermata`} value={allIn("manifestazione_interesse")} icon="hand" tone="violet"
          onClick={() => setTab("manifestazione_interesse")} active={tab === "manifestazione_interesse"} />
        <KpiTile label="Gare" hint={`${confirmedIn("gara")} con scadenza confermata`} value={allIn("gara")} icon="flag" tone="emerald" onClick={() => setTab("gara")} active={tab === "gara"} />
        <KpiTile label="Da verificare" value={data.da_verificare?.length ?? 0} icon="alert" tone="amber"
          hint="senza scadenza confermata" onClick={() => setTab("verifica")} active={tab === "verifica"} />
      </section>
      <div className="card flex flex-wrap items-center gap-4 p-3 text-xs text-neutral-600 dark:text-neutral-300">
        <span className="font-medium">Stato dei siti</span>
        <div className="min-w-[10rem] flex-1">
          <StackedBar height="h-2" parts={[
            { label: "Raggiungibili", value: data.comuni.filter((c) => c.stato === "ok").length, tone: "emerald" },
            { label: "Con errori", value: failing, tone: "red" },
            { label: "Non verificati", value: data.comuni.filter((c) => c.stato === "unchecked").length, tone: "neutral" },
          ]} />
        </div>
        <span className="text-emerald-700">{data.comuni.filter((c) => c.stato === "ok").length} ok</span>
        <span className="text-red-600">{failing} errori</span>
        <span>{data.comuni.filter((c) => c.stato === "unchecked").length} da verificare</span>
      </div>
      <RegionTabs tabs={tabs} active={tab} onSelect={setTab} />

      {tab === "scan" ? (
        <ScanView region={region} />
      ) : tab === "storico" ? (
        <ScanHistory region={region} />
      ) : tab === "lavorazione" ? (
        <LavorazioneView
          records={data.records}
          ultimaRaccolta={data.ultimo_scan?.at ?? null}
          onVaiRaccolta={() => setTab("scan")}
          admin={admin}
          busy={busyId}
          onDecide={(id, stato) => decide.mutate({ id, stato })}
          onPacchetto={(id, profondita) => pacchetto.mutate({ id, profondita })}
          onEmail={(id) => prepareEmail.mutate(id)}
          onSlide={(id, ente) => download(`records/${id}/slide.pptx`, `scheda_${ente}.pptx`)}
          renderDraft={(id) =>
            draft?.id === id ? (
              <EmailDraftBox draft={draft} onChange={setDraft} copied={copied} onCopied={() => setCopied(true)}
                onCopyError={() => setMessage("Copia non riuscita: seleziona il testo e copialo a mano.")} onClose={() => setDraft(null)} />
            ) : null
          }
        />
      ) : tab === "referenti" ? (
        <ReferentiTable
          rows={(data.referenti_comuni ?? []).filter((r) => r.cercato)}
          admin={admin}
          busy={referentiEnte.isPending}
          onFind={(e) => referentiEnte.mutate(e)}
        />
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
              {r.nota && <p className="mt-1 rounded bg-neutral-50 p-2 text-[11px] text-neutral-600 dark:bg-neutral-800/60 dark:text-neutral-300">Provato: {r.nota}</p>}
              <a href={r.link} target="_blank" rel="noreferrer" className="text-xs text-sky-700 underline">apri il documento</a>
            </li>
          ))}
        </ul>
      ) : tab !== "siti" ? (
        <ul className="space-y-3">
          <li className="flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-500">
            <span>
              Tutti i candidati trovati: quelli <b className="text-amber-700">da verificare</b> non hanno ancora la scadenza letta nel documento
              (non partono nelle email finché non sono confermati).
            </span>
            <label className="flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" checked={onlyConfirmed} onChange={(e) => setOnlyConfirmed(e.target.checked)} />
              solo confermati
            </label>
          </li>
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
            <li key={r.id} className={`card border-l-4 p-4 text-sm ${TONE[CAT_TONE[r.categoria]].border}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className={`grid h-8 w-8 place-items-center rounded-lg ${TONE[CAT_TONE[r.categoria]].bg} ${TONE[CAT_TONE[r.categoria]].fg}`}>
                    <Icon name="building" className="h-4 w-4" />
                  </span>
                  <b className="text-base tracking-tight">{r.ente}</b>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Countdown iso={r.scadenza} />
                  {r.confermato === false ? (
                    <span className="chip bg-amber-50 text-amber-700" title="Scadenza non ancora letta nel documento: usa Verifica ora">da verificare</span>
                  ) : (
                    <span className="chip bg-emerald-50 text-emerald-700"><Icon name="check" className="h-3.5 w-3.5" />confermato</span>
                  )}
                  {r.riclassificato && (
                    <span className="chip bg-violet-50 text-violet-700" title={r.verifica_nota ?? "Dopo l'analisi dei documenti l'avviso è stato spostato nella categoria giusta"}>
                      riclassificato dopo l&apos;analisi
                    </span>
                  )}
                  {r.scaduto && !r.scadenza && <span className="chip bg-red-50 text-red-700">molto vecchio</span>}
                  {r.data_non_verificata && <span className="chip bg-amber-50 text-amber-700">data non verificata</span>}
                  <span className={`chip ${r.notificato ? "bg-emerald-50 text-emerald-700" : "bg-neutral-100 text-neutral-500"}`}>
                    <Icon name="mail" className="h-3.5 w-3.5" />{r.notificato ? "email inviata" : "email in attesa"}
                  </span>
                </div>
              </div>
              <div className="mt-1 text-[11px] text-neutral-400">
                individuato il {fmt(r.first_seen_at).split(",")[0]}
                {r.scadenza && <> · scadenza {fmt(r.scadenza).split(",")[0]}</>}
              </div>
              {r.servizi.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {r.servizi.map((k) => (
                    <span key={k} className="chip bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-200">
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
                {r.ricerca && (
                  <details className="mt-1 text-neutral-600 dark:text-neutral-400">
                    <summary className="cursor-pointer">
                      Checklist {r.ricerca.passi_ok}/12
                      {r.ricerca.mandato_scadenza && <> · mandato fino al {fmt(r.ricerca.mandato_scadenza).split(",")[0].slice(3)} (stimato)</>}
                      {" · "}ricerca {r.ricerca.metodo} del {fmt(r.ricerca.eseguita_il).split(",")[0]}
                    </summary>
                    <ul className="mt-1 space-y-0.5">
                      {r.ricerca.passi.map((x) => (
                        <li key={x.n}>
                          <span className={x.ok ? "text-emerald-700" : "text-red-700"}>{x.ok ? "✔" : "✖"}</span> {x.n}. {x.passo}
                          {x.nota && <span className="text-neutral-500"> – {x.nota}</span>}
                          {x.urls.slice(0, 2).map((u) => (
                            <a key={u} href={u} target="_blank" rel="noreferrer" className="ml-1 underline">link</a>
                          ))}
                        </li>
                      ))}
                    </ul>
                    {r.ricerca.lacune.length > 0 && (
                      <p className="mt-1">Lacune: {r.ricerca.lacune.slice(0, 5).join(" · ")}</p>
                    )}
                    {r.ricerca.stampa && <p>Stampa: {r.ricerca.stampa}</p>}
                  </details>
                )}
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" disabled={prepareEmail.isPending}
                    className="rounded-lg border border-sky-400 bg-sky-50 px-3 py-1 text-xs text-sky-900 hover:bg-sky-100 disabled:opacity-50 dark:bg-sky-950 dark:text-sky-100"
                    title="Prepara il testo di una mail standard con i principali elementi dell'avviso"
                    onClick={() => prepareEmail.mutate(r.id)}>
                    Prepara email
                  </button>
                </div>
                {draft?.id === r.id && (
                  <EmailDraftBox draft={draft} onChange={setDraft} copied={copied} onCopied={() => setCopied(true)}
                    onCopyError={() => setMessage("Copia non riuscita: seleziona il testo e copialo a mano.")} onClose={() => setDraft(null)} />
                )}
                {admin && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button type="button" disabled={referenti.isPending}
                      className="rounded-lg border px-3 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800"
                      onClick={() => referenti.mutate(r.id)}>
                      {(r.referenti ?? []).length > 0 ? "Aggiorna referenti del comune" : "Referenti del comune"}
                    </button>
                    <button type="button" disabled={analizza.isPending}
                      className="rounded-lg border px-3 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800"
                      title="Legge la pagina dell'avviso e i suoi allegati ed estrae i dati (CIG, importo, durata, punti luce, scadenza, RUP…)"
                      onClick={() => analizza.mutate({ id: r.id })}>
                      {r.analisi ? "Aggiorna analisi documentazione" : "Analizza documentazione"}
                    </button>
                    <button type="button" disabled={analizza.isPending}
                      className="rounded-lg border px-3 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800"
                      title="Legge anche i documenti citati dai documenti (delibere, relazioni): più a fondo, più lento"
                      onClick={() => analizza.mutate({ id: r.id, profondita: "approfondita" })}>
                      Approfondisci documentazione
                    </button>
                    <button type="button"
                      className="rounded-lg border px-3 py-1 text-xs hover:bg-neutral-100 dark:hover:bg-neutral-800"
                      title="Presentazione standard (PowerPoint): sintesi, referenti, documentazione, prossimi passi"
                      onClick={() => download(`records/${r.id}/slide.pptx`, `scheda_${r.ente}.pptx`)}>
                      Genera slide (PPT)
                    </button>
                  </div>
                )}
                {r.analisi && (
                  <details className="mt-2 text-neutral-600 dark:text-neutral-400" open>
                    <summary className="cursor-pointer">
                      Documentazione: {r.analisi.documenti.filter((d) => d.letto).length}/{r.analisi.documenti.length} letti ·{" "}
                      {Object.keys(r.analisi.campi).length} dati estratti
                    </summary>
                    <dl className="mt-1 grid grid-cols-[10rem_1fr] gap-x-3 gap-y-0.5">
                      {Object.entries(r.analisi.campi).map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt className="text-neutral-500">{k.replaceAll("_", " ")}</dt>
                          <dd title={v.contesto}>
                            {Array.isArray(v.valore) ? v.valore.join(", ") : String(v.valore)}
                            <span className="ml-1 text-[10px] text-neutral-400">({v.fonte})</span>
                          </dd>
                        </div>
                      ))}
                    </dl>
                    <ul className="mt-1">
                      {r.analisi.documenti.map((d) => (
                        <li key={d.url}>
                          <a className="underline" href={d.url} target="_blank" rel="noreferrer">{d.nome}</a>{" "}
                          <span className="text-[10px] text-neutral-400">{d.letto ? `${d.caratteri} caratteri` : "non leggibile (scansione o protetto)"}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
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
