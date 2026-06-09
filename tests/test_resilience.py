"""Tests for the Nexus resilience layer: retry, circuit breaker, idempotency, fallback chain."""

import time
import unittest
from typing import Any, Dict, List, Optional, Tuple

from nexus.core.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    FallbackProviderChain,
    FallbackTarget,
    IdempotencyManager,
    ProviderNotAvailableError,
    ResilienceConfig,
    RetryConfig,
    compute_backoff,
    resilient_call,
    retry_call,
)


# ---------------------------------------------------------------------------
# Tests: Retry (exponential backoff + jitter)
# ---------------------------------------------------------------------------


class TestComputeBackoff(unittest.TestCase):
    def test_first_attempt_min_backoff(self):
        cfg = RetryConfig(min_backoff=1.0, max_backoff=60.0, backoff_multiplier=2.0, jitter_factor=0.0)
        delay = compute_backoff(1, cfg)
        self.assertEqual(delay, 1.0)  # no jitter

    def test_second_attempt_doubles(self):
        cfg = RetryConfig(min_backoff=1.0, max_backoff=60.0, backoff_multiplier=2.0, jitter_factor=0.0)
        delay = compute_backoff(2, cfg)
        self.assertEqual(delay, 2.0)

    def test_backoff_capped_at_max(self):
        cfg = RetryConfig(min_backoff=1.0, max_backoff=10.0, backoff_multiplier=10.0, jitter_factor=0.0)
        delay = compute_backoff(3, cfg)
        self.assertLessEqual(delay, 10.0)

    def test_jitter_adds_randomness(self):
        cfg = RetryConfig(min_backoff=1.0, max_backoff=60.0, backoff_multiplier=2.0, jitter_factor=0.5)
        delays = [compute_backoff(2, cfg) for _ in range(20)]
        # With jitter, delays should vary.
        self.assertGreater(max(delays) - min(delays), 0.01)


class TestRetryCall(unittest.TestCase):
    def test_success_first_attempt(self):
        """Should succeed on first try."""
        call_count = 0

        def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = retry_call(succeed, retry_config=RetryConfig(max_retries=3))
        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 1)

    def test_retry_on_failure(self):
        """Should retry on retryable errors."""
        call_count = 0

        def fail_twice_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient error")
            return "recovered"

        result = retry_call(
            fail_twice_then_succeed,
            retry_config=RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=0.1),
            is_retryable=lambda e: isinstance(e, ConnectionError),
        )
        self.assertEqual(result, "recovered")
        self.assertEqual(call_count, 3)

    def test_exhaust_retries(self):
        """Should raise after exhausting retries."""
        call_count = 0

        def always_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")

        with self.assertRaises(ConnectionError):
            retry_call(
                always_fail,
                retry_config=RetryConfig(max_retries=3, min_backoff=0.01, max_backoff=0.1),
                is_retryable=lambda e: isinstance(e, ConnectionError),
            )
        self.assertEqual(call_count, 3)

    def test_non_retryable_exception(self):
        """Non-retryable exception should raise immediately."""
        def fail() -> str:
            raise ValueError("non-retryable")

        with self.assertRaises(ValueError):
            retry_call(
                fail,
                retry_config=RetryConfig(max_retries=3),
                is_retryable=lambda e: isinstance(e, ConnectionError),
            )

    def test_on_retry_callback(self):
        """on_retry callback should be invoked on each retry."""
        retry_events: List[Tuple[int, Exception, float]] = []

        def fail() -> str:
            raise ConnectionError("fail")

        with self.assertRaises(ConnectionError):
            retry_call(
                fail,
                retry_config=RetryConfig(max_retries=2, min_backoff=0.01, max_backoff=0.1),
                is_retryable=lambda e: isinstance(e, ConnectionError),
                on_retry=lambda a, e, d: retry_events.append((a, e, d)),
            )
        self.assertEqual(len(retry_events), 1)
        self.assertEqual(retry_events[0][0], 1)


