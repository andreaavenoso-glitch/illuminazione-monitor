from app.collectors.anac import ANACCollector
from app.collectors.base import BaseCollector, CollectorError
from app.collectors.guri import GURICollector
from app.collectors.ted import TEDCollector

COLLECTOR_REGISTRY: dict[str, type[BaseCollector]] = {
    "ted": TEDCollector,
    "anac": ANACCollector,
    "bdncp": ANACCollector,
    "guri": GURICollector,
}

__all__ = [
    "ANACCollector",
    "BaseCollector",
    "COLLECTOR_REGISTRY",
    "CollectorError",
    "GURICollector",
    "TEDCollector",
]
