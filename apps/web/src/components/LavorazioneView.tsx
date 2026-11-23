"use client";

import type { ReactNode } from "react";
import { Countdown } from "@/components/ui";
import { CATEGORIA_LABEL, PREGARA_LABEL, type Categoria, type RegionRecord } from "@/lib/regions";

type Decisione = "selezionata" | "scartata" | "nessuna";

const FLUSSO: Record<Categoria, { titolo: string; cosa: string; tono: string }> = {
  pre_gara: {
    titolo: CATEGORIA_LABEL.pre_gara,
    cosa:
      "Un segnale, non ancora una gara (delibera, impegno di spesa, mandato al verificatore, società di consulenza, manutenzione degli impianti). " +
      "Produce un'e-mail con le informazioni principali; l'analisi dei documenti più in profondità è facoltativa.",
    tono: "border-sky-300",
  },
  manifestazione_interesse: {
    titolo: CATEGORIA_LABEL.manifestazione_interesse,
    cosa:
      "Si selezionano con cura: solo quelle con scadenza confermata nel documento. Producono l'e-mail e il documento di sintesi (scheda Gate 1), " +
      "dopo un'analisi approfondita della documentazione dell'avviso.",
    tono: "border-violet-300",
  },
  gara: {
    titolo: CATEGORIA_LABEL.gara,
    cosa:
      "Come le manifestazioni: solo gare con scadenza confermata. E-mail e documento di sintesi, con l'analisi approfondita della documentazione di gara.",
    tono: "border-emerald-300",
  },
};

const fmt = (d: string | null | undefined) =>
  d ? new Date(d).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : null;

function Passo({ ok, label, dettaglio }: { ok: boolean; label: string; dettaglio?: string | null }) {
  return (
    <span
      className={`chip ${ok ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-100" : "bg-neutral-100 text-neutral-500 dark:bg-neutral-800"}`}
      title={dettaglio ?? undefined}
    >
      {ok ? "✔" : "○"} {label}
    </span>
  );
}

export interface LavorazioneViewProps {
  records: RegionRecord[];
  admin: boolean;
  busy: string | null;
  onDecide: (id: string, stato: Decisione) => void;
  onPacchetto: (id: string, profondita?: "base" | "approfondita") => void;
  onEmail: (id: string) => void;
  onSlide: (id: string, ente: string) => void;
  renderDraft: (id: string) => ReactNode;
}

function Riga({
  r,
  azioni,
  extra,
}: {
  r: RegionRecord;
  azioni: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <li className="rounded-lg border p-3 text-sm dark:border-neutral-800">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <b>{r.ente}</b>
        <span className="text-xs text-neutral-500">
          {r.scadenza && <>scadenza {new Date(r.scadenza).toLocaleDateString("it-IT")} </>}
          <Countdown iso={r.scadenza} />
        </span>
      </div>
      <p className="mt-1 line-clamp-2 text-neutral-700 dark:text-neutral-300">{r.descrizione}</p>
      {(r.pregara_tipi ?? []).length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {(r.pregara_tipi ?? []).map((t) => (
            <span key={t} className="chip bg-sky-50 text-sky-800 dark:bg-sky-950 dark:text-sky-100">{PREGARA_LABEL[t] ?? t}</span>
          ))}
        </div>
      )}
      {extra}
      <div className="mt-2 flex flex-wrap gap-2">{azioni}</div>
    </li>
  );
}

const btn =
  "rounded-lg border px-3 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800";
const btnPrimary = "rounded-lg bg-brand-600 px-3 py-1 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50";

