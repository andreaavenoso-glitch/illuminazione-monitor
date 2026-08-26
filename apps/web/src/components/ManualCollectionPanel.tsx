"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";

type TaskStatus = {
  task_id: string;
  status: string;
  ready: boolean;
  result?: Record<string, number | string> | null;
  error?: string;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

async function pollTask(
  taskId: string,
  { intervalMs = 4000, timeoutMs = 20 * 60_000 }: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<TaskStatus> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await api.get<TaskStatus>(`/admin/task-status/${taskId}`);
    if (status.status === "SUCCESS" || status.status === "FAILURE") {
      return status;
    }
    await sleep(intervalMs);
  }
  throw new Error("tempo massimo di attesa superato: il lavoro sembra bloccato sul server");
}

function summarizeResult(result: TaskStatus["result"]): string {
  if (!result) return "";
  const parts: string[] = [];
  if (typeof result.sources_run === "number") parts.push(`${result.sources_run} fonti interrogate`);
  if (typeof result.items_scanned === "number") parts.push(`${result.items_scanned} comuni scansionati`);
  if (typeof result.records_found === "number") parts.push(`${result.records_found} trovati`);
  if (typeof result.records_valid === "number") parts.push(`${result.records_valid} validi`);
  if (typeof result.records_weak === "number" && result.records_weak > 0)
    parts.push(`${result.records_weak} deboli`);
  if (typeof result.duplicates_removed === "number" && result.duplicates_removed > 0)
    parts.push(`${result.duplicates_removed} doppioni rimossi`);
  if (typeof result.errors === "number" && result.errors > 0) parts.push(`${result.errors} errori`);
  return parts.join(", ");
}

// Labels for the 3 collection jobs fired in parallel by /admin/run-daily-monitor.
const COLLECT_JOBS: { key: string; label: string }[] = [
  { key: "official_task_id", label: "Fonti ufficiali (ANAC, TED, GURI, Consip)" },
  { key: "eproc_task_id", label: "Portali e-procurement" },
  { key: "watchlist_task_id", label: "Comuni in watchlist" },
];

const ADVANCED_ACTIONS = [
  {
    key: "anomalies",
    label: "Rileva anomalie (proroghe, revoche, ricorsi, stallo)",
    run: () => api.post("/admin/detect-anomalies"),
  },
  {
    key: "backfill7",
    label: "Backfill ultimi 7 giorni",
    run: () => api.post("/admin/run-backfill?days=7"),
  },
] as const;

