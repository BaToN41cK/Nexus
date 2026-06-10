"""
Pre-emptive health checker for provider circuit breakers.

Automatically pings OPEN providers in the background and resets their
circuit breaker when they recover — no need to wait for *recovery_timeout*
+ a real user request.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Protocol, Tuple

from nexus.core.resilience import CircuitBreaker, CircuitState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Health-check protocol
# ---------------------------------------------------------------------------


class PingFn(Protocol):
    """
    A lightweight health-check callable.

    Should return ``True`` if the provider is healthy, ``False`` otherwise.
    Must NOT raise — exceptions are caught and treated as unhealthy.
    """

    def __call__(self) -> bool:
        ...


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class HealthCheckConfig:
    """Configuration for the pre-emptive health checker."""

    def __init__(
        self,
        check_interval: float = 15.0,
    ):
        """
        Args:
            check_interval: Seconds between health-check rounds.
        """
        self.check_interval = check_interval


# ---------------------------------------------------------------------------
# Health Checker
# ---------------------------------------------------------------------------


class HealthChecker:
    """
    Background health checker that periodically pings OPEN circuit breakers.

    When a ping succeeds for a provider whose circuit breaker is in OPEN state,
    the circuit breaker is immediately reset to CLOSED — bypassing the normal
    *recovery_timeout* + *half-open* + *consecutive successes* dance.

    Threading model
    ---------------
    The checker runs a single daemon thread.  Each round iterates over all
    registered providers and pings only those whose circuit breaker is OPEN.
    Liveness probes are spaced ``check_interval`` seconds apart.
    """

    def __init__(self, config: Optional[HealthCheckConfig] = None):
        self.config = config or HealthCheckConfig()

        # provider_id → (ping_fn, circuit_breaker)
        self._providers: Dict[str, Tuple[PingFn, CircuitBreaker]] = {}

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        provider_id: str,
        ping_fn: PingFn,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        """
        Register a provider for health checking.

        Args:
            provider_id: Unique identifier (e.g. ``"groq:llama-3.3-70b"``).
            ping_fn: Callable that returns True when the provider is healthy.
            circuit_breaker: The :class:`CircuitBreaker` to reset on recovery.
        """
        with self._lock:
            self._providers[provider_id] = (ping_fn, circuit_breaker)
            logger.debug("HealthChecker: registered %s", provider_id)

    def unregister(self, provider_id: str) -> None:
        """Remove a previously registered provider."""
        with self._lock:
            self._providers.pop(provider_id, None)
            logger.debug("HealthChecker: unregistered %s", provider_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background checking thread (no-op if already running)."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="health-checker",
            daemon=True,
        )
        self._thread.start()
        logger.info("HealthChecker: started (interval=%.1fs)", self.config.check_interval)

    def stop(self, timeout: float = 5.0) -> None:
        """
        Signal the background thread to stop and wait for it.

        Args:
            timeout: Seconds to wait for thread completion.
        """
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            logger.info("HealthChecker: stopped")

    def is_running(self) -> bool:
        """Return *True* if the background thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Single-round helpers (also useful for tests)
    # ------------------------------------------------------------------

    def check_once(self) -> int:
        """
        Run a single health-check round against all **OPEN** circuit breakers.

        Returns:
            Number of circuit breakers that were reset (i.e. recovered).
        """
        recovered = 0

        with self._lock:
            snapshot = list(self._providers.items())

        for provider_id, (ping_fn, cb) in snapshot:
            with cb._lock:
                if cb._state != CircuitState.OPEN:
                    continue  # only probe OPEN circuits

            recovered += self._ping_and_reset(provider_id, ping_fn, cb)

        return recovered

    def _ping_and_reset(
        self,
        provider_id: str,
        ping_fn: PingFn,
        cb: CircuitBreaker,
    ) -> int:
        """Ping a single provider and reset its circuit breaker on success."""
        try:
            healthy = ping_fn()
        except Exception as exc:
            logger.debug("HealthChecker: ping %s failed with exception: %s", provider_id, exc)
            return 0

        if healthy:
            with cb._lock:
                if cb._state == CircuitState.OPEN:
                    cb._state = CircuitState.CLOSED
                    cb._failure_count = 0
                    cb._success_count = 0
                    cb._half_open_calls = 0
                    cb._last_failure_time = 0.0
                    logger.info(
                        "HealthChecker: %s recovered — circuit breaker CLOSED (pre-emptive)",
                        provider_id,
                    )
                    return 1
        else:
            logger.debug("HealthChecker: ping %s returned unhealthy", provider_id)

        return 0

    def _run_loop(self) -> None:
        """Main loop executed in the background thread."""
        while not self._stop_event.is_set():
            try:
                recovered = self.check_once()
                if recovered:
                    logger.info("HealthChecker: %d circuit(s) recovered this round", recovered)
            except Exception:
                logger.exception("HealthChecker: unexpected error in check round")

            # Sleep with early-exit on stop.
            self._stop_event.wait(self.config.check_interval)