export function LavorazioneView(p: LavorazioneViewProps) {
  const cats: Categoria[] = ["pre_gara", "manifestazione_interesse", "gara"];
  return (
    <div className="space-y-6">
      <p className="text-xs text-neutral-500">
        Qui si decide cosa lavorare e si prepara il materiale. <b>Seleziona</b> un avviso, poi <b>Prepara pacchetto</b>: legge i documenti
        (in profondità per manifestazioni e gare) e cerca i referenti del comune. Quando è pronto, l&apos;e-mail e il documento di sintesi si
        generano dai dati raccolti. Nulla viene inviato dall&apos;app.
      </p>
      {cats.map((c) => {
        const tutti = p.records.filter((r) => r.categoria === c && !r.scaduto);
        const strict = c !== "pre_gara";
        const inLavoro = p.records.filter((r) => r.categoria === c && r.lavorazione?.stato === "selezionata");
        const scartati = p.records.filter((r) => r.categoria === c && r.lavorazione?.stato === "scartata");
        const nonDecisi = tutti.filter((r) => !r.lavorazione);
        const candidati = nonDecisi.filter((r) => !strict || r.confermato === true);
        const nonConfermati = nonDecisi.length - candidati.length;
        const f = FLUSSO[c];
        return (
          <section key={c} className={`space-y-3 rounded-2xl border-l-4 bg-white p-4 shadow-card dark:bg-neutral-900 ${f.tono}`}>
            <header>
              <h2 className="text-lg font-semibold">
                {f.titolo} <span className="text-sm font-normal text-neutral-500">· {inLavoro.length} in lavorazione</span>
              </h2>
              <p className="text-xs text-neutral-500">{f.cosa}</p>
            </header>

            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500">In lavorazione</h3>
              {inLavoro.length === 0 && <p className="text-sm text-neutral-500">Nessun avviso selezionato.</p>}
              <ul className="space-y-2">
                {inLavoro.map((r) => {
                  const lav = r.lavorazione!;
                  const profondita = r.analisi?.profondita;
                  const docOk = strict ? profondita === "approfondita" : !!r.analisi;
                  const lavora = p.busy === r.id;
                  return (
                    <div key={r.id}>
                      <Riga
                        r={r}
                        extra={
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            <Passo ok={docOk} label={strict ? "documenti approfonditi" : profondita === "approfondita" ? "documenti approfonditi" : "documenti letti"}
                              dettaglio={r.analisi ? `${r.analisi.documenti.filter((d) => d.letto).length}/${r.analisi.documenti.length} documenti letti` : "non ancora analizzata"} />
                            <Passo ok={(r.referenti ?? []).length > 0} label="referenti" dettaglio={`${(r.referenti ?? []).length} nomi`} />
                            <Passo ok={!!lav.email_il} label="e-mail" dettaglio={fmt(lav.email_il) ? `preparata il ${fmt(lav.email_il)}` : "da preparare"} />
                            {strict && <Passo ok={!!lav.sintesi_il} label="sintesi" dettaglio={fmt(lav.sintesi_il) ? `generata il ${fmt(lav.sintesi_il)}` : "da generare"} />}
                          </div>
                        }
                        azioni={
                          p.admin ? (
                            <>
                              <button type="button" disabled={lavora} className={btnPrimary} onClick={() => p.onPacchetto(r.id)}
                                title={strict ? "Legge i documenti in profondità e cerca i referenti" : "Legge i documenti (primo livello) e cerca i referenti"}>
                                {lavora ? "In corso…" : "Prepara pacchetto"}
                              </button>
                              {!strict && (
                                <button type="button" disabled={lavora} className={btn} onClick={() => p.onPacchetto(r.id, "approfondita")}
                                  title="Come sopra ma leggendo anche i documenti citati dai documenti (delibere, relazioni)">
                                  Approfondisci documentazione
                                </button>
                              )}
                              <button type="button" className={btn} onClick={() => p.onEmail(r.id)}>E-mail</button>
                              {strict && (
                                <button type="button" className={btn} onClick={() => p.onSlide(r.id, r.ente)}
                                  title="Scheda Gate 1 (PowerPoint) con i dati della documentazione">
                                  Documento di sintesi (PPT)
                                </button>
                              )}
                              <button type="button" className="px-2 py-1 text-xs text-neutral-500 underline" onClick={() => p.onDecide(r.id, "scartata")}>
                                Scarta
                              </button>
                            </>
                          ) : null
                        }
                      />
                      {p.renderDraft(r.id)}
                    </div>
                  );
                })}
              </ul>
            </div>

            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500">
                {strict ? "Candidati con scadenza confermata" : "Candidati"} ({candidati.length})
              </h3>
              {strict && nonConfermati > 0 && (
                <p className="mb-1 text-xs text-amber-700">
                  {nonConfermati} {nonConfermati === 1 ? "avviso non è candidabile" : "avvisi non sono candidabili"}: la scadenza non è ancora stata letta nel documento
                  (tab «Da verificare»).
                </p>
              )}
              {candidati.length === 0 && <p className="text-sm text-neutral-500">Nessun candidato in attesa di decisione.</p>}
              <ul className="space-y-2">
                {candidati.slice(0, 40).map((r) => (
                  <Riga
                    key={r.id}
                    r={r}
                    azioni={
                      p.admin ? (
                        <>
                          <button type="button" className={btnPrimary} onClick={() => p.onDecide(r.id, "selezionata")}>Seleziona</button>
                          <button type="button" className={btn} onClick={() => p.onDecide(r.id, "scartata")}>Scarta</button>
                          <a className="px-2 py-1 text-xs underline" href={r.link} target="_blank" rel="noreferrer">apri avviso</a>
                        </>
                      ) : null
                    }
                  />
                ))}
              </ul>
              {candidati.length > 40 && <p className="mt-1 text-xs text-neutral-500">…e altri {candidati.length - 40}: decidi questi per vedere i successivi.</p>}
            </div>

            {scartati.length > 0 && (
              <details className="text-sm text-neutral-600 dark:text-neutral-400">
                <summary className="cursor-pointer">Scartati ({scartati.length})</summary>
                <ul className="mt-1 space-y-1">
                  {scartati.map((r) => (
                    <li key={r.id} className="flex flex-wrap items-center justify-between gap-2">
                      <span>{r.ente} — {(r.descrizione ?? "").slice(0, 90)}</span>
                      {p.admin && (
                        <button type="button" className="text-xs underline" onClick={() => p.onDecide(r.id, "nessuna")}>ripristina</button>
                      )}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        );
      })}
    </div>
  );
}
