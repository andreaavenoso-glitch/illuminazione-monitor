import { AlertsBoard } from "@/components/AlertsBoard";

export default function AlertsPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Alert &amp; anomalie</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Anomalie rilevate dal motore (proroghe multiple, revoche, ricorsi, procedure ponte, stallo).
        </p>
      </header>
      <AlertsBoard />
    </div>
  );
}
