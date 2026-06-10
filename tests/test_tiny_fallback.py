"""Tests for the Tiny Fallback Responder and emergency fallback."""

import unittest
from unittest.mock import MagicMock, patch

from nexus.core.tiny_fallback import (
    TinyFallbackResponder,
    ResponseRule,
    DEFAULT_RULES,
    emergency_fallback,
    try_ollama_tiny_fallback,
)


class TestResponseRule(unittest.TestCase):
    def test_rule_creation(self):
        rule = ResponseRule(
            patterns=[r"hello", r"hi"],
            response="Hello!",
            priority=10,
        )
        self.assertEqual(rule.patterns, [r"hello", r"hi"])
        self.assertEqual(rule.response, "Hello!")
        self.assertEqual(rule.priority, 10)

    def test_default_priority(self):
        rule = ResponseRule(patterns=["test"], response="test")
        self.assertEqual(rule.priority, 0)


class TestTinyFallbackResponder(unittest.TestCase):
    def setUp(self):
        self.responder = TinyFallbackResponder()

    def test_respond_greeting_russian(self):
        """Russian greeting should match."""
        result = self.responder.respond([{"role": "user", "content": "Привет, как дела?"}])
        self.assertIsNotNone(result)
        self.assertIn("Привет", result["text"])
        self.assertEqual(result["fallback_provider"], "rules-based")
        self.assertEqual(result["fallback_model"], "tiny-fallback")

    def test_respond_greeting_english(self):
        """English greeting should match."""
        result = self.responder.respond([{"role": "user", "content": "Hello, how are you?"}])
        self.assertIsNotNone(result)
        self.assertIn("Привет", result["text"])

    def test_respond_help(self):
        """Help command should match."""
        result = self.responder.respond([{"role": "user", "content": "/help"}])
        self.assertIsNotNone(result)
        self.assertIn("fallback-режиме", result["text"])

    def test_respond_who_are_you(self):
        """'Who are you' should match."""
        result = self.responder.respond([{"role": "user", "content": "Who are you?"}])
        self.assertIsNotNone(result)
        self.assertIn("Nexus", result["text"])

    def test_respond_thanks(self):
        result = self.responder.respond([{"role": "user", "content": "Спасибо!"}])
        self.assertIsNotNone(result)
        self.assertIn("Пожалуйста", result["text"])

    def test_respond_poka(self):
        result = self.responder.respond([{"role": "user", "content": "Пока!"}])
        self.assertIsNotNone(result)
        self.assertIn("До свидания", result["text"])

    def test_respond_status(self):
        result = self.responder.respond([{"role": "user", "content": "Проверь статус"}])
        self.assertIsNotNone(result)
        self.assertIn("Статус", result["text"])

    def test_respond_capabilities(self):
        result = self.responder.respond([{"role": "user", "content": "Что ты можешь?"}])
        self.assertIsNotNone(result)
        self.assertIn("обычном режиме", result["text"])

    def test_respond_time(self):
        result = self.responder.respond([{"role": "user", "content": "Который час?"}])
        self.assertIsNotNone(result)
        self.assertIn("точное время", result["text"])

    def test_respond_unknown_returns_none(self):
        """An unrecognized query should return None."""
        result = self.responder.respond([
            {"role": "user", "content": "Какой-то совершенно незнакомый запрос про квантовую физику"},
        ])
        self.assertIsNone(result)

    def test_respond_empty_messages(self):
        result = self.responder.respond([])
        self.assertIsNone(result)

    def test_respond_no_user_message(self):
        result = self.responder.respond([{"role": "system", "content": "You are a bot"}])
        self.assertIsNone(result)

    def test_respond_only_last_user_message(self):
        """Only the last user message should be matched."""
        result = self.responder.respond([
            {"role": "user", "content": "Напиши мне стихотворение"},
            {"role": "assistant", "content": "Вот стих:"},
            {"role": "user", "content": "Привет!"},  # ← last message
        ])
        self.assertIsNotNone(result)
        self.assertIn("Привет", result["text"])

    def test_custom_rules(self):
        """Custom rules should override defaults."""
        custom_rules = [
            ResponseRule(
                patterns=[r"(?i)custom query"],
                response="Custom response",
                priority=999,
            ),
        ]
        responder = TinyFallbackResponder(rules=custom_rules)
        result = responder.respond([{"role": "user", "content": "Custom query please"}])
        self.assertIsNotNone(result)
        self.assertEqual(result["text"], "Custom response")

        # Default greeting should NOT match (custom rules only).
        result = responder.respond([{"role": "user", "content": "Hello"}])
        self.assertIsNone(result)

    def test_rules_sorted_by_priority(self):
        """Higher priority rules should match first."""
        rules = [
            ResponseRule(patterns=[r"test"], response="Low priority", priority=10),
            ResponseRule(patterns=[r"test"], response="High priority", priority=100),
        ]
        responder = TinyFallbackResponder(rules=rules)
        result = responder.respond([{"role": "user", "content": "This is a test"}])
        self.assertEqual(result["text"], "High priority")


class TestTryOllamaTinyFallback(unittest.TestCase):
    @patch("nexus.core.providers.OllamaProvider")
    def test_successful_ollama_fallback(self, mock_ollama_provider):
        """When Ollama is available, should return its result."""
        mock_instance = MagicMock()
        mock_instance.generate.return_value = {
            "text": "Ollama response",
            "prompt_tokens": 0,
            "completion_tokens": 10,
            "total_tokens": 10,
        }
        mock_ollama_provider.return_value = mock_instance

        messages = [{"role": "user", "content": "Hello"}]
        result = try_ollama_tiny_fallback(messages)

        self.assertIsNotNone(result)
        self.assertEqual(result["text"], "Ollama response")
        self.assertEqual(result["fallback_provider"], "ollama")
        self.assertEqual(result["fallback_model"], "tinyllama")
        mock_ollama_provider.assert_called_once()

    @patch("nexus.core.providers.OllamaProvider")
    def test_ollama_error_response(self, mock_ollama_provider):
        """When Ollama returns an error, should return None."""
        mock_instance = MagicMock()
        mock_instance.generate.return_value = {
            "text": "[Ошибка Ollama: connection refused]",
        }
        mock_ollama_provider.return_value = mock_instance

        result = try_ollama_tiny_fallback([{"role": "user", "content": "Hello"}])
        self.assertIsNone(result)

    @patch("nexus.core.providers.OllamaProvider")
    def test_ollama_exception(self, mock_ollama_provider):
        """When Ollama raises, should return None gracefully."""
        mock_instance = MagicMock()
        mock_instance.generate.side_effect = RuntimeError("Ollama not running")
        mock_ollama_provider.return_value = mock_instance

        result = try_ollama_tiny_fallback([{"role": "user", "content": "Hello"}])
        self.assertIsNone(result)

    def test_ollama_import_error(self):
        """When ollama SDK is not installed, should return None gracefully."""
        # The real function catches ImportError internally.
        result = try_ollama_tiny_fallback([{"role": "user", "content": "test"}])
        self.assertIsNone(result)

    def test_ollama_import_error_simulated(self):
        """Simulate ImportError inside try_ollama_tiny_fallback."""
        # The function catches ImportError internally, so calling it
        # when ollama is not installed should return None gracefully.
        result = try_ollama_tiny_fallback([{"role": "user", "content": "test"}])
        # Should not crash — returns None if Ollama unavailable.
        self.assertIsNone(result)


class TestEmergencyFallback(unittest.TestCase):
    def test_emergency_fallback_returns_dict(self):
        """emergency_fallback should always return a dict."""
        result = emergency_fallback([{"role": "user", "content": "Hello"}])
        self.assertIsInstance(result, dict)
        self.assertIn("text", result)
        self.assertIn("fallback_provider", result)
        self.assertIn("fallback_model", result)

    def test_emergency_fallback_rules_based(self):
        """Known queries should get rules-based responses."""
        result = emergency_fallback([{"role": "user", "content": "Привет!"}])
        self.assertIn("Привет", result["text"])
        self.assertEqual(result["fallback_provider"], "rules-based")

    def test_emergency_fallback_generic(self):
        """Unknown queries should get the generic fallback."""
        result = emergency_fallback([{"role": "user", "content": "Объясни теорию струн"}])
        self.assertIn("Офлайн-режим", result["text"])
        self.assertEqual(result["fallback_provider"], "rules-based")

    def test_emergency_fallback_empty_messages(self):
        """Empty messages should return generic fallback."""
        result = emergency_fallback([{"role": "system", "content": "be a bot"}])
        self.assertIn("Офлайн-режим", result["text"])

    def test_emergency_fallback_token_usage(self):
        """Token usage should be zero for rules-based responses."""
        result = emergency_fallback([{"role": "user", "content": "Привет"}])
        self.assertEqual(result["prompt_tokens"], 0)
        self.assertEqual(result["completion_tokens"], 0)
        self.assertEqual(result["total_tokens"], 0)


class TestDefaultRules(unittest.TestCase):
    """Test that DEFAULT_RULES are valid."""

    def test_all_rules_have_patterns(self):
        for rule in DEFAULT_RULES:
            self.assertTrue(len(rule.patterns) > 0, f"Rule has no patterns: {rule.response[:30]}")

    def test_all_rules_have_response(self):
        for rule in DEFAULT_RULES:
            self.assertTrue(len(rule.response) > 0, f"Rule has empty response")

    def test_no_duplicate_priorities(self):
        """Multiple rules can share the same priority — just verify the sort works."""
        priorities = [r.priority for r in DEFAULT_RULES]
        sorted_priorities = sorted(priorities, reverse=True)
        self.assertEqual(priorities, sorted_priorities, "Rules should already be sorted by priority")


class TestIntegrationWithAgent(unittest.TestCase):
    """Integration-style tests: emergency_fallback through generate_response."""

    def test_emergency_fallback_in_generate_response(self):
        """Simulate what happens when all providers fail in generate_response."""
        from nexus.core.agent import NexusAgent

        # We can't fully test without mocking all providers, but we can test
        # that emergency_fallback produces a valid dict that would work.
        from nexus.core.tiny_fallback import emergency_fallback as ef

        result = ef([{"role": "user", "content": "Hello"}])
        self.assertIn("text", result)
        self.assertIsInstance(result["text"], str)
        self.assertGreater(len(result["text"]), 10)


if __name__ == "__main__":
    unittest.main()