/** Copyright note, creation date and contact person of the application (set in .env). */
const CREATED_ON = "21/04/2026";

export function AppFooter() {
  const holder = process.env.NEXT_PUBLIC_APP_COPYRIGHT_HOLDER?.trim();
  const owner = process.env.NEXT_PUBLIC_APP_OWNER?.trim();
  const contact = process.env.NEXT_PUBLIC_APP_OWNER_CONTACT?.trim();
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-neutral-200 px-6 py-4 text-center text-xs text-neutral-500 dark:border-neutral-800">
      © {CREATED_ON.slice(-4)}
      {year > Number(CREATED_ON.slice(-4)) ? `–${year}` : ""} {holder || "Tutti i diritti riservati"}
      {holder ? ". Tutti i diritti riservati" : ""}. Applicazione creata il {CREATED_ON}.
      {" "}Referente: {owner || "da indicare"}
      {contact && (
        <>
          {" · "}
          <a className="underline" href={contact.includes("@") ? `mailto:${contact}` : contact}>
            {contact}
          </a>
        </>
      )}
    </footer>
  );
}
