"""
Resilience layer for LLM calls — Retry, Circuit Breaker, Fallback, Idempotency.

Provides:
  - :class:`RetryConfig` — exponential backoff with jitter (tenacity-style).
  - :class:`CircuitBreaker` — state machine (closed → open → half-open).
  - :class:`IdempotencyManager` — idempotency keys for safe retries.
  - :class:`FallbackProviderChain` — multi-provider fallback chain.
  - :func:`resilient_call` — unified decorator wrapping all resilience patterns.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Retry with exponential backoff + jitter (tenacity-style)
# ---------------------------------------------------------------------------


@dataclass
class RetryConfig:
    """Configuration for retry behaviour."""

    max_retries: int = 3
    min_backoff: float = 1.0       # seconds
    max_backoff: float = 60.0      # seconds
    jitter_factor: float = 0.1     # 10% random jitter
    backoff_multiplier: float = 2.0
    retryable_exceptions: Tuple[type, ...] = (
        ConnectionError,
        TimeoutError,
        IOError,
    )


def compute_backoff(attempt: int, config: RetryConfig) -> float:
    """
    Compute exponential backoff with jitter for a given attempt number.

    Args:
        attempt: Current attempt number (1-based).
        config: Retry configuration.

    Returns:
        Sleep time in seconds.
    """
    delay = min(
        config.min_backoff * (config.backoff_multiplier ** (attempt - 1)),
        config.max_backoff,
    )
    jitter = delay * config.jitter_factor * random.random()
    return delay + jitter


def retry_call(
    fn: Callable[..., T],
    *args: Any,
    retry_config: Optional[RetryConfig] = None,
    is_retryable: Optional[Callable[[Exception], bool]] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    **kwargs: Any,
) -> T:
    """
    Call *fn* with retry, exponential backoff, and jitter (tenacity-style).

    Args:
        fn: Callable to invoke.
        *args: Positional args for fn.
        retry_config: Retry configuration (default: RetryConfig()).
        is_retryable: Optional predicate to determine if an exception is retryable.
                      If None, uses retry_config.retryable_exceptions.
        on_retry: Optional callback invoked before each retry.
        **kwargs: Keyword args for fn.

    Returns:
        The result of fn.

    Raises:
        The last exception encountered after exhausting retries.
    """
    cfg = retry_config or RetryConfig()

    if is_retryable is None:
        def _is_retryable(exc: Exception) -> bool:
            return isinstance(exc, cfg.retryable_exceptions)
        is_retryable = _is_retryable

    last_exc: Optional[Exception] = None

    for attempt in range(1, cfg.max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if not is_retryable(exc):
                raise  # Non-retryable → re-raise immediately

            if attempt < cfg.max_retries:
                backoff = compute_backoff(attempt, cfg)
                if on_retry:
                    on_retry(attempt, exc, backoff)
                logger.warning(
                    "Retry %d/%d failed: %s — backing off %.2fs",
                    attempt, cfg.max_retries, exc, backoff,
                )
                time.sleep(backoff)
            else:
                logger.error("All %d retries exhausted: %s", cfg.max_retries, exc)

    assert last_exc is not None  # guaranteed by loop
    raise last_exc


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitState(Enum):
    CLOSED = auto()       # Normal operation
    OPEN = auto()         # Failing — fast-fail
    HALF_OPEN = auto()    # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5         # failures before open
    recovery_timeout: float = 30.0     # seconds before half-open
    half_open_max_calls: int = 3       # calls allowed in half-open
    consecutive_successes_to_close: int = 2  # successes to close half-open


class CircuitBreaker:
    """
    Thread-safe circuit breaker for LLM provider calls.

    States:
        CLOSED → OPEN (on failure_threshold failures)
        OPEN → HALF_OPEN (after recovery_timeout)
        HALF_OPEN → CLOSED (on consecutive_successes_to_close successes)
        HALF_OPEN → OPEN (on any failure)
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    def allow_request(self) -> bool:
        """
        Check if a request should be allowed through the circuit.

        Thread-safe.
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed.
                if time.monotonic() - self._last_failure_time >= self.config.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count = 0
                    logger.info("Circuit breaker: OPEN → HALF_OPEN (recovery timeout elapsed)")
                    return True
                return False

            # HALF_OPEN: allow limited calls.
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.consecutive_successes_to_close:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._half_open_calls = 0
                    logger.info("Circuit breaker: HALF_OPEN → CLOSED (recovered)")
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # reset on success

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._half_open_calls = 0
                self._success_count = 0
                logger.warning("Circuit breaker: HALF_OPEN → OPEN (failure)")
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "Circuit breaker: CLOSED → OPEN (%d failures)",
                        self.config.failure_threshold,
                    )

    def reset(self) -> None:
        """Manually reset circuit to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._last_failure_time = 0.0
            logger.info("Circuit breaker: manually reset to CLOSED")


