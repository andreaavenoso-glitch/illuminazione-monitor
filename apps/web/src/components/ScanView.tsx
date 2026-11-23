"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ScanItemView, ScanRunView } from "@/lib/regions";
import { usd } from "@/lib/usage";

const BAR: Record<ScanItemView["status"], string> = {
  done: "bg-emerald-500",
  running: "bg-sky-500 animate-pulse",
  error: "bg-red-500",
  skipped: "bg-neutral-400",
  interrupted: "bg-amber-500",
  queued: "",
};

const STATUS_LABEL: Record<ScanRunView["status"], string> = {
  running: "in corso",
  done: "conclusa",
  failed: "conclusa con errori",
  interrupted: "interrotta (il worker si è fermato)",
  stopped: "fermata dall'utente",
};

function clock(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function hhmm(ms: number): string {
  return new Date(ms).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

/** Claude's signal for one comune: not called / called N times / a call failed. */
function ClaudeDot({ i }: { i: ScanItemView }) {
  if (i.claude_errors > 0) {
    return <span className="text-red-600" title={`${i.claude_errors} chiamate a Claude fallite`}>● errore</span>;
  }
  if (i.claude_calls > 0) {
    return <span className="text-sky-600" title={`${i.claude_calls} pagine inviate a Claude`}>● {i.claude_calls}</span>;
  }
  if (i.status === "queued" || i.status === "running") return <span className="text-neutral-300">○</span>;
  return <span className="text-neutral-400" title="nessuna pagina ha superato il filtro: Claude non chiamato">○ —</span>;
}

export function ScanView({ region }: { region: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["scan", region],
    queryFn: () => api.get<ScanRunView | null>(`/regions/${encodeURIComponent(region)}/scan`),
    // Fast while a run is going, and also while none exists yet: a run just started
    // shows up within seconds instead of after the slow poll.
    refetchInterval: (q) => (!q.state.data || q.state.data.status === "running" ? 3000 : 20000),
  });

  if (isLoading) return <p className="text-sm text-neutral-500">Caricamento…</p>;
  if (!data) {
    return (
      <p className="text-sm text-neutral-500">
        Nessuna raccolta registrata per questa regione. Premi &quot;Prova con 10 comuni&quot; o &quot;Raccogli ora&quot;.
        Se l&apos;hai appena premuto, aspetta qualche secondo: questa pagina si aggiorna da sola appena il worker comincia.
      </p>
    );
  }

  const start = Date.parse(data.started_at);
  // A finished run ends at its end time, an interrupted one at its last sign of
  // life (not "now", which would stretch the timeline to hours later).
  const end = data.ended_at
    ? Date.parse(data.ended_at)
    : data.status === "interrupted"
      ? start + data.elapsed_s * 1000
      : Date.now();
  const span = Math.max(1000, end - start);
  const pct = data.total ? Math.round((data.done / data.total) * 100) : 0;
  const claude = data.claude;

  return (
    <div className="space-y-4">
      {/* Overall progress */}
      <section className="rounded border p-3 dark:border-neutral-800">
        <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
          <span>
            Raccolta <b>{STATUS_LABEL[data.status]}</b>
            {data.limit ? <span className="text-neutral-500"> · prova su {data.limit} comuni</span> : null}
          </span>
          <span className="text-xs text-neutral-500">
            iniziata alle {hhmm(start)} · durata {clock(data.elapsed_s)}
            {data.status === "running" && data.eta_s != null && <> · fine stimata alle <b>{hhmm(Date.now() + data.eta_s * 1000)}</b> (tra {clock(data.eta_s)})</>}
            {data.ended_at && <> · finita alle {hhmm(end)}</>}
          </span>
        </div>
        <div className="mt-2 h-3 w-full overflow-hidden rounded bg-neutral-200 dark:bg-neutral-800">
          <div className={`h-full ${data.status === "interrupted" || data.status === "failed" || data.status === "stopped" ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">
          {data.done}/{data.total} comuni ({pct}%) · {data.running} in corso
          {data.interrupted > 0 && <> · {data.interrupted} interrotti a metà</>} · {data.queued} in coda · {data.errors} con errore
        </p>
        {data.total === 0 && data.status !== "running" && (
          <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-100">
            Nessun comune da leggere: con &quot;Riprendi&quot; vengono saltati i comuni già letti nelle ultime 24 ore, e
            qui sono tutti già letti. Per rifarli comunque usa &quot;Raccogli ora&quot;.
          </p>
        )}
        {data.error && <p className="mt-2 rounded bg-red-50 p-2 text-xs text-red-900 dark:bg-red-950 dark:text-red-100">{data.error.slice(0, 300)}</p>}
      </section>

      {/* Claude signal */}
      <section
        className={`rounded border p-3 text-sm ${
          claude.status === "down"
            ? "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100"
            : claude.status === "rules"
              ? "border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-100"
              : claude.status === "ok"
              ? "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100"
              : "border-neutral-300 bg-neutral-50 text-neutral-700 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-300"
        }`}
      >
        {claude.status === "down" && (
          <>
            <b>Claude non disponibile.</b> La raccolta si è fermata: ogni chiamata viene rifiutata.
            {claude.error && <div className="mt-1 text-xs">{claude.error.slice(0, 300)}</div>}
          </>
        )}
        {claude.status === "rules" && (
          <>
            <b>Modalità regole (senza costi)</b>: gli avvisi sono estratti dagli elenchi strutturati con regole fisse. Le pagine senza
            elenco non vengono lette finché Claude non è di nuovo disponibile; le scadenze si leggono con "Verifica ora".
            {claude.error && <div className="mt-1 text-xs">{claude.error.slice(0, 300)}</div>}
          </>
        )}
        {claude.status === "ok" && (
          <>
            <b>Claude attivo</b>: {claude.calls} pagine analizzate
            {data.cost_usd != null && <> · costo stimato di questa raccolta <b>{usd(data.cost_usd)}</b></>}
            {claude.call_errors > 0 && <span className="text-red-700"> · {claude.call_errors} chiamate fallite</span>}
          </>
        )}
        {claude.status === "unused" && (
          <>
            <b>Claude non ancora chiamato.</b> Nessuna pagina ha superato il filtro finora (il filtro scarta le pagine senza
            parole chiave dei servizi prima di spendere una chiamata).
          </>
        )}
      </section>

      {/* Timeline: one bar per comune, from start to end of its reading */}
      <section>
        <div className="mb-1 flex items-center justify-between text-[11px] text-neutral-500">
          <span>Linea del tempo (0 → {clock(span / 1000)}) · ● Claude chiamato, ○ non chiamato</span>
          <span className="flex gap-3">
            <span><span className="mr-1 inline-block h-2 w-3 rounded bg-emerald-500" />finito</span>
            <span><span className="mr-1 inline-block h-2 w-3 rounded bg-sky-500" />in corso</span>
            <span><span className="mr-1 inline-block h-2 w-3 rounded bg-red-500" />errore</span>
            <span><span className="mr-1 inline-block h-2 w-3 rounded bg-amber-500" />interrotto</span>
          </span>
        </div>
        <ul className="space-y-0.5">
          {data.items.map((i) => {
            const s = i.started_at ? Date.parse(i.started_at) : null;
            const e = i.ended_at ? Date.parse(i.ended_at) : end;
            const left = s == null ? 0 : Math.min(99.4, Math.max(0, ((s - start) / span) * 100));
            const width = s == null ? 0 : Math.min(100 - left, Math.max(0.6, ((e - s) / span) * 100));
            const tip =
              `${i.ente}\n${i.status}` +
              (i.duration_s != null ? ` · ${clock(i.duration_s)}` : "") +
              `\npagine lette ${i.pages_read}, scartate ${i.pages_skipped}, a Claude ${i.claude_calls}` +
              (i.deepest ? `, profondità ${i.deepest}` : "") +
              (i.stopped_by ? `, fermata per: ${i.stopped_by}` : "") +
              (i.error ? `\n${i.error}` : "");
            return (
              <li key={i.ente + (i.started_at ?? "")} className="flex items-center gap-2 text-xs" title={tip}>
                <span className="w-44 shrink-0 truncate">{i.ente}</span>
                <span className="relative h-3.5 flex-1 rounded bg-neutral-100 dark:bg-neutral-900">
                  {s != null && (
                    <span className={`absolute top-0 h-full rounded ${BAR[i.status]}`} style={{ left: `${left}%`, width: `${width}%` }} />
                  )}
                  {i.status === "queued" && <span className="absolute inset-0 flex items-center pl-1 text-[10px] text-neutral-400">in coda</span>}
                </span>
                <span className="w-16 shrink-0 text-right tabular-nums text-neutral-500">{i.duration_s != null ? clock(i.duration_s) : ""}</span>
                <span className="w-16 shrink-0"><ClaudeDot i={i} /></span>
                <span className="w-14 shrink-0 text-right tabular-nums text-neutral-500">
                  {i.cost_usd ? usd(i.cost_usd) : ""}
                </span>
                <span className="w-20 shrink-0 text-right text-neutral-500">
                  {i.status === "done" || i.status === "error" ? `${i.records_found} record` : ""}
                </span>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
