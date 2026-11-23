"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ItalyTileMap } from "@/components/ItalyTileMap";
import { Donut, Icon, KpiTile, StackedBar, TONE } from "@/components/ui";
import { api } from "@/lib/api";
import { getUser, hasRole } from "@/lib/auth";
import { type RegionSummary } from "@/lib/regions";

const tot = (r: RegionSummary) => r.pre_gara + r.manifestazione_interesse + r.gara;

function RegionCard({ r, admin }: { r: RegionSummary; admin: boolean }) {
  const qc = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => api.patch(`/regions/${encodeURIComponent(r.region)}`, { enabled: !r.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["regions"] }),
  });
  const n = tot(r);
  return (
    <div className={`card group p-4 transition hover:-translate-y-0.5 hover:shadow-lift ${r.enabled ? "" : "opacity-75"}`}>
      <div className="flex items-start justify-between gap-2">
        <Link href={`/regions/${encodeURIComponent(r.region)}`} className="min-w-0">
          <span className="block truncate text-lg font-semibold tracking-tight group-hover:text-brand-600">{r.region}</span>
          <span className="text-xs text-neutral-500">{r.comuni} comuni · {r.regional_sites} siti regionali</span>
        </Link>
        {admin ? (
          <button type="button" onClick={() => toggle.mutate()} disabled={toggle.isPending}
            className={`chip shrink-0 ${r.enabled ? "bg-emerald-100 text-emerald-800" : "bg-neutral-200 text-neutral-600"}`}
            title={r.enabled ? "Clic per spegnere la regione" : "Clic per attivarla"}>
            <span className={`h-1.5 w-1.5 rounded-full ${r.enabled ? "bg-emerald-500" : "bg-neutral-400"}`} />
            {r.enabled ? "attiva" : "spenta"}
          </button>
        ) : (
          <span className="chip bg-neutral-100 text-neutral-600">{r.enabled ? "attiva" : "spenta"}</span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        {([["Pre-gare", r.pre_gara, "sky"], ["Manifestazioni", r.manifestazione_interesse, "violet"], ["Gare", r.gara, "emerald"]] as const).map(
          ([label, v, tone]) => (
            <div key={label} className={`rounded-xl px-1 py-2 ${TONE[tone].bg}`}>
              <div className={`text-xl font-semibold leading-none ${TONE[tone].fg}`}>{v}</div>
              <div className="mt-1 text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
            </div>
          ),
        )}
      </div>
      <div className="mt-3">
        <StackedBar
          parts={[
            { label: "Pre-gare", value: r.pre_gara, tone: "sky" },
            { label: "Manifestazioni", value: r.manifestazione_interesse, tone: "violet" },
            { label: "Gare", value: r.gara, tone: "emerald" },
          ]}
          empty="Nessuna opportunità"
        />
        <div className="mt-1 flex justify-between text-[11px] text-neutral-500">
          <span>{n} opportunità</span>
          <span>{r.confermate} confermate{r.da_verificare > 0 ? ` · ${r.da_verificare} da verificare` : ""}</span>
          {r.da_notificare > 0 && <span className="text-amber-600">{r.da_notificare} in attesa di email</span>}
        </div>
      </div>

      <div className="mt-3 border-t pt-3 dark:border-neutral-800">
        <StackedBar
          height="h-1.5"
          parts={[
            { label: "Raggiungibili", value: r.ok, tone: "emerald" },
            { label: "Con errori", value: r.failing, tone: "red" },
            { label: "Non verificati", value: r.unchecked, tone: "neutral" },
          ]}
        />
        <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-neutral-500">
          <span className="text-emerald-700">{r.ok} ok</span>
          {r.failing > 0 && <span className="text-red-600">{r.failing} con errori</span>}
          <span>{r.unchecked} da verificare</span>
        </div>
      </div>
    </div>
  );
}

export default function RegionsPage() {
  const admin = hasRole(getUser(), "admin");
  const { data, isLoading, error } = useQuery({
    queryKey: ["regions"],
    queryFn: () => api.get<RegionSummary[]>("/regions"),
    refetchInterval: 30000,
  });
  const all = data ?? [];
  const enabled = all.filter((r) => r.enabled);
  const off = all.filter((r) => !r.enabled);
  const sum = (f: (r: RegionSummary) => number) => all.reduce((a, r) => a + f(r), 0);
  const pre = sum((r) => r.pre_gara);
  const man = sum((r) => r.manifestazione_interesse);
  const gara = sum((r) => r.gara);
  const total = pre + man + gara;
  const top = [...all].filter((r) => tot(r) > 0).sort((a, b) => tot(b) - tot(a)).slice(0, 5);
  const maxTop = Math.max(1, ...top.map(tot));

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-600 via-brand-500 to-sky-500 p-6 text-white shadow-lift sm:p-8">
        <div className="absolute -right-10 -top-10 h-48 w-48 rounded-full bg-white/10" />
        <div className="absolute -bottom-16 right-24 h-40 w-40 rounded-full bg-white/10" />
        <h1 className="relative text-3xl font-semibold tracking-tight">Opportunità in Italia</h1>
        <p className="relative mt-1 max-w-2xl text-sm text-white/85">
          Pre-gare, manifestazioni di interesse e gare di illuminazione pubblica e servizi collegati, raccolte dai comuni e
          verificate sui documenti. Scegli una regione per vedere gli avvisi, i referenti e preparare il contatto.
        </p>
        <div className="relative mt-5 flex flex-wrap gap-x-8 gap-y-2 text-sm">
          <span><b className="text-xl">{sum((r) => r.comuni).toLocaleString("it-IT")}</b> comuni monitorati</span>
          <span><b className="text-xl">{enabled.length}</b> regioni attive</span>
          <span><b className="text-xl">{sum((r) => r.regional_sites)}</b> siti regionali</span>
          {sum((r) => r.failing) > 0 && <span className="text-amber-200"><b className="text-xl">{sum((r) => r.failing)}</b> siti con errori</span>}
        </div>
      </section>

      {isLoading && <p className="text-sm text-neutral-500">Caricamento…</p>}
      {error && <p className="text-sm text-red-600">Impossibile caricare le regioni.</p>}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile label="Opportunità trovate" value={total} icon="bulb" tone="brand" hint={`${sum((r) => r.confermate)} confermate · ${sum((r) => r.da_verificare)} da verificare`} />
        <KpiTile label="Pre-gare" value={pre} icon="bolt" tone="sky" hint="segnali prima dell'avviso" />
        <KpiTile label="Manifestazioni di interesse" value={man} icon="hand" tone="violet" hint="con scadenza confermata" />
        <KpiTile label="Gare" value={gara} icon="flag" tone="emerald" hint="con scadenza confermata" />
      </section>

      <section className="grid items-start gap-4 lg:grid-cols-[auto_1fr]">
        <div className="card p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold"><Icon name="globe" className="h-4 w-4 text-brand-500" />Mappa delle opportunità</h2>
          <ItalyTileMap regions={all} />
          <div className="mt-3 flex items-center justify-center gap-1 text-[10px] text-neutral-500">
            poche
            {["bg-brand-200", "bg-brand-300", "bg-brand-500", "bg-brand-600"].map((c) => <span key={c} className={`h-2.5 w-5 rounded ${c}`} />)}
            molte · contorno = regione attiva
          </div>
        </div>
        <div className="grid items-start gap-4 md:grid-cols-2">
          <div className="card flex flex-col items-center p-5">
            <h2 className="mb-3 self-start text-sm font-semibold">Per categoria</h2>
            <Donut
              size={150}
              parts={[
                { label: "Pre-gare", value: pre, tone: "sky" },
                { label: "Manifestazioni", value: man, tone: "violet" },
                { label: "Gare", value: gara, tone: "emerald" },
              ]}
              center={<div><div className="text-3xl font-semibold leading-none">{total}</div><div className="text-[11px] text-neutral-500">totale</div></div>}
            />
            <ul className="mt-3 w-full space-y-1 text-xs">
              {([["Pre-gare", pre, "sky"], ["Manifestazioni", man, "violet"], ["Gare", gara, "emerald"]] as const).map(([l, v, t]) => (
                <li key={l} className="flex items-center justify-between">
                  <span className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-full ${TONE[t].solid}`} />{l}</span>
                  <b>{v}</b>
                </li>
              ))}
            </ul>
          </div>
          <div className="card p-5">
            <h2 className="mb-3 text-sm font-semibold">Regioni con più opportunità</h2>
            {top.length === 0 && <p className="text-sm text-neutral-500">Nessuna opportunità ancora: avvia una raccolta da una regione.</p>}
            <ul className="space-y-3">
              {top.map((r) => (
                <li key={r.region}>
                  <Link href={`/regions/${encodeURIComponent(r.region)}`} className="group block">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium group-hover:text-brand-600">{r.region}</span>
                      <span className="text-neutral-500">{tot(r)}</span>
                    </div>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
                      <div className="h-full rounded-full bg-gradient-to-r from-brand-500 to-sky-400" style={{ width: `${(100 * tot(r)) / maxTop}%` }} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-neutral-600 dark:text-neutral-300">Regioni attive</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {enabled.map((r) => <RegionCard key={r.region} r={r} admin={admin} />)}
        </div>
        {enabled.length === 0 && <p className="text-sm text-neutral-500">Nessuna regione attiva: accendine una qui sotto.</p>}
      </section>

      {off.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-sm font-semibold text-neutral-500">Regioni spente ({off.length}) ▾</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {off.map((r) => <RegionCard key={r.region} r={r} admin={admin} />)}
          </div>
        </details>
      )}
    </div>
  );
}
