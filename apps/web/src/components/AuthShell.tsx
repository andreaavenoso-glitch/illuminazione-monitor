"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { clearSession, getUser, hasRole, type AuthUser } from "@/lib/auth";

const PUBLIC_PATHS = ["/login"];

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
  if (isLogin) return <>{children}</>;

  if (!hydrated || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-neutral-500">
        Caricamento…
      </div>
    );
  }

  return (
    <>
      <header className="border-b border-neutral-200 bg-white px-6 py-4 dark:border-neutral-800 dark:bg-neutral-900">
        <nav className="mx-auto flex max-w-7xl items-center justify-between">
          <Link href="/" className="text-lg font-semibold">
            Lighting Procurement Monitor
          </Link>
          <ul className="flex items-center gap-4 text-sm text-neutral-600 dark:text-neutral-400">
            <li><Link href="/records" className="hover:underline">Records</Link></li>
            <li><Link href="/reports" className="hover:underline">Reports</Link></li>
            <li><Link href="/alerts" className="hover:underline">Alerts</Link></li>
            <li><Link href="/weak-evidence" className="hover:underline">Weak evidence</Link></li>
            {hasRole(user, "admin") && (
              <li><Link href="/admin/watchlist" className="hover:underline">Watchlist</Link></li>
            )}
            <li className="ml-2 flex items-center gap-2 border-l border-neutral-300 pl-4 dark:border-neutral-700">
              <span className="text-xs">
                {user.email}{" "}
                <span className="rounded-full bg-neutral-200 px-2 py-0.5 text-[10px] font-medium uppercase text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300">
                  {user.role}
                </span>
              </span>
              <button
                type="button"
                onClick={onLogout}
                className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
              >
                Logout
              </button>
            </li>
          </ul>
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </>
  );
}
