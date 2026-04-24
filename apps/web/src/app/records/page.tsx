import { RecordsExplorer } from "@/components/RecordsExplorer";

export default function RecordsPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Gare</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Tutti i procurement records indicizzati — filtrabili per regione, stato, priorità e flag.
        </p>
      </header>
      <RecordsExplorer />
    </div>
  );
}
