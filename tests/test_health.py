"""Tests for the pre-emptive health checker."""

import time
import unittest
import threading
from unittest.mock import MagicMock, patch

from nexus.core.health import HealthChecker, HealthCheckConfig
from nexus.core.resilience import CircuitBreaker, CircuitBreakerConfig, CircuitState


class TestHealthCheckConfig(unittest.TestCase):
    def test_default_interval(self):
        cfg = HealthCheckConfig()
        self.assertEqual(cfg.check_interval, 15.0)

    def test_custom_interval(self):
        cfg = HealthCheckConfig(check_interval=5.0)
        self.assertEqual(cfg.check_interval, 5.0)


class TestHealthChecker(unittest.TestCase):
    def setUp(self):
        self.checker = HealthChecker(HealthCheckConfig(check_interval=0.05))

    def tearDown(self):
        self.checker.stop()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def test_register_provider(self):
        cb = CircuitBreaker()
        ping_fn = MagicMock(return_value=True)
        self.checker.register("test:model", ping_fn, cb)
        with self.checker._lock:
            self.assertIn("test:model", self.checker._providers)

    def test_unregister_provider(self):
        cb = CircuitBreaker()
        ping_fn = MagicMock(return_value=True)
        self.checker.register("test:model", ping_fn, cb)
        self.checker.unregister("test:model")
        with self.checker._lock:
            self.assertNotIn("test:model", self.checker._providers)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def test_start_and_stop(self):
        self.assertFalse(self.checker.is_running())
        self.checker.start()
        self.assertTrue(self.checker.is_running())
        self.checker.stop()
        self.assertFalse(self.checker.is_running())

    def test_start_is_idempotent(self):
        self.checker.start()
        thread_id = id(self.checker._thread)
        self.checker.start()  # second start — no-op
        self.assertEqual(id(self.checker._thread), thread_id)

    def test_stop_without_start(self):
        # Should not raise.
        self.checker.stop()

    # ------------------------------------------------------------------
    # check_once — ping logic
    # ------------------------------------------------------------------

    def test_check_once_ignores_closed_circuits(self):
        cb = CircuitBreaker()
        ping_fn = MagicMock(return_value=True)
        self.checker.register("test:model", ping_fn, cb)
        # Circuit is CLOSED — ping should NOT be called.
        recovered = self.checker.check_once()
        self.assertEqual(recovered, 0)
        ping_fn.assert_not_called()

    def test_check_once_resets_open_circuit_on_success(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()  # → OPEN
        self.assertEqual(cb.state, CircuitState.OPEN)

        ping_fn = MagicMock(return_value=True)
        self.checker.register("test:model", ping_fn, cb)

        recovered = self.checker.check_once()
        self.assertEqual(recovered, 1)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        ping_fn.assert_called_once()

    def test_check_once_leaves_open_circuit_on_failure(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()  # → OPEN

        ping_fn = MagicMock(return_value=False)
        self.checker.register("test:model", ping_fn, cb)

        recovered = self.checker.check_once()
        self.assertEqual(recovered, 0)
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_check_once_handles_exception_in_ping(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()  # → OPEN

        def failing_ping() -> bool:
            raise RuntimeError("ping failed")

        self.checker.register("test:model", failing_ping, cb)

        recovered = self.checker.check_once()
        self.assertEqual(recovered, 0)
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_check_once_ignores_half_open_circuits(self):
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=0.01,
        ))
        cb.record_failure()  # → OPEN
        time.sleep(0.02)
        cb.allow_request()  # → HALF_OPEN

        ping_fn = MagicMock(return_value=True)
        self.checker.register("test:model", ping_fn, cb)

        recovered = self.checker.check_once()
        # HALF_OPEN circuits should NOT be pinged by the health checker.
        self.assertEqual(recovered, 0)
        ping_fn.assert_not_called()

    def test_check_once_multiple_providers_some_open(self):
        cb1 = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb1.record_failure()  # OPEN
        cb2 = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))  # CLOSED

        ping1 = MagicMock(return_value=True)
        ping2 = MagicMock(return_value=True)

        self.checker.register("provider1", ping1, cb1)
        self.checker.register("provider2", ping2, cb2)

        recovered = self.checker.check_once()
        self.assertEqual(recovered, 1)  # only provider1 was OPEN
        ping1.assert_called_once()
        ping2.assert_not_called()

    # ------------------------------------------------------------------
    # Background loop integration
    # ------------------------------------------------------------------

    def test_background_loop_closes_open_circuits(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()  # → OPEN

        ping_fn = MagicMock(return_value=True)
        self.checker.register("test:model", ping_fn, cb)

        self.checker.start()
        # Wait for at least one check round.
        time.sleep(0.15)
        self.checker.stop()

        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertGreaterEqual(ping_fn.call_count, 1)

    def test_background_loop_does_not_ping_closed_circuits(self):
        cb = CircuitBreaker()
        ping_fn = MagicMock(return_value=True)
        self.checker.register("test:model", ping_fn, cb)

        self.checker.start()
        time.sleep(0.15)
        self.checker.stop()

        # Should never have pinged a CLOSED circuit.
        ping_fn.assert_not_called()

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_check_once_empty_registry(self):
        recovered = self.checker.check_once()
        self.assertEqual(recovered, 0)

    def test_register_after_start(self):
        self.checker.start()

        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()  # → OPEN
        ping_fn = MagicMock(return_value=True)
        self.checker.register("late:model", ping_fn, cb)

        time.sleep(0.15)
        self.checker.stop()

        self.assertEqual(cb.state, CircuitState.CLOSED)
        ping_fn.assert_called()

    def test_unregister_prevents_ping(self):
        """After unregistering, check_once should skip the provider."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()  # → OPEN
        ping_fn = MagicMock(return_value=True)
        self.checker.register("soon-gone", ping_fn, cb)

        # Unregister before any check round.
        self.checker.unregister("soon-gone")

        recovered = self.checker.check_once()
        self.assertEqual(recovered, 0)
        ping_fn.assert_not_called()

    def test_loop_survives_exception_in_check_once(self):
        """An exception in the check loop should not kill the background thread."""
        # Register a ping that raises after the first call.
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()  # → OPEN
        call_count = 0

        def flaky_ping() -> bool:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            return True

        self.checker.register("flaky", flaky_ping, cb)
        self.checker.start()
        time.sleep(0.2)
        self.checker.stop()

        # The thread should still be alive and eventually recover.
        self.assertGreaterEqual(call_count, 2)
        self.assertEqual(cb.state, CircuitState.CLOSED)


class TestHealthCheckerWithCircuitBreaker(unittest.TestCase):
    """
    Integration tests: HealthChecker + real CircuitBreaker state machine.
    """

    def setUp(self):
        self.checker = HealthChecker(HealthCheckConfig(check_interval=0.05))

    def tearDown(self):
        self.checker.stop()

    def test_circuit_recovers_before_recovery_timeout(self):
        """
        Pre-emptive health check should reset the circuit breaker
        *before* recovery_timeout would normally allow a request through.
        """
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=60.0,  # very long — would normally need 60s
        ))
        cb.record_failure()  # OPEN — would block for 60s

        ping_fn = MagicMock(return_value=True)
        self.checker.register("test:model", ping_fn, cb)

        # Run a single check round — should recover immediately.
        self.checker.check_once()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        # allow_request should return True right away.
        self.assertTrue(cb.allow_request())
        ping_fn.assert_called_once()

    def test_circuit_stays_open_if_still_down(self):
        """If the provider is still down, the circuit stays OPEN."""
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=999.0,  # extremely long
        ))
        cb.record_failure()  # OPEN

        ping_fn = MagicMock(return_value=False)
        self.checker.register("test:model", ping_fn, cb)

        self.checker.check_once()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())

    def test_background_recovers_multiple_circuits(self):
        """Multiple OPEN circuit breakers can be recovered in one round."""
        cbs = []
        pings = []
        for i in range(5):
            cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
            cb.record_failure()  # OPEN
            ping = MagicMock(return_value=True)
            self.checker.register(f"p{i}:model", ping, cb)
            cbs.append(cb)
            pings.append(ping)

        self.checker.start()
        time.sleep(0.15)
        self.checker.stop()

        for i, cb in enumerate(cbs):
            self.assertEqual(
                cb.state, CircuitState.CLOSED,
                f"circuit {i} should be CLOSED after recovery",
            )
            self.assertGreaterEqual(pings[i].call_count, 1)


if __name__ == "__main__":
    unittest.main()