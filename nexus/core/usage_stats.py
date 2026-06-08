"""
Persistent usage statistics for Nexus.

Tracks API calls, tokens consumed, errors encountered, and session data
across all Nexus invocations.  Data is stored in a lightweight JSON file
inside the Nexus directory so it survives restarts.

Usage::

    from nexus.core.usage_stats import UsageStats

    stats = UsageStats()
    stats.record_request(provider="groq", model="llama-3.3-70b-versatile",
                         prompt_tokens=150, completion_tokens=300, total_tokens=450)
    stats.record_error(provider="groq", error_type="rate_limit")
    stats.save()

    summary = stats.get_summary()
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Approximate cost per 1K tokens (USD) — used for cost estimation.
# These are rough estimates; actual pricing may vary.
_COST_PER_1K_TOKENS: Dict[str, Dict[str, float]] = {
    "groq": {
        "prompt": 0.05,
        "completion": 0.10,
    },
    "openai": {
        "prompt": 0.0025,   # gpt-4o average
        "completion": 0.010,
    },
    "anthropic": {
        "prompt": 0.003,
        "completion": 0.015,
    },
    "ollama": {
        "prompt": 0.0,
        "completion": 0.0,
    },
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class UsageStats:
    """Persistent usage statistics for the Nexus application."""

    # --- Aggregate counters ---
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_errors: int = 0

    # --- Per-provider stats ---
    provider_requests: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    provider_prompt_tokens: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    provider_completion_tokens: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    provider_errors: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # --- Per-model stats ---
    model_requests: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    model_tokens: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # --- Error breakdown ---
    error_types: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # --- Session tracking ---
    first_used: str = ""
    last_used: str = ""
    total_sessions: int = 0

    # --- File path (transient, not serialized) ---
    _filepath: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        from nexus.core.paths import NEXUS_DIR

        if not self._filepath:
            self._filepath = os.path.join(NEXUS_DIR, "usage_stats.json")

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_request(
        self,
        provider: str = "",
        model: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """Record a successful API request."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.first_used:
            self.first_used = now
        self.last_used = now

        self.total_requests += 1
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += total_tokens

        if provider:
            self.provider_requests[provider] += 1
            self.provider_prompt_tokens[provider] += prompt_tokens
            self.provider_completion_tokens[provider] += completion_tokens

        if model:
            self.model_requests[model] += 1
            self.model_tokens[model] += total_tokens

    def record_error(
        self,
        provider: str = "",
        error_type: str = "unknown",
    ) -> None:
        """Record an API error."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.first_used:
            self.first_used = now
        self.last_used = now

        self.total_errors += 1
        if provider:
            self.provider_errors[provider] += 1
        self.error_types[error_type] += 1

    def record_session(self) -> None:
        """Record a new session start."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.first_used:
            self.first_used = now
        self.last_used = now
        self.total_sessions += 1

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    def estimated_cost(self, provider: Optional[str] = None) -> float:
        """
        Estimate total cost in USD based on token usage.

        Args:
            provider: If given, estimate cost only for this provider.

        Returns:
            Estimated cost in USD.
        """
        total_cost = 0.0

        providers = [provider] if provider else set(
            list(self.provider_prompt_tokens.keys())
            + list(self.provider_completion_tokens.keys())
        )

        for prov in providers:
            costs = _COST_PER_1K_TOKENS.get(prov, _COST_PER_1K_TOKENS["openai"])
            p_tokens = self.provider_prompt_tokens.get(prov, 0)
            c_tokens = self.provider_completion_tokens.get(prov, 0)
            total_cost += (p_tokens / 1000.0) * costs["prompt"]
            total_cost += (c_tokens / 1000.0) * costs["completion"]

        return total_cost

    # ------------------------------------------------------------------
    # Summary / formatting
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """Return a dictionary summary of all stats."""
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_errors": self.total_errors,
            "estimated_cost_usd": round(self.estimated_cost(), 4),
            "providers": {
                prov: {
                    "requests": self.provider_requests.get(prov, 0),
                    "prompt_tokens": self.provider_prompt_tokens.get(prov, 0),
                    "completion_tokens": self.provider_completion_tokens.get(prov, 0),
                    "errors": self.provider_errors.get(prov, 0),
                    "cost_usd": round(self.estimated_cost(prov), 4),
                }
                for prov in sorted(set(
                    list(self.provider_requests.keys())
                    + list(self.provider_prompt_tokens.keys())
                ))
            },
            "top_models": sorted(
                self.model_tokens.items(), key=lambda x: -x[1]
            )[:5],
            "error_breakdown": dict(self.error_types),
            "first_used": self.first_used,
            "last_used": self.last_used,
            "total_sessions": self.total_sessions,
        }

    def format_summary_rich(self) -> str:
        """Format a Rich-markup summary string for terminal display."""
        lines: List[str] = []

        # Overall
        lines.append(f"[bold]Всего запросов:[/bold] {self.total_requests}")
        lines.append(
            f"[bold]Токенов использовано:[/bold] "
            f"{self.total_tokens:,} "
            f"[dim](prompt: {self.total_prompt_tokens:,}, "
            f"completion: {self.total_completion_tokens:,})[/dim]"
        )
        cost = self.estimated_cost()
        lines.append(f"[bold]Примерная стоимость:[/bold] ${cost:.4f}")
        if self.total_errors:
            lines.append(
                f"[bold yellow]Ошибок:[/bold yellow] {self.total_errors}"
            )
        if self.total_sessions:
            lines.append(f"[bold]Сессий:[/bold] {self.total_sessions}")

        # Per-provider breakdown
        providers = sorted(set(
            list(self.provider_requests.keys())
            + list(self.provider_prompt_tokens.keys())
        ))
        if providers:
            lines.append("")
            lines.append("[bold cyan]По провайдерам:[/bold cyan]")
            for prov in providers:
                reqs = self.provider_requests.get(prov, 0)
                ptok = self.provider_prompt_tokens.get(prov, 0)
                ctok = self.provider_completion_tokens.get(prov, 0)
                errs = self.provider_errors.get(prov, 0)
                pcost = self.estimated_cost(prov)
                err_str = f" [yellow]⚠ {errs} ошибок[/yellow]" if errs else ""
                lines.append(
                    f"  {prov:12s}  "
                    f"запросов: {reqs:5d}  "
                    f"токенов: {ptok + ctok:>10,}  "
                    f"стоимость: ${pcost:.4f}"
                    f"{err_str}"
                )

        # Top models
        top = sorted(self.model_tokens.items(), key=lambda x: -x[1])[:5]
        if top:
            lines.append("")
            lines.append("[bold cyan]Топ модели:[/bold cyan]")
            for model, tokens in top:
                reqs = self.model_requests.get(model, 0)
                lines.append(f"  {model:30s}  {tokens:>10,} токенов  ({reqs} запросов)")

        # Error breakdown
        if self.error_types:
            lines.append("")
            lines.append("[bold cyan]Типы ошибок:[/bold cyan]")
            for etype, count in sorted(
                self.error_types.items(), key=lambda x: -x[1]
            ):
                lines.append(f"  {etype:25s}  {count}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist stats to the JSON file."""
        try:
            data = self._to_serializable()
            os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
            with open(self._filepath, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Failed to save usage stats: %s", e)

    def load(self) -> None:
        """Load stats from the JSON file (if it exists)."""
        if not os.path.isfile(self._filepath):
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh) or {}
            self._from_serializable(data)
        except Exception as e:
            logger.debug("Failed to load usage stats: %s", e)

    def _to_serializable(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "total_requests": self.total_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_errors": self.total_errors,
            "provider_requests": dict(self.provider_requests),
            "provider_prompt_tokens": dict(self.provider_prompt_tokens),
            "provider_completion_tokens": dict(self.provider_completion_tokens),
            "provider_errors": dict(self.provider_errors),
            "model_requests": dict(self.model_requests),
            "model_tokens": dict(self.model_tokens),
            "error_types": dict(self.error_types),
            "first_used": self.first_used,
            "last_used": self.last_used,
            "total_sessions": self.total_sessions,
        }

    def _from_serializable(self, data: Dict[str, Any]) -> None:
        """Restore from a JSON dict."""
        self.total_requests = data.get("total_requests", 0)
        self.total_prompt_tokens = data.get("total_prompt_tokens", 0)
        self.total_completion_tokens = data.get("total_completion_tokens", 0)
        self.total_tokens = data.get("total_tokens", 0)
        self.total_errors = data.get("total_errors", 0)
        self.first_used = data.get("first_used", "")
        self.last_used = data.get("last_used", "")
        self.total_sessions = data.get("total_sessions", 0)

        for k, v in data.get("provider_requests", {}).items():
            self.provider_requests[k] = v
        for k, v in data.get("provider_prompt_tokens", {}).items():
            self.provider_prompt_tokens[k] = v
        for k, v in data.get("provider_completion_tokens", {}).items():
            self.provider_completion_tokens[k] = v
        for k, v in data.get("provider_errors", {}).items():
            self.provider_errors[k] = v
        for k, v in data.get("model_requests", {}).items():
            self.model_requests[k] = v
        for k, v in data.get("model_tokens", {}).items():
            self.model_tokens[k] = v
        for k, v in data.get("error_types", {}).items():
            self.error_types[k] = v

    # ------------------------------------------------------------------
    # Singleton-like convenience
    # ------------------------------------------------------------------

    @classmethod
    def load_global(cls) -> "UsageStats":
        """Load (or create) the global usage stats instance."""
        stats = cls()
        stats.load()
        return stats


# Global singleton — lazily initialised
_global_stats: Optional[UsageStats] = None


def get_global_stats() -> UsageStats:
    """Return the global :class:`UsageStats` singleton, loading it if needed."""
    global _global_stats
    if _global_stats is None:
        _global_stats = UsageStats.load_global()
    return _global_stats


def record_request(
    provider: str = "",
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> None:
    """Convenience: record a request to the global stats."""
    stats = get_global_stats()
    stats.record_request(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    stats.save()


def record_error(provider: str = "", error_type: str = "unknown") -> None:
    """Convenience: record an error to the global stats."""
    stats = get_global_stats()
    stats.record_error(provider=provider, error_type=error_type)
    stats.save()