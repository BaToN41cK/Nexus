"""
Validated configuration for Nexus.

Defines :class:`NexusConfig` — a :func:`dataclasses.dataclass` that
describes the full set of options Nexus understands.  The class
performs type coercion and range checks in :meth:`__post_init__` so
that any malformed YAML (or env override) is reported with a clear
``ConfigError`` instead of silently falling back to a default.

The dataclass-based approach was chosen over a schema library so
that Nexus has **no new runtime dependencies**.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ConfigError(ValueError):
    """Raised when the configuration file is malformed or invalid."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_PROVIDERS: List[str] = ["groq", "openai", "anthropic", "ollama"]
VALID_BACKENDS: List[str] = ["auto", "duckduckgo", "tavily", "searxng", "bing"]
VALID_EMBEDDING_BACKENDS: List[str] = ["sentence-transformers", "openai", "ollama"]
VALID_VECTOR_STORE_BACKENDS: List[str] = ["faiss", "chroma"]

# Default model for each provider — used for auto-detection when the
# provider changes but the model is still the default from another one.
_DEFAULT_MODEL_BY_PROVIDER: Dict[str, str] = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "ollama": "llama3.2",
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class RAGConfig:
    """Configuration for RAG (Retrieval-Augmented Generation)."""

    enabled: bool = False
    embedding_backend: str = "sentence-transformers"
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_store_backend: str = "faiss"
    index_path: str = "~/.nexus/rag/index.faiss"
    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k_initial: int = 20
    top_k_after_rerank: int = 5
    use_bm25: bool = True
    use_mmr: bool = True
    use_cross_encoder: bool = False

    def __post_init__(self) -> None:
        if self.embedding_backend not in VALID_EMBEDDING_BACKENDS:
            raise ConfigError(
                f"rag.embedding_backend must be one of {VALID_EMBEDDING_BACKENDS}, "
                f"got: {self.embedding_backend!r}"
            )
        if self.vector_store_backend not in VALID_VECTOR_STORE_BACKENDS:
            raise ConfigError(
                f"rag.vector_store_backend must be one of {VALID_VECTOR_STORE_BACKENDS}, "
                f"got: {self.vector_store_backend!r}"
            )
        if not (1 <= int(self.chunk_size) <= 10000):
            raise ConfigError(f"rag.chunk_size must be between 1 and 10000, got: {self.chunk_size!r}")
        if not (0 <= int(self.chunk_overlap) < int(self.chunk_size)):
            raise ConfigError(
                f"rag.chunk_overlap must be between 0 and chunk_size, "
                f"got: {self.chunk_overlap!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "embedding_backend": self.embedding_backend,
            "embedding_model": self.embedding_model,
            "vector_store_backend": self.vector_store_backend,
            "index_path": self.index_path,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "top_k_initial": self.top_k_initial,
            "top_k_after_rerank": self.top_k_after_rerank,
            "use_bm25": self.use_bm25,
            "use_mmr": self.use_mmr,
            "use_cross_encoder": self.use_cross_encoder,
        }


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    consecutive_successes_to_close: int = 2

    def __post_init__(self) -> None:
        if int(self.failure_threshold) < 1:
            raise ConfigError(
                f"resilience.circuit_breaker.failure_threshold must be >= 1, "
                f"got: {self.failure_threshold!r}"
            )
        if float(self.recovery_timeout) < 0:
            raise ConfigError(
                f"resilience.circuit_breaker.recovery_timeout must be >= 0, "
                f"got: {self.recovery_timeout!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "half_open_max_calls": self.half_open_max_calls,
            "consecutive_successes_to_close": self.consecutive_successes_to_close,
        }


@dataclass
class ResilienceRetryConfig:
    """Configuration for retry behaviour."""

    max_retries: int = 3
    min_backoff: float = 1.0
    max_backoff: float = 60.0
    backoff_multiplier: float = 2.0
    jitter_factor: float = 0.1

    def __post_init__(self) -> None:
        if int(self.max_retries) < 0:
            raise ConfigError(f"resilience.retry.max_retries must be >= 0, got: {self.max_retries!r}")
        if float(self.min_backoff) < 0:
            raise ConfigError(f"resilience.retry.min_backoff must be >= 0, got: {self.min_backoff!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "min_backoff": self.min_backoff,
            "max_backoff": self.max_backoff,
            "backoff_multiplier": self.backoff_multiplier,
            "jitter_factor": self.jitter_factor,
        }


