"""Local API-key holder.

Loads keys from (in order):
1. Environment variables.
2. A local JSON file at $DOCING_KEYS_FILE or `./.api_keys.json`.

The keys file is git-ignored and never logged. It is the ONLY supported
place to put secrets when running the pipeline locally.

Expected JSON shape:
    {
        "anthropic": "sk-ant-...",
        "openai": "sk-...",
        "vlm_endpoint": "http://localhost:11434/v1"   # optional override
    }
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(".api_keys.json")


@lru_cache(maxsize=1)
def _load_file() -> dict:
    path = Path(os.getenv("DOCING_KEYS_FILE", _DEFAULT_PATH))
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read keys file %s: %s", path, exc)
        return {}


def get(name: str, default: str | None = None) -> str | None:
    """Return a credential by logical name.

    Looks up upper-case env var first (e.g. ANTHROPIC_API_KEY for "anthropic"),
    then the JSON file under the lower-case key.
    """
    env_name = name.upper() if name.endswith("_KEY") or "_" in name else f"{name.upper()}_API_KEY"
    value = os.getenv(env_name)
    if value:
        return value
    return _load_file().get(name.lower(), default)


def require(name: str) -> str:
    value = get(name)
    if not value:
        raise RuntimeError(
            f"Missing credential '{name}'. Set {name.upper()}_API_KEY env var "
            f"or add it to .api_keys.json."
        )
    return value
