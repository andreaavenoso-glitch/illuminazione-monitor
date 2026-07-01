from app.collectors.base import BaseCollector, CollectorError, CollectorResult
from app.collectors.smart_llm import SmartLLMCollector
from app.collectors.ted_api import TEDCollector

# Most platform_types route to the generic LLM-based collector.
# The collector reads PLATFORM_SEARCH_URLS internally to know where to fetch.
_LLM_PLATFORM_TYPES = [
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
    pt: SmartLLMCollector for pt in _LLM_PLATFORM_TYPES
}
# TED exposes a real JSON REST API — bypass the LLM entirely for cost/reliability.
COLLECTOR_REGISTRY["ted"] = TEDCollector

__all__ = [
    "BaseCollector",
    "COLLECTOR_REGISTRY",
    "CollectorError",
    "CollectorResult",
    "SmartLLMCollector",
    "TEDCollector",
]
