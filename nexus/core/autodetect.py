"""
Auto-detect the best available provider and model.

Probes environment variables for API keys and checks Ollama availability
to recommend (or auto-select) the optimal provider + model combination.

Usage::

    from nexus.core.autodetect import detect_best_provider, detect_available_providers

    best = detect_best_provider()
    print(best)  # {"provider": "groq", "model": "llama-3.3-70b-versatile", ...}
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexus.core.providers import DEFAULT_MODELS, FALLBACK_MODELS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ProviderProbe:
    """Result of probing a single provider."""

    name: str
    available: bool = False
    api_key: bool = False
    sdk_installed: bool = False
    model: str = ""
    base_url: str = ""
    error: str = ""
    priority: int = 0  # higher = better


@dataclass
class AutoDetectResult:
    """Full auto-detect result."""

    best_provider: str = "groq"
    best_model: str = ""
    available_providers: List[ProviderProbe] = field(default_factory=list)
    detection_log: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SDK detection helpers
# ---------------------------------------------------------------------------


def _is_sdk_installed(name: str) -> bool:
    """Check if a Python package is importable."""
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _check_ollama_running(host: str = "http://localhost:11434") -> bool:
    """Check if Ollama is reachable via HTTP."""
    try:
        import urllib.request
        import urllib.error

        req = urllib.request.Request(f"{host}/api/tags", method="GET")
        resp = urllib.request.urlopen(req, timeout=3)
        resp.read()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Provider probing
# ---------------------------------------------------------------------------

# Priority weights: higher = preferred when multiple providers are available.
_PROVIDER_PRIORITY: Dict[str, int] = {
    "groq": 40,      # Fast + free tier
    "anthropic": 30,  # High quality
    "openai": 25,     # Widely used
    "ollama": 15,     # Local, no cost
}


def _probe_groq() -> ProviderProbe:
    """Probe Groq availability."""
    probe = ProviderProbe(name="groq")
    key = os.getenv("GROQ_API_KEY", "").strip()
    probe.api_key = bool(key)
    probe.sdk_installed = _is_sdk_installed("groq")
    probe.model = DEFAULT_MODELS.get("groq", "")
    probe.available = probe.api_key and probe.sdk_installed
    probe.priority = _PROVIDER_PRIORITY["groq"] if probe.available else 0
    if probe.available:
        probe.priority += 5  # bonus: fast inference
    return probe


def _probe_openai() -> ProviderProbe:
    """Probe OpenAI availability."""
    probe = ProviderProbe(name="openai")
    key = os.getenv("OPENAI_API_KEY", "").strip()
    probe.api_key = bool(key)
    probe.sdk_installed = _is_sdk_installed("openai")
    probe.model = DEFAULT_MODELS.get("openai", "")
    # Check for custom base URL (e.g. Azure, OpenRouter)
    base = os.getenv("OPENAI_BASE_URL", "").strip()
    if base:
        probe.base_url = base
    probe.available = probe.api_key and probe.sdk_installed
    probe.priority = _PROVIDER_PRIORITY["openai"] if probe.available else 0
    return probe


def _probe_anthropic() -> ProviderProbe:
    """Probe Anthropic availability."""
    probe = ProviderProbe(name="anthropic")
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    probe.api_key = bool(key)
    probe.sdk_installed = _is_sdk_installed("anthropic")
    probe.model = DEFAULT_MODELS.get("anthropic", "")
    probe.available = probe.api_key and probe.sdk_installed
    probe.priority = _PROVIDER_PRIORITY["anthropic"] if probe.available else 0
    return probe


def _probe_ollama() -> ProviderProbe:
    """Probe local Ollama availability."""
    probe = ProviderProbe(name="ollama")
    probe.sdk_installed = _is_sdk_installed("ollama")
    probe.model = DEFAULT_MODELS.get("ollama", "")
    probe.api_key = True  # Ollama doesn't need a key
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    probe.base_url = host
    running = _check_ollama_running(host)
    probe.available = probe.sdk_installed and running
    probe.priority = _PROVIDER_PRIORITY["ollama"] if probe.available else 0
    if not running and probe.sdk_installed:
        probe.error = "Ollama SDK installed but server not reachable"
    elif not probe.sdk_installed:
        probe.error = "Ollama SDK not installed"
    return probe


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_available_providers() -> List[ProviderProbe]:
    """
    Probe all known providers and return a list of :class:`ProviderProbe`
    objects, sorted by priority (best first).
    """
    probes = [
        _probe_groq(),
        _probe_openai(),
        _probe_anthropic(),
        _probe_ollama(),
    ]
    # Sort: available first, then by priority descending
    probes.sort(key=lambda p: (-int(p.available), -p.priority))
    return probes


def detect_best_provider(
    preferred: Optional[str] = None,
) -> AutoDetectResult:
    """
    Detect the best available provider and model.

    Args:
        preferred: If given, prefer this provider (if available).

    Returns:
        An :class:`AutoDetectResult` with the recommended provider/model.
    """
    result = AutoDetectResult()
    probes = detect_available_providers()
    result.available_providers = probes

    available = [p for p in probes if p.available]
    result.detection_log.append(
        f"Probed {len(probes)} providers, {len(available)} available"
    )

    if not available:
        result.detection_log.append("No providers available — using defaults")
        result.best_provider = "groq"
        result.best_model = DEFAULT_MODELS.get("groq", "")
        return result

    # If a preferred provider is requested and available, use it
    if preferred:
        for p in available:
            if p.name == preferred:
                result.best_provider = p.name
                result.best_model = p.model
                result.detection_log.append(
                    f"Using preferred provider: {p.name} ({p.model})"
                )
                return result
        result.detection_log.append(
            f"Preferred provider '{preferred}' not available, auto-selecting"
        )

    # Auto-select the best available provider
    best = available[0]
    result.best_provider = best.name
    result.best_model = best.model
    result.detection_log.append(
        f"Auto-selected: {best.name} ({best.model}, priority={best.priority})"
    )

    return result


def get_available_providers_summary() -> str:
    """
    Return a short human-readable summary of available providers.

    Useful for the ``nexus status`` command.
    """
    probes = detect_available_providers()
    lines: List[str] = []
    for p in probes:
        status = "✅" if p.available else "❌"
        sdk = "SDK ✓" if p.sdk_installed else "SDK ✗"
        key = "Key ✓" if p.api_key else "Key ✗"
        extra = ""
        if p.name == "ollama" and p.sdk_installed and not p.available:
            extra = f" ({p.error})"
        elif p.name == "ollama" and p.available:
            extra = " (local)"
        lines.append(f"  {status} {p.name:12s}  {sdk}  {key}  {p.model}{extra}")
    return "\n".join(lines)