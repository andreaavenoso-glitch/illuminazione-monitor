import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AuthShell } from "@/components/AuthShell";
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
          <AuthShell>{children}</AuthShell>
        </QueryProvider>
      </body>
    </html>
  );
}
