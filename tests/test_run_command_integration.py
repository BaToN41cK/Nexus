"""Integration-level tests for the :mod:`nexus.commands.run` module.

These tests exercise higher-level functions including rendering, main command
execution via mocked agent, and the full run_command flow with mocked dependencies.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from nexus.commands.run import (
    _render_response,
    _response_title,
    _sources_title,
    CACHE_CLEAR_GREEN,
)


class TestRenderResponse(unittest.TestCase):
    def test_render_response_returns_panel(self):
        from rich.panel import Panel
        result = _render_response("Hello **world**")
        self.assertIsInstance(result, Panel)
        # The panel should have the translated response title
        self.assertIsNotNone(result.title)

    def test_render_response_empty(self):
        from rich.panel import Panel
        result = _render_response("")
        self.assertIsInstance(result, Panel)

    def test_render_response_code(self):
        from rich.panel import Panel
        result = _render_response("```python\nx = 1\n```")
        self.assertIsInstance(result, Panel)

    def test_cache_clear_color_is_hex(self):
        self.assertIsInstance(CACHE_CLEAR_GREEN, str)
        self.assertTrue(CACHE_CLEAR_GREEN.startswith("#"))

    def test_response_title_is_string(self):
        title = _response_title()
        self.assertIsInstance(title, str)

    def test_sources_title_is_string(self):
        title = _sources_title()
        self.assertIsInstance(title, str)


class TestRunCommandFlow(unittest.TestCase):
    """Test the run_command function with mocked dependencies."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        # Patch NEXUS_DIR and other paths
        self.patchers = [
            patch("nexus.commands.run.NEXUS_DIR", self.tmp_dir),
            patch("nexus.commands.run.CACHE_DIR", os.path.join(self.tmp_dir, "cache")),
            patch("nexus.commands.run.HISTORY_DIR", os.path.join(self.tmp_dir, "history")),
            patch("nexus.commands.run.SEARCH_CACHE_DIR", os.path.join(self.tmp_dir, "search_cache")),
        ]
        for p in self.patchers:
            p.start()
        os.makedirs(os.path.join(self.tmp_dir, "cache"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp_dir, "history"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp_dir, "search_cache"), exist_ok=True)

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("nexus.commands.run.console")
    @patch("nexus.commands.run.load_config_validated")
    def test_run_command_no_api_key_shows_error(self, mock_load_config, mock_console):
        """When no API key is found, an error should be shown."""
        mock_cfg = MagicMock()
        mock_cfg.provider = "groq"
        mock_cfg.groq_model = "llama"
        mock_cfg.base_url = ""
        mock_cfg.max_content_length = 50000
        mock_cfg.summarize_threshold = 40000
        mock_cfg.cache_ttl = 3600
        mock_cfg.max_cache_size_mb = 50
        mock_cfg.timeout = 30
        mock_cfg.max_tokens = 4096
        mock_cfg.temperature = 0.7
        mock_cfg.system_prompt = ""
        mock_cfg.conversation_history_size = 5
        mock_cfg.to_dict.return_value = {"provider": "groq"}
        mock_load_config.return_value = mock_cfg

        args = MagicMock()
        args.prompt = "test prompt"
        args.verbose = False
        args.no_cache = False
        args.config = None
        args.search = None
        args.no_search = False

        with patch("nexus.commands.run._load_env", return_value=None):
            with patch("nexus.commands.run._resolve_api_key", return_value=None):
                from nexus.commands.run import run_command
                run_command(args)

        # Should print an error about missing API key
        mock_console.print.assert_called()
        error_texts = [str(c) for c in mock_console.print.call_args_list]
        has_error = any("API ключ не найден" in str(c) for c in error_texts)
        self.assertTrue(has_error)

    @patch("nexus.commands.run.console")
    @patch("nexus.commands.run.load_config_validated")
    def test_run_command_ollama_no_key_needed(self, mock_load_config, mock_console):
        """Ollama provider does not require an API key."""
        mock_cfg = MagicMock()
        mock_cfg.provider = "ollama"
        mock_cfg.groq_model = "llama3.2"
        mock_cfg.base_url = ""
        mock_cfg.max_content_length = 50000
        mock_cfg.summarize_threshold = 40000
        mock_cfg.cache_ttl = 3600
        mock_cfg.max_cache_size_mb = 50
        mock_cfg.timeout = 30
        mock_cfg.max_tokens = 4096
        mock_cfg.temperature = 0.7
        mock_cfg.system_prompt = ""
        mock_cfg.conversation_history_size = 5
        mock_cfg.to_dict.return_value = {"provider": "ollama"}
        mock_load_config.return_value = mock_cfg

        args = MagicMock()
        args.prompt = "test"
        args.verbose = False
        args.no_cache = False
        args.config = None
        args.search = None
        args.no_search = False

        with patch("nexus.commands.run._load_env", return_value=""):
            from nexus.commands.run import run_command
            # Should not crash - ollama doesn't need a key
            # The full flow will try to create an agent and fail differently
            # but it should not print the API key error
            run_command(args)
            error_texts = [str(c) for c in mock_console.print.call_args_list]
            has_api_key_error = any("API ключ не найден" in str(c) for c in error_texts)
            self.assertFalse(has_api_key_error)

    @patch("nexus.commands.run.console")
    @patch("nexus.commands.run._load_env")
    @patch("nexus.commands.run.load_config_validated")
    def test_run_command_config_error(self, mock_load_config, mock_load_env, mock_console):
        """When config validation fails, it should show an error."""
        from nexus.core.config import ConfigError
        mock_load_config.side_effect = ConfigError("invalid config")

        args = MagicMock()
        args.prompt = "test"
        args.verbose = False
        args.no_cache = False
        args.config = None
        args.search = None
        args.no_search = False

        from nexus.commands.run import run_command
        run_command(args)

        # Should print config error
        mock_console.print.assert_called()
        error_texts = [str(c) for c in mock_console.print.call_args_list]
        has_error = any("Ошибка конфигурации" in str(c) for c in error_texts)
        self.assertTrue(has_error)


if __name__ == "__main__":
    unittest.main()