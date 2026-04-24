"use client";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function ExportButtons({ queryString }: { queryString: string }) {
  const link = (fmt: "xlsx" | "csv" | "json") =>
    `${BASE_URL}/records/export/${fmt}${queryString}`;
  const cls =
    "rounded border border-neutral-300 px-3 py-1 text-xs font-medium hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800";
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-neutral-500">Esporta:</span>
      <a className={cls} href={link("xlsx")} download>
        XLSX
      </a>
      <a className={cls} href={link("csv")} download>
        CSV
      </a>
      <a className={cls} href={link("json")} download>
        JSON
      </a>
    </div>
  );
}
