import { WatchlistTable } from "@/components/WatchlistTable";

export default function WatchlistAdminPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Watchlist</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Enti e fonti monitorati per l&apos;illuminazione pubblica.
        </p>
      </header>
      <WatchlistTable />
    </div>
  );
}
