"""
Provider Factory Module for Nexus.

Provides an abstract factory pattern for creating LLM providers,
allowing external plugins to register custom provider implementations.

Usage:
    from nexus.core.provider_factory import ProviderFactory

    # Register a custom provider from a plugin
    from nexus.core.providers import BaseProvider, ProviderConfig

    class MyCustomProvider(BaseProvider):
        ...

    ProviderFactory.register("my_provider", MyCustomProvider)

    # Create a provider instance
    provider = ProviderFactory.create(
        name="my_provider",
        api_key="...",
        model="...",
    )
"""

import logging
from typing import Any, Dict, Optional, Type

from nexus.core.providers import (
    BaseProvider,
    GroqProvider,
    OpenAIProvider,
    AnthropicProvider,
    OllamaProvider,
    ProviderConfig,
)

logger = logging.getLogger(__name__)

# Built-in provider registry — maps name → provider class.
_BUILTIN_PROVIDERS: Dict[str, Type[BaseProvider]] = {
    "groq": GroqProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "ollama": OllamaProvider,
}

# Mutable registry that plugins can extend.
_custom_providers: Dict[str, Type[BaseProvider]] = {}


class ProviderFactory:
    """
    Factory for creating LLM provider instances.

    Supports built-in providers (Groq, OpenAI, Anthropic, Ollama) and
    custom providers registered via :meth:`register`.
    """

    _default_models: Dict[str, str] = {
        "groq": "llama-3.3-70b-versatile",
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-20250514",
        "ollama": "llama3.2",
    }

    _fallback_models: Dict[str, str] = {
        "groq": "llama-3.1-8b-instant",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-haiku-20241022",
        "ollama": "llama3.2",
    }

    @classmethod
    def register(cls, name: str, provider_cls: Type[BaseProvider]) -> None:
        """
        Register a custom provider class.

        Args:
            name: Provider name (e.g. ``"my_provider"``).
            provider_cls: A subclass of :class:`BaseProvider`.

        Raises:
            ValueError: If a provider with this name is already registered.
        """
        if name in _BUILTIN_PROVIDERS:
            raise ValueError(
                f"Cannot override built-in provider {name!r}. "
                f"Use a different name."
            )
        if name in _custom_providers:
            raise ValueError(
                f"Provider {name!r} is already registered. "
                f"Unregister it first if you want to replace it."
            )
        if not issubclass(provider_cls, BaseProvider):
            raise ValueError(
                f"Provider class must be a subclass of BaseProvider, "
                f"got {provider_cls.__name__}"
            )
        _custom_providers[name] = provider_cls
        logger.info("Registered custom provider: %s", name)

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a previously registered custom provider."""
        if name in _custom_providers:
            del _custom_providers[name]
            logger.info("Unregistered custom provider: %s", name)
        else:
            logger.debug("Provider %r not found in custom registry", name)

    @classmethod
    def list_providers(cls) -> Dict[str, Type[BaseProvider]]:
        """Return a combined dict of all built-in and custom providers."""
        return {**_BUILTIN_PROVIDERS, **_custom_providers}

    @classmethod
    def create(
        cls,
        name: str,
        api_key: str = "",
        model: str = "",
        base_url: str = "",
        timeout: int = 30,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        max_retries: int = 3,
        rate_limit: float = 5.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> BaseProvider:
        """
        Create a provider instance by name.

        Args:
            name: Provider name (built-in or custom).
            api_key: API key for the provider.
            model: Model name. If empty, uses the default for this provider.
            base_url: Custom base URL.
            timeout: Request timeout in seconds.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
            max_retries: Maximum number of retries on failure.
            rate_limit: Requests per second limit.
            extra: Additional provider-specific configuration.

        Returns:
            A concrete provider instance.

        Raises:
            ValueError: If *name* is unknown.
        """
        providers = cls.list_providers()
        provider_cls = providers.get(name)
        if provider_cls is None:
            raise ValueError(
                f"Unknown provider: {name}. "
                f"Available: {', '.join(providers.keys())}"
            )

        config = ProviderConfig(
            name=name,
            api_key=api_key,
            model=model or cls._default_models.get(name, ""),
            base_url=base_url,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
            max_retries=max_retries,
            rate_limit=rate_limit,
            extra=extra or {},
        )
        return provider_cls(config)

    @classmethod
    def get_default_model(cls, name: str) -> str:
        """Return the default model for *name*, or empty string."""
        return cls._default_models.get(name, "")

    @classmethod
    def get_fallback_model(cls, name: str) -> Optional[str]:
        """Return the fallback model for *name*, or ``None``."""
        return cls._fallback_models.get(name)