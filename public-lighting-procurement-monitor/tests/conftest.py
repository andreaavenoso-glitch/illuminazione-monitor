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

os.environ.setdefault("APP_ENV", "test")
