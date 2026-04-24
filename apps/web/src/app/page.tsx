import { HomeDashboard } from "@/components/HomeDashboard";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          Monitoraggio procurement illuminazione pubblica — stato aggiornato.
        </p>
      </header>
      <HomeDashboard />
    </div>
  );
}