@dataclass
class ResilienceConfig:
    """Configuration for resilience features."""

    retry: ResilienceRetryConfig = field(default_factory=ResilienceRetryConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    idempotency_ttl: int = 3600

    def to_dict(self) -> Dict[str, Any]:
        return {
            "retry": self.retry.to_dict(),
            "circuit_breaker": self.circuit_breaker.to_dict(),
            "idempotency_ttl": self.idempotency_ttl,
        }


@dataclass
class WebSearchConfig:
    """Configuration for the :class:`WebSearcher` facade."""

    enabled: bool = False
    backend: str = "auto"
    max_results: int = 5
    fetch_top_n: int = 3
    timeout: int = 15
    cache_enabled: bool = True
    cache_ttl: int = 3600
    tavily_api_key: str = ""
    bing_api_key: str = ""
    searxng_url: str = ""

    def __post_init__(self) -> None:
        if self.backend not in VALID_BACKENDS:
            raise ConfigError(
                f"web_search.backend must be one of {VALID_BACKENDS}, "
                f"got: {self.backend!r}"
            )
        if not (1 <= int(self.max_results) <= 20):
            raise ConfigError(
                f"web_search.max_results must be between 1 and 20, "
                f"got: {self.max_results!r}"
            )
        if not (0 <= int(self.fetch_top_n) <= 10):
            raise ConfigError(
                f"web_search.fetch_top_n must be between 0 and 10, "
                f"got: {self.fetch_top_n!r}"
            )
        if int(self.timeout) <= 0:
            raise ConfigError(
                f"web_search.timeout must be > 0, got: {self.timeout!r}"
            )
        if int(self.cache_ttl) < 0:
            raise ConfigError(
                f"web_search.cache_ttl must be >= 0, got: {self.cache_ttl!r}"
            )


@dataclass
class NexusConfig:
    """
    Top-level Nexus configuration.

    All fields have sensible defaults — a missing or partial YAML will
    be filled in automatically.  Invalid values raise :class:`ConfigError`.
    """

    # --- Provider ---
    provider: str = "groq"
    groq_model: str = "llama-3.3-70b-versatile"
    base_url: str = ""

    # --- Generation ---
    timeout: int = 30
    max_tokens: int = 4096
    temperature: float = 0.7

    # --- Content loading ---
    max_content_length: int = 50000
    summarize_threshold: int = 40000

    # --- Cache ---
    cache_ttl: int = 3600
    max_cache_size_mb: int = 50
    max_retries: int = 3
    rate_limit: int = 5

    # --- Conversation ---
    conversation_history_size: int = 5
    react_max_iterations: int = 6

    # --- System prompt ---
    system_prompt: str = (
        "Ты — Nexus, продвинутый ИИ-ассистент-разработчик. Твоя главная задача — "
        "помогать пользователям с любыми вопросами по программированию, конфигурации, "
        "архитектуре и разработке в целом.\n\n"
        "ВАЖНЫЕ ПРАВИЛА:\n"
        "1. Отвечай ПОДРОБНО и РАЗВЁРНУТО. Не сокращай ответы до минимума — если вопрос "
        "заслуживает длинного ответа, дай длинный ответ с объяснениями.\n"
        "2. Всегда добавляй КОНТЕКСТ: объясняй ЗАЧЕМ что-то делается, какие есть "
        "альтернативы, какие подводные камни.\n"
        "3. Используй структурированный markdown-формат: заголовки, списки, блоки кода, "
        "таблицы, когда это уместно.\n"
        "4. Давай ПОЛНЫЕ примеры кода с комментариями, а не только фрагменты.\n"
        "5. Если вопрос подразумевает анализ — проводи его глубоко, выделяй ключевые "
        "моменты, плюсы/минусы, рекомендации.\n"
        "6. Отвечай на том же языке, на котором задан вопрос.\n"
        "7. Не бойся повторить важные моменты — лучше перестраховаться.\n"
        "8. Если что-то непонятно — задай уточняющий вопрос, а не давай "
        "поверхностный ответ.\n"
        "9. По возможности предлагай следующие шаги или расширяй тему."
    )

    # --- RAG (nested dataclass) ---
    rag: RAGConfig = field(default_factory=RAGConfig)

    # --- Resilience (nested dataclass) ---
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)

    # --- Web search (nested dataclass) ---
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        if self.provider not in VALID_PROVIDERS:
            raise ConfigError(
                f"provider must be one of {VALID_PROVIDERS}, got: {self.provider!r}"
            )
        # Auto-detect model: if the current model is a default for a *different*
        # provider, swap it to the correct default for the active provider.
        if self.groq_model:
            other_defaults = {
                prov: model
                for prov, model in _DEFAULT_MODEL_BY_PROVIDER.items()
                if prov != self.provider
            }
            if self.groq_model in other_defaults.values():
                new_model = _DEFAULT_MODEL_BY_PROVIDER.get(self.provider, self.groq_model)
                logger.info(
                    "Auto-switching model from '%s' to '%s' for provider '%s'",
                    self.groq_model, new_model, self.provider,
                )
                self.groq_model = new_model
        if not self.groq_model:
            raise ConfigError("groq_model must not be empty")
        if int(self.timeout) <= 0:
            raise ConfigError(f"timeout must be > 0, got: {self.timeout!r}")
        if not (1 <= int(self.max_tokens) <= 1_000_000):
            raise ConfigError(
                f"max_tokens must be between 1 and 1000000, got: {self.max_tokens!r}"
            )
        if not (0.0 <= float(self.temperature) <= 2.0):
            raise ConfigError(
                f"temperature must be between 0.0 and 2.0, got: {self.temperature!r}"
            )
        if int(self.max_content_length) <= 0:
            raise ConfigError(
                f"max_content_length must be > 0, got: {self.max_content_length!r}"
            )
        if int(self.summarize_threshold) < 0:
            raise ConfigError(
                f"summarize_threshold must be >= 0, got: {self.summarize_threshold!r}"
            )
        if int(self.cache_ttl) < 0:
            raise ConfigError(f"cache_ttl must be >= 0, got: {self.cache_ttl!r}")
        if int(self.max_cache_size_mb) <= 0:
            raise ConfigError(
                f"max_cache_size_mb must be > 0, got: {self.max_cache_size_mb!r}"
            )
        if int(self.max_retries) < 0:
            raise ConfigError(
                f"max_retries must be >= 0, got: {self.max_retries!r}"
            )
        if int(self.rate_limit) < 0:
            raise ConfigError(
                f"rate_limit must be >= 0, got: {self.rate_limit!r}"
            )
        if int(self.conversation_history_size) < 0:
            raise ConfigError(
                f"conversation_history_size must be >= 0, "
                f"got: {self.conversation_history_size!r}"
            )
        if int(self.react_max_iterations) < 1:
            raise ConfigError(
                f"react_max_iterations must be >= 1, "
                f"got: {self.react_max_iterations!r}"
            )

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def api_key_env_var(self) -> Optional[str]:
        """Return the env var name that holds the API key for this provider."""
        return {
            "groq": "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "ollama": None,
        }.get(self.provider)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain ``dict`` representation (suitable for YAML dump)."""
        out: Dict[str, Any] = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if isinstance(val, WebSearchConfig):
                out["web_search"] = {k: v for k, v in vars(val).items() if v != ""}
            elif isinstance(val, RAGConfig):
                out["rag"] = val.to_dict()
            elif isinstance(val, ResilienceConfig):
                out["resilience"] = val.to_dict()
            else:
                out[f.name] = val
        return out


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _coerce(value: Any, target: type) -> Any:
    """
    Best-effort coercion of *value* to *target* (only the types we need).
    Raises :class:`ConfigError` on failure.
    """
    if value is None:
        return None
    try:
        if target is bool:
            # ``bool`` is a subclass of ``int`` — handle it explicitly
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if target is int:
            return int(value)
        if target is float:
            return float(value)
        if target is str:
            return str(value)
    except (TypeError, ValueError) as e:
        raise ConfigError(
            f"expected {target.__name__}, got {value!r}: {e}"
        ) from e
    return value


def _parse_section(raw: Dict[str, Any]) -> NexusConfig:
    """
    Build a :class:`NexusConfig` from an untyped dict (e.g. loaded YAML).
    Unknown keys are dropped with a debug log.  Missing keys keep their
    defaults.  Type mismatches raise :class:`ConfigError`.
    """
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping, got: {type(raw).__name__}")

    known_scalar = {
        f.name: f.type for f in fields(NexusConfig)
        if f.name not in ("web_search", "rag", "resilience")
    }

    kwargs: Dict[str, Any] = {}
    for key, value in raw.items():
        if key in ("web_search", "rag", "resilience"):
            continue
        if key not in known_scalar:
            logger.debug("Ignoring unknown config key: %r", key)
            continue
        target = known_scalar[key]
        if target == "str" or target is str:
            kwargs[key] = _coerce(value, str)
        elif target == "int" or target is int:
            kwargs[key] = _coerce(value, int)
        elif target == "float" or target is float:
            kwargs[key] = _coerce(value, float)
        elif target == "bool" or target is bool:
            kwargs[key] = _coerce(value, bool)
        else:
            kwargs[key] = value

    # ---- Nested sections ----

    # Nested web_search section
    web_raw = raw.get("web_search") or {}
    if not isinstance(web_raw, dict):
        raise ConfigError(
            f"web_search must be a mapping, got: {type(web_raw).__name__}"
        )
    web_kwargs: Dict[str, Any] = {}
    ws_fields = {f.name: f.type for f in fields(WebSearchConfig)}
    for key, value in web_raw.items():
        if key not in ws_fields:
            logger.debug("Ignoring unknown web_search key: %r", key)
            continue
        target = ws_fields[key]
        if target == "bool" or target is bool:
            web_kwargs[key] = _coerce(value, bool)
        elif target == "int" or target is int:
            web_kwargs[key] = _coerce(value, int)
        elif target == "str" or target is str:
            web_kwargs[key] = _coerce(value, str)
        else:
            web_kwargs[key] = value

    # Fall back to environment variables for search provider keys.
    web_kwargs.setdefault("tavily_api_key", os.getenv("TAVILY_API_KEY", ""))
    web_kwargs.setdefault("bing_api_key", os.getenv("BING_API_KEY", ""))
    web_kwargs.setdefault("searxng_url", os.getenv("SEARXNG_URL", ""))

    # Nested rag section
    rag_raw = raw.get("rag") or {}
    rag_kwargs: Dict[str, Any] = {}
    if isinstance(rag_raw, dict):
        rag_fields = {f.name: f.type for f in fields(RAGConfig)}
        for key, value in rag_raw.items():
            if key not in rag_fields:
                logger.debug("Ignoring unknown rag key: %r", key)
                continue
            target = rag_fields[key]
            if target == "bool" or target is bool:
                rag_kwargs[key] = _coerce(value, bool)
            elif target == "int" or target is int:
                rag_kwargs[key] = _coerce(value, int)
            elif target == "str" or target is str:
                rag_kwargs[key] = _coerce(value, str)
            elif target == "float" or target is float:
                rag_kwargs[key] = _coerce(value, float)
            else:
                rag_kwargs[key] = value
    rag_config = RAGConfig(**rag_kwargs)

    # Nested resilience section
    resilience_raw = raw.get("resilience") or {}
    resilience_kwargs: Dict[str, Any] = {}
    if isinstance(resilience_raw, dict):
        # retry sub-section
        retry_raw = resilience_raw.get("retry") or {}
        retry_kwargs: Dict[str, Any] = {}
        if isinstance(retry_raw, dict):
            for key, value in retry_raw.items():
                if key in ("max_retries",):
                    retry_kwargs[key] = _coerce(value, int)
                elif key in ("min_backoff", "max_backoff", "backoff_multiplier", "jitter_factor"):
                    retry_kwargs[key] = _coerce(value, float)
                else:
                    retry_kwargs[key] = value
        retry_config = ResilienceRetryConfig(**retry_kwargs)

        # circuit_breaker sub-section
        cb_raw = resilience_raw.get("circuit_breaker") or {}
        cb_kwargs: Dict[str, Any] = {}
        if isinstance(cb_raw, dict):
            for key, value in cb_raw.items():
                if key in ("failure_threshold", "half_open_max_calls", "consecutive_successes_to_close"):
                    cb_kwargs[key] = _coerce(value, int)
                elif key in ("recovery_timeout",):
                    cb_kwargs[key] = _coerce(value, float)
                else:
                    cb_kwargs[key] = value
        cb_config = CircuitBreakerConfig(**cb_kwargs)

        idem_ttl = _coerce(resilience_raw.get("idempotency_ttl", 3600), int)
        resilience_config = ResilienceConfig(
            retry=retry_config,
            circuit_breaker=cb_config,
            idempotency_ttl=idem_ttl,
        )
    else:
        resilience_config = ResilienceConfig()

    return NexusConfig(
        web_search=WebSearchConfig(**web_kwargs),
        rag=rag_config,
        resilience=resilience_config,
        **kwargs,
    )


def load_config(config_path: Optional[str] = None) -> NexusConfig:
    """
    Load and validate the Nexus configuration.

    If *config_path* does not exist it is created with defaults and the
    defaults are returned.  Validation errors raise :class:`ConfigError`.
    """
    from nexus.core.paths import DEFAULT_CONFIG_PATH  # local import — avoids cycle

    path = config_path or DEFAULT_CONFIG_PATH

    if not os.path.isfile(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        defaults = NexusConfig()
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(defaults.to_dict(), fh, default_flow_style=False, allow_unicode=True)
        logger.info("Created default config at %s", path)
        return defaults

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse YAML config at {path}: {e}") from e

    return _parse_section(raw)