# ---------------------------------------------------------------------------
# Tests: Circuit Breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker(unittest.TestCase):
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        self.assertEqual(cb.state, CircuitState.CLOSED)

        for _ in range(3):
            cb.record_failure()

        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())

    def test_half_open_after_recovery(self):
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout=0.01,
        ))
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        time.sleep(0.02)
        self.assertTrue(cb.allow_request())
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

    def test_closes_after_consecutive_successes(self):
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout=0.01,
            consecutive_successes_to_close=2,
        ))
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        time.sleep(0.02)
        cb.allow_request()  # transitions to HALF_OPEN

        cb.record_success()
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_opens_again_on_half_open_failure(self):
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=0.01,
        ))
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        time.sleep(0.02)
        cb.allow_request()  # HALF_OPEN
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_reset(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        cb.reset()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

    def test_success_resets_failure_count_in_closed(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # Should still be CLOSED since successes reset counter.
        self.assertEqual(cb.state, CircuitState.CLOSED)
        cb.record_failure()
        cb.record_failure()
        # Still 2 failures, not 3.
        self.assertEqual(cb.state, CircuitState.CLOSED)


# ---------------------------------------------------------------------------
# Tests: Idempotency Manager
# ---------------------------------------------------------------------------


class TestIdempotencyManager(unittest.TestCase):
    def setUp(self):
        self.mgr = IdempotencyManager(ttl=60.0)

    def test_make_key_deterministic(self):
        key1 = IdempotencyManager.make_key("groq", "llama-3.3-70b", [{"role": "user", "content": "hello"}])
        key2 = IdempotencyManager.make_key("groq", "llama-3.3-70b", [{"role": "user", "content": "hello"}])
        self.assertEqual(key1, key2)

    def test_make_key_different_inputs(self):
        key1 = IdempotencyManager.make_key("groq", "llama-3.3-70b", [{"role": "user", "content": "hello"}])
        key2 = IdempotencyManager.make_key("groq", "llama-3.3-70b", [{"role": "user", "content": "world"}])
        self.assertNotEqual(key1, key2)

    def test_is_completed(self):
        key = "test_key_123"
        self.assertFalse(self.mgr.is_completed(key))
        self.mgr.mark_completed(key, "result")
        self.assertTrue(self.mgr.is_completed(key))

    def test_get_completed_result(self):
        key = "test_key_result"
        self.mgr.mark_completed(key, {"text": "hello"})
        result = self.mgr.get_completed_result(key)
        self.assertEqual(result, {"text": "hello"})

    def test_ttl_expiry(self):
        mgr = IdempotencyManager(ttl=0.01)
        key = "ttl_key"
        mgr.mark_completed(key, "data")
        time.sleep(0.02)
        result = mgr.get_completed_result(key)
        self.assertIsNone(result)

    def test_mark_started(self):
        key = "inflight_key"
        self.assertTrue(self.mgr.mark_started(key))
        self.assertFalse(self.mgr.mark_started(key))  # already in flight

    def test_mark_failed(self):
        key = "fail_key"
        self.mgr.mark_started(key)
        self.mgr.mark_failed(key)
        # Should be able to start again.
        self.assertTrue(self.mgr.mark_started(key))

    def test_cleanup(self):
        mgr = IdempotencyManager(ttl=0.01)
        mgr.mark_completed("k1", "v1")
        mgr.mark_started("k2")
        time.sleep(0.02)
        removed = mgr.cleanup()
        self.assertGreaterEqual(removed, 1)


# ---------------------------------------------------------------------------
# Tests: Fallback Provider Chain
# ---------------------------------------------------------------------------


class TestFallbackProviderChain(unittest.TestCase):
    def test_first_target_succeeds(self):
        chain = FallbackProviderChain(
            targets=[
                FallbackTarget(provider_name="groq", model="llama-3.3-70b"),
                FallbackTarget(provider_name="openai", model="gpt-4o"),
            ],
            use_circuit_breaker=False,
        )

        def make_call(target: FallbackTarget) -> str:
            if target.provider_name == "groq":
                return "groq_response"
            raise RuntimeError("should not reach")

        result, target = chain.call([{"role": "user", "content": "hi"}], make_call)
        self.assertEqual(result, "groq_response")
        self.assertEqual(target.provider_name, "groq")

    def test_fallback_on_failure(self):
        chain = FallbackProviderChain(
            targets=[
                FallbackTarget(provider_name="groq", model="llama-3.3-70b"),
                FallbackTarget(provider_name="openai", model="gpt-4o"),
            ],
            use_circuit_breaker=False,
        )

        call_order: List[str] = []

        def make_call(target: FallbackTarget) -> str:
            call_order.append(target.provider_name)
            if target.provider_name == "groq":
                raise ConnectionError("groq down")
            return "openai_response"

        result, target = chain.call([{"role": "user", "content": "hi"}], make_call)
        self.assertEqual(result, "openai_response")
        self.assertEqual(target.provider_name, "openai")
        self.assertEqual(call_order, ["groq", "openai"])

    def test_all_targets_fail(self):
        chain = FallbackProviderChain(
            targets=[
                FallbackTarget(provider_name="groq", model="llama-3.3-70b"),
                FallbackTarget(provider_name="openai", model="gpt-4o"),
            ],
            use_circuit_breaker=False,
        )

        def make_call(target: FallbackTarget) -> str:
            raise ConnectionError(f"{target.provider_name} down")

        with self.assertRaises(ProviderNotAvailableError):
            chain.call([{"role": "user", "content": "hi"}], make_call)

    def test_circuit_breaker_skips_open_target(self):
        chain = FallbackProviderChain(
            targets=[
                FallbackTarget(provider_name="groq", model="llama-3.3-70b"),
                FallbackTarget(provider_name="openai", model="gpt-4o"),
            ],
            use_circuit_breaker=True,
        )

        # Trip the circuit breaker for groq.
        cb = chain._get_circuit_breaker(chain.targets[0])
        for _ in range(cb.config.failure_threshold):
            cb.record_failure()

        call_order: List[str] = []

        def make_call(target: FallbackTarget) -> str:
            call_order.append(target.provider_name)
            return f"{target.provider_name}_response"

        result, target = chain.call([{"role": "user", "content": "hi"}], make_call)
        self.assertEqual(target.provider_name, "openai")
        self.assertEqual(call_order, ["openai"])  # groq skipped


# ---------------------------------------------------------------------------
# Tests: Resilient Call (unified)
# ---------------------------------------------------------------------------


class TestResilientCall(unittest.TestCase):
    def test_basic_success(self):
        """Resilient call succeeds on first attempt."""
        def ok() -> str:
            return "ok"

        result = resilient_call(ok, config=ResilienceConfig(use_idempotency=False))
        self.assertEqual(result, "ok")

    def test_with_idempotency(self):
        """Resilient call with idempotency caches result."""
        call_count = 0
        mgr = IdempotencyManager()

        def calculate() -> int:
            nonlocal call_count
            call_count += 1
            return 42

        # First call.
        key = "unique_key_123"
        result1 = resilient_call(
            calculate,
            config=ResilienceConfig(use_idempotency=True),
            idempotency_manager=mgr,
            idempotency_key=key,
        )
        self.assertEqual(result1, 42)
        self.assertEqual(call_count, 1)

        # Second call with same key — should use cache.
        result2 = resilient_call(
            calculate,
            config=ResilienceConfig(use_idempotency=True),
            idempotency_manager=mgr,
            idempotency_key=key,
        )
        self.assertEqual(result2, 42)
        self.assertEqual(call_count, 1)  # no second call

    def test_circuit_breaker_blocks(self):
        """Circuit breaker in OPEN state should block request."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()  # now OPEN

        def ok() -> str:
            return "should not reach"

        with self.assertRaises(ConnectionError):
            resilient_call(
                ok,
                config=ResilienceConfig(use_idempotency=False),
                circuit_breaker=cb,
            )

    def test_retry_exhausted(self):
        """Should raise after exhausting retries."""
        call_count = 0

        def fail() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        cfg = ResilienceConfig(
            retry=RetryConfig(max_retries=2, min_backoff=0.01, max_backoff=0.1),
            use_idempotency=False,
        )

        with self.assertRaises(ConnectionError):
            resilient_call(fail, config=cfg, is_retryable=lambda e: isinstance(e, ConnectionError))
        self.assertEqual(call_count, 2)


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()