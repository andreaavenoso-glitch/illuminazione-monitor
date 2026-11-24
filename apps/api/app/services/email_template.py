"""Standard e-mail with the main elements of a notice (pre-gara, manifestazione di interesse, gara).

Pure function: the text is built from what the app knows (record, extracted fields, referenti); a value
that is not known is left out or marked "non indicata", never guessed. The user edits it before sending.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from shared_models.pregara import pregara_label, pregara_tipi

TIPO = {"pre_gara": "Pre-gara", "manifestazione_interesse": "Manifestazione di interesse", "gara": "Gara"}
PROSSIMO_PASSO = {
    "pre_gara": "Valutare un primo contatto con l'amministrazione per posizionarci prima della pubblicazione dell'avviso.",
    "manifestazione_interesse": "Valutare la presentazione della manifestazione di interesse entro la scadenza indicata.",
    "gara": "Valutare la partecipazione: verificare i requisiti e i tempi per preparare l'offerta.",
}
SERVIZIO_LABEL = {
    "illuminazione_pubblica": "Illuminazione pubblica", "illuminazione_artistica": "Illuminazione artistica",
    "piste_ciclabili_pedonali": "Piste ciclabili e pedonali", "semafori": "Semafori",
    "videosorveglianza": "Videosorveglianza", "relamping_edifici": "Edifici pubblici e scuole",
    "fotovoltaico_cer": "Fotovoltaico e CER", "ricarica_ev": "Ricarica EV", "connettivita_5g": "5G e telecomunicazioni",
    "digital_advertising": "Digital advertising", "smart_city": "Smart city",
}
CAMPO_LABEL = [
    ("cig", "CIG"), ("importo_massimo_eur", "Importo massimo"), ("durata", "Durata"), ("punti_luce", "Punti luce"),
    ("procedura", "Procedura"), ("criterio_aggiudicazione", "Criterio di aggiudicazione"),
    ("finanziamento", "Finanziamento"), ("rup", "RUP"),
]
# A pre-gara e-mail carries the main information of the act (which signal, which act, how much, who was appointed);
# a manifestazione di interesse / gara adds what the deep reading of the documents found.
CAMPI_PREGARA = [
    ("atto_estremi", "Atto"), ("impegno_spesa_eur", "Impegno di spesa"), ("incaricato", "Incaricato"),
    ("importo_massimo_eur", "Importo"), ("durata", "Durata"),
]
CAMPI_EXTRA = [("sopralluogo", "Sopralluogo"), ("pec_invio", "PEC per l'invio dell'offerta"), ("consumi_mwh", "Consumi (MWh/anno)"),
               ("spesa_annua_eur", "Spesa annua"), ("canone_annuo_eur", "Canone annuo di riferimento")]
_DELEGA_LLPP = re.compile(r"lavori pubblici|ll\.? ?pp|opere pubbliche|manutenzion|illuminazion|urbanistic|patrimonio|energia|ambiente", re.IGNORECASE)


def ruolo_label(p: dict, default: str) -> str:
    """The role of a person as written: an assessore is "ai Lavori pubblici" only when his delega says so (the other
    assessori are simply assessori: they are listed because they are in the giunta, not because they hold that delega)."""
    if p.get("ruolo") == "assessore":
        return "Assessore ai Lavori pubblici" if _DELEGA_LLPP.search(p.get("qualifica") or "") else "Assessore"
    return default


RUOLO_LABEL = [("sindaco", "Sindaco"), ("assessore", "Assessore ai Lavori pubblici"), ("responsabile_tecnico", "Referente tecnico"), ("rup", "RUP")]


def _d(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _eur(v: float) -> str:
    return "€ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _campo(key: str, v: Any) -> str:
    if key.endswith("_eur"):
        return _eur(float(v))
    return ", ".join(v) if isinstance(v, list) else str(v)


def _persona(p: dict) -> str:
    bits = [p["nome"]]
    if p.get("qualifica"):
        bits.append(f"({p['qualifica']})")
    contatti = " · ".join(x for x in (p.get("email"), p.get("telefono")) if x)
    s = " ".join(bits) + (f" – {contatti}" if contatti else "")
    return s + (" [da confermare]" if p.get("stato") != "verificato" else "")


def build_email(
    *,
    categoria: str,
    ente: str,
    descrizione: str | None,
    link: str,
    scadenza: Any,
    visto_il: Any,
    servizi: list[str],
    provincia: str | None,
    campi: dict[str, dict] | None,
    referenti: list[dict],
    pec: str | None,
    today: date,
) -> dict[str, str]:
    """{"oggetto", "corpo"}."""
    tipo = TIPO.get(categoria, "Avviso")
    scad = _d(scadenza)
    titolo = " ".join((descrizione or "").split())
    breve = titolo if len(titolo) <= 80 else titolo[:77].rstrip() + "…"
    oggetto = f"[{tipo}] {ente} – {breve}" + (f" – scadenza {scad:%d/%m/%Y}" if scad else "")

    righe = [
        "Ciao,",
        "",
        "segnalo un'opportunità individuata dal monitoraggio degli appalti di illuminazione pubblica e servizi collegati.",
        "",
        f"Tipo: {tipo}",
        f"Ente: {ente}" + (f" ({provincia})" if provincia else ""),
        f"Oggetto: {titolo or 'non indicato'}",
    ]
    if servizi:
        righe.append("Servizi: " + ", ".join(SERVIZIO_LABEL.get(s, s) for s in servizi))
    if scad:
        giorni = (scad - today).days
        righe.append(f"Scadenza: {scad:%d/%m/%Y}" + (f" (tra {giorni} giorni)" if giorni >= 0 else " (SCADUTA)"))
    else:
        righe.append("Scadenza: non indicata (da verificare sul documento)")
    visto = _d(visto_il)
    if visto:
        righe.append(f"Individuato il: {visto:%d/%m/%Y}")
    righe.append(f"Documento: {link}")

    if categoria == "pre_gara":
        keys = (campi or {}).get("pregara_tipi", {}).get("valore") or pregara_tipi(titolo)
        if keys:
            righe.insert(righe.index(f"Oggetto: {titolo or 'non indicato'}") + 1, f"Di cosa si tratta: {pregara_label(keys)}")
        lista = CAMPI_PREGARA
    else:
        lista = CAMPO_LABEL + CAMPI_EXTRA
    dati = [(lab, _campo(k, campi[k]["valore"])) for k, lab in lista if campi and k in campi]
    if dati:
        righe += ["", "Dati dalla documentazione:" if categoria != "pre_gara" else "Dati dell'atto:"] + [f"- {lab}: {val}" for lab, val in dati]
    if categoria != "pre_gara":
        righe += ["", "In allegato la scheda di sintesi (Gate 1) con i dati della documentazione analizzata."]

    contatti = []
    for ruolo, lab in RUOLO_LABEL:
        if ruolo == "rup" and campi and "rup" in campi:
            continue  # already listed among the documentation data
        for p in [x for x in referenti if x["ruolo"] == ruolo][:2]:
            contatti.append(f"- {ruolo_label(p, lab)}: {_persona(p)}")
    if pec:
        contatti.append(f"- PEC dell'ente: {pec}")
    if contatti:
        righe += ["", "Referenti del comune:"] + contatti
        if any("[da confermare]" in c for c in contatti):
            righe.append("(i nomi \"da confermare\" vanno verificati prima di un contatto)")

    righe += [
        "",
        "Prossimo passo proposto: " + PROSSIMO_PASSO.get(categoria, "Valutare l'opportunità."),
        "",
        "Resto a disposizione per un confronto.",
        "Cordiali saluti,",
    ]
    return {"oggetto": oggetto, "corpo": "\n".join(righe)}
