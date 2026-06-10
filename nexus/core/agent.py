"""
Nexus Agent Module

Provides the NexusAgent class that wraps any LLM provider (Groq, OpenAI,
Anthropic, Ollama) via the provider abstraction layer.

Supports both streaming and non-streaming generation, summarization,
and response improvement. Also exposes :meth:`search_and_answer_stream`
which augments the prompt with web-search context before calling the LLM.

Resilience features:
  - Retry with exponential backoff + jitter (via resilience module)
  - Circuit breaker per provider (stops hammering failing APIs)
  - Idempotency keys (prevents duplicate requests)
  - Fallback provider chain (auto-failover to backup provider on errors)
  - DEFAULT_FALLBACK_CHAIN — built-in multi-provider fallback list
  - Emergency fallback (Ollama tiny model / rules-based) when all providers down
"""

import logging
from typing import Any, Dict, Generator, List, Optional, Tuple

from nexus.core.providers import (
    BaseProvider,
    DEFAULT_MODELS,
    FALLBACK_MODELS,
    PROVIDER_MAP,
    ProviderConfig,
    create_provider,
)
from nexus.core.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    FallbackProviderChain,
    FallbackTarget,
    IdempotencyManager,
    ProviderNotAvailableError,
    ResilienceConfig,
    RetryConfig,
    resilient_call,
)
from nexus.core.tiny_fallback import emergency_fallback
from nexus.core.web_search import WebSearchConfig, WebSearcher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default fallback chain — built-in ordered list of provider fallbacks.
# Nexus will try each in order when the primary provider fails.
# ---------------------------------------------------------------------------

DEFAULT_FALLBACK_CHAIN: List[Dict[str, str]] = [
    # Primary — order matters; first match wins if API key is present.
    {"provider": "groq", "model": "llama-3.3-70b-versatile", "fallback_model": "llama-3.1-8b-instant"},
    {"provider": "openai", "model": "gpt-4o", "fallback_model": "gpt-4o-mini"},
    {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "fallback_model": "claude-3-5-haiku-20241022"},
    {"provider": "ollama", "model": "llama3.2", "fallback_model": "llama3.2"},
]

# Well-known environment variable names for each provider.
PROVIDER_ENV_KEYS: Dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": "",  # Ollama doesn't need an API key
}


def _detect_available_providers() -> List[Dict[str, str]]:
    """
    Auto-detect which providers have API keys configured in environment.

    Scans DEFAULT_FALLBACK_CHAIN and returns only the entries whose
    API key is available (env var set) or that don't need a key (ollama).

    Returns:
        Filtered list of provider config dicts.
    """
    import os
    result: List[Dict[str, str]] = []
    for entry in DEFAULT_FALLBACK_CHAIN:
        provider_name = entry["provider"]
        env_key = PROVIDER_ENV_KEYS.get(provider_name, "")
        if not env_key:
            # Ollama — always available (local).
            result.append(entry)
        elif os.environ.get(env_key):
            result.append(entry)
        else:
            logger.debug(
                "Provider '%s' skipped (env %s not set)",
                provider_name, env_key,
            )
    return result


