"""Referenti by web research: Claude with web search + web fetch, following the checklist of the
"referenti comuni verificati" method (every cell has a source; nothing is deduced).

The agent returns JSON with a source URL and page date for each person. Nothing it says is trusted
blindly: ``freshness`` (shared_models.referenti_logic) decides verificato / da_confermare from the
page date, the last election and the existence of an appointment decree, the roles are checked
against the allowed list, and a name that is page furniture is dropped.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

import anthropic
import structlog
from app.collectors.albo_pretorio_llm import is_fatal_api_error
from app.collectors.referenti import RUOLI, looks_like_name
from app.config import WorkerSettings
from app.usage import record_usage
from shared_models.referenti_logic import freshness

log = structlog.get_logger(__name__)
MAX_CONTINUATIONS = 6

SYSTEM_PROMPT = """Sei un ricercatore di contatti istituzionali. Trovi i referenti di UN comune italiano per interloquire su un appalto di illuminazione pubblica (partenariato pubblico-privato, finanza di progetto, servizi collegati). Ogni dato che riporti deve avere una prova; se non e' provato lo lasci vuoto. Non stimi, non ricostruisci, non deduci.

# RUOLI
1. sindaco: nome, email, telefono, deleghe trattenute.
2. assessore: l'assessore con delega a Lavori pubblici / Illuminazione pubblica / Energia (testo della delega, email, telefono). Se nessun assessore ha la delega, il referente e' il sindaco: dimostralo aprendo la scheda di TUTTI gli assessori; altrimenti non scrivere "nessuno".
3. responsabile_tecnico: responsabile ufficio tecnico / LLPP / area tecnica (dirigente, responsabile d'area o EQ), con ruolo esatto.
4. rup: solo se un atto lo nomina per questa procedura.
Inoltre: PEC dell'ente (da IPA, indicepa.gov.it), data dell'ultima elezione e scadenza naturale del mandato.

# REGOLE DI PROVA
- Fonti primarie: sito istituzionale del comune (schede persona, uffici, Amministrazione Trasparente, albo pretorio, atti), IPA, Anagrafe amministratori del Ministero dell'Interno, Eligendo. Stampa, aggregatori e snippet di ricerca valgono SOLO come riscontro.
- Il sito del comune e' la fonte base: un dato del comune che supera la freschezza basta. Passa ad altre fonti solo se la freschezza non e' superata, il dato manca o qualcosa lo contraddice.
- Apri davvero le pagine (web_fetch); la ricerca serve a trovare gli URL. Niente dati da uno snippet senza aprire la pagina. Niente email ricostruite dal formato.
- Freschezza: POLITICI (sindaco, assessori): pagina successiva all'ultima elezione e nessun rimpasto/dimissione/avvicendamento nella stampa locale degli ultimi 6 mesi (anche con decorrenza futura). TECNICI: le elezioni non contano; pagina aggiornata negli ultimi 12 mesi OPPURE decreto di incarico in vigore.
- Se la stampa contraddice il sito (assessore cessato ma citato in carica), riapri la pagina della giunta e la scheda della persona.
- Conflitti tra fonti: scegli l'atto formale piu' recente, poi la data piu' recente; spiegalo in "note".
- Se una pagina non si apre, riprova con un URL alternativo prima di arrenderti: un fallimento tecnico non vale "non pubblicato".
- "Non pubblicato" solo dopo aver controllato: pagina Giunta/Politici, scheda sindaco, scheda di ogni assessore, uffici LLPP/Area tecnica, Amministrazione Trasparente (organizzazione, personale), albo/atti (decreti di nomina), IPA, Ministero Interno/Eligendo, stampa locale degli ultimi 6 mesi.

# OUTPUT
Alla fine rispondi SOLO con un JSON (nessun altro testo):
{
 "elezione_data": "YYYY-MM-DD o null", "mandato_scadenza": "YYYY-MM-DD o null",
 "pec": {"valore": "...", "fonte_url": "..."} o null,
 "persone": [{"ruolo": "sindaco|assessore|responsabile_tecnico|rup", "nome": "...", "qualifica": "ruolo/delega come scritta", "email": "...|null", "telefono": "...|null", "fonte_url": "URL della pagina", "data_pagina": "YYYY-MM-DD o null (aggiornamento della pagina)", "decreto_in_vigore": true|false, "citazione": "frase copiata dalla fonte", "stato": "VERIFICATO|PARZIALE|NON_VERIFICATO", "note": "..."}],
 "lacune": ["cio' che non hai trovato e perche'"],
 "url_controllati": ["..."],
 "stampa": "esito del controllo stampa degli ultimi 6 mesi in una riga"
}
"stato": VERIFICATO = dato sul sito del comune che supera la freschezza o confermato da atto recente; PARZIALE = freschezza non superata e nessuna conferma, o conflitto; NON_VERIFICATO = solo fonti secondarie."""


def tools(settings: WorkerSettings) -> list[dict[str, Any]]:
    return [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": settings.referenti_max_searches},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": settings.referenti_max_fetches},
    ]


def parse_json(text: str) -> dict[str, Any] | None:
    """The first JSON object of the agent's final text (it may wrap it in a code fence)."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _d(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def normalize_result(data: dict[str, Any], today: date) -> dict[str, Any]:
    """Referente rows (verificato / da_confermare decided by the rules, not by the agent) plus the
    ente-level facts. Pure: no network."""
    elezione = _d(data.get("elezione_data"))
    people: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for p in data.get("persone") or []:
        if not isinstance(p, dict):
            continue
        ruolo, nome = p.get("ruolo"), " ".join(str(p.get("nome") or "").split())
        if ruolo not in RUOLI or not looks_like_name(nome) or not p.get("fonte_url"):
            continue
        key = (ruolo, nome.lower())
        if key in seen:
            continue
        seen.add(key)
        data_fonte = _d(p.get("data_pagina"))
        ok, motivo = freshness(ruolo, data_fonte, elezione, bool(p.get("decreto_in_vigore")), today)
        agent_ok = str(p.get("stato") or "").upper() == "VERIFICATO"
        if agent_ok and ok:
            stato, why = "verificato", None
        else:
            stato = "da_confermare"
            why = motivo if not ok else (str(p.get("note") or "").strip()[:200] or "non confermato da una seconda fonte")
        people.append({
            "nome": nome, "ruolo": ruolo,
            "qualifica": (str(p.get("qualifica") or "").strip() or None),
            "email": (str(p.get("email") or "").strip() or None),
            "telefono": (str(p.get("telefono") or "").strip() or None),
            "citazione": (str(p.get("citazione") or "").strip()[:240] or None),
            "fonte_url": str(p["fonte_url"]), "data_fonte": data_fonte, "elezione_data": elezione,
            "stato": stato, "motivo": why,
        })
    pec = data.get("pec") if isinstance(data.get("pec"), dict) else None
    return {
        "people": people,
        "pec": (str(pec.get("valore")).strip(), str(pec.get("fonte_url") or "")) if pec and pec.get("valore") else None,
        "elezione": elezione, "mandato_scadenza": _d(data.get("mandato_scadenza")),
        "lacune": [str(x) for x in (data.get("lacune") or [])][:20],
        "urls": [str(x) for x in (data.get("url_controllati") or [])][:60],
        "stampa": str(data.get("stampa") or "")[:300],
    }


async def research(
    ente: str, regione: str | None, hints: list[str], settings: WorkerSettings, status: dict | None = None
) -> dict[str, Any] | None:
    """Run the research. None when the call failed (``status`` says why and whether it is fatal)."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    task = (
        f"Comune: {ente}" + (f" ({regione})" if regione else "") + "\n"
        f"Data odierna: {date.today().isoformat()}\n"
        + ("Indirizzi gia' noti (punto di partenza, non unica fonte):\n- " + "\n- ".join(hints) + "\n" if hints else "")
        + "Trova sindaco, assessore ai Lavori pubblici/Illuminazione/Energia, responsabile tecnico, PEC e mandato, "
        "secondo le regole. Rispondi solo con il JSON."
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    response = None
    for _ in range(MAX_CONTINUATIONS):
        try:
            response = await client.messages.create(
                model=settings.referenti_model,
                max_tokens=16000,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                tools=tools(settings),
                messages=messages,
            )
        except anthropic.APIError as exc:
            log.warning("referenti_agent.error", ente=ente, error=str(exc))
            if status is not None:
                status.update(ok=False, error=str(exc), fatal=is_fatal_api_error(exc))
            return None
        await record_usage(response.usage, model=settings.referenti_model, purpose="referenti_agent", label=ente[:60])
        if response.stop_reason != "pause_turn":
            break
        # the server-side loop paused: send back the assistant turn and it resumes by itself
        messages = [messages[0], {"role": "assistant", "content": response.content}]
    if response is None:
        return None
    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
    data = parse_json(text)
    if data is None:
        log.warning("referenti_agent.no_json", ente=ente, stop=response.stop_reason, chars=len(text))
        if status is not None:
            status.update(ok=False, error="risposta senza JSON", fatal=False)
        return None
    return normalize_result(data, date.today())
