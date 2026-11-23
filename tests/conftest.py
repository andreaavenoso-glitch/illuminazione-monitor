import os
import sys
from pathlib import Path

# Make packages/* and apps/worker importable when running pytest from the
# monorepo root (outside Docker). Inside containers pip install -e already
# handles packages/*, and PYTHONPATH is extended in docker-compose.
ROOT = Path(__file__).resolve().parents[1]
for pkg in ("parsing_rules", "scoring_engine", "sector_dictionaries", "shared_models", "shared_schemas"):
    candidate = ROOT / "packages" / pkg
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

worker_root = ROOT / "apps" / "worker"
if worker_root.exists() and str(worker_root) not in sys.path:
    sys.path.insert(0, str(worker_root))

api_root = ROOT / "apps" / "api"
if api_root.exists() and str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))

os.environ.setdefault("APP_ENV", "test")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_fetch_retry(monkeypatch):
    """The tests count requests one by one: the second attempt of adaptive_fetch is switched off (test_fetch_retry
    switches it on again for itself)."""
    try:
        from app.collectors import adaptive_fetch
    except Exception:  # noqa: BLE001 -- tests that do not need the worker
        return
    monkeypatch.setattr(adaptive_fetch, "RETRY_ENABLED", False)
    monkeypatch.setattr(adaptive_fetch, "HOST_MIN_INTERVAL", 0.0)
    adaptive_fetch._HOST_NEXT.clear()
    adaptive_fetch._HOST_INTERVAL.clear()
    adaptive_fetch._RETRY_AFTER.clear()
    adaptive_fetch._COOLDOWN_UNTIL.clear()
