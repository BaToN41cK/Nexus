"""Unit tests for the :mod:`nexus.core.providers` module.

Tests focus on the abstract base provider, rate limiting, retry logic,
and each concrete provider implementation with mocked HTTP clients.
"""

import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from nexus.core.providers import (
    BaseProvider,
    GroqProvider,
    OpenAIProvider,
    AnthropicProvider,
    OllamaProvider,
    ProviderConfig,
    _RateLimiter,
    create_provider,
    DEFAULT_MODELS,
    FALLBACK_MODELS,
    PROVIDER_MAP,
)


class TestRateLimiter(unittest.TestCase):
    def test_acquire_allows_first_request(self):
        limiter = _RateLimiter(rate=10)
        limiter.acquire()  # Should not raise

    def test_acquire_multiple_requests(self):
        limiter = _RateLimiter(rate=1000)
        for _ in range(10):
            limiter.acquire()  # Should not raise


class TestBaseProvider(unittest.TestCase):
    """Test the non-abstract methods of BaseProvider."""

    def setUp(self):
        # Create a concrete subclass for testing
        class ConcreteProvider(BaseProvider):
            def _init_client(self):
                self._client = MagicMock()

            def generate(self, messages, stream=False):
                return {"text": "ok", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        self.config = ProviderConfig(name="test", api_key="k", model="test-model")
        self.provider = ConcreteProvider(self.config)

    def test_is_error_response_empty(self):
        self.assertFalse(BaseProvider._is_error_response(""))

    def test_is_error_response_normal(self):
        self.assertFalse(BaseProvider._is_error_response("Hello, how can I help?"))

    def test_is_error_response_error_russian(self):
        self.assertTrue(BaseProvider._is_error_response("[Ошибка: something]"))

    def test_is_error_response_error_english(self):
        self.assertTrue(BaseProvider._is_error_response("[Error: API failed]"))

    def test_is_error_response_no_bracket(self):
        """Must start with [ to be considered an error."""
        self.assertFalse(BaseProvider._is_error_response("Ошибка: something"))

    def test_use_model_context_manager(self):
        provider = self.provider
        with provider._use_model("temporary"):
            self.assertEqual(provider.config.model, "temporary")
        self.assertEqual(provider.config.model, "test-model")

    def test_retry_success_on_first_try(self):
        fn = MagicMock(return_value="success")
        result = self.provider._retry(fn, "arg1", kw="kwarg")
        self.assertEqual(result, "success")
        fn.assert_called_once_with("arg1", kw="kwarg")

    def test_retry_succeeds_after_retry(self):
        fn = MagicMock(side_effect=[Exception("first"), Exception("second"), "success"])
        result = self.provider._retry(fn)
        self.assertEqual(result, "success")
        self.assertEqual(fn.call_count, 3)

    def test_retry_raises_after_all_attempts(self):
        fn = MagicMock(side_effect=Exception("always fails"))
        with self.assertRaises(Exception):
            self.provider._retry(fn)
        self.assertEqual(fn.call_count, 3)

    def test_get_fallback_model(self):
        model = self.provider._get_fallback_model()
        # "test" is not in FALLBACK_MODELS, so should return None
        self.assertIsNone(model)

    def test_build_messages_with_system(self):
        msgs = self.provider._build_messages("prompt", system_prompt="sys")
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1]["role"], "user")

    def test_build_messages_without_system(self):
        msgs = self.provider._build_messages("prompt")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "user")

    def test_generate_stream_fallback(self):
        gen = self.provider.generate_stream([{"role": "user", "content": "hi"}])
        tokens = list(gen)
        self.assertEqual(tokens, ["ok"])


class TestCreateProvider(unittest.TestCase):
    def test_create_groq(self):
        config = ProviderConfig(name="groq", api_key="gk", model="llama")
        provider = create_provider(config)
        self.assertIsInstance(provider, GroqProvider)

    def test_create_unknown_provider(self):
        config = ProviderConfig(name="unknown")
        with self.assertRaises(ValueError):
            create_provider(config)

    def test_create_sets_default_model(self):
        config = ProviderConfig(name="groq", api_key="gk")
        provider = create_provider(config)
        self.assertEqual(provider.config.model, DEFAULT_MODELS["groq"])