# ---------------------------------------------------------------------------
# Idempotency Keys
# ---------------------------------------------------------------------------


class IdempotencyManager:
    """
    Idempotency key manager for safe retries.

    Generates deterministic idempotency keys from (provider, model, messages)
    and tracks which requests have already been completed.
    """

    def __init__(self, ttl: float = 3600.0):
        """
        Args:
            ttl: Time-to-live for completed keys in seconds.
        """
        self._lock = threading.Lock()
        self._completed: Dict[str, Tuple[float, Any]] = {}  # key → (timestamp, result)
        self._in_flight: Dict[str, float] = {}  # key → timestamp
        self._ttl = ttl

    @staticmethod
    def make_key(
        provider: str,
        model: str,
        messages: List[Dict[str, str]],
        **extra: Any,
    ) -> str:
        """
        Generate a deterministic idempotency key.

        Args:
            provider: Provider name (e.g. "groq", "openai").
            model: Model name.
            messages: The messages payload.
            **extra: Any extra context (e.g. temperature, max_tokens).

        Returns:
            A hex string key.
        """
        payload = {
            "provider": provider,
            "model": model,
            "messages": messages,
            **extra,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def is_completed(self, key: str) -> bool:
        """Check if a request with this key has already completed successfully."""
        with self._lock:
            return key in self._completed

    def get_completed_result(self, key: str) -> Optional[Any]:
        """Get the cached result for a completed idempotency key."""
        with self._lock:
            entry = self._completed.get(key)
            if entry is None:
                return None
            ts, result = entry
            if time.monotonic() - ts > self._ttl:
                del self._completed[key]
                return None
            return result

    def mark_started(self, key: str) -> bool:
        """
        Mark a request as in-flight. Returns False if already in-flight.

        This prevents duplicate concurrent requests.
        """
        with self._lock:
            if key in self._in_flight:
                return False  # already in progress
            self._in_flight[key] = time.monotonic()
            return True

    def mark_completed(self, key: str, result: Any) -> None:
        """Mark a request as completed and cache the result."""
        with self._lock:
            self._completed[key] = (time.monotonic(), result)
            self._in_flight.pop(key, None)

    def mark_failed(self, key: str) -> None:
        """Remove a key from in-flight tracking on failure."""
        with self._lock:
            self._in_flight.pop(key, None)

    def cleanup(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        now = time.monotonic()
        with self._lock:
            expired = [k for k, (ts, _) in self._completed.items() if now - ts > self._ttl]
            for k in expired:
                del self._completed[k]
            # Also clean stale in-flight entries.
            stale = [k for k, ts in self._in_flight.items() if now - ts > self._ttl]
            for k in stale:
                del self._in_flight[k]
        return len(expired) + len(stale)


# ---------------------------------------------------------------------------
# Fallback Provider Chain
# ---------------------------------------------------------------------------


class ProviderNotAvailableError(Exception):
    """Raised when no provider in the fallback chain is available."""


@dataclass
class FallbackTarget:
    """A single target in the fallback chain."""

    provider_name: str
    model: str
    api_key: str = ""
    base_url: str = ""
    timeout: int = 30
    max_tokens: int = 4096
    temperature: float = 0.7


class FallbackProviderChain:
    """
    Chain of fallback providers for LLM calls.

    Attempts each provider in order, falling back to the next on failure.
    Optionally uses a circuit breaker for each target.

    When a *health_checker* is provided, all circuit breakers are automatically
    registered for pre-emptive health checks (the health checker periodically
    pings OPEN providers and closes the circuit when they recover).
    """

    def __init__(
        self,
        targets: List[FallbackTarget],
        use_circuit_breaker: bool = True,
        idempotency_manager: Optional[IdempotencyManager] = None,
        health_checker: Optional[Any] = None,
    ):
        """
        Args:
            targets: Ordered list of fallback targets.
            use_circuit_breaker: Whether to use circuit breakers per target.
            idempotency_manager: Optional idempotency manager.
            health_checker: Optional :class:`HealthChecker` instance for
                pre-emptive circuit breaker recovery.
        """
        self.targets = targets
        self.use_circuit_breaker = use_circuit_breaker
        self.idempotency_manager = idempotency_manager or IdempotencyManager()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        self._health_checker = health_checker

    def _get_circuit_breaker(self, target: FallbackTarget) -> CircuitBreaker:
        key = f"{target.provider_name}:{target.model}"
        with self._lock:
            if key not in self._circuit_breakers:
                cb = CircuitBreaker()
                self._circuit_breakers[key] = cb
                # Register with health checker if available.
                if self._health_checker is not None and self.use_circuit_breaker:
                    self._health_checker.register(key, self._build_ping_fn(target), cb)
            return self._circuit_breakers[key]

    @staticmethod
    def _build_ping_fn(target: FallbackTarget) -> Callable[[], bool]:
        """
        Build a lightweight health-check ping function for a target.

        This sends an empty messages list to the provider's API and checks
        whether the call raises an exception.  Subclasses may override to
        provide a cheaper probe (e.g. a dedicated /health endpoint).
        """
        def ping() -> bool:
            try:
                # Import here to avoid circular dependency.
                from nexus.core.providers import create_provider, ProviderConfig
                config = ProviderConfig(
                    name=target.provider_name,
                    api_key=target.api_key,
                    model=target.model,
                    base_url=target.base_url,
                    timeout=min(target.timeout, 10),  # short timeout for health checks
                    max_tokens=1,
                    temperature=0.0,
                )
                provider = create_provider(config)
                # Send a minimal ping — empty messages list.
                result = provider.generate([])
                # Check result doesn't contain an error pattern.
                text = result.get("text", "")
                if not text or text.startswith("["):
                    return False
                return True
            except Exception:
                return False
        return ping

    def call(
        self,
        messages: List[Dict[str, str]],
        make_call: Callable[[FallbackTarget], Any],
        idempotency_extra: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, FallbackTarget]:
        """
        Call a provider, falling back through the chain.

        Args:
            messages: The messages payload.
            make_call: A callable that takes a FallbackTarget and returns the result.
            idempotency_extra: Extra context for idempotency key generation.

        Returns:
            ``(result, target)`` — the result and which target succeeded.

        Raises:
            ProviderNotAvailableError: If all providers fail.
        """
        # Generate idempotency key.
        extra = idempotency_extra or {}
        key = IdempotencyManager.make_key(
            "fallback_chain", str([t.model for t in self.targets]),
            messages, **extra,
        )

        # Check if already completed (idempotency).
        if self.idempotency_manager.is_completed(key):
            cached = self.idempotency_manager.get_completed_result(key)
            if cached is not None:
                logger.debug("Idempotency hit for key %s...", key[:12])
                return cached, self.targets[0]

        # Try to mark as started.
        if not self.idempotency_manager.mark_started(key):
            logger.debug("Request already in-flight for key %s...", key[:12])
            # Wait briefly then check completed.
            time.sleep(0.5)
            cached = self.idempotency_manager.get_completed_result(key)
            if cached is not None:
                return cached, self.targets[0]

        last_error: Optional[Exception] = None

        for i, target in enumerate(self.targets):
            # Check circuit breaker.
            if self.use_circuit_breaker:
                cb = self._get_circuit_breaker(target)
                if not cb.allow_request():
                    logger.warning(
                        "Circuit breaker OPEN for %s/%s, skipping",
                        target.provider_name, target.model,
                    )
                    continue

            try:
                result = make_call(target)

                # Record success in circuit breaker.
                if self.use_circuit_breaker:
                    cb.record_success()

                # Mark as completed.
                self.idempotency_manager.mark_completed(key, (result, target))
                return result, target

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Fallback %d/%d (%s/%s) failed: %s",
                    i + 1, len(self.targets),
                    target.provider_name, target.model, exc,
                )

                # Record failure in circuit breaker.
                if self.use_circuit_breaker:
                    cb.record_failure()

                # Continue to next target.
                continue

        # All providers failed.
        self.idempotency_manager.mark_failed(key)

        if last_error:
            raise ProviderNotAvailableError(
                f"All {len(self.targets)} providers failed. Last error: {last_error}"
            ) from last_error
        raise ProviderNotAvailableError("No providers available in fallback chain")


# ---------------------------------------------------------------------------
# Unified resilient call
# ---------------------------------------------------------------------------


@dataclass
class ResilienceConfig:
    """Unified resilience configuration."""

    retry: RetryConfig = field(default_factory=RetryConfig)
    circuit_breaker: Optional[CircuitBreakerConfig] = field(
        default_factory=CircuitBreakerConfig
    )
    use_idempotency: bool = True
    fallback_chain: Optional[FallbackProviderChain] = None


def resilient_call(
    fn: Callable[..., T],
    *args: Any,
    config: Optional[ResilienceConfig] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    idempotency_manager: Optional[IdempotencyManager] = None,
    idempotency_key: Optional[str] = None,
    is_retryable: Optional[Callable[[Exception], bool]] = None,
    **kwargs: Any,
) -> T:
    """
    Unified resilient call with retry + circuit breaker + idempotency.

    Order of operations:
      1. Check idempotency (if key provided).
      2. Check circuit breaker.
      3. Retry loop with exponential backoff.
      4. Record success/failure in circuit breaker.
      5. Cache result for idempotency.

    Args:
        fn: Callable to invoke.
        *args: Positional args for fn.
        config: Resilience configuration.
        circuit_breaker: Optional circuit breaker instance.
        idempotency_manager: Optional idempotency manager.
        idempotency_key: Optional idempotency key (auto-generated if None and manager provided).
        is_retryable: Optional predicate to determine retryable exceptions.
        **kwargs: Keyword args for fn.

    Returns:
        The result of fn.

    Raises:
        Exception from fn after all retries.
    """
    cfg = config or ResilienceConfig()

    # Idempotency check.
    if cfg.use_idempotency and idempotency_manager is not None:
        key = idempotency_key or IdempotencyManager.make_key(
            fn.__name__, str(args), **kwargs,
        )
        if idempotency_manager.is_completed(key):
            cached = idempotency_manager.get_completed_result(key)
            if cached is not None:
                logger.debug("Resilient call: idempotency hit for %s", key[:12])
                return cached  # type: ignore[return-value]

        idempotency_manager.mark_started(key)
    else:
        key = None
        idempotency_manager = None

    # Circuit breaker check.
    if circuit_breaker is not None:
        if not circuit_breaker.allow_request():
            raise ConnectionError(
                f"Circuit breaker OPEN — request blocked "
                f"(state: {circuit_breaker.state.name})"
            )

    try:
        result = retry_call(
            fn, *args,
            retry_config=cfg.retry,
            is_retryable=is_retryable,
            **kwargs,
        )

        # Record success.
        if circuit_breaker is not None:
            circuit_breaker.record_success()

        # Cache idempotency result.
        if key is not None and idempotency_manager is not None:
            idempotency_manager.mark_completed(key, result)

        return result

    except Exception as exc:
        # Record failure.
        if circuit_breaker is not None:
            circuit_breaker.record_failure()

        # Mark idempotency as failed.
        if key is not None and idempotency_manager is not None:
            idempotency_manager.mark_failed(key)

        raise