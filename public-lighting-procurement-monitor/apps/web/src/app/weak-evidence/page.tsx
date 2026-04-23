import { WeakEvidenceTable } from "@/components/WeakEvidenceTable";

export default function WeakEvidencePage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Evidenze deboli</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Record che non rispettano la regola §9.1 (mancano importo/CIG/scadenza/procedura) — non
          confluiscono nel report ma restano disponibili per validazione manuale.
        </p>
      </header>
      <WeakEvidenceTable />
    </div>
  );
}
