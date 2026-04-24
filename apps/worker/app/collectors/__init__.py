from app.collectors.anac import ANACCollector
from app.collectors.asmecomm import ASMECOMMCollector
from app.collectors.base import BaseCollector, CollectorError, CollectorResult
from app.collectors.generic_html import GenericHTMLCollector
from app.collectors.guri import GURICollector
from app.collectors.html_base import HTMLCollectorBase
from app.collectors.sater import SATERCollector
from app.collectors.start_toscana import StartToscanaCollector
from app.collectors.ted import TEDCollector
from app.collectors.traspare import TraspareCollector
from app.collectors.tuttogare import TuttogareCollector

COLLECTOR_REGISTRY: dict[str, type[BaseCollector]] = {
    # Official sources
    "ted": TEDCollector,
    "anac": ANACCollector,
    "bdncp": ANACCollector,
    "guri": GURICollector,
    # Tier A e-procurement
    "asmecomm": ASMECOMMCollector,
    "traspare": TraspareCollector,
    "tuttogare": TuttogareCollector,
    "sater": SATERCollector,
    "start_toscana": StartToscanaCollector,
    # Generic HTML fallback (albo, press, others)
    "generic_html": GenericHTMLCollector,
}

__all__ = [
    "ANACCollector",
    "ASMECOMMCollector",
    "BaseCollector",
    "COLLECTOR_REGISTRY",
    "CollectorError",
    "CollectorResult",
    "GURICollector",
    "GenericHTMLCollector",
    "HTMLCollectorBase",
    "SATERCollector",
    "StartToscanaCollector",
    "TEDCollector",
    "TraspareCollector",
    "TuttogareCollector",
]
