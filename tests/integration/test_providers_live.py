"""
Integration tests for live provider APIs.

These tests require real API keys set in environment variables.
They are skipped automatically when the corresponding key is absent.

Usage::

    # Run only integration tests (add -k integ for even faster filtering):
    pytest tests/integration/ -v

    # With a single key:
    GROQ_API_KEY=gsk_... pytest tests/integration/ -v

    # With all keys:
    GROQ_API_KEY=gsk_... OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=sk-ant-... pytest tests/integration/ -v
"""

import os
import time
import unittest
import logging

logging.basicConfig(level=logging.DEBUG)

from nexus.core.providers import (
    GroqProvider,
    OpenAIProvider,
    AnthropicProvider,
    OllamaProvider,
    ProviderConfig,
    create_provider,
)
from nexus.core.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    FallbackProviderChain,
    FallbackTarget,
    ProviderNotAvailableError,
)
from nexus.core.health import HealthChecker, HealthCheckConfig
from nexus.core.tiny_fallback import (
    TinyFallbackResponder,
    emergency_fallback,
    try_ollama_tiny_fallback,
)

# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------

HAS_GROQ = bool(os.environ.get("GROQ_API_KEY"))
HAS_OPENAI = bool(os.environ.get("OPENAI_API_KEY"))
HAS_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY"))

skip_no_groq = unittest.skipUnless(HAS_GROQ, "GROQ_API_KEY not set")
skip_no_openai = unittest.skipUnless(HAS_OPENAI, "OPENAI_API_KEY not set")
skip_no_anthropic = unittest.skipUnless(HAS_ANTHROPIC, "ANTHROPIC_API_KEY not set")


# ---------------------------------------------------------------------------
# Basic generation — each provider
# ---------------------------------------------------------------------------


@skip_no_groq
class TestGroqLiveGeneration(unittest.TestCase):
    """Test Groq provider with a real API call."""

    def setUp(self):
        self.provider = GroqProvider(ProviderConfig(
            name="groq",
            api_key=os.environ["GROQ_API_KEY"],
            model="llama-3.1-8b-instant",
            timeout=15,
            max_tokens=50,
            temperature=0.0,
        ))

    def test_generate_simple_prompt(self):
        """A real Groq call should return a non-error, non-empty response."""
        result = self.provider.generate([
            {"role": "user", "content": "Say exactly: hello world"},
        ])
        text = result.get("text", "")
        self.assertNotIn("[", text, f"Got error response: {text}")
        self.assertGreater(len(text), 0)
        self.assertGreaterEqual(result.get("total_tokens", 0), 2)
        self.assertIn("hello", text.lower())

    def test_generate_stream(self):
        """Streaming should yield tokens and return usage stats."""
        gen = self.provider.generate_stream([
            {"role": "user", "content": "Say exactly: streaming works"},
        ])
        tokens = list(gen)
        # At least one token yielded.
        self.assertGreater(len(tokens), 0)
        self.assertIn("streaming", " ".join(tokens).lower())

    def test_generate_with_system_prompt(self):
        """System prompt should influence the response."""
        result = self.provider.generate([
            {"role": "system", "content": "Always answer in one word."},
            {"role": "user", "content": "What color is the sky?"},
        ])
        text = result.get("text", "")
        self.assertNotIn("[", text)
        self.assertGreater(len(text), 0)


@skip_no_openai
class TestOpenAILiveGeneration(unittest.TestCase):
    """Test OpenAI provider with a real API call."""

    def setUp(self):
        self.provider = OpenAIProvider(ProviderConfig(
            name="openai",
            api_key=os.environ["OPENAI_API_KEY"],
            model="gpt-4o-mini",
            timeout=15,
            max_tokens=50,
            temperature=0.0,
        ))

    def test_generate_simple_prompt(self):
        result = self.provider.generate([
            {"role": "user", "content": "Say exactly: hello from openai"},
        ])
        text = result.get("text", "")
        self.assertNotIn("[", text)
        self.assertGreater(len(text), 0)
        self.assertIn("hello", text.lower())

    def test_generate_stream(self):
        gen = self.provider.generate_stream([
            {"role": "user", "content": "Say exactly: openai streaming works"},
        ])
        tokens = list(gen)
        self.assertGreater(len(tokens), 0)


