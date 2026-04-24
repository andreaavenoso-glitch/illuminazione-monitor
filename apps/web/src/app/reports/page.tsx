import { DailyReportViewer } from "@/components/DailyReportViewer";

export default function ReportsPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Report giornaliero</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Ultimo report generato — sezioni: nuove gare, aggiornamenti, pre-gara,
          evidenze deboli, fonti interrogate.
        </p>
      </header>
      <DailyReportViewer />
    </div>
  );
}
