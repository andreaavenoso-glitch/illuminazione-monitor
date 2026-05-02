from app.api.routes import (
    admin,
    alerts,
    auth,
    dashboard,
    documents,
    entities,
    health,
    records,
    reports,
    sources,
    watchlist,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import limiter
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(health.router)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(sources.router, prefix="/sources", tags=["sources"])
app.include_router(entities.router, prefix="/entities", tags=["entities"])
app.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
app.include_router(records.router, prefix="/records", tags=["records"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.on_event("startup")
async def startup() -> None:
    log.info("api.started", env=settings.app_env)
