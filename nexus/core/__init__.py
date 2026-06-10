"""
Nexus core — resilience, providers, health checks, and agent logic.
"""

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

from nexus.core.health import (
    HealthChecker,
    HealthCheckConfig,
)

from nexus.core.tiny_fallback import (
    TinyFallbackResponder,
    emergency_fallback,
    try_ollama_tiny_fallback,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "FallbackProviderChain",
    "FallbackTarget",
    "HealthChecker",
    "HealthCheckConfig",
    "IdempotencyManager",
    "ProviderNotAvailableError",
    "ResilienceConfig",
    "RetryConfig",
    "TinyFallbackResponder",
    "emergency_fallback",
    "try_ollama_tiny_fallback",
    "compute_backoff",
    "resilient_call",
    "retry_call",
]
