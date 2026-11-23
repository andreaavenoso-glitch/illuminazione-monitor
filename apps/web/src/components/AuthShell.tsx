"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { clearSession, getUser, hasRole, type AuthUser } from "@/lib/auth";
import { ActiveScanBadge } from "./ActiveScanBadge";
import { AppFooter } from "./AppFooter";
import { ClaudeDownPill } from "./ClaudeStatusBanner";
import { Icon } from "./ui";
import { UsageBadge } from "./UsageBadge";

const PUBLIC_PATHS = ["/login"];

function NavLink({ href, active, children }: { href: Route; active: boolean; children: ReactNode }) {
  return (
    <li>
      <Link href={href}
        className={`rounded-lg px-3 py-1.5 transition ${
          active
            ? "bg-brand-50 font-medium text-brand-700 dark:bg-brand-900/40 dark:text-brand-200"
            : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
        }`}>
        {children}
      </Link>
    </li>
  );
}

export function AuthShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setUser(getUser());
    setHydrated(true);
    const handler = () => setUser(getUser());
    window.addEventListener("lpm-auth-changed", handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener("lpm-auth-changed", handler);
      window.removeEventListener("storage", handler);
    };
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    const isPublic = PUBLIC_PATHS.some((p) => pathname?.startsWith(p));
    if (!user && !isPublic) {
      const redirect = pathname || "/";
      router.replace(`/login?redirect=${encodeURIComponent(redirect)}`);
    }
  }, [hydrated, user, pathname, router]);

  const onLogout = () => {
    clearSession();
    router.replace("/login");
  };

  const isLogin = pathname?.startsWith("/login");
  if (isLogin) {
    return (
      <>
        {children}
        <AppFooter />
      </>
    );
  }

  if (!hydrated || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-neutral-500">
        Caricamento…
      </div>
    );
  }

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-neutral-200/70 bg-white/80 backdrop-blur dark:border-neutral-800 dark:bg-neutral-950/80">
        <div className="h-0.5 bg-gradient-to-r from-brand-500 via-sky-400 to-emerald-400" />
        <nav className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-3">
          <Link href="/regions" className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-sky-500 text-white shadow-lift">
              <Icon name="bulb" className="h-5 w-5" />
            </span>
            <span className="leading-tight">
              <span className="block text-base font-semibold tracking-tight">Monitor Illuminazione</span>
              <span className="block text-[11px] text-neutral-500">Pre-gare, manifestazioni, gare</span>
            </span>
          </Link>
          <ul className="flex flex-wrap items-center gap-1 text-sm">
            <NavLink href="/regions" active={pathname?.startsWith("/regions") ?? false}>Regioni</NavLink>
            <NavLink href="/level1" active={pathname?.startsWith("/level1") ?? false}>Nazionali</NavLink>
            {hasRole(user, "admin") && (
              <NavLink href="/admin/watchlist" active={pathname?.startsWith("/admin") ?? false}>Watchlist</NavLink>
            )}
            <li className="relative">
              <details className="group">
                <summary className="cursor-pointer list-none rounded-lg px-3 py-1.5 text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800">Altro ▾</summary>
                <ul className="card absolute right-0 z-10 mt-2 w-44 space-y-0.5 p-1.5">
                  {([["/records", "Tutti i record"], ["/reports", "Report"], ["/alerts", "Alert"], ["/weak-evidence", "Evidenze deboli"], ["/usage", "Costi API"]] as [Route, string][]).map(([h, l]) => (
                    <li key={h}><Link href={h} className="block rounded-md px-3 py-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800">{l}</Link></li>
                  ))}
                </ul>
              </details>
            </li>
            <li className="ml-1"><ActiveScanBadge /></li>
            <li><ClaudeDownPill /></li>
            <li><UsageBadge /></li>
            <li className="ml-2 flex items-center gap-2 border-l border-neutral-200 pl-3 dark:border-neutral-700">
              <span className="grid h-7 w-7 place-items-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700" title={user.email}>
                {user.email.slice(0, 1).toUpperCase()}
              </span>
              <span className="chip bg-neutral-100 uppercase text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300">{user.role}</span>
              <button type="button" onClick={onLogout}
                className="rounded-lg border border-neutral-200 px-2.5 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800">
                Esci
              </button>
            </li>
          </ul>
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
      <AppFooter />
    </>
  );
}
