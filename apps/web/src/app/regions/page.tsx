"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { getUser, hasRole } from "@/lib/auth";
import { CATEGORIA_LABEL, type RegionSummary } from "@/lib/regions";

function RegionBox({ r, admin }: { r: RegionSummary; admin: boolean }) {
  const qc = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => api.patch(`/regions/${encodeURIComponent(r.region)}`, { enabled: !r.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["regions"] }),
  });
  const cats = ["pre_gara", "manifestazione_interesse", "gara"] as const;
  return (
    <div
      className={`rounded-lg border p-4 ${
        r.enabled
          ? "border-neutral-300 bg-white dark:border-neutral-700 dark:bg-neutral-900"
          : "border-dashed border-neutral-300 bg-neutral-50 opacity-70 dark:border-neutral-800 dark:bg-neutral-950"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <Link href={`/regions/${encodeURIComponent(r.region)}`} className="text-lg font-semibold hover:underline">
          {r.region}
        </Link>
        {admin ? (
          <button
            type="button"
            onClick={() => toggle.mutate()}
            disabled={toggle.isPending}
            className={`rounded-full px-2 py-0.5 text-xs ${
              r.enabled ? "bg-emerald-100 text-emerald-800" : "bg-neutral-200 text-neutral-600"
            }`}
          >
            {r.enabled ? "attiva" : "spenta"}
          </button>
        ) : (
          <span className="text-xs text-neutral-500">{r.enabled ? "attiva" : "spenta"}</span>
        )}
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
        {cats.map((c) => (
          <div key={c}>
            <dt className="text-[11px] leading-tight text-neutral-500">{CATEGORIA_LABEL[c]}</dt>
            <dd className="text-xl font-semibold">{r[c]}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-neutral-600 dark:text-neutral-400">
        {r.comuni} comuni · {r.ok} raggiungibili · {r.failing} con errori · {r.unchecked} non verificati
        <br />
        {r.regional_sites} siti regionali
        {r.da_notificare > 0 && <> · {r.da_notificare} in attesa di email</>}
      </p>
    </div>
  );
}

export default function RegionsPage() {
  const user = getUser();
  const admin = hasRole(user, "admin");
  const { data, isLoading, error } = useQuery({
    queryKey: ["regions"],
    queryFn: () => api.get<RegionSummary[]>("/regions"),
    refetchInterval: 30000,
  });
  const enabled = (data ?? []).filter((r) => r.enabled);
  const off = (data ?? []).filter((r) => !r.enabled);
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Regioni</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Un riquadro per regione: pre-gare, manifestazioni di interesse e gare, con lo stato dei siti.
          Le regioni spente non vengono raccolte né notificate.
        </p>
      </header>
      {isLoading && <p className="text-sm text-neutral-500">Caricamento…</p>}
      {error && <p className="text-sm text-red-600">Impossibile caricare le regioni.</p>}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {enabled.map((r) => <RegionBox key={r.region} r={r} admin={admin} />)}
      </section>
      {off.length > 0 && (
        <>
          <h2 className="text-sm font-medium text-neutral-500">Regioni spente</h2>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {off.map((r) => <RegionBox key={r.region} r={r} admin={admin} />)}
          </section>
        </>
      )}
    </div>
  );
}
