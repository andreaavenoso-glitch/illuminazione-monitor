"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";

type DocumentRow = {
  id: string;
  filename: string | null;
  mime_type: string | null;
  storage_url: string;
  checksum: string | null;
  created_at: string;
};

export function DocumentsList({ recordId, defaultUrl }: { recordId: string; defaultUrl?: string }) {
  const qc = useQueryClient();
  const [url, setUrl] = useState(defaultUrl ?? "");

  const query = useQuery({
    queryKey: ["documents", recordId],
    queryFn: () => api.get<DocumentRow[]>(`/documents/by-record/${recordId}`),
  });

  const ingest = useMutation({
    mutationFn: (payload: { url: string }) =>
      api.post<{ status: string; task_id: string }>("/documents/ingest", {
        procurement_record_id: recordId,
        url: payload.url,
      }),
    onSuccess: () => {
      setUrl("");
      // documents may take a moment to appear (Celery task) — refetch after short delay
      setTimeout(() => qc.invalidateQueries({ queryKey: ["documents", recordId] }), 1500);
    },
  });

  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="text-lg font-semibold">Documenti collegati</h2>
      {query.isLoading ? (
        <p className="mt-2 text-sm text-neutral-500">Caricamento…</p>
      ) : (query.data ?? []).length === 0 ? (
        <p className="mt-2 text-sm text-neutral-500">Nessun documento ancora salvato per questa gara.</p>
      ) : (
        <ul className="mt-3 divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
          {(query.data ?? []).map((d) => (
            <li key={d.id} className="flex items-center justify-between py-2">
              <div>
                <a href={d.storage_url} target="_blank" rel="noreferrer" className="font-medium text-sky-600 hover:underline">
                  {d.filename ?? d.id}
                </a>
                <p className="text-xs text-neutral-500">
                  {d.mime_type ?? "—"} · salvato {fmtDate(d.created_at)}
                  {d.checksum && ` · sha256:${d.checksum.slice(0, 8)}`}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}

      <form
        className="mt-4 flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (url.trim()) ingest.mutate({ url: url.trim() });
        }}
      >
        <input
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://… url del documento da scaricare"
          className="flex-1 min-w-[260px] rounded border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-950"
        />
        <button
          type="submit"
          disabled={ingest.isPending}
          className="rounded border border-neutral-300 px-3 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
        >
          {ingest.isPending ? "Scarico…" : "Scarica e archivia"}
        </button>
        {ingest.error && (
          <p className="w-full text-xs text-red-600">{(ingest.error as Error).message}</p>
        )}
        {ingest.data && (
          <p className="w-full text-xs text-emerald-600">Task in coda — controlla a breve.</p>
        )}
      </form>
    </section>
  );
}
