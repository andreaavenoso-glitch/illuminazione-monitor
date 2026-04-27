"""Regex patterns for procurement identifiers.

CIG / CUP ported from scripts/pipeline.js:168 (CIG) and expanded.
CPV codes specific to public lighting (Common Procurement Vocabulary, EU).
"""
import re

CIG_PATTERN = re.compile(r"^[A-Z0-9]{8,10}$")
CUP_PATTERN = re.compile(r"^[A-Z][0-9]{14}[A-Z0-9]$")
CPV_PATTERN = re.compile(r"\b\d{8}(?:-\d)?\b")

# CPV codes commonly used for public lighting procurement.
CPV_LIGHTING_CODES: frozenset[str] = frozenset(
    {
        "31518200",  # emergency lighting equipment
        "31520000",  # lamps and light fittings
        "31521000",  # lamps
        "31527200",  # outdoor lamps (street lamps)
        "31527260",  # lighting systems
        "34928510",  # street-lighting poles / columns
        "34993000",  # road-lighting equipment
        "45316100",  # installation of outdoor lighting equipment
        "45316110",  # installation of road lighting equipment
        "50232000",  # maintenance of public-lighting installations
        "50232100",  # street-lighting maintenance
        "71323100",  # electrical power systems design services
        "71323200",  # industrial engineering plant design
    }
)


def valid_cig(value: str | None) -> bool:
    if not value:
        return False
    return bool(CIG_PATTERN.match(value.strip().upper()))


def contains_lighting_cpv(text: str | None) -> bool:
    if not text:
        return False
    for match in CPV_PATTERN.findall(text):
        code = match.split("-")[0]
        if code in CPV_LIGHTING_CODES:
            return True
    return False
