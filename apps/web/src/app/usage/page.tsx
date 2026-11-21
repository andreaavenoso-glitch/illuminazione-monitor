"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { PURPOSE_LABEL, usd, type UsageSummary, type UsageWindow } from "@/lib/usage";

function Card({ title, w }: { title: string; w: UsageWindow }) {
  return (
    <div className="rounded border p-3 dark:border-neutral-800">
      <div className="text-xs text-neutral-500">{title}</div>
      <div className="text-2xl font-semibold">{usd(w.cost_usd)}</div>
      <div className="text-xs text-neutral-500">
        {w.calls} chiamate · {Math.round(w.input_tokens / 1000)}k token in · {Math.round(w.output_tokens / 1000)}k token out
      </div>
    </div>
  );
}

export default function UsagePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["usage"],
    queryFn: () => api.get<UsageSummary>("/usage"),
    refetchInterval: 15000,
  });
  if (isLoading || !data) return <p className="text-sm text-neutral-500">Caricamento…</p>;

  const peak = Math.max(0.0001, ...data.days.map((d) => d.cost_usd));
  const b = data.budget;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Spesa sull&apos;API di Claude</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Stima calcolata dai token che l&apos;API riporta per ogni chiamata, moltiplicati per i prezzi sotto. Conta solo le
          chiamate di questa app, da quando esiste il contatore: la spesa reale (e il limite) sono quelli della console Anthropic.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-3">
        <Card title="Oggi" w={data.today} />
        <Card title="Questo mese" w={data.month} />
        <Card title="Totale" w={data.total} />
      </section>

      {b ? (
        <section className="rounded border p-3 dark:border-neutral-800">
          <div className="flex justify-between text-sm">
            <span>Budget del mese: {usd(b.limit_usd)}</span>
            <span className={b.remaining_usd < 0 ? "text-red-700" : ""}>residuo {usd(b.remaining_usd)}</span>
          </div>
          <div className="mt-2 h-3 overflow-hidden rounded bg-neutral-200 dark:bg-neutral-800">
            <div
              className={`h-full ${b.spent_usd > b.limit_usd * 0.9 ? "bg-red-500" : "bg-emerald-500"}`}
              style={{ width: `${Math.min(100, (b.spent_usd / Math.max(0.01, b.limit_usd)) * 100)}%` }}
            />
          </div>
        </section>
      ) : (
        <p className="text-xs text-neutral-500">
          Per vedere quanto del tuo limite hai usato imposta <code>ANTHROPIC_BUDGET_USD</code> nel file <code>.env</code>.
        </p>
      )}

      <section>
        <h2 className="mb-2 font-semibold">Ultimi 14 giorni</h2>
        <ul className="space-y-0.5">
          {data.days.map((d) => (
            <li key={d.day} className="flex items-center gap-2 text-xs">
              <span className="w-24 shrink-0 text-neutral-500">{d.day}</span>
              <span className="h-3.5 flex-1 rounded bg-neutral-100 dark:bg-neutral-900">
                <span className="block h-full rounded bg-sky-500" style={{ width: `${(d.cost_usd / peak) * 100}%` }} />
              </span>
              <span className="w-20 shrink-0 text-right tabular-nums">{usd(d.cost_usd)}</span>
              <span className="w-20 shrink-0 text-right text-neutral-500">{d.calls} chiamate</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="grid gap-6 sm:grid-cols-2">
        <div>
          <h2 className="mb-2 font-semibold">Questo mese, per uso</h2>
          <table className="w-full text-left text-sm">
            <tbody>
              {data.by_purpose.length === 0 && <tr><td className="text-neutral-500">Nessuna chiamata registrata.</td></tr>}
              {data.by_purpose.map((r) => (
                <tr key={r.name} className="border-t dark:border-neutral-800">
                  <td className="py-1">{PURPOSE_LABEL[r.name] ?? r.name}</td>
                  <td className="text-right tabular-nums">{usd(r.cost_usd)}</td>
                  <td className="w-24 text-right text-xs text-neutral-500">{r.calls} chiamate</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h2 className="mb-2 font-semibold">Questo mese, per modello</h2>
          <table className="w-full text-left text-sm">
            <tbody>
              {data.by_model.map((r) => (
                <tr key={r.name} className="border-t dark:border-neutral-800">
                  <td className="py-1">{r.name}</td>
                  <td className="text-right tabular-nums">{usd(r.cost_usd)}</td>
                  <td className="w-24 text-right text-xs text-neutral-500">{r.calls} chiamate</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded border p-3 text-xs text-neutral-600 dark:border-neutral-800 dark:text-neutral-400">
        <b>Prezzi usati</b> (dollari per milione di token) per il modello <code>{data.pricing.model}</code>: input{" "}
        ${data.pricing.input_per_mtok}, output ${data.pricing.output_per_mtok}; i token di cache in lettura costano il 10% e
        quelli in scrittura il 125% dell&apos;input.
        {!data.pricing.model_in_table && (
          <span className="text-amber-700"> Il modello non è nella tabella dei prezzi: è calcolato come Haiku, potrebbe non essere esatto.</span>
        )}{" "}
        Per correggere i prezzi: <code>ANTHROPIC_PRICE_INPUT_PER_MTOK</code> e <code>ANTHROPIC_PRICE_OUTPUT_PER_MTOK</code> nel{" "}
        <code>.env</code>.
      </section>
    </div>
  );
}
