"""Ported from scripts/pipeline.js:156-157 in the legacy Node prototype."""

LIGHTING_INCLUDE: tuple[str, ...] = (
    "illuminazione pubblica",
    "pubblica illuminazione",
    "relamping",
    "telegestione",
    "telecontrollo",
    "smart lighting",
    "riqualificazione illuminazione",
    "pali illuminazione",
    "pali di illuminazione",
    "global service illuminazione",
    "accordo quadro illuminazione",
    "servizio luce",
    "illuminazione stradale",
    # Maintenance / replacement / efficiency wordings seen in real notices.
    "illuminazione comunale",
    "corpi illuminanti",
    "punti luce",
    "retrofit",
    "inquinamento luminoso",
    "piano regolatore dell'illuminazione",
    "conduzione e manutenzione degli impianti di illuminazione",
)

LIGHTING_EXCLUDE: tuple[str, ...] = (
    "illuminazione interna",
    "impianto elettrico generico",
    "facility management",
    "climatizzazione",
    "edifici",
    "immobili",
    "fotovoltaico senza ip",
)
