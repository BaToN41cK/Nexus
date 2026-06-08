"""Tests for the :mod:`nexus.core.interactive_ui` module."""

import unittest

from nexus.core.interactive_ui import (
    COMMAND_DESCRIPTIONS,
    UIConfig,
    build_interactive_completer,
    create_progress,
    create_search_progress,
    format_sources,
    format_token_info,
    load_ui_config,
)


class TestUIConfig(unittest.TestCase):
    def test_default_values(self):
        cfg = UIConfig()
        self.assertEqual(cfg.user_color, "bold cyan")
        self.assertEqual(cfg.assistant_color, "green")
        self.assertEqual(cfg.prompt_prefix, "💬 ")

    def test_custom_values(self):
        cfg = UIConfig(
            user_color="white",
            assistant_color="cyan",
            prompt_prefix=">> ",
        )
        self.assertEqual(cfg.user_color, "white")
        self.assertEqual(cfg.assistant_color, "cyan")
        self.assertEqual(cfg.prompt_prefix, ">> ")


class TestCommandDescriptions(unittest.TestCase):
    def test_basic_commands_present(self):
        for cmd in ("!search on", "!search off", "!help", "exit", "quit"):
            self.assertIn(cmd, COMMAND_DESCRIPTIONS)

    def test_lang_commands_present(self):
        for lang in ("ru", "en", "de", "fr", "es"):
            self.assertIn(f"!lang {lang}", COMMAND_DESCRIPTIONS)

    def test_descriptions_are_non_empty(self):
        for cmd, desc in COMMAND_DESCRIPTIONS.items():
            self.assertIsInstance(desc, str)
            self.assertTrue(len(desc) > 0)


class TestBuildInteractiveCompleter(unittest.TestCase):
    def test_returns_none_without_prompt_toolkit(self):
        # If prompt_toolkit is available, it returns a completer
        # If not, returns None. Either way, no crash.
        result = build_interactive_completer()
        # May be None (no prompt_toolkit) or a WordCompleter
        self.assertTrue(result is None or hasattr(result, "get_completions"))

    def test_with_history_words(self):
        result = build_interactive_completer(history_words=["hello", "world"])
        # Should not crash; either returns None or completer
        self.assertTrue(result is None or hasattr(result, "get_completions"))


class TestCreateProgress(unittest.TestCase):
    def test_create_progress_returns_progress(self):
        from rich.console import Console
        console = Console()
        progress = create_progress(console, description="Working...")
        self.assertIsNotNone(progress)

    def test_create_search_progress(self):
        from rich.console import Console
        console = Console()
        progress = create_search_progress(console, backend="duckduckgo")
        self.assertIsNotNone(progress)


class TestFormatSources(unittest.TestCase):
    def test_format_sources_returns_panel(self):
        from rich.panel import Panel
        panel = format_sources(["https://example.com", "https://test.com"])
        self.assertIsInstance(panel, Panel)

    def test_format_sources_empty(self):
        from rich.panel import Panel
        panel = format_sources([])
        self.assertIsInstance(panel, Panel)


class TestFormatTokenInfo(unittest.TestCase):
    def test_format_token_info(self):
        result = format_token_info(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        self.assertIn("Prompt: 100", result)
        self.assertIn("Completion: 50", result)
        self.assertIn("Total: 150", result)

    def test_format_token_info_with_time(self):
        result = format_token_info(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            elapsed_secs=1.5,
        )
        self.assertIn("Time: 1.5s", result)

    def test_format_token_info_with_thousands_separator(self):
        result = format_token_info(prompt_tokens=1500, completion_tokens=500, total_tokens=2000)
        self.assertIn("1,500", result)
        self.assertIn("2,000", result)


class TestLoadUIConfig(unittest.TestCase):
    def test_default_when_no_config(self):
        cfg = load_ui_config({})
        self.assertEqual(cfg.user_color, "bold cyan")
        self.assertTrue(cfg.show_response_time)

    def test_override_from_config(self):
        cfg = load_ui_config({
            "ui": {
                "user_color": "white",
                "prompt_prefix": ">> ",
                "show_token_usage": True,
            }
        })
        self.assertEqual(cfg.user_color, "white")
        self.assertEqual(cfg.prompt_prefix, ">> ")
        self.assertTrue(cfg.show_token_usage)

    def test_unknown_keys_ignored(self):
        """Unknown config keys are silently ignored."""
        cfg = load_ui_config({"ui": {"nonexistent_key": "value"}})
        # Should not raise and should have default
        self.assertEqual(cfg.user_color, "bold cyan")

    def test_none_input(self):
        cfg = load_ui_config(None)
        self.assertEqual(cfg.user_color, "bold cyan")


if __name__ == "__main__":
    unittest.main()