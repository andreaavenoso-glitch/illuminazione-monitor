"use client";

export interface EmailDraft {
  id: string;
  oggetto: string;
  corpo: string;
}

/** The editable e-mail text of a notice, with copy and "open in the mail program". Nothing is sent from here. */
export function EmailDraftBox({
  draft,
  onChange,
  copied,
  onCopied,
  onCopyError,
  onClose,
}: {
  draft: EmailDraft;
  onChange: (d: EmailDraft) => void;
  copied: boolean;
  onCopied: () => void;
  onCopyError: () => void;
  onClose: () => void;
}) {
  return (
    <div className="mt-2 space-y-2 rounded-lg border bg-white p-3 dark:border-neutral-700 dark:bg-neutral-900">
      <input
        className="w-full rounded border px-2 py-1 text-sm font-medium dark:border-neutral-700 dark:bg-neutral-950"
        value={draft.oggetto}
        onChange={(e) => onChange({ ...draft, oggetto: e.target.value })}
      />
      <textarea
        className="h-72 w-full rounded border p-2 font-mono text-xs leading-relaxed dark:border-neutral-700 dark:bg-neutral-950"
        value={draft.corpo}
        onChange={(e) => onChange({ ...draft, corpo: e.target.value })}
      />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-lg bg-neutral-900 px-3 py-1 text-xs text-white dark:bg-neutral-100 dark:text-neutral-900"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(`${draft.oggetto}\n\n${draft.corpo}`);
              onCopied();
            } catch {
              onCopyError();
            }
          }}
        >
          {copied ? "Copiato ✔" : "Copia oggetto e testo"}
        </button>
        <a
          className="rounded-lg border px-3 py-1 text-xs hover:bg-neutral-100 dark:hover:bg-neutral-800"
          href={`mailto:?subject=${encodeURIComponent(draft.oggetto)}&body=${encodeURIComponent(draft.corpo)}`}
        >
          Apri nel programma di posta
        </a>
        <button type="button" className="px-2 py-1 text-xs underline" onClick={onClose}>
          chiudi
        </button>
      </div>
      <p className="text-[11px] text-neutral-500">
        Il testo è generato dai dati che l&apos;app conosce (nulla è inventato): controllalo e modificalo prima di inviarlo.
        Se il programma di posta non si apre con tutto il testo, usa &quot;Copia&quot;.
      </p>
    </div>
  );
}
