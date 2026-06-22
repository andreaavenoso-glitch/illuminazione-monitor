from app.collectors.base import BaseCollector, CollectorError, CollectorResult
from app.collectors.smart_llm import SmartLLMCollector

# All platform_types route to the same LLM-based collector.
# The collector reads PLATFORM_SEARCH_URLS internally to know where to fetch.
_PLATFORM_TYPES = [
    "ted",
    "anac",
    "bdncp",
    "guri",
    "asmecomm",
    "traspare",
    "tuttogare",
    "sater",
    "start_toscana",
    "digitalpa",
    "portale_appalti",
    "sintel",
    "net4market",
    "acquistinrete",
    "sardegnacat",
    "generic_html",
]

COLLECTOR_REGISTRY: dict[str, type[BaseCollector]] = {
    pt: SmartLLMCollector for pt in _PLATFORM_TYPES
}

__all__ = [
    "BaseCollector",
    "COLLECTOR_REGISTRY",
    "CollectorError",
    "CollectorResult",
    "SmartLLMCollector",
]
