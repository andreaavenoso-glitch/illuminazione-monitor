"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";

type StepStatus = "pending" | "running" | "done" | "error";

type Step = {
  key: string;
  label: string;
  waitLabel: string;
  waitMs: number;
  run: () => Promise<unknown>;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

const STEPS: Step[] = [
  {
    key: "collect",
    label: "Raccolta da fonti ufficiali e comuni",
    waitLabel: "Attendo che il worker scarichi i dati…",
    waitMs: 60_000,
    run: () => api.post("/admin/run-daily-monitor"),
  },
  {
    key: "normalize",
    label: "Pulizia e normalizzazione dei risultati",
    waitLabel: "Normalizzo i risultati…",
    waitMs: 10_000,
    run: () => api.post("/admin/normalize-records"),
  },
  {
    key: "score",
    label: "Calcolo priorità e rimozione doppioni",
    waitLabel: "Calcolo punteggi e rimuovo doppioni…",
    waitMs: 5_000,
    run: () => api.post("/admin/score-and-dedupe"),
  },
  {
    key: "report",
    label: "Generazione report del giorno",
    waitLabel: "",
    waitMs: 0,
    run: () => api.post(`/admin/rebuild-report/${todayIso()}`),
  },
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

  const runFullCollection = async () => {
    setRunning(true);
    setOutcome("idle");
    setLog([]);

    try {
      for (const step of STEPS) {
        setCurrentStep(step.label);
        await step.run();
        appendLog(`${step.label}: avviato`);
        if (step.waitMs > 0) {
          setCurrentStep(step.waitLabel);
          await sleep(step.waitMs);
        }
      }
      setCurrentStep(null);
      setOutcome("done");
      appendLog("Completato. Controlla la pagina Elenco gare.");
    } catch (err) {
      setCurrentStep(null);
      setOutcome("error");
      const msg = err instanceof ApiError ? err.message : "Errore imprevisto";
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
            forzare una raccolta adesso e vedere i risultati senza aspettare.
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