@skip_no_anthropic
class TestAnthropicLiveGeneration(unittest.TestCase):
    """Test Anthropic provider with a real API call."""

    def setUp(self):
        self.provider = AnthropicProvider(ProviderConfig(
            name="anthropic",
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model="claude-3-5-haiku-20241022",
            timeout=15,
            max_tokens=50,
            temperature=0.0,
        ))

    def test_generate_simple_prompt(self):
        result = self.provider.generate([
            {"role": "user", "content": "Say exactly: hello from anthropic"},
        ])
        text = result.get("text", "")
        self.assertNotIn("[", text)
        self.assertGreater(len(text), 0)
        self.assertIn("hello", text.lower())

    def test_generate_with_system(self):
        result = self.provider.generate([
            {"role": "system", "content": "Answer in one word."},
            {"role": "user", "content": "Say: ok"},
        ])
        text = result.get("text", "")
        self.assertNotIn("[", text)


# ---------------------------------------------------------------------------
# Fallback chain — live cross-provider failover
# ---------------------------------------------------------------------------


class TestLiveFallbackChain(unittest.TestCase):
    """Test real fallback between available providers."""

    def _available_targets(self) -> list:
        targets = []
        if HAS_GROQ:
            targets.append(FallbackTarget(
                provider_name="groq",
                model="llama-3.1-8b-instant",
                api_key=os.environ.get("GROQ_API_KEY", ""),
                timeout=10,
                max_tokens=50,
                temperature=0.0,
            ))
        if HAS_OPENAI:
            targets.append(FallbackTarget(
                provider_name="openai",
                model="gpt-4o-mini",
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                timeout=10,
                max_tokens=50,
                temperature=0.0,
            ))
        if HAS_ANTHROPIC:
            targets.append(FallbackTarget(
                provider_name="anthropic",
                model="claude-3-5-haiku-20241022",
                api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
                timeout=10,
                max_tokens=50,
                temperature=0.0,
            ))
        return targets

    def _make_call(self, target: FallbackTarget) -> dict:
        config = ProviderConfig(
            name=target.provider_name,
            api_key=target.api_key,
            model=target.model,
            timeout=target.timeout,
            max_tokens=target.max_tokens,
            temperature=target.temperature,
        )
        provider = create_provider(config)
        return provider.generate([
            {"role": "user", "content": f"Say exactly: hello from {target.provider_name}"},
        ])

    def test_fallback_first_provider_succeeds(self):
        """The first available provider should succeed."""
        targets = self._available_targets()
        if not targets:
            self.skipTest("No API keys available")
        chain = FallbackProviderChain(targets=targets, use_circuit_breaker=True)

        result, used_target = chain.call(
            [{"role": "user", "content": "say hi"}],
            make_call=self._make_call,
        )
        self.assertIn("text", result)
        self.assertGreater(len(result["text"]), 0)

    def test_fallback_fails_over_to_next_provider(self):
        """If first provider fails (bad key), should fall to the next."""
        targets = self._available_targets()
        if len(targets) < 2:
            self.skipTest("Need at least 2 providers for fallback test")

        # Sabotage the first target's API key.
        original_key = targets[0].api_key
        targets[0].api_key = "bad-key-that-will-fail"

        chain = FallbackProviderChain(targets=targets, use_circuit_breaker=False)

        result, used_target = chain.call(
            [{"role": "user", "content": "say hi"}],
            make_call=self._make_call,
        )
        self.assertIn("text", result)
        # Should have used the second provider.
        self.assertEqual(used_target.provider_name, targets[1].provider_name)
        self.assertGreater(len(result["text"]), 0)

        # Restore (for other tests).
        targets[0].api_key = original_key


