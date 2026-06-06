"""
Centralised filesystem paths used by Nexus.

Having a single source of truth avoids the previous duplication between
``cli.py`` and ``commands/run.py`` (where the same ``NEXUS_DIR`` /
``CACHE_DIR`` constants were defined twice).
"""

from __future__ import annotations

import os

NEXUS_DIR: str = os.path.join(os.path.expanduser("~"), ".nexus")
CACHE_DIR: str = os.path.join(NEXUS_DIR, "cache")
HISTORY_DIR: str = os.path.join(NEXUS_DIR, "history")
HISTORY_LOG: str = os.path.join(HISTORY_DIR, "history.log")
SEARCH_CACHE_DIR: str = os.path.join(NEXUS_DIR, "search_cache")
DEFAULT_CONFIG_PATH: str = os.path.join(NEXUS_DIR, "config.yaml")

# In-package directories
LOCALE_DIR: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locale"
)


def ensure_dirs() -> None:
    """Create the user-level Nexus directories if they don't exist."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(SEARCH_CACHE_DIR, exist_ok=True)
