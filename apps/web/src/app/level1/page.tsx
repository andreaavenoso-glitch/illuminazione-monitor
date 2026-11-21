"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Level1Overview } from "@/lib/regions";

function fmt(d: string | null): string {
  return d ? new Date(d).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—";
}

export default function Level1Page() {
  const { data, isLoading } = useQuery({
    queryKey: ["level1"],
    queryFn: () => api.get<Level1Overview>("/level1"),
    refetchInterval: 30000,
  });
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Portali nazionali (Livello 1)</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Solo analisi e verifica delle fonti nazionali. Ciò che trovano viene assegnato a una regione e compare nel suo
          riquadro. Consip è gestita a parte.
        </p>
      </header>
      {isLoading && <p className="text-sm text-neutral-500">Caricamento…</p>}
      {data && (
        <>
          <p className="text-sm">
            Record assegnati a una regione (ultimi 60 giorni): <b>{data.record_assegnati_a_regione}</b> · senza regione
            (da assegnare): <b className={data.record_senza_regione > 0 ? "text-amber-700" : ""}>{data.record_senza_regione}</b>
          </p>
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-neutral-500">
              <tr><th className="py-1">Fonte</th><th>Ultimo run</th><th>Trovati / validi</th><th>Righe grezze 7 gg</th><th>Affidabilità</th></tr>
            </thead>
            <tbody>
              {data.fonti.map((s) => (
                <tr key={s.id} className="border-t align-top dark:border-neutral-800">
                  <td className="py-1.5"><a href={s.url} target="_blank" rel="noreferrer" className="underline">{s.nome}</a></td>
                  <td>
                    {s.ultimo_run == null ? "mai eseguito" : (
                      <>
                        <span className={s.ultimo_run.status === "failed" ? "text-red-700" : s.ultimo_run.status === "partial" ? "text-amber-700" : "text-emerald-700"}>
                          {s.ultimo_run.status}
                        </span>{" "}
                        <span className="text-xs text-neutral-500">{fmt(s.ultimo_run.at)}</span>
                        {s.ultimo_run.errore && <div className="max-w-md break-words text-xs text-red-700">{s.ultimo_run.errore.slice(0, 160)}</div>}
                      </>
                    )}
                  </td>
                  <td>{s.ultimo_run ? `${s.ultimo_run.found} / ${s.ultimo_run.valid}` : "—"}</td>
                  <td>{s.raw_7gg}</td>
                  <td>{Math.round(s.affidabilita * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
