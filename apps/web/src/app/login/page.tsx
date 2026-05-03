"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { setSession, type AuthUser } from "@/lib/auth";

type LoginResponse = {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
};

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const redirect = params.get("redirect") || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const tokenRes = await api.post<LoginResponse>("/auth/login", {
        email,
        password,
      });
      // Store token first so the next request includes it.
      window.localStorage.setItem("lpm.token", tokenRes.access_token);
      const me = await api.get<AuthUser>("/auth/me");
      setSession(tokenRes.access_token, me);
      router.replace(redirect);
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 401
          ? "Email o password non validi."
          : err instanceof ApiError && err.status === 429
          ? "Troppi tentativi, riprova tra un minuto."
          : (err as Error).message;
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-md items-center justify-center px-6">
      <form
        onSubmit={onSubmit}
        className="w-full space-y-4 rounded-lg border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900"
      >
        <div>
          <h1 className="text-xl font-bold">Accedi</h1>
          <p className="mt-1 text-sm text-neutral-500">
            Lighting Procurement Monitor
          </p>
        </div>
        <div>
          <label className="text-xs uppercase text-neutral-500">Email</label>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-950"
          />
        </div>
        <div>
          <label className="text-xs uppercase text-neutral-500">Password</label>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-950"
          />
        </div>
        {error && (
          <p className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-100">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
        >
          {submitting ? "Accesso in corso…" : "Accedi"}
        </button>
      </form>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
