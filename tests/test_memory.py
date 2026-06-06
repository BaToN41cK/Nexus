"""Tests for the pluggable memory stores.

Both backends (JSON and SQLite) share the same :class:`MemoryStore`
contract, so a parametrised test class runs the same scenarios against
both.
"""

import os
import tempfile
import unittest

from nexus.core.memory import (
    Exchange,
    JsonMemoryStore,
    MemoryStore,
    SqliteMemoryStore,
    create_memory_store,
)


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


def _make_store(backend: str, **kwargs) -> MemoryStore:
    """Build a fresh store in a temp directory."""
    tmp = tempfile.mkdtemp()
    if backend == "json":
        return JsonMemoryStore(path=os.path.join(tmp, "memory.json"), **kwargs)
    if backend == "sqlite":
        return SqliteMemoryStore(path=os.path.join(tmp, "memory.db"), **kwargs)
    raise ValueError(backend)


class _BackendContract(unittest.TestCase):
    """Common contract for all backends.  Subclasses set ``self.backend``."""

    backend: str = ""

    def _store(self, **kwargs) -> MemoryStore:
        return _make_store(self.backend, **kwargs)

    def setUp(self):
        self.store = self._store(max_exchanges=5)
        self.assertIsInstance(self.store, MemoryStore)


# Concrete test classes — one per backend, so unittest reports them
# separately and a failure in one doesn't hide the other.
class JsonBackendContract(_BackendContract):
    backend = "json"


class SqliteBackendContract(_BackendContract):
    backend = "sqlite"


def _make_contract_tests():
    """Generate test methods on a class for each scenario in the contract."""

    def test_empty_initially(self):
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(self.store.build_context()[0], "")

    def test_add_and_read(self):
        self.store.add_exchange("Q1", "A1")
        self.store.add_exchange("Q2", "A2")
        self.assertEqual(self.store.count(), 2)
        text, exchanges = self.store.build_context()
        self.assertIn("Q1", text)
        self.assertIn("A2", text)
        self.assertEqual([e.prompt for e in exchanges], ["Q1", "Q2"])

    def test_max_exchanges_trims(self):
        for i in range(10):
            self.store.add_exchange(f"P{i}", f"R{i}")
        self.assertEqual(self.store.count(), 5)
        text, _ = self.store.build_context()
        # The first 5 should be dropped.
        self.assertNotIn("P0", text)
        self.assertNotIn("P4", text)
        self.assertIn("P5", text)
        self.assertIn("P9", text)

    def test_clear(self):
        self.store.add_exchange("x", "y")
        self.assertEqual(self.store.count(), 1)
        self.store.clear()
        self.assertEqual(self.store.count(), 0)

    def test_search_finds_matches(self):
        self.store.add_exchange("Tell me about Python", "Python is a language.")
        self.store.add_exchange("About cats", "Cats are furry.")
        results = self.store.search("Python")
        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(
            any("Python" in e.prompt or "Python" in e.response for e in results)
        )

    def test_search_empty_query_returns_nothing(self):
        self.store.add_exchange("Q", "A")
        self.assertEqual(self.store.search(""), [])

    def test_build_context_includes_system_prompt(self):
        self.store.add_exchange("Q", "A")
        text, _ = self.store.build_context(system_prompt="Be brief.")
        self.assertIn("Be brief.", text)

    def test_persistence(self):
        self.store.add_exchange("Q", "A")
        # Re-open the same file and confirm the data survived.
        store2 = _make_store(self.backend, max_exchanges=5)
        # Use the same file the first store wrote to.
        store2.path = self.store.path
        self.assertEqual(store2.count(), 1)
        _, exchanges = store2.build_context()
        self.assertEqual(exchanges[0].prompt, "Q")

    methods = [
        test_empty_initially,
        test_add_and_read,
        test_max_exchanges_trims,
        test_clear,
        test_search_finds_matches,
        test_search_empty_query_returns_nothing,
        test_build_context_includes_system_prompt,
        test_persistence,
    ]
    return methods


for _fn in _make_contract_tests():
    setattr(JsonBackendContract, _fn.__name__, _fn)
    setattr(SqliteBackendContract, _fn.__name__, _fn)


# ---------------------------------------------------------------------------
# Backend-specific tests
# ---------------------------------------------------------------------------


class TestJsonBackend(unittest.TestCase):
    def test_corrupted_file_returns_empty(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "bad.json")
        with open(path, "w") as fh:
            fh.write("not json")
        store = JsonMemoryStore(path=path, max_exchanges=5)
        self.assertEqual(store.count(), 0)

    def test_missing_file_returns_empty(self):
        store = JsonMemoryStore(path=os.path.join(tempfile.mkdtemp(), "x.json"))
        self.assertEqual(store.count(), 0)

    def test_search_uses_substring(self):
        store = _make_store("json", max_exchanges=5)
        store.add_exchange("I love Python", "Me too")
        store.add_exchange("I love Rust", "Cool")
        results = store.search("python")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].prompt, "I love Python")


class TestSqliteBackend(unittest.TestCase):
    def test_fts5_is_used_when_available(self):
        store = _make_store("sqlite", max_exchanges=5)
        # The probe may or may not be supported depending on the build; we
        # only assert the attribute exists, not its value.
        self.assertTrue(hasattr(store, "_fts5"))

    def test_in_memory_like_path(self):
        # :memory: is a valid sqlite path — exercise the connect path.
        store = SqliteMemoryStore(path=":memory:", max_exchanges=5)
        store.add_exchange("Q", "A")
        self.assertEqual(store.count(), 1)

    def test_trim_keeps_newest(self):
        store = _make_store("sqlite", max_exchanges=3)
        for i in range(7):
            store.add_exchange(f"P{i}", f"R{i}")
        self.assertEqual(store.count(), 3)
        _, exchanges = store.build_context()
        self.assertEqual([e.prompt for e in exchanges], ["P4", "P5", "P6"])


# ---------------------------------------------------------------------------
# Factory + Exchange dataclass
# ---------------------------------------------------------------------------


class TestFactory(unittest.TestCase):
    def test_factory_json(self):
        store = create_memory_store("json", path=os.path.join(tempfile.mkdtemp(), "m.json"))
        self.assertIsInstance(store, JsonMemoryStore)

    def test_factory_sqlite(self):
        store = create_memory_store("sqlite", path=os.path.join(tempfile.mkdtemp(), "m.db"))
        self.assertIsInstance(store, SqliteMemoryStore)

    def test_factory_default_is_json(self):
        store = create_memory_store(path=os.path.join(tempfile.mkdtemp(), "m.json"))
        self.assertIsInstance(store, JsonMemoryStore)

    def test_factory_unknown_raises(self):
        with self.assertRaises(ValueError):
            create_memory_store("redis")


class TestExchange(unittest.TestCase):
    def test_roundtrip(self):
        ex = Exchange(prompt="Q", response="A")
        d = ex.to_dict()
        self.assertEqual(d, {"prompt": "Q", "response": "A"})
        ex2 = Exchange.from_dict(d)
        self.assertEqual(ex, ex2)

    def test_from_dict_handles_missing(self):
        ex = Exchange.from_dict({})
        self.assertEqual(ex.prompt, "")
        self.assertEqual(ex.response, "")


if __name__ == "__main__":
    unittest.main()
