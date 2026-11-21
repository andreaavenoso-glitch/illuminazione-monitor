import { redirect } from "next/navigation";

// La pagina iniziale e' la vista per regioni (Italia -> Regione -> Comuni).
export default function HomePage() {
  redirect("/regions");
}
