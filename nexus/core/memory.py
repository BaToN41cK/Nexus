"""
Pluggable memory backends for Nexus.

Defines a common :class:`MemoryStore` interface and two implementations:

  - :class:`JsonMemoryStore`  — the legacy file-backed store (JSON, plain text).
  - :class:`SqliteMemoryStore` — a SQLite store with FTS5 full-text search.

Use :func:`create_memory_store` to build one by name::

    store = create_memory_store("sqlite", path=Path("~/.nexus/memory.db").expanduser())
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


@dataclass
class Exchange:
    """A single conversation exchange."""

    prompt: str
    response: str

    def to_dict(self) -> Dict[str, str]:
        return {"prompt": self.prompt, "response": self.response}

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Exchange":
        return cls(prompt=str(data.get("prompt", "")), response=str(data.get("response", "")))


class MemoryStore(ABC):
    """Abstract memory store.  All implementations are thread-safe."""

    @abstractmethod
    def add_exchange(self, prompt: str, response: str, max_exchanges: int = 5) -> None:
        """Append a new exchange, trimming the store to ``max_exchanges`` entries."""

    @abstractmethod
    def build_context(
        self,
        system_prompt: Optional[str] = None,
        max_exchanges: int = 5,
    ) -> Tuple[str, List[Exchange]]:
        """Return a context string and the exchanges used to build it."""

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> List[Exchange]:
        """Full-text search over past exchanges.  Returns matches sorted by relevance."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all stored exchanges."""

    @abstractmethod
    def count(self) -> int:
        """Return the number of exchanges currently stored."""


# ---------------------------------------------------------------------------
# JSON file backend
# ---------------------------------------------------------------------------


class JsonMemoryStore(MemoryStore):
    """
    Simple JSON-file backed memory store.  Matches the behaviour of the
    pre-pluggable ``nexus.core.history`` module.
    """

    def __init__(self, path: str, max_exchanges: int = 5):
        self.path = path
        self.default_max_exchanges = max_exchanges
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # ---- I/O helpers ----

    def _load(self, max_exchanges: int) -> List[Exchange]:
        if not os.path.isfile(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            logger.debug("Memory: failed to load %s: %s", self.path, e)
            return []
        if not isinstance(data, list):
            return []
        return [Exchange.from_dict(item) for item in data[-max_exchanges:]]

    def _save(self, exchanges: List[Exchange], max_exchanges: int) -> None:
        trimmed = exchanges[-max_exchanges:]
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump([e.to_dict() for e in trimmed], fh, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.debug("Memory: failed to save %s: %s", self.path, e)

    # ---- public API ----

    def add_exchange(self, prompt: str, response: str, max_exchanges: Optional[int] = None) -> None:
        cap = max_exchanges or self.default_max_exchanges
        with self._lock:
            exchanges = self._load(cap)
            exchanges.append(Exchange(prompt=prompt, response=response))
            self._save(exchanges, cap)

    def build_context(
        self,
        system_prompt: Optional[str] = None,
        max_exchanges: Optional[int] = None,
    ) -> Tuple[str, List[Exchange]]:
        cap = max_exchanges or self.default_max_exchanges
        with self._lock:
            exchanges = self._load(cap)
        if not exchanges:
            return "", []
        parts: List[str] = []
        if system_prompt:
            parts.append(f"System: {system_prompt}")
        parts.append(f"Below is the conversation history (last {len(exchanges)} exchanges):")
        for i, ex in enumerate(exchanges, 1):
            parts.append(f"\n--- Exchange {i} ---")
            parts.append(f"User: {ex.prompt}")
            parts.append(f"Assistant: {ex.response}")
        parts.append("\n--- End of history ---")
        parts.append("Now respond to the new user message below, using the history for context if relevant.")
        return "\n".join(parts), exchanges

    def search(self, query: str, limit: int = 5) -> List[Exchange]:
        if not query or not os.path.isfile(self.path):
            return []
        with self._lock:
            exchanges = self._load(self.default_max_exchanges)
        q = query.lower()
        scored: List[Tuple[int, Exchange]] = []
        for i, ex in enumerate(exchanges):
            score = 0
            if q in ex.prompt.lower():
                score += 2
            if q in ex.response.lower():
                score += 1
            if score:
                # Newer items get a tiny tie-breaker boost.
                scored.append((score * 1000 + i, ex))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored[:limit]]

    def clear(self) -> None:
        with self._lock:
            try:
                if os.path.isfile(self.path):
                    os.remove(self.path)
            except OSError as e:
                logger.debug("Memory: failed to clear %s: %s", self.path, e)

    def count(self) -> int:
        with self._lock:
            return len(self._load(self.default_max_exchanges))


# ---------------------------------------------------------------------------
# SQLite (FTS5) backend
# ---------------------------------------------------------------------------


_FTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS exchanges (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt    TEXT    NOT NULL,
    response  TEXT    NOT NULL,
    created   REAL    NOT NULL DEFAULT (julianday('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS exchanges_fts USING fts5(
    prompt, response, content='exchanges', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS exchanges_ai AFTER INSERT ON exchanges BEGIN
    INSERT INTO exchanges_fts(rowid, prompt, response) VALUES (new.id, new.prompt, new.response);
END;

CREATE TRIGGER IF NOT EXISTS exchanges_ad AFTER DELETE ON exchanges BEGIN
    INSERT INTO exchanges_fts(exchanges_fts, rowid, prompt, response) VALUES('delete', old.id, old.prompt, old.response);
END;

CREATE TRIGGER IF NOT EXISTS exchanges_au AFTER UPDATE ON exchanges BEGIN
    INSERT INTO exchanges_fts(exchanges_fts, rowid, prompt, response) VALUES('delete', old.id, old.prompt, old.response);
    INSERT INTO exchanges_fts(rowid, prompt, response) VALUES (new.id, new.prompt, new.response);
END;
"""


class SqliteMemoryStore(MemoryStore):
    """
    SQLite-backed memory store with FTS5 full-text search.

    Uses Python's standard library ``sqlite3`` module — no external deps.

    Falls back to a plain LIKE search if FTS5 is not compiled in (older
    Python distributions).
    """

    def __init__(self, path: str, max_exchanges: int = 5):
        self.path = path
        self.default_max_exchanges = max_exchanges
        self._lock = threading.Lock()
        # Persistent connection for :memory: (each sqlite3.connect to
        # ":memory:" yields a brand-new empty database otherwise).
        self._persistent_conn: Optional[sqlite3.Connection] = None
        # Make sure the parent directory exists (no-op for :memory:).
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if path == ":memory:":
            self._persistent_conn = self._connect_raw()
            self._persistent_conn.executescript(_FTS_SCHEMA)
            self._persistent_conn.commit()
        # Decide once whether FTS5 is available.
        with self._connect() as conn:
            self._fts5 = self._probe_fts5(conn)

    def _connect_raw(self) -> sqlite3.Connection:
        """Open a fresh sqlite3 connection (no schema setup)."""
        conn = sqlite3.connect(self.path, timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = self._connect_raw()
        # Make sure the schema exists. Safe to run repeatedly (IF NOT EXISTS).
        conn.executescript(_FTS_SCHEMA)
        conn.commit()
        return conn

    @staticmethod
    def _probe_fts5(conn: sqlite3.Connection) -> bool:
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
            conn.execute("DROP TABLE _fts5_probe")
            return True
        except sqlite3.OperationalError:
            return False

    def _trim(self, conn: sqlite3.Connection, max_exchanges: int) -> None:
        """Keep only the last ``max_exchanges`` rows."""
        cur = conn.execute("SELECT COUNT(*) AS c FROM exchanges")
        total = cur.fetchone()["c"]
        if total <= max_exchanges:
            return
        excess = total - max_exchanges
        conn.execute(
            "DELETE FROM exchanges WHERE id IN (SELECT id FROM exchanges ORDER BY id ASC LIMIT ?)",
            (excess,),
        )

    # ---- public API ----

    def add_exchange(self, prompt: str, response: str, max_exchanges: Optional[int] = None) -> None:
        cap = max_exchanges or self.default_max_exchanges
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO exchanges (prompt, response) VALUES (?, ?)",
                    (prompt, response),
                )
                self._trim(conn, cap)
                conn.commit()

    def build_context(
        self,
        system_prompt: Optional[str] = None,
        max_exchanges: Optional[int] = None,
    ) -> Tuple[str, List[Exchange]]:
        cap = max_exchanges or self.default_max_exchanges
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT prompt, response FROM exchanges ORDER BY id DESC LIMIT ?",
                    (cap,),
                ).fetchall()
        exchanges = [Exchange(prompt=r["prompt"], response=r["response"]) for r in rows]
        exchanges.reverse()  # chronological
        if not exchanges:
            return "", []
        parts: List[str] = []
        if system_prompt:
            parts.append(f"System: {system_prompt}")
        parts.append(f"Below is the conversation history (last {len(exchanges)} exchanges):")
        for i, ex in enumerate(exchanges, 1):
            parts.append(f"\n--- Exchange {i} ---")
            parts.append(f"User: {ex.prompt}")
            parts.append(f"Assistant: {ex.response}")
        parts.append("\n--- End of history ---")
        parts.append("Now respond to the new user message below, using the history for context if relevant.")
        return "\n".join(parts), exchanges

    def search(self, query: str, limit: int = 5) -> List[Exchange]:
        if not query:
            return []
        with self._lock, self._connect() as conn:
            if self._fts5:
                rows = conn.execute(
                    """
                    SELECT e.prompt, e.response
                    FROM exchanges_fts f
                    JOIN exchanges e ON e.id = f.rowid
                    WHERE exchanges_fts MATCH ?
                    ORDER BY bm25(exchanges_fts), e.id DESC
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
            else:
                like = f"%{query}%"
                rows = conn.execute(
                    """
                    SELECT prompt, response FROM exchanges
                    WHERE prompt LIKE ? OR response LIKE ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (like, like, limit),
                ).fetchall()
        return [Exchange(prompt=r["prompt"], response=r["response"]) for r in rows]

    def clear(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM exchanges")
            conn.commit()

    def count(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM exchanges").fetchone()
        return int(row["c"])


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_memory_store(backend: str = "json", **kwargs: Any) -> MemoryStore:
    """
    Build a memory store by name.

    Args:
        backend: ``"json"`` or ``"sqlite"``.
        **kwargs: forwarded to the store constructor.  ``path`` is required
            for both; ``max_exchanges`` is optional (default 5).
    """
    backend = (backend or "json").lower()
    if backend == "json":
        return JsonMemoryStore(**kwargs)
    if backend == "sqlite":
        return SqliteMemoryStore(**kwargs)
    raise ValueError(f"Unknown memory backend: {backend!r}. Use 'json' or 'sqlite'.")
