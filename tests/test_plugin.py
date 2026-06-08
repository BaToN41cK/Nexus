"""Tests for the :mod:`nexus.core.plugin` module."""

import tempfile
import os
import unittest
from unittest.mock import MagicMock, patch

from nexus.core.plugin import (
    register_hook,
    run_hook,
    register_cli_command,
    list_custom_commands,
    discover_plugins,
    get_loaded_plugins,
    register_provider,
    register_search_backend,
)


class TestHooks(unittest.TestCase):
    def test_register_and_run_hook(self):
        results = []

        def my_hook(arg):
            results.append(arg)

        register_hook("pre_command", my_hook)
        run_hook("pre_command", "hello")
        self.assertIn("hello", results)

    def test_hook_exception_does_not_crash(self):
        def broken_hook():
            raise RuntimeError("hook failed")

        register_hook("on_startup", broken_hook)
        run_hook("on_startup")  # Should not raise

    def test_unknown_hook_name(self):
        with self.assertRaises(ValueError):
            register_hook("nonexistent_hook", lambda: None)


class TestCLICommands(unittest.TestCase):
    def test_register_cli_command(self):
        register_cli_command("mycmd", "My custom command", lambda args: None)
        commands = list_custom_commands()
        self.assertIn("mycmd", commands)
        self.assertEqual(commands["mycmd"]["help"], "My custom command")

    def test_list_custom_commands_empty_initial(self):
        # Should return a dict (may have items from other tests)
        commands = list_custom_commands()
        self.assertIsInstance(commands, dict)


class TestDiscoverPlugins(unittest.TestCase):
    def test_discover_nonexistent_dir(self):
        result = discover_plugins("/nonexistent/plugin/dir")
        self.assertEqual(result, [])

    def test_discover_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = discover_plugins(tmpdir)
        self.assertEqual(result, [])

    def test_discover_broken_plugin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = os.path.join(tmpdir, "broken_plugin.py")
            with open(plugin_path, "w") as f:
                f.write("this is not valid python $%^")
            result = discover_plugins(tmpdir)
        # Should not crash, just skip the broken file
        self.assertEqual(result, [])

    def test_discover_valid_plugin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = os.path.join(tmpdir, "good_plugin.py")
            with open(plugin_path, "w") as f:
                f.write("def setup():\n    pass\n")
            result = discover_plugins(tmpdir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "good_plugin")

    def test_get_loaded_plugins(self):
        plugins = get_loaded_plugins()
        self.assertIsInstance(plugins, dict)


class TestRegisterProvider(unittest.TestCase):
    def test_register_provider_via_plugin(self):
        from nexus.core.providers import BaseProvider
        from nexus.core.provider_factory import ProviderFactory

        class PluginProvider(BaseProvider):
            name = "plugin_test_provider"
            def _init_client(self):
                self._client = MagicMock()
            def generate(self, messages, stream=False):
                return {"text": "plugin", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        register_provider(PluginProvider)
        providers = ProviderFactory.list_providers()
        self.assertIn("plugin_test_provider", providers)
        ProviderFactory.unregister("plugin_test_provider")


class TestRegisterSearchBackend(unittest.TestCase):
    def test_register_search_backend_via_plugin(self):
        from nexus.core.web_search import SearchBackend

        class PluginBackend(SearchBackend):
            name = "plugin_backend"
            def search(self, query, max_results):
                return []

        register_search_backend(PluginBackend)
        from nexus.core.web_search import _custom_backends
        self.assertIn("plugin_backend", _custom_backends)

    def test_register_invalid_backend(self):
        with self.assertRaises(TypeError):
            register_search_backend(str)  # str is not a SearchBackend subclass


if __name__ == "__main__":
    unittest.main()