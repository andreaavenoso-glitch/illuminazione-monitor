"""The services the monitor looks for, each with its own keywords.

Built from the company's service sheets (A2A Illuminazione Pubblica: company
profile 2026 and "servizi innovativi"): public lighting and everything that is
sold on the same poles and contracts. The page gate, the extraction prompt and
the perimeter check all read this list, so adding a service here is enough.

Which ones are active is configuration (``configure``), not code: the filter
uses the union of the keywords of the active services.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    key: str
    label: str
    keywords: tuple[str, ...]


SERVICES: tuple[Service, ...] = (
    Service("illuminazione_pubblica", "Illuminazione pubblica (gestione, manutenzione, riqualificazione)", (
        "illuminazione pubblica", "pubblica illuminazione", "illuminazione comunale", "illuminazione stradale",
        "impianti di illuminazione", "impianto di illuminazione", "punti luce", "punto luce",
        "corpi illuminanti", "apparecchi illuminanti", "sostituzione corpi", "retrofit", "relamping",
        "servizio luce", "telegestione", "inquinamento luminoso", "conduzione e manutenzione",
        "illuminazione led", "riqualificazione illuminazione", "pali di illuminazione", "pali illuminazione",
        "global service illuminazione", "accordo quadro illuminazione", "led",
    )),
    Service("illuminazione_artistica", "Illuminazione artistica e architettonica", (
        "illuminazione artistica", "illuminazione architettonica", "illuminazione monumentale",
        "illuminazione scenografica", "valorizzazione illuminotecnica", "illuminazione dei monumenti",
    )),
    Service("piste_ciclabili_pedonali", "Illuminazione di piste ciclabili e passaggi pedonali", (
        "illuminazione piste ciclabili", "illuminazione percorsi ciclopedonali",
        "illuminazione attraversamenti pedonali", "illuminazione passaggi pedonali",
        "attraversamenti pedonali illuminati", "attraversamenti pedonali intelligenti",
        "passaggi pedonali luminosi",
    )),
    Service("semafori", "Semafori e lanterne semaforiche", (
        "impianti semaforici", "impianto semaforico", "lanterne semaforiche", "semafori intelligenti",
        "regolazione semaforica", "semafori a led", "semafori",
    )),
    Service("videosorveglianza", "Videosorveglianza e video-analisi", (
        "videosorveglianza", "video sorveglianza", "videoanalisi", "video-analisi",
        "telecamere di sorveglianza", "lettura targhe", "sicurezza urbana integrata",
    )),
    Service("relamping_edifici", "Relamping e efficientamento energetico di edifici pubblici e scuole", (
        "efficientamento energetico", "riqualificazione energetica", "illuminazione degli edifici",
        "illuminazione edifici pubblici", "relamping edifici", "illuminazione delle scuole",
        "illuminazione scolastica",
    )),
    Service("fotovoltaico_cer", "Fotovoltaico e comunità energetiche", (
        "fotovoltaico", "impianti fotovoltaici", "pannelli fotovoltaici", "comunità energetica",
        "comunità energetiche", "comunita energetica", "comunita energetiche", "autoconsumo collettivo",
        "configurazione di autoconsumo",
    )),
    Service("ricarica_ev", "Ricarica per veicoli elettrici", (
        "ricarica veicoli elettrici", "ricarica per veicoli elettrici", "colonnine di ricarica",
        "colonnina di ricarica", "stazioni di ricarica", "infrastrutture di ricarica", "city plug",
        "mobilità elettrica", "mobilita elettrica",
    )),
    Service("connettivita_5g", "Connettività 5G e infrastrutture di telecomunicazione", (
        "5g", "small cell", "fibra ottica", "stazioni radio base", "infrastrutture di telecomunicazione",
        "infrastrutture digitali", "antenne su pali",
    )),
    Service("digital_advertising", "Digital advertising e impianti pubblicitari", (
        "digital advertising", "pubblicità digitale", "pubblicita digitale", "impianti pubblicitari",
        "schermi digitali", "affissioni digitali", "totem digitali", "spazi pubblicitari",
    )),
    Service("smart_city", "Smart city, pali intelligenti e digital twin", (
        "smart city", "città intelligente", "citta intelligente", "pali intelligenti", "smart pole",
        "digital twin", "gemello digitale", "sensoristica urbana",
    )),
)

# Not a service of its own: PPP / finanza di progetto acts often do not name the
# service in the title, so they pass the gate on their own wording.
PPP_GATE_KEYWORDS: tuple[str, ...] = (
    "finanza di progetto", "project financing", "partenariato pubblico privato",
    "partenariato pubblico-privato", "proposta di finanza", "ppp", "art. 193", "articolo 193",
    "sollecitazione di proposte", "pric",
)

_BY_KEY = {s.key: s for s in SERVICES}
_enabled: tuple[str, ...] = tuple(s.key for s in SERVICES)


def configure(enabled_keys: list[str] | None) -> None:
    """Set the active services. ``None`` or empty means all of them. Unknown
    keys are ignored (a typo in the setting must not switch everything off)."""
    global _enabled
    keys = [k.strip() for k in (enabled_keys or []) if k.strip() in _BY_KEY]
    _enabled = tuple(keys) if keys else tuple(s.key for s in SERVICES)


def parse_enabled(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def enabled_services() -> tuple[Service, ...]:
    return tuple(_BY_KEY[k] for k in _enabled)


def gate_keywords() -> tuple[str, ...]:
    """Keywords that let a page through to the paid extraction."""
    words: list[str] = []
    for s in enabled_services():
        words.extend(s.keywords)
    words.extend(PPP_GATE_KEYWORDS)
    return tuple(dict.fromkeys(words))


def _matches(text_lower: str, keyword: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", text_lower) is not None


def detect_services(text: str | None) -> list[str]:
    """Keys of the services whose keywords appear in the text, in catalog order.
    ``led`` and ``semafori`` are weak on their own but fine as a label."""
    if not text:
        return []
    low = text.lower()
    return [s.key for s in SERVICES if any(_matches(low, k) for k in s.keywords)]


def mentions_any_service(text: str | None) -> bool:
    return bool(detect_services(text))


def prompt_block() -> str:
    """The services as a bullet list for the extraction prompt."""
    lines = []
    for s in enabled_services():
        examples = ", ".join(s.keywords[:4])
        lines.append(f"  - {s.label} (es.: {examples})")
    return "\n".join(lines)
