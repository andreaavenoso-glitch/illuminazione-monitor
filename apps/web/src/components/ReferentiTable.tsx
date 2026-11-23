"use client";

import { RUOLO_LABEL, type Referente, type ReferentiRiga } from "@/lib/regions";

const ETICHETTA: Record<string, string> = {
  certo: "bg-emerald-100 text-emerald-800",
  probabile: "bg-amber-100 text-amber-800",
  ipotetico: "bg-neutral-200 text-neutral-700",
};

function Persona({ p }: { p: Referente }) {
  return (
    <div className="mb-1.5 last:mb-0">
      <div className="font-medium">
        {p.nome}
        {p.stato === "da_confermare" && (
          <span className="ml-1 rounded bg-amber-100 px-1 text-[10px] font-normal text-amber-900" title={p.motivo ?? undefined}>
            da confermare
          </span>
        )}
      </div>
      {p.qualifica && <div className="text-[11px] text-neutral-500">{p.qualifica}</div>}
      <div className="text-[11px]">
        {p.email && <a className="text-sky-700 underline" href={`mailto:${p.email}`}>{p.email}</a>}
        {p.email && p.telefono && " · "}
        {p.telefono}
        {" "}
        <a className="text-neutral-400 underline" href={p.fonte_url} target="_blank" rel="noreferrer" title={p.citazione ?? "fonte"}>fonte</a>
      </div>
      {p.stato === "da_confermare" && p.motivo && <div className="text-[10px] text-amber-700">{p.motivo}</div>}
    </div>
  );
}

function Cella({ ruolo, people }: { ruolo: string; people: Referente[] }) {
  if (people.length === 0) return <span className="text-xs text-neutral-400">— non trovato</span>;
  return (
    <div title={RUOLO_LABEL[people[0].ruolo as keyof typeof RUOLO_LABEL] ?? ruolo}>
      {people.slice(0, 3).map((p) => <Persona key={`${p.ruolo}-${p.nome}`} p={p} />)}
    </div>
  );
}

/** What is needed to get in touch: sindaco, assessore ai LL.PP. and referente tecnico of every comune. */
export function ReferentiTable({
  rows,
  admin,
  busy,
  onFind,
}: {
  rows: ReferentiRiga[];
  admin: boolean;
  busy: boolean;
  onFind: (ente: string) => void;
}) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-500">
        <span>
          Riepilogo dei comuni di cui hai chiesto i referenti (dal pulsante "Referenti del comune" di un avviso):
          sindaco, assessore ai lavori pubblici e referente tecnico, ognuno con la fonte.
        </span>
      </div>
      {rows.length === 0 && <p className="text-sm text-neutral-500">Nessun comune ancora: apri un avviso e premi "Referenti del comune".</p>}
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border dark:border-neutral-800">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="bg-neutral-100 text-xs uppercase text-neutral-500 dark:bg-neutral-900">
              <tr>
                <th className="p-2">Comune</th>
                <th className="p-2">Sindaco</th>
                <th className="p-2">Assessore LL.PP.</th>
                <th className="p-2">Referente tecnico</th>
                <th className="p-2">PEC</th>
                <th className="p-2">Affidabilità</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.ente} className="border-t align-top dark:border-neutral-800">
                  <td className="p-2 font-medium">
                    {r.ente}
                    {r.mandato_scadenza && <div className="text-[11px] font-normal text-neutral-500">mandato fino al {r.mandato_scadenza.slice(0, 7)} (stimato)</div>}
                    {admin && (
                      <button type="button" disabled={busy} onClick={() => onFind(r.ente)} className="mt-1 block text-[11px] font-normal underline">
                        {r.cercato ? "aggiorna" : "cerca referenti"}
                      </button>
                    )}
                  </td>
                  <td className="p-2"><Cella ruolo="sindaco" people={r.sindaco} /></td>
                  <td className="p-2"><Cella ruolo="assessore" people={r.assessore} /></td>
                  <td className="p-2"><Cella ruolo="tecnico" people={r.tecnico} /></td>
                  <td className="p-2 text-xs">{r.pec ?? <span className="text-neutral-400">—</span>}</td>
                  <td className="p-2 text-xs">
                    <span className={`rounded-full px-2 py-0.5 ${ETICHETTA[r.etichetta]}`}>{r.etichetta} {r.affidabilita_pct}%</span>
                    <div className="mt-1">{r.azione}</div>
                    {r.passi_ok !== null && <div className="text-neutral-500">checklist {r.passi_ok}/12</div>}
                    <a className="text-neutral-500 underline" href={r.stampa_url} target="_blank" rel="noreferrer">controlla la stampa</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
