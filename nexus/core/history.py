"""
Conversation History Module

This module is a thin compatibility shim around the pluggable
:class:`nexus.core.memory.MemoryStore` interface.  It exposes the same
function names the project has used since v1, so existing call sites
keep working.  New code should use :mod:`nexus.core.memory` directly.

The default backend is :class:`JsonMemoryStore` (the file-based store).
The backend can be swapped at runtime via :func:`set_default_store` — for
example, to migrate to SQLite without touching the rest of the codebase::

    from nexus.core.history import set_default_store
    from nexus.core.memory import SqliteMemoryStore
    set_default_store(SqliteMemoryStore(path="~/.nexus/memory.db"))
"""

import logging
import os
import threading
from typing import List, Optional, Tuple

from nexus.core.memory import Exchange, JsonMemoryStore, MemoryStore

logger = logging.getLogger(__name__)

NEXUS_DIR = os.path.join(os.path.expanduser("~"), ".nexus")
CONVERSATION_FILE = os.path.join(NEXUS_DIR, "conversation.json")
DEFAULT_MAX_EXCHANGES = 5

# A default store may be injected via :func:`set_default_store`.  When no
# store has been injected we build a fresh :class:`JsonMemoryStore` on
# every call — this lets tests patch ``CONVERSATION_FILE`` and see the
# change without a process restart.
_injected_store: Optional[MemoryStore] = None
_inject_lock = threading.Lock()


def _resolve_default_store() -> MemoryStore:
    """Return the active store: the injected one, or a fresh JSON one."""
    with _inject_lock:
        if _injected_store is not None:
            return _injected_store
    return JsonMemoryStore(path=CONVERSATION_FILE, max_exchanges=DEFAULT_MAX_EXCHANGES)


def set_default_store(store: MemoryStore) -> None:
    """Replace the default store (used by the module-level helpers)."""
    global _injected_store
    with _inject_lock:
        _injected_store = store


def reset_default_store() -> None:
    """Forget the injected store.  Next call rebuilds a JSON one."""
    global _injected_store
    with _inject_lock:
        _injected_store = None


# ---------------------------------------------------------------------------
# Public API (legacy)
# ---------------------------------------------------------------------------


def _load_conversation(max_exchanges: int = DEFAULT_MAX_EXCHANGES) -> List[dict]:
    """Load the last *max_exchanges* as plain dicts (for backward compat)."""
    return [e.to_dict() for e in _resolve_default_store()._load(max_exchanges)]  # type: ignore[attr-defined]


def _save_conversation(exchanges: List[dict], max_exchanges: int = DEFAULT_MAX_EXCHANGES) -> None:
    """Persist a list of dicts (legacy helper)."""
    store = _resolve_default_store()
    objs = [Exchange.from_dict(x) for x in exchanges]
    # Use the store's internal _save (kept public-ish for legacy reasons).
    if hasattr(store, "_save"):
        store._save(objs, max_exchanges)  # type: ignore[attr-defined]
    else:  # pragma: no cover - any custom store gets rebuilt by clear+add
        store.clear()
        for ex in objs[-max_exchanges:]:
            store.add_exchange(ex.prompt, ex.response, max_exchanges)


def add_exchange(prompt: str, response: str, max_exchanges: int = DEFAULT_MAX_EXCHANGES) -> None:
    """Add a new exchange to the conversation history."""
    _resolve_default_store().add_exchange(prompt, response, max_exchanges)


def build_context(
    system_prompt: Optional[str] = None,
    max_exchanges: int = DEFAULT_MAX_EXCHANGES,
) -> Tuple[str, List[dict]]:
    """Return a context string and the exchanges used to build it."""
    text, exchanges = _resolve_default_store().build_context(system_prompt, max_exchanges)
    return text, [e.to_dict() for e in exchanges]


def clear() -> None:
    """Clear the conversation history."""
    _resolve_default_store().clear()