# ---------------------------------------------------------------------------
# Health checker — pinging real providers
# ---------------------------------------------------------------------------


@skip_no_groq
class TestLiveHealthChecker(unittest.TestCase):
    """Health checker integration with a real Groq provider."""

    def setUp(self):
        self.checker = HealthChecker(HealthCheckConfig(check_interval=0.1))
        self.cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2))

    def tearDown(self):
        self.checker.stop()

    def test_health_check_detects_healthy_provider(self):
        """A healthy Groq provider should pass the health check and close the circuit."""
        # Trip the circuit breaker.
        self.cb.record_failure()
        self.cb.record_failure()
        self.assertEqual(self.cb.state, CircuitState.OPEN)

        messages = [{"role": "user", "content": "health check ping"}]
        api_key = os.environ["GROQ_API_KEY"]

        def ping() -> bool:
            try:
                provider = GroqProvider(ProviderConfig(
                    name="groq",
                    api_key=api_key,
                    model="llama-3.1-8b-instant",
                    timeout=5,
                    max_tokens=5,
                    temperature=0.0,
                ))
                result = provider.generate(messages)
                text = result.get("text", "")
                return bool(text) and not text.startswith("[")
            except Exception:
                return False

        self.checker.register("groq:live-test", ping, self.cb)

        # Run a single check — should recover the circuit.
        recovered = self.checker.check_once()
        self.assertEqual(recovered, 1)
        self.assertEqual(self.cb.state, CircuitState.CLOSED)
        self.assertTrue(self.cb.allow_request())

    def test_health_check_background_loop(self):
        """Background health checks should eventually recover an OPEN circuit."""
        self.cb.record_failure()
        self.cb.record_failure()
        self.assertEqual(self.cb.state, CircuitState.OPEN)

        api_key = os.environ["GROQ_API_KEY"]

        def ping() -> bool:
            try:
                provider = GroqProvider(ProviderConfig(
                    name="groq",
                    api_key=api_key,
                    model="llama-3.1-8b-instant",
                    timeout=5,
                    max_tokens=5,
                    temperature=0.0,
                ))
                result = provider.generate([
                    {"role": "user", "content": "ping"},
                ])
                text = result.get("text", "")
                return bool(text) and not text.startswith("[")
            except Exception:
                return False

        self.checker.register("groq:bg-test", ping, self.cb)
        self.checker.start()

        # Wait for at least one health check round.
        time.sleep(0.3)
        self.checker.stop()

        self.assertEqual(self.cb.state, CircuitState.CLOSED)


# ---------------------------------------------------------------------------
# Emergency fallback with Ollama (if available)
# ---------------------------------------------------------------------------


class TestLiveEmergencyFallback(unittest.TestCase):
    """Test the 3-tier emergency fallback in a real environment."""

    def test_try_ollama_tiny_fallback_live(self):
        """If Ollama is running locally, this should succeed."""
        result = try_ollama_tiny_fallback([
            {"role": "user", "content": "Say exactly: ollama is online"},
        ])
        if result is not None:
            # Ollama is running — verify response.
            self.assertIn("text", result)
            self.assertGreater(len(result["text"]), 0)
            self.assertEqual(result.get("fallback_provider"), "ollama")
        else:
            # Ollama not running — that's fine, it gracefully returns None.
            pass

    def test_emergency_fallback_always_returns_result(self):
        """emergency_fallback should always return a dict (rules-based or generic)."""
        result = emergency_fallback([
            {"role": "user", "content": "hello"},
        ])
        self.assertIn("text", result)
        self.assertGreater(len(result["text"]), 0)
        self.assertIn("fallback_provider", result)

    def test_emergency_fallback_rules_when_offline(self):
        """Known patterns should match even when completely offline."""
        result = TinyFallbackResponder().respond([
            {"role": "user", "content": "What time is it?"},
        ])
        self.assertIsNotNone(result)
        self.assertIn("точное время", result["text"])


# ---------------------------------------------------------------------------
# Circuit breaker with real errors
# ---------------------------------------------------------------------------


