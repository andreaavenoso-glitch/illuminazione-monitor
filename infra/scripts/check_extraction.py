"""End-to-end check of the Claude extraction on known examples (a few cents).

The dry run never calls Claude, and the real trials so far found 0 records, so
nothing has shown yet that the extraction + prompt + service catalog actually
return what they should. This sends ONE small compact list, shaped like what the
page gate sends, with notices that must be found (several services) and notices
that must not (elections, an award, an event), and prints PASS / FAIL for each.

Run inside the worker container (it has the API key):

    docker compose exec worker python -m infra.scripts.check_extraction
"""
from __future__ import annotations

import asyncio
import sys

BASE = "https://www.comune.esempio.it/albo"

# (text to look for in the returned title/body, must it be returned?, label)
CASES: list[tuple[str, bool, str]] = [
    ("manutenzione degli impianti di pubblica illuminazione", True,
     "manifestazione di interesse - illuminazione pubblica"),
    ("sollecitazione di proposte di finanza di progetto", True,
     "PPP / finanza di progetto - illuminazione"),
    ("sistemi di videosorveglianza urbana", True, "indagine di mercato - videosorveglianza"),
    ("colonnine di ricarica per veicoli elettrici", True, "manifestazione di interesse - ricarica EV"),
    ("efficientamento energetico degli edifici scolastici", True, "efficientamento edifici e scuole"),
    ("incarico di advisor", True, "incarico advisor per proposta PPP"),
    ("tessera elettorale", False, "notizia elettorale"),
    ("esito di gara", False, "esito di gara (aggiudicazione)"),
    ("luci di natale", False, "sponsorizzazione evento"),
    ("somministrazione di alimenti", False, "concessione area pubblica"),
]

SAMPLE_HTML = """<ul>
<li><a href="/a1">Avviso di manifestazione di interesse per l'affidamento del servizio di manutenzione degli impianti di pubblica illuminazione</a> (12/11/2026) Scadenza 30/11/2026</li>
<li><a href="/a2">Avviso per la sollecitazione di proposte di finanza di progetto per la gestione e la riqualificazione dell'illuminazione pubblica</a> (10/11/2026)</li>
<li><a href="/a3">Indagine di mercato per la fornitura e posa di sistemi di videosorveglianza urbana</a> (09/11/2026)</li>
<li><a href="/a4">Manifestazione di interesse per l'installazione di colonnine di ricarica per veicoli elettrici sul territorio comunale</a> (08/11/2026)</li>
<li><a href="/a5">Avviso esplorativo per lavori di efficientamento energetico degli edifici scolastici comunali</a> (07/11/2026)</li>
<li><a href="/a6">Affidamento dell'incarico di advisor tecnico-finanziario per la valutazione della proposta di partenariato pubblico privato sull'illuminazione pubblica</a> (06/11/2026)</li>
<li><a href="/b1">Avviso agli elettori: rilascio della tessera elettorale</a> (05/11/2026)</li>
<li><a href="/b2">Esito di gara: aggiudicazione dei lavori di manutenzione dell'illuminazione pubblica</a> (04/11/2026)</li>
<li><a href="/b3">Manifestazione di interesse per la sponsorizzazione dell'evento Luci di Natale 2026</a> (03/11/2026)</li>
<li><a href="/b4">Concessione di area pubblica per l'attivita di somministrazione di alimenti e bevande</a> (02/11/2026)</li>
</ul>"""


def evaluate(records: list[dict], cases: list[tuple[str, bool, str]] = CASES) -> list[tuple[str, bool, str]]:
    """(label, passed, detail) per case. A case is "found" when its text appears
    in the title or body of any returned record. Pure, tested."""
    blobs = [f"{r.get('title', '')} {r.get('body', '')}".lower() for r in records]
    out = []
    for needle, must_find, label in cases:
        found = any(needle.lower() in b for b in blobs)
        out.append((label, found == must_find, "trovato" if found else "non trovato"))
    return out


async def main() -> int:
    from app.collectors.albo_pretorio_llm import extract_albo_records
    from app.config import get_worker_settings
    from shared_models.services import configure, parse_enabled

    settings = get_worker_settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY non impostata: impossibile provare l'estrazione.")
        return 2
    configure(parse_enabled(settings.enabled_services))
    status = {"ok": True}
    records = await extract_albo_records(SAMPLE_HTML, url=BASE, settings=settings, label="check", status=status)
    print(f"Chiamata a Claude: {'ok' if status['ok'] else 'FALLITA (vedi log: albo_pretorio.claude_error)'}")
    print(f"Record restituiti: {len(records)}\n")
    for r in records:
        print(f"  - [{r.get('atto_tipo')}] {str(r.get('title'))[:110]}")
    print()
    results = evaluate(records)
    for label, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: {detail}")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} corretti")
    return 1 if failed or not status["ok"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