class TestGroqProvider(unittest.TestCase):
    def setUp(self):
        self.config = ProviderConfig(
            name="groq",
            api_key="fake-key",
            model="llama-3.3-70b-versatile",
            timeout=1,
            max_retries=1,
            rate_limit=100,
        )
        # Create mock error types that inherit from Exception
        self.APIError = type("APIError", (Exception,), {})
        self.RateLimitError = type("RateLimitError", (self.APIError,), {})
        self.APITimeoutError = type("APITimeoutError", (self.APIError,), {})

    def _make_provider(self):
        provider = GroqProvider.__new__(GroqProvider)
        provider.config = self.config
        provider._groq = MagicMock()
        provider._groq.APIError = self.APIError
        provider._groq.RateLimitError = self.RateLimitError
        provider._groq.APITimeoutError = self.APITimeoutError
        provider._client = MagicMock()
        provider._rate_limiter = _RateLimiter(100)
        return provider

    def test_generate_with_timeout_error(self):
        provider = self._make_provider()
        provider._client.chat.completions.create.side_effect = self.APITimeoutError("timeout")
        result = provider._generate_impl([{"role": "user", "content": "hi"}])
        self.assertIn("таймаут", result["text"])

    def test_generate_with_rate_limit_error(self):
        provider = self._make_provider()
        provider._client.chat.completions.create.side_effect = self.RateLimitError("rate")
        result = provider._generate_impl([{"role": "user", "content": "hi"}])
        self.assertIn("лимит запросов", result["text"])

    def test_generate_with_api_error_403(self):
        provider = self._make_provider()
        provider._client.chat.completions.create.side_effect = self.APIError("403 Access denied")
        result = provider._generate_impl([{"role": "user", "content": "hi"}])
        self.assertIn("403", result["text"])

    def test_generate_with_api_error_generic(self):
        provider = self._make_provider()
        provider._client.chat.completions.create.side_effect = self.APIError("internal error")
        result = provider._generate_impl([{"role": "user", "content": "hi"}])
        self.assertIn("Ошибка Groq API", result["text"])

    def test_generate_with_unexpected_error(self):
        provider = self._make_provider()
        provider._client.chat.completions.create.side_effect = RuntimeError("unexpected")
        result = provider._generate_impl([{"role": "user", "content": "hi"}])
        self.assertIn("Неожиданная ошибка", result["text"])

    def test_generate_fallback_on_error(self):
        provider = self._make_provider()
        # First call fails, second succeed
        provider._generate_impl = MagicMock(side_effect=[
            {"text": "[Ошибка Groq API: rate limit]", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            {"text": "fallback response", "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        ])
        result = provider.generate([{"role": "user", "content": "hi"}])
        self.assertEqual(result["text"], "fallback response")
        self.assertEqual(provider._generate_impl.call_count, 2)

    def test_generate_without_fallback_on_success(self):
        provider = self._make_provider()
        provider._generate_impl = MagicMock(return_value={
            "text": "good response", "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2,
        })
        result = provider.generate([{"role": "user", "content": "hi"}])
        self.assertEqual(result["text"], "good response")
        provider._generate_impl.assert_called_once()

    def test_generate_stream_rate_limit(self):
        provider = self._make_provider()
        provider._client.chat.completions.create.side_effect = self.RateLimitError("rate")
        gen = provider._generate_stream_impl([{"role": "user", "content": "hi"}])
        tokens = list(gen)
        self.assertIn("лимит запросов", tokens[0])

    def test_generate_stream_api_error(self):
        provider = self._make_provider()
        provider._client.chat.completions.create.side_effect = self.APIError("stream error")
        gen = provider._generate_stream_impl([{"role": "user", "content": "hi"}])
        tokens = list(gen)
        self.assertIn("Ошибка Groq API", tokens[0])

    def test_generate_stream_unexpected_error(self):
        provider = self._make_provider()
        provider._client.chat.completions.create.side_effect = RuntimeError("unexpected")
        gen = provider._generate_stream_impl([{"role": "user", "content": "hi"}])
        tokens = list(gen)
        self.assertIn("Неожиданная ошибка", tokens[0])


class TestOpenAIProvider(unittest.TestCase):
    def setUp(self):
        self.config = ProviderConfig(
            name="openai",
            api_key="sk-fake",
            model="gpt-4o",
            timeout=1,
            max_retries=1,
            rate_limit=100,
        )

    def _make_provider(self):
        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider.config = self.config
        provider._client = MagicMock()
        provider._rate_limiter = _RateLimiter(100)
        return provider

    def test_generate_error(self):
        provider = self._make_provider()
        provider._client.chat.completions.create.side_effect = RuntimeError("OpenAI error")
        result = provider._generate_impl([{"role": "user", "content": "hi"}])
        self.assertIn("Ошибка OpenAI", result["text"])

    def test_generate_stream_error(self):
        provider = self._make_provider()
        provider._client.chat.completions.create.side_effect = RuntimeError("stream error")
        gen = provider._generate_stream_impl([{"role": "user", "content": "hi"}])
        tokens = list(gen)
        self.assertIn("Ошибка OpenAI", tokens[0])


class TestAnthropicProvider(unittest.TestCase):
    def setUp(self):
        self.config = ProviderConfig(
            name="anthropic",
            api_key="sk-ant-fake",
            model="claude-sonnet-4-20250514",
            timeout=1,
            max_retries=1,
            rate_limit=100,
        )

    def _make_provider(self):
        provider = AnthropicProvider.__new__(AnthropicProvider)
        provider.config = self.config
        provider._client = MagicMock()
        provider._rate_limiter = _RateLimiter(100)
        return provider

    def test_build_anthropic_messages(self):
        provider = self._make_provider()
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        system, msgs = provider._build_anthropic_messages(messages)
        self.assertEqual(system, "You are helpful")
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[1]["role"], "assistant")

    def test_generate_error(self):
        provider = self._make_provider()
        provider._client.messages.create.side_effect = RuntimeError("Anthropic error")
        result = provider._generate_impl([{"role": "user", "content": "hi"}])
        self.assertIn("Ошибка Anthropic", result["text"])

    def test_generate_stream_error(self):
        provider = self._make_provider()
        provider._client.messages.create.side_effect = RuntimeError("stream error")
        gen = provider._generate_stream_impl([{"role": "user", "content": "hi"}])
        tokens = list(gen)
        self.assertIn("Ошибка Anthropic", tokens[0])


class TestOllamaProvider(unittest.TestCase):
    def setUp(self):
        self.config = ProviderConfig(
            name="ollama",
            api_key="",
            model="llama3.2",
            timeout=1,
            max_retries=1,
            rate_limit=100,
        )

    def _make_provider(self):
        provider = OllamaProvider.__new__(OllamaProvider)
        provider.config = self.config
        provider._ollama = MagicMock()
        provider._host = "http://localhost:11434"
        provider._rate_limiter = _RateLimiter(100)
        return provider

    def test_generate_error(self):
        provider = self._make_provider()
        provider._ollama.chat.side_effect = RuntimeError("Ollama not running")
        result = provider._generate_impl([{"role": "user", "content": "hi"}])
        self.assertIn("Ошибка Ollama", result["text"])

    def test_generate_stream_error(self):
        provider = self._make_provider()
        provider._ollama.chat.side_effect = RuntimeError("stream error")
        gen = provider._generate_stream_impl([{"role": "user", "content": "hi"}])
        tokens = list(gen)
        self.assertIn("Ошибка Ollama", tokens[0])


class TestProviderConstants(unittest.TestCase):
    def test_all_providers_have_default_models(self):
        for name in PROVIDER_MAP:
            self.assertIn(name, DEFAULT_MODELS)

    def test_all_providers_have_fallback_models(self):
        for name in PROVIDER_MAP:
            self.assertIn(name, FALLBACK_MODELS)


if __name__ == "__main__":
    unittest.main()