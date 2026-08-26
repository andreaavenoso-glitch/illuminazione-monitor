from app.collectors.anac_ocds import ANACOCDSCollector
from app.collectors.base import BaseCollector, CollectorError, CollectorResult
from app.collectors.consip_opendata import ConsipOpenDataCollector
from app.collectors.smart_llm import SmartLLMCollector
from app.collectors.ted_api import TEDCollector

# Most platform_types route to the generic LLM-based collector.
# The collector reads PLATFORM_SEARCH_URLS internally to know where to fetch.
_LLM_PLATFORM_TYPES = [
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
    "empulia",
    "scr_piemonte",
    "sisgap",
    "stella_lazio",
    "contracta",
    "bandi_altoadige",
    "molise",
    "giada",
    "eappalti_fvg",
    "place_vda",
    "generic_html",
]

COLLECTOR_REGISTRY: dict[str, type[BaseCollector]] = {
    pt: SmartLLMCollector for pt in _LLM_PLATFORM_TYPES
}
# TED, Consip Open Data and ANAC (OCDS bulk) all expose real JSON feeds —
# bypass the LLM entirely for cost/reliability on these. ANAC previously
# routed through SmartLLMCollector, which just reads whatever a generic
# Superset dashboard page happens to render client-side, with no real query
# or filter at all — see anac_ocds.py's module docstring for why.
COLLECTOR_REGISTRY["ted"] = TEDCollector
COLLECTOR_REGISTRY["consip_opendata"] = ConsipOpenDataCollector
COLLECTOR_REGISTRY["anac"] = ANACOCDSCollector

__all__ = [
    "ANACOCDSCollector",
    "BaseCollector",
    "COLLECTOR_REGISTRY",
    "CollectorError",
    "CollectorResult",
    "ConsipOpenDataCollector",
    "SmartLLMCollector",
    "TEDCollector",
]
