"""Tests for the history module."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from nexus.core.history import (
    _load_conversation,
    add_exchange,
    build_context,
    clear,
    CONVERSATION_FILE,
)


class TestHistory(unittest.TestCase):
    """Test conversation history management."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.patcher = patch("nexus.core.history.NEXUS_DIR", self.temp_dir)
        self.patcher.start()
        # Re-set the CONVERSATION_FILE path
        from nexus.core import history
        history.CONVERSATION_FILE = os.path.join(self.temp_dir, "conversation.json")

    def tearDown(self):
        self.patcher.stop()
        for f in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, f))
        os.rmdir(self.temp_dir)

    def _get_conversation_file(self):
        return os.path.join(self.temp_dir, "conversation.json")

    def test_empty_conversation(self):
        """Loading an empty conversation returns empty list."""
        exchanges = _load_conversation()
        self.assertEqual(exchanges, [])

    def test_add_and_load_single(self):
        """Adding an exchange and loading it back."""
        add_exchange("Hello", "Hi there!")
        exchanges = _load_conversation()
        self.assertEqual(len(exchanges), 1)
        self.assertEqual(exchanges[0]["prompt"], "Hello")
        self.assertEqual(exchanges[0]["response"], "Hi there!")

    def test_max_exchanges(self):
        """Only last N exchanges are kept."""
        for i in range(10):
            add_exchange(f"Prompt {i}", f"Response {i}", max_exchanges=5)
        exchanges = _load_conversation(max_exchanges=5)
        self.assertEqual(len(exchanges), 5)
        # The last 5 should be 5..9
        self.assertEqual(exchanges[0]["prompt"], "Prompt 5")
        self.assertEqual(exchanges[-1]["prompt"], "Prompt 9")

    def test_build_context_empty(self):
        """build_context returns empty string when no history."""
        context, exchanges = build_context()
        self.assertEqual(context, "")
        self.assertEqual(exchanges, [])

    def test_build_context_with_history(self):
        """build_context includes history in output."""
        add_exchange("Q1", "A1")
        add_exchange("Q2", "A2")
        context, exchanges = build_context(system_prompt="You are helpful")
        self.assertIn("Q1", context)
        self.assertIn("A1", context)
        self.assertIn("Q2", context)
        self.assertIn("A2", context)
        self.assertIn("You are helpful", context)
        self.assertEqual(len(exchanges), 2)

    def test_clear(self):
        """Clearing removes the file."""
        add_exchange("Hello", "Hi")
        self.assertTrue(os.path.isfile(self._get_conversation_file()))
        clear()
        self.assertFalse(os.path.isfile(self._get_conversation_file()))

    def test_corrupted_json(self):
        """Corrupted JSON returns empty list."""
        os.makedirs(self.temp_dir, exist_ok=True)
        with open(self._get_conversation_file(), "w") as f:
            f.write("this is not json")
        exchanges = _load_conversation()
        self.assertEqual(exchanges, [])

    def test_custom_max_exchanges(self):
        """Custom max_exchanges works for add_exchange and build_context."""
        for i in range(3):
            add_exchange(f"P{i}", f"R{i}", max_exchanges=3)
        context, exchanges = build_context(max_exchanges=3)
        self.assertEqual(len(exchanges), 3)
        # Only 3 exchanges
        self.assertEqual([e["prompt"] for e in exchanges], ["P0", "P1", "P2"])


if __name__ == "__main__":
    unittest.main()