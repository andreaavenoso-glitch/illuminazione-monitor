export default function HomePage() {
  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="mt-2 text-neutral-600 dark:text-neutral-400">
          Sistema di monitoraggio procurement illuminazione pubblica.
        </p>
      </section>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          "Nuove gare oggi",
          "Aggiornamenti",
          "Pre-gara",
          "Anomalie aperte",
        ].map((label) => (
          <div
            key={label}
            className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
          >
            <p className="text-xs uppercase text-neutral-500">{label}</p>
            <p className="mt-2 text-3xl font-bold">—</p>
          </div>
        ))}
      </section>

      <section className="rounded-lg border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="text-lg font-semibold">Prossimi passi</h2>
        <ul className="mt-3 list-disc pl-5 text-sm text-neutral-600 dark:text-neutral-400">
          <li>Sprint 1 — fondazione tecnica (attiva)</li>
          <li>Sprint 2 — modello dati e admin base</li>
          <li>Sprint 3 — collector ufficiali (TED, ANAC, GURI)</li>
        </ul>
      </section>
    </div>
  );
}
