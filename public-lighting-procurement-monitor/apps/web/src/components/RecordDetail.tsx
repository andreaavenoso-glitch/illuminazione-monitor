"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtDate, fmtDateLong, fmtEur, daysUntil } from "@/lib/format";
import type { ProcurementRecord } from "@/types";
import { PriorityBadge, StatoBadge } from "./Badge";

type FieldItem = { label: string; value: string | null };

function Grid({ items }: { items: FieldItem[] }) {
  return (
    <dl className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {items.map(({ label, value }) => (
        <div key={label}>
          <dt className="text-xs uppercase tracking-wide text-neutral-500">{label}</dt>
          <dd className="mt-0.5 text-sm text-neutral-900 dark:text-neutral-100">
            {value ?? <span className="text-neutral-400">—</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function RecordDetail({ id }: { id: string }) {
  const query = useQuery({
    queryKey: ["records", id],
    queryFn: () => api.get<ProcurementRecord>(`/records/${id}`),
  });

  if (query.isLoading) return <div className="text-sm text-neutral-500">Caricamento…</div>;
  if (query.error) {
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-100">
        Errore: {(query.error as Error).message}
      </div>
    );
  }

  const r = query.data!;
  const tags = (r.tag_tecnico ?? "").split(",").filter(Boolean);
  const scadDays = daysUntil(r.scadenza);

  return (
    <div className="space-y-6">
      <div>
        <Link href="/records" className="text-sm text-sky-600 hover:underline">
          ← Tutte le gare
        </Link>
      </div>

      <header className="rounded-lg border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold">{r.ente}</h1>
            <p className="mt-1 text-neutral-700 dark:text-neutral-300">{r.descrizione ?? "—"}</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <PriorityBadge value={r.priorita_commerciale ?? null} />
            <StatoBadge value={r.stato_procedurale} />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2 text-xs">
          {tags.map((t) => (
            <span
              key={t}
              className="rounded-full bg-sky-100 px-2 py-0.5 text-sky-800 dark:bg-sky-950 dark:text-sky-200"
            >
              {t}
            </span>
          ))}
          {r.is_weak_evidence && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-900 dark:bg-amber-950 dark:text-amber-100">
              evidenza debole
            </span>
          )}
          {r.master_record_id && (
            <span className="rounded-full bg-neutral-200 px-2 py-0.5 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-200">
              duplicato
            </span>
          )}
        </div>
      </header>

      <section className="rounded-lg border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="text-lg font-semibold">Dati gara</h2>
        <div className="mt-4">
          <Grid
            items={[
              { label: "Importo (IVA escl.)", value: fmtEur(r.importo) },
              { label: "CIG", value: r.cig },
              { label: "Data pubblicazione", value: fmtDateLong(r.data_pubblicazione) },
              {
                label: "Scadenza",
                value:
                  r.scadenza && scadDays !== null
                    ? `${fmtDate(r.scadenza)} (${scadDays >= 0 ? `tra ${scadDays}gg` : `${-scadDays}gg fa`})`
                    : fmtDate(r.scadenza),
              },
              { label: "Procedura", value: r.tipologia_gara_procedura },
              { label: "Criterio aggiudicazione", value: r.criterio },
              { label: "Macrosettore", value: r.macrosettore },
              { label: "Tipo novità", value: r.tipo_novita },
              { label: "Regione", value: r.regione },
              { label: "Provincia", value: r.provincia },
              { label: "Comune", value: r.comune },
              { label: "Validation level", value: r.validation_level },
              { label: "Reliability", value: r.reliability_index },
              {
                label: "Score commerciale",
                value: r.score_commerciale !== null ? String(r.score_commerciale) : null,
              },
            ]}
          />
        </div>
      </section>

      <section className="rounded-lg border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="text-lg font-semibold">Flag di business</h2>
        <div className="mt-4">
          <Grid
            items={[
              { label: "PPP / doppio oggetto", value: r.flag_ppp_doppio_oggetto },
              { label: "Concessione ambito", value: r.flag_concessione_ambito },
              { label: "In-house ambito", value: r.flag_in_house_ambito },
              { label: "O&M", value: r.flag_om },
              { label: "Pre-gara", value: r.flag_pre_gara },
            ]}
          />
        </div>
      </section>

      <section className="rounded-lg border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="text-lg font-semibold">Link &amp; tracking</h2>
        <div className="mt-3 space-y-2 text-sm">
          <p>
            <span className="text-neutral-500">Bando:</span>{" "}
            <a
              href={r.link_bando}
              target="_blank"
              rel="noreferrer"
              className="text-sky-600 hover:underline break-all"
            >
              {r.link_bando}
            </a>
          </p>
          <p className="text-xs text-neutral-500">
            Primo avvistamento: {fmtDateLong(r.first_seen_at)} · Ultimo aggiornamento: {fmtDateLong(r.last_seen_at)}
          </p>
          {r.dedup_key && (
            <p className="text-xs text-neutral-500">
              Dedup key: <code>{r.dedup_key}</code>
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