@skip_no_groq
class TestLiveCircuitBreaker(unittest.TestCase):
    """Circuit breaker behaviour with a real provider."""

    def test_circuit_opens_on_real_failures(self):
        """Multiple real failures should open the circuit breaker."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        # Create a provider with a deliberately wrong model name.
        provider = GroqProvider(ProviderConfig(
            name="groq",
            api_key=os.environ["GROQ_API_KEY"],
            model="nonexistent-model-xyz-999",
            timeout=5,
            max_tokens=5,
        ))

        for i in range(3):
            result = provider.generate([
                {"role": "user", "content": "ping"},
            ])
            text = result.get("text", "")
            is_error = text.startswith("[") or "Ошибка" in text
            if is_error:
                cb.record_failure()

        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())


# ---------------------------------------------------------------------------
# Real fallback chain with circuit breaker + recovery
# ---------------------------------------------------------------------------


class TestLiveFallbackWithCircuitBreaker(unittest.TestCase):
    """End-to-end: fallback chain + circuit breaker + health checker."""

    def test_fallback_chain_circuit_breaker_and_health_checker(self):
        """
        Scenario:
          1. Set up a 2-provider chain (Groq + OpenAI).
          2. Trip the Groq circuit breaker via failures.
          3. Verify it falls back to OpenAI.
          4. Use HealthChecker to ping Groq and recover it.
          5. Verify Groq is used again.
        """
        if not HAS_GROQ or not HAS_OPENAI:
            self.skipTest("Need both GROQ_API_KEY and OPENAI_API_KEY")

        health_checker = HealthChecker(HealthCheckConfig(check_interval=0.1))

        groq_target = FallbackTarget(
            provider_name="groq",
            model="llama-3.1-8b-instant",
            api_key=os.environ["GROQ_API_KEY"],
            timeout=10,
            max_tokens=50,
            temperature=0.0,
        )
        openai_target = FallbackTarget(
            provider_name="openai",
            model="gpt-4o-mini",
            api_key=os.environ["OPENAI_API_KEY"],
            timeout=10,
            max_tokens=50,
            temperature=0.0,
        )

        chain = FallbackProviderChain(
            targets=[groq_target, openai_target],
            use_circuit_breaker=True,
            health_checker=health_checker,
        )

        def make_call(target: FallbackTarget) -> dict:
            config = ProviderConfig(
                name=target.provider_name,
                api_key=target.api_key,
                model=target.model,
                timeout=target.timeout,
                max_tokens=target.max_tokens,
                temperature=target.temperature,
            )
            provider = create_provider(config)
            return provider.generate([
                {"role": "user", "content": f"Say exactly: {target.provider_name} is working"},
            ])

        # 1. First call — should use Groq.
        result, target = chain.call(
            [{"role": "user", "content": "test 1"}],
            make_call=make_call,
        )
        self.assertEqual(target.provider_name, "groq")

        # 2. Trip Groq's circuit breaker.
        groq_cb = chain._circuit_breakers.get("groq:llama-3.1-8b-instant")
        self.assertIsNotNone(groq_cb)
        for _ in range(groq_cb.config.failure_threshold):
            groq_cb.record_failure()
        self.assertEqual(groq_cb.state, CircuitState.OPEN)

        # 3. Next call should fall back to OpenAI.
        result, target = chain.call(
            [{"role": "user", "content": "test 2"}],
            make_call=make_call,
        )
        self.assertEqual(target.provider_name, "openai")

        # 4. Run health checker to recover Groq.
        health_checker.start()
        time.sleep(0.3)
        health_checker.stop()

        # 5. Groq should be recovered.
        self.assertEqual(groq_cb.state, CircuitState.CLOSED)

        # 6. Next call should use Groq again.
        result, target = chain.call(
            [{"role": "user", "content": "test 3"}],
            make_call=make_call,
        )
        self.assertEqual(target.provider_name, "groq")


if __name__ == "__main__":
    unittest.main()