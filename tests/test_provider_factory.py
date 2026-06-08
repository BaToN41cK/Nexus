"""Tests for the :mod:`nexus.core.provider_factory` module."""

import unittest
from unittest.mock import MagicMock, patch

from nexus.core.providers import BaseProvider, GroqProvider, ProviderConfig
from nexus.core.provider_factory import ProviderFactory


class TestProviderFactory(unittest.TestCase):
    def test_create_groq(self):
        provider = ProviderFactory.create(name="groq", api_key="test-key")
        self.assertIsInstance(provider, GroqProvider)
        self.assertEqual(provider.config.model, "llama-3.3-70b-versatile")
        self.assertEqual(provider.config.api_key, "test-key")

    def test_create_with_custom_model(self):
        provider = ProviderFactory.create(
            name="groq", api_key="k", model="mixtral-8x7b"
        )
        self.assertEqual(provider.config.model, "mixtral-8x7b")

    def test_create_unknown_provider(self):
        with self.assertRaises(ValueError):
            ProviderFactory.create(name="unknown_provider")

    def test_list_providers(self):
        providers = ProviderFactory.list_providers()
        self.assertIn("groq", providers)
        self.assertIn("openai", providers)

    def test_get_default_model(self):
        model = ProviderFactory.get_default_model("groq")
        self.assertEqual(model, "llama-3.3-70b-versatile")
        self.assertEqual(ProviderFactory.get_default_model("nonexistent"), "")

    def test_get_fallback_model(self):
        model = ProviderFactory.get_fallback_model("groq")
        self.assertEqual(model, "llama-3.1-8b-instant")
        self.assertIsNone(ProviderFactory.get_fallback_model("nonexistent"))

    def test_create_with_all_params(self):
        provider = ProviderFactory.create(
            name="groq",
            api_key="k",
            model="m",
            base_url="https://custom.url",
            timeout=60,
            max_tokens=2048,
            temperature=0.5,
            max_retries=5,
            rate_limit=10.0,
            extra={"custom": "value"},
        )
        self.assertEqual(provider.config.base_url, "https://custom.url")
        self.assertEqual(provider.config.timeout, 60)
        self.assertEqual(provider.config.max_tokens, 2048)
        self.assertEqual(provider.config.temperature, 0.5)
        self.assertEqual(provider.config.max_retries, 5)
        self.assertEqual(provider.config.rate_limit, 10.0)
        self.assertEqual(provider.config.extra, {"custom": "value"})


class TestProviderFactoryCustomProvider(unittest.TestCase):
    def setUp(self):
        # Clean up any custom registrations from previous tests
        ProviderFactory.unregister("test_provider")

    def tearDown(self):
        ProviderFactory.unregister("test_provider")

    def test_register_custom_provider(self):
        # Create a minimal mock provider
        class TestProvider(BaseProvider):
            name = "test_provider"

            def _init_client(self):
                self._client = MagicMock()

            def generate(self, messages, stream=False):
                return {"text": "ok", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        ProviderFactory.register("test_provider", TestProvider)
        providers = ProviderFactory.list_providers()
        self.assertIn("test_provider", providers)

        provider = ProviderFactory.create("test_provider", api_key="k")
        self.assertIsInstance(provider, TestProvider)

    def test_register_duplicate_custom(self):
        class TestProvider(BaseProvider):
            name = "test_provider"
            def _init_client(self): self._client = MagicMock()
            def generate(self, messages, stream=False): return {"text": "ok", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        ProviderFactory.register("test_provider", TestProvider)
        with self.assertRaises(ValueError):
            ProviderFactory.register("test_provider", TestProvider)

    def test_register_builtin_override_forbidden(self):
        class FakeGroq(BaseProvider):
            name = "fake_groq"
            def _init_client(self): self._client = MagicMock()
            def generate(self, messages, stream=False): return {"text": "no", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        with self.assertRaises(ValueError):
            ProviderFactory.register("groq", FakeGroq)

    def test_unregister_custom(self):
        class TestProvider(BaseProvider):
            name = "temp_provider"
            def _init_client(self): self._client = MagicMock()
            def generate(self, messages, stream=False): return {"text": "ok", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        ProviderFactory.register("temp_provider", TestProvider)
        self.assertIn("temp_provider", ProviderFactory.list_providers())
        ProviderFactory.unregister("temp_provider")
        self.assertNotIn("temp_provider", ProviderFactory.list_providers())


if __name__ == "__main__":
    unittest.main()