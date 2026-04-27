import type { Metadata } from "next";
import type { ReactNode } from "react";
import { QueryProvider } from "@/lib/query-provider";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "Public Lighting Procurement Monitor",
  description: "Monitoring service for Italian public lighting procurement",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="it">
      <body className="min-h-screen bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
        <QueryProvider>
          <header className="border-b border-neutral-200 bg-white px-6 py-4 dark:border-neutral-800 dark:bg-neutral-900">
            <nav className="mx-auto flex max-w-7xl items-center justify-between">
              <a href="/" className="text-lg font-semibold">
                Lighting Procurement Monitor
              </a>
              <ul className="flex gap-4 text-sm text-neutral-600 dark:text-neutral-400">
                <li><a href="/records" className="hover:underline">Records</a></li>
                <li><a href="/reports" className="hover:underline">Reports</a></li>
                <li><a href="/alerts" className="hover:underline">Alerts</a></li>
                <li><a href="/weak-evidence" className="hover:underline">Weak evidence</a></li>
                <li><a href="/admin/watchlist" className="hover:underline">Watchlist</a></li>
              </ul>
            </nav>
          </header>
          <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
        </QueryProvider>
      </body>
    </html>
  );
}
