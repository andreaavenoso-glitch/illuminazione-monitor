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
    "global service illuminazione",
    "accordo quadro illuminazione",
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