export function ManualCollectionPanel() {
  const [running, setRunning] = useState(false);
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [outcome, setOutcome] = useState<"idle" | "done" | "error">("idle");
  const [advancedBusyKey, setAdvancedBusyKey] = useState<string | null>(null);
  const [advancedLog, setAdvancedLog] = useState<string | null>(null);

  const appendLog = (line: string) =>
    setLog((prev) => [...prev, `${new Date().toLocaleTimeString("it-IT")} — ${line}`]);

  const runSingleTaskStep = async (
    label: string,
    dispatch: () => Promise<{ task_id: string }>,
    timeoutMs = 5 * 60_000,
  ) => {
    setCurrentStep(`${label}…`);
    const { task_id } = await dispatch();
    const status = await pollTask(task_id, { intervalMs: 3000, timeoutMs });
    if (status.status === "SUCCESS") {
      appendLog(`${label}: completato — ${summarizeResult(status.result)}`);
    } else {
      appendLog(`${label}: errore — ${status.error ?? "sconosciuto"}`);
    }
  };

  const runCollectStep = async () => {
    const dispatched = await api.post<Record<string, string>>("/admin/run-daily-monitor");
    const jobs = COLLECT_JOBS.filter((job) => dispatched[job.key]);
    let doneCount = 0;
    setCurrentStep(`Raccolta dalle fonti in corso (0/${jobs.length} completate)… può richiedere diversi minuti`);

    await Promise.all(
      jobs.map(async (job) => {
        try {
          // Watchlist scan is the slowest leg (up to ~9 pages per comune x 73
          // comuni, one AI call each) so it gets the longest budget.
          const timeoutMs = job.key === "watchlist_task_id" ? 25 * 60_000 : 15 * 60_000;
          const status = await pollTask(dispatched[job.key], { intervalMs: 5000, timeoutMs });
          doneCount += 1;
          setCurrentStep(`Raccolta dalle fonti in corso (${doneCount}/${jobs.length} completate)…`);
          if (status.status === "SUCCESS") {
            appendLog(`${job.label}: completata — ${summarizeResult(status.result)}`);
          } else {
            appendLog(`${job.label}: errore — ${status.error ?? "sconosciuto"}`);
          }
        } catch (err) {
          doneCount += 1;
          setCurrentStep(`Raccolta dalle fonti in corso (${doneCount}/${jobs.length} completate)…`);
          appendLog(`${job.label}: ${err instanceof Error ? err.message : "errore imprevisto"}`);
        }
      }),
    );
  };

  const runFullCollection = async () => {
    setRunning(true);
    setOutcome("idle");
    setLog([]);

    try {
      await runCollectStep();
      await runSingleTaskStep("Pulizia e normalizzazione dei risultati", () =>
        api.post("/admin/normalize-records"),
      );
      await runSingleTaskStep("Calcolo priorità e rimozione doppioni", () =>
        api.post("/admin/score-and-dedupe"),
      );
      await runSingleTaskStep("Generazione report del giorno", () =>
        api.post(`/admin/rebuild-report/${todayIso()}`),
      );
      setCurrentStep(null);
      setOutcome("done");
      appendLog("Completato. Controlla la pagina Elenco gare.");
    } catch (err) {
      setCurrentStep(null);
      setOutcome("error");
      const msg = err instanceof ApiError || err instanceof Error ? err.message : "Errore imprevisto";
      appendLog(`Errore: ${msg}`);
    } finally {
      setRunning(false);
    }
  };

  const runAdvanced = async (action: (typeof ADVANCED_ACTIONS)[number]) => {
    setAdvancedBusyKey(action.key);
    setAdvancedLog(null);
    try {
      await action.run();
      setAdvancedLog(`${action.label}: avviato ✓`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Errore imprevisto";
      setAdvancedLog(`${action.label}: errore — ${msg}`);
    } finally {
      setAdvancedBusyKey(null);
    }
  };

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">Raccolta manuale</h2>
          <p className="mt-1 text-sm text-neutral-500">
            Normalmente il sistema raccoglie da solo ogni notte. Usa questo pulsante per
            forzare una raccolta adesso: aspetta il completamento reale di ogni fase (può
            richiedere diversi minuti, soprattutto per la scansione dei comuni) invece di
            fermarsi dopo un tempo fisso.
          </p>
        </div>
        <button
          type="button"
          onClick={runFullCollection}
          disabled={running}
          className="shrink-0 rounded bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "Raccolta in corso…" : "Avvia raccolta ora"}
        </button>
      </div>

      {(running || log.length > 0) && (
        <div className="mt-4 space-y-2">
          {running && currentStep && (
            <div className="flex items-center gap-2 text-sm text-sky-700 dark:text-sky-400">
              <span className="h-2 w-2 animate-pulse rounded-full bg-sky-500" />
              {currentStep}
            </div>
          )}
          {outcome === "done" && (
            <div className="rounded border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-100">
              Fatto. Vai su{" "}
              <Link href="/records" className="underline">
                Elenco gare
              </Link>{" "}
              per vedere i risultati (può risultare vuoto se in questi giorni non è stato
              pubblicato nulla di pertinente: non è un errore).
            </div>
          )}
          {outcome === "error" && (
            <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-100">
              Qualcosa è andato storto. Guarda il dettaglio qui sotto.
            </div>
          )}
          <ul className="space-y-1 text-xs text-neutral-500">
            {log.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      <details className="mt-5 border-t border-neutral-200 pt-4 dark:border-neutral-800">
        <summary className="cursor-pointer text-sm font-medium text-neutral-600 dark:text-neutral-400">
          Azioni avanzate
        </summary>
        <div className="mt-3 flex flex-wrap gap-2">
          {ADVANCED_ACTIONS.map((action) => (
            <button
              key={action.key}
              type="button"
              onClick={() => runAdvanced(action)}
              disabled={advancedBusyKey !== null}
              className="rounded border border-neutral-300 px-3 py-1.5 text-xs hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
            >
              {advancedBusyKey === action.key ? "Avvio…" : action.label}
            </button>
          ))}
        </div>
        {advancedLog && <p className="mt-2 text-xs text-neutral-500">{advancedLog}</p>}
      </details>
    </div>
  );
}
