"""Vercel Python entrypoint for the Charvi FastAPI control plane."""
from pathlib import Path
import sys

# The monorepo keeps the API package under apps/api while pyproject.toml stays at the root.
API_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(API_PACKAGE_ROOT))

from charvi_api.main import app  # noqa: E402
