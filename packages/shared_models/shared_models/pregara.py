"""What a pre-gara notice is about. A pre-gara is not a tender yet: it is a signal that the administration is
moving (a delibera, money set aside, a verifier or consultants appointed, maintenance of the plants). The e-mail
for a pre-gara says WHICH signal it is, in words; the deeper reading of the documents is optional.

Pure functions, free: the wording of the title (and, when read, of the documents) decides.
"""
from __future__ import annotations

import re

TIPI: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("delibera", "Delibera", re.compile(
        r"delibera(?:zione)?\b|atto di indirizzo|presa d.atto|approvazione (?:del )?(?:progetto|piano|documento)", re.I)),
    ("impegno_spesa", "Impegno di spesa", re.compile(
        r"impegno di spesa|impegno (?:della )?spesa|impegna\w* la spesa|determina(?:zione)? (?:di )?impegno|"
        r"impegno contabile|prenotazione d.impegno|assunzione (?:di )?impegno", re.I)),
    ("mandato_verificatore", "Mandato al verificatore", re.compile(
        r"verificatore|verifica (?:del |della |dei )?(?:pfte|proposta|progetto)|validazione (?:del )?progetto|"
        r"organismo di (?:ispezione|verifica)|mandato (?:al|per la|di) verifica|incarico di verifica", re.I)),
    ("consulenza", "Società di consulenza / advisor", re.compile(
        r"advisor|societ[àa] di consulenza|consulen(?:za|te|ti)\b|supporto (?:tecnico|specialistico|al rup)|"
        r"assistenza tecnico[- ]amministrativa|incarico (?:di|per) (?:supporto|assistenza|consulenza)", re.I)),
    ("manutenzione", "Manutenzione degli impianti", re.compile(
        r"manutenzion\w*|pronto intervento|riparazion\w*|ripristino (?:degli )?impianti|gestione degli impianti", re.I)),
)
LABEL = {k: lab for k, lab, _ in TIPI}


def pregara_tipi(text: str | None) -> list[str]:
    """The keys of the signals found in ``text``, in the order above (a notice may carry more than one)."""
    flat = " ".join((text or "").split())
    return [k for k, _, rx in TIPI if rx.search(flat)]


def pregara_label(keys: list[str] | None) -> str:
    return ", ".join(LABEL.get(k, k) for k in (keys or []))
