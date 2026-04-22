from app.api.routes import admin, entities, health, records, sources, watchlist
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

configure_logging()
log = get_logger("app")

settings = get_settings()

app = FastAPI(
    title="Public Lighting Procurement Monitor",
    version="0.1.0",
    description="Monitoring service for Italian public lighting procurement.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sources.router, prefix="/sources", tags=["sources"])
app.include_router(entities.router, prefix="/entities", tags=["entities"])
app.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
app.include_router(records.router, prefix="/records", tags=["records"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.on_event("startup")
async def startup() -> None:
    log.info("api.started", env=settings.app_env)
