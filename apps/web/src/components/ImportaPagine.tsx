"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";

/** Portals that refuse the server's address (dgegovpa.it, halleyweb.com): the pages are read by the user's own browser. */
export function ImportaPagine({ region }: { region: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [comune, setComune] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const script = useQuery({
    queryKey: ["import-script", region],
    queryFn: () => api.get<{ script: string }>(`/regions/${encodeURIComponent(region)}/import-pagine/script`),
    enabled: open,
  });

  const copy = async () => {
    if (!script.data) return;
    await navigator.clipboard.writeText(script.data.script);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const send = async () => {
    if (!file || !comune.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const token = getToken();
      const form = new FormData();
      form.append("comune", comune.trim());
      form.append("file", file);
      const res = await fetch(`${base}/regions/${encodeURIComponent(region)}/import-pagine`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      const body = (await res.json().catch(() => ({}))) as { detail?: string; pagine?: number };
      if (!res.ok) {
        setMsg({ ok: false, text: body.detail ?? `Errore ${res.status}` });
      } else {
        setMsg({ ok: true, text: `${body.pagine} pagine inviate all'analisi: il risultato compare qui sopra (Raccolta) tra pochi secondi.` });
        setFile(null);
        qc.invalidateQueries({ queryKey: ["scan", region] });
      }
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-2xl border border-neutral-200 bg-white p-4 text-sm">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between text-left font-medium">
        <span>Portale che blocca il server? Leggilo con il tuo browser</span>
        <span className="text-neutral-400">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="mt-3 space-y-3 text-neutral-700">
          <p>
            Alcuni portali (dgegovpa.it, halleyweb.com) rifiutano le connessioni del server. Il tuo browser invece li apre:
            lo script legge le pagine con la tua connessione e l'app le analizza come una raccolta normale.
          </p>
          <ol className="list-decimal space-y-1 pl-5">
            <li>
              <button onClick={copy} disabled={!script.data} className="rounded-lg border border-neutral-300 px-2 py-0.5 hover:bg-neutral-50 disabled:opacity-50">
                {copied ? "Copiato ✓" : "Copia lo script"}
              </button>
            </li>
            <li>Apri in Chrome la pagina del portale con l'elenco (es. Albo Pretorio o Atti del comune).</li>
            <li>
              Premi <b>F12</b>, scheda <b>Console</b>. Se Chrome lo chiede, scrivi <code>allow pasting</code> e Invio. Incolla lo
              script e premi Invio: si scarica <code>monitor_pagine.json</code>.
            </li>
            <li>Ripeti per le altre pagine utili (Atti amministrativi, Amministrazione trasparente: ogni volta un file).</li>
            <li>Carica qui il file, con il nome del comune:</li>
          </ol>
          <div className="flex flex-wrap items-center gap-2">
            <input value={comune} onChange={(e) => setComune(e.target.value)} placeholder="Comune (es. Arluno)" className="rounded-lg border border-neutral-300 px-2 py-1" />
            <input type="file" accept=".json,application/json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <button onClick={send} disabled={busy || !file || !comune.trim()} className="rounded-lg bg-sky-600 px-3 py-1 text-white disabled:opacity-50">
              {busy ? "Invio…" : "Analizza"}
            </button>
          </div>
          {msg && <p className={msg.ok ? "text-emerald-700" : "text-red-700"}>{msg.text}</p>}
        </div>
      )}
    </section>
  );
}
