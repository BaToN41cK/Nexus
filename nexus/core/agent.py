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
"""

import logging
from typing import Any, Dict, Generator, List, Optional, Tuple

from nexus.core.providers import (
    BaseProvider,
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
from nexus.core.web_search import WebSearchConfig, WebSearcher

logger = logging.getLogger(__name__)


class NexusAgent:
    """
    Main agent class that communicates with LLM providers.

    Uses the provider abstraction layer to support Groq, OpenAI, Anthropic,
    and Ollama with a unified interface.
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
        Initialize the NexusAgent.

        Args:
            api_key: API key for the provider.
            model: The model name (e.g. "llama-3.3-70b-versatile", "gpt-4o").
            provider: Provider name ("groq", "openai", "anthropic", "ollama").
            base_url: Custom base URL (for OpenAI-compatible or Ollama).
            timeout: Request timeout in seconds.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature.
        """
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
        self.provider_name = provider
        self.model = model

        # Resilience infrastructure.
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

        logger.debug(
            "NexusAgent initialized: provider=%s, model=%s, resilience=enabled",
            provider, model,
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

    def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> dict:
        """
        Send a prompt to the provider and return the response.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system-level instruction.
            history: Optional conversation history.

        Returns:
            dict with keys: 'text', 'prompt_tokens', 'completion_tokens', 'total_tokens'.
        """
        messages = self._build_messages(prompt, system_prompt, history)
        logger.debug(
            "Sending request (provider=%s, model=%s, messages=%d)",
            self.provider_name, self.model, len(messages),
        )
        result = self.provider.generate(messages, stream=False)
        logger.debug(
            "Response received: %d tokens (prompt=%d, completion=%d)",
            result["total_tokens"], result["prompt_tokens"], result["completion_tokens"],
        )
        return result

    def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[str, None, dict]:
        """
        Stream a response from the provider, yielding tokens as they arrive.

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
        logger.debug(
            "Starting stream (provider=%s, model=%s, messages=%d)",
            self.provider_name, self.model, len(messages),
        )
        return self.provider.generate_stream(messages)

    def generate_response_resilient(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> dict:
        """
        Send a prompt with full resilience: circuit breaker + idempotency + retry.

        This wraps the normal ``generate_response`` with the resilience layer:
          - Idempotency key prevents duplicate identical requests.
          - Circuit breaker stops hammering a failing provider.
          - Exponential backoff with jitter for transient errors.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system-level instruction.
            history: Optional conversation history.

        Returns:
            dict with keys: 'text', 'prompt_tokens', 'completion_tokens', 'total_tokens'.
        """
        messages = self._build_messages(prompt, system_prompt, history)

        # Generate idempotency key.
        idem_key = IdempotencyManager.make_key(
            self.provider_name, self.model, messages,
            temperature=self.provider.config.temperature,
            max_tokens=self.provider.config.max_tokens,
        )

        # Use resilient_call wrapper.
        def _do_generate() -> dict:
            return self.provider.generate(messages, stream=False)

        try:
            result = resilient_call(
                _do_generate,
                config=self._resilience_config,
                circuit_breaker=self._circuit_breaker,
                idempotency_manager=self._idempotency_manager,
                idempotency_key=idem_key,
                is_retryable=lambda e: not isinstance(e, (KeyboardInterrupt, SystemExit)),
            )
            logger.debug(
                "Resilient response: %d tokens (prompt=%d, completion=%d)",
                result.get("total_tokens", 0),
                result.get("prompt_tokens", 0),
                result.get("completion_tokens", 0),
            )
            return result

        except ConnectionError as exc:
            logger.error("Circuit breaker blocked request: %s", exc)
            return {
                "text": f"[Сервис временно недоступен. Circuit breaker OPEN. "
                        f"Попробуйте позже или переключите провайдера.]",
                "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            }
        except Exception as exc:
            logger.exception("All resilience layers exhausted for request")
            return {
                "text": f"[Ошибка после всех попыток: {exc}]",
                "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            }

    def get_circuit_breaker_state(self) -> str:
        """Get the current circuit breaker state name."""
        return self._circuit_breaker.state.name

    def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker to closed state."""
        self._circuit_breaker.reset()

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