def _build_fallback_chain(
    primary_api_key: str = "",
    primary_provider: str = "groq",
    primary_model: str = "llama-3.3-70b-versatile",
    primary_base_url: str = "",
    timeout: int = 30,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> List[FallbackTarget]:
    """
    Build a list of FallbackTarget from auto-detected available providers.

    The primary provider is placed first, followed by auto-detected
    alternatives in priority order.

    Args:
        primary_api_key: API key for the primary provider.
        primary_provider: Primary provider name.
        primary_model: Primary model name.
        primary_base_url: Custom base URL for primary.
        timeout, max_tokens, temperature: Shared params.

    Returns:
        Ordered list of FallbackTarget.
    """
    import os
    targets: List[FallbackTarget] = []

    # 1. Primary provider (always first).
    targets.append(FallbackTarget(
        provider_name=primary_provider,
        model=primary_model,
        api_key=primary_api_key,
        base_url=primary_base_url,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
    ))

    # 2. Auto-detect available fallback providers.
    available = _detect_available_providers()
    for entry in available:
        if entry["provider"] == primary_provider:
            continue  # already added as primary
        provider_name = entry["provider"]
        env_key = PROVIDER_ENV_KEYS.get(provider_name, "")
        api_key = os.environ.get(env_key, "") if env_key else ""
        targets.append(FallbackTarget(
            provider_name=provider_name,
            model=entry["model"],
            api_key=api_key,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
        ))

    logger.info(
        "Fallback chain built: %s",
        " -> ".join(f"{t.provider_name}/{t.model}" for t in targets),
    )
    return targets


# ---------------------------------------------------------------------------
# Main Agent
# ---------------------------------------------------------------------------


class NexusAgent:
    """
    Main agent class that communicates with LLM providers.

    Supports automatic multi-provider fallback — if the primary provider
    is unavailable, Nexus will automatically try the next available provider
    in the chain (Groq → OpenAI → Anthropic → Ollama by default).

    If *all* providers fail, Nexus uses an **emergency fallback**:
      1. Try Ollama with a tiny local model (``tinyllama``)
      2. Match the query against rules-based patterns
      3. Return a generic offline message

    Usage::

        agent = NexusAgent(api_key="gsk_...")
        # Groq is primary. If Groq fails, auto-falls back to OpenAI,
        # then Anthropic, then Ollama.

        result = agent.generate_response("Hello")
        # Or with full resilience:
        result = agent.generate_response_resilient("Hello")
    """

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        provider: str = "groq",
        base_url: str = "",
        timeout: int = 30,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        """
        Initialize the NexusAgent with automatic multi-provider fallback.

        Args:
            api_key: API key for the primary provider.
            model: The model name for the primary provider.
            provider: Primary provider name ("groq", "openai", "anthropic", "ollama").
            base_url: Custom base URL for the primary provider.
            timeout: Request timeout in seconds.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.
        """
        self.provider_name = provider
        self.model = model

        # Primary provider.
        config = ProviderConfig(
            name=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self.provider: BaseProvider = create_provider(config)

        # Build the fallback provider chain using auto-detected providers.
        fallback_targets = _build_fallback_chain(
            primary_api_key=api_key,
            primary_provider=provider,
            primary_model=model,
            primary_base_url=base_url,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self._fallback_chain = FallbackProviderChain(
            targets=fallback_targets,
            use_circuit_breaker=True,
        )

        # Resilience infrastructure (per-provider circuit breaker is handled
        # inside FallbackProviderChain; this one is for the primary).
        self._circuit_breaker = CircuitBreaker()
        self._idempotency_manager = IdempotencyManager()
        self._resilience_config = ResilienceConfig(
            retry=RetryConfig(
                max_retries=config.max_retries,
                min_backoff=1.0,
                max_backoff=60.0,
            ),
            circuit_breaker=CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=30.0,
            ),
            use_idempotency=True,
        )

        logger.info(
            "NexusAgent initialized: primary=%s/%s, fallbacks=%d",
            provider, model, len(fallback_targets) - 1,
        )

    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """
        Build a messages list for the API call.

        Args:
            prompt: The user's prompt.
            system_prompt: Optional system instruction.
            history: Optional list of previous exchanges (for multi-turn).

        Returns:
            List of message dicts.
        """
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        return messages

    def _make_llm_call(self, target: FallbackTarget) -> dict:
        """
        Create a provider and call it for the given fallback target.

        Args:
            target: The fallback target to use.

        Returns:
            dict with 'text', token usage.

        Raises:
            Exception: If provider creation or call fails.
        """
        config = ProviderConfig(
            name=target.provider_name,
            api_key=target.api_key,
            model=target.model,
            base_url=target.base_url,
            timeout=target.timeout,
            max_tokens=target.max_tokens,
            temperature=target.temperature,
        )
        provider = create_provider(config)
        logger.info(
            "Falling back to provider: %s/%s",
            target.provider_name, target.model,
        )
        return provider.generate(self._last_messages, stream=False)

    # ------------------------------------------------------------------
    # Non-streaming generation
    # ------------------------------------------------------------------

    def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> dict:
        """
        Send a prompt to the provider with automatic multi-provider fallback.

        If the primary provider fails (timeout, rate limit, API error),
        Nexus will automatically try the next available provider in the
        fallback chain::

            Groq → OpenAI → Anthropic → Ollama

        If **all** providers fail, Nexus uses the emergency fallback:
        local Ollama tiny model → rules-based patterns → generic offline message.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system-level instruction.
            history: Optional conversation history.

        Returns:
            dict with keys: 'text', 'prompt_tokens', 'completion_tokens',
            'total_tokens', and optionally 'fallback_provider'.
        """
        messages = self._build_messages(prompt, system_prompt, history)
        self._last_messages = messages

        logger.debug(
            "Sending request (primary=%s/%s, messages=%d)",
            self.provider_name, self.model, len(messages),
        )

        # First, try the primary provider directly.
        result = self.provider.generate(messages, stream=False)

        # If the primary returned an error, try fallback chain.
        if self.provider._is_error_response(result.get("text", "")):
            logger.warning(
                "Primary provider %s/%s returned error, trying fallbacks",
                self.provider_name, self.model,
            )
            try:
                fallback_result, target = self._fallback_chain.call(
                    messages,
                    make_call=self._make_llm_call,
                )
                if fallback_result:
                    fallback_result["fallback_provider"] = target.provider_name
                    fallback_result["fallback_model"] = target.model
                    logger.info(
                        "Fallback succeeded: %s/%s",
                        target.provider_name, target.model,
                    )
                    return fallback_result
            except ProviderNotAvailableError:
                logger.warning(
                    "All primary & fallback providers failed — using emergency fallback",
                )
                return emergency_fallback(messages)

        return result

    def generate_response_resilient(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> dict:
        """
        Send a prompt with full resilience: circuit breaker + idempotency
        + retry + automatic multi-provider fallback.

        This wraps the normal ``generate_response`` with:
          - Idempotency key prevents duplicate identical requests.
          - Circuit breaker stops hammering a failing provider.
          - Exponential backoff with jitter for transient errors.
          - Automatic fallback to next provider if all retries fail.
          - Emergency fallback (Ollama tiny model / rules-based) as last resort.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system-level instruction.
            history: Optional conversation history.

        Returns:
            dict with keys: 'text', 'prompt_tokens', 'completion_tokens',
            'total_tokens', and optionally 'fallback_provider'.
        """
        messages = self._build_messages(prompt, system_prompt, history)
        self._last_messages = messages

        # Generate idempotency key covering the entire fallback chain.
        idem_key = IdempotencyManager.make_key(
            self.provider_name, self.model, messages,
            temperature=self.provider.config.temperature,
            max_tokens=self.provider.config.max_tokens,
            fallback_targets=",".join(
                f"{t.provider_name}:{t.model}"
                for t in self._fallback_chain.targets
            ),
        )

        def _do_primary_generate() -> dict:
            return self.provider.generate(messages, stream=False)

        def _do_generate_with_fallback() -> dict:
            """Try primary with resilience; on failure, try fallback chain."""
            try:
                return resilient_call(
                    _do_primary_generate,
                    config=self._resilience_config,
                    circuit_breaker=self._circuit_breaker,
                    is_retryable=lambda e: not isinstance(e, (KeyboardInterrupt, SystemExit)),
                )
            except Exception as exc:
                logger.warning(
                    "Primary provider exhausted retries (%s), trying fallback chain",
                    exc,
                )
                try:
                    fallback_result, target = self._fallback_chain.call(
                        messages,
                        make_call=self._make_llm_call,
                    )
                    if fallback_result:
                        fallback_result["fallback_provider"] = target.provider_name
                        fallback_result["fallback_model"] = target.model
                        return fallback_result
                except ProviderNotAvailableError:
                    logger.error("All providers in fallback chain failed")
                raise

        try:
            result = resilient_call(
                _do_generate_with_fallback,
                config=ResilienceConfig(
                    retry=RetryConfig(max_retries=1),  # outer retry handles fallback
                    use_idempotency=True,
                ),
                idempotency_manager=self._idempotency_manager,
                idempotency_key=idem_key,
            )
            logger.debug(
                "Resilient response: %d tokens",
                result.get("total_tokens", 0),
            )
            return result

        except ConnectionError as exc:
            logger.error("Circuit breaker blocked request: %s", exc)
            return emergency_fallback(messages)
        except ProviderNotAvailableError as exc:
            logger.error("All providers failed: %s", exc)
            return emergency_fallback(messages)
        except Exception as exc:
            logger.exception("All resilience layers exhausted, using emergency fallback")
            return emergency_fallback(messages)

    # ------------------------------------------------------------------
    # Streaming generation
    # ------------------------------------------------------------------

    def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[str, None, dict]:
        """
        Stream a response from the provider, yielding tokens as they arrive.

        If the primary provider fails during streaming, falls back to
        non-streaming from the next available provider.

        If **all** providers fail, the emergency fallback result is yielded
        as a single token.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system-level instruction.
            history: Optional conversation history.

        Yields:
            str: Each content token as it arrives.

        Returns:
            dict with final token usage (after generator is exhausted).
        """
        messages = self._build_messages(prompt, system_prompt, history)
        self._last_messages = messages

        logger.debug(
            "Starting stream (primary=%s/%s, messages=%d)",
            self.provider_name, self.model, len(messages),
        )

        gen = self.provider.generate_stream(messages)
        first_token = next(gen, None)

        # If primary streaming fails at first token, try fallback chain.
        if first_token is not None and self.provider._is_error_response(first_token):
            logger.warning(
                "Primary streaming error on '%s/%s', trying fallback chain",
                self.provider_name, self.model,
            )
            try:
                fallback_result, target = self._fallback_chain.call(
                    messages,
                    make_call=lambda t: self._make_llm_call(t),
                )
                text = fallback_result.get("text", "")
                if text:
                    yield text
                    return {
                        "text": text,
                        "prompt_tokens": fallback_result.get("prompt_tokens", 0),
                        "completion_tokens": fallback_result.get("completion_tokens", 0),
                        "total_tokens": fallback_result.get("total_tokens", 0),
                        "fallback_provider": target.provider_name,
                    }
            except ProviderNotAvailableError:
                logger.warning(
                    "All providers failed during stream — using emergency fallback",
                )
                fallback = emergency_fallback(messages)
                text = fallback.get("text", "")
                if text:
                    yield text
                    return fallback

        if first_token is not None:
            yield first_token
        return (yield from gen)

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def get_circuit_breaker_state(self) -> str:
        """Get the current circuit breaker state name."""
        return self._circuit_breaker.state.name

    def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker to closed state."""
        self._circuit_breaker.reset()

    def get_fallback_chain(self) -> List[str]:
        """
        Get the ordered list of providers in the fallback chain.

        Returns:
            List like ``["groq/llama-3.3-70b", "openai/gpt-4o", ...]``.
        """
        return [
            f"{t.provider_name}/{t.model}"
            for t in self._fallback_chain.targets
        ]

    def summarize(self, text: str) -> str:
        """
        Summarize a long text.

        Args:
            text: The text to summarize.

        Returns:
            Summarized text.
        """
        prompt = (
            "Пожалуйста, сделай краткое изложение следующего текста. "
            "Выдели основные идеи и ключевые моменты:\n\n" + text
        )
        result = self.generate_response(prompt)
        return result["text"]

    def search_and_answer_stream(
        self,
        prompt: str,
        web_searcher: WebSearcher,
        web_config: WebSearchConfig,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[Generator[str, None, Dict[str, Any]], List[str]]:
        """
        Run a web-augmented query: search the web for the prompt, fetch the
        top results, and stream the LLM's response that uses that context.

        The returned generator yields response tokens; the return value of
        the generator (i.e. the value passed to ``StopIteration.value``) is
        a dict with ``text``, ``sources`` (list of URLs) and ``tokens``.

        Args:
            prompt: The user's question / prompt.
            web_searcher: A configured :class:`WebSearcher` instance.
            web_config: A :class:`WebSearchConfig` describing limits.
            system_prompt: Optional override for the system instruction.
            history: Optional multi-turn history.

        Returns:
            ``(generator, sources)`` — sources is a list of URLs that were
            included as context, even if streaming fails early.
        """
        sources: List[str] = []
        context_text = ""
        try:
            context_text, fetched = web_searcher.search_and_format(
                prompt, max_results=web_config.max_results
            )
            sources = [r.url for r in fetched]
        except Exception as e:  # search must NEVER break the command
            logging.getLogger(__name__).warning(
                "Web search step failed, falling back to plain LLM: %s", e
            )

        if not context_text:
            # No useful search results — behave like a regular stream.
            return self.generate_stream(prompt, system_prompt, history), sources

        # Build the augmented prompt and stream the response.
        instruction = (
            "Ты ассистент Nexus. У тебя есть блок CONTEXT с актуальной информацией "
            "из интернета. Используй его для ответа на вопрос пользователя. "
            "В самом конце ответа перечисли использованные источники списком со ссылками."
        )
        augmented_user = (
            f"{prompt}\n\n"
            f"=== CONTEXT (актуальная информация из интернета) ===\n"
            f"{context_text}\n"
            f"=== END CONTEXT ==="
        )
        # Use the user-supplied system_prompt (if any) as a base,
        # otherwise fall back to the default search instruction.
        sys_p = system_prompt or instruction
        return self.generate_stream(augmented_user, sys_p, history), sources