"""
Provider abstraction layer for Nexus.

Supports:
- Groq (via groq SDK)
- OpenAI (via openai SDK)
- Anthropic (via anthropic SDK)
- Ollama (local, via ollama SDK or raw HTTP)

Each provider implements the BaseProvider interface.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ProviderConfig:
    """Configuration for a single provider."""
    name: str             # "groq" | "openai" | "anthropic" | "ollama"
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    timeout: int = 30
    max_tokens: int = 4096
    temperature: float = 0.7
    max_retries: int = 3
    rate_limit: float = 5.0  # requests per second
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, rate: float):
        self._rate = rate
        self._tokens = rate
        self._last = time.monotonic()

    def acquire(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
        self._last = now
        if self._tokens < 1:
            wait = (1 - self._tokens) / self._rate
            logger.debug("Rate limiter: sleeping %.2fs", wait)
            time.sleep(wait)
            self._tokens = 0
        else:
            self._tokens -= 1


class BaseProvider(ABC):
    """Abstract provider that all providers must implement."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._client = None
        self._rate_limiter = _RateLimiter(config.rate_limit)
        self._init_client()

    def _retry(self, fn, *args, **kwargs):
        """Call *fn* with retry + rate limiting."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.config.max_retries + 1):
            self._rate_limiter.acquire()
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < self.config.max_retries:
                    backoff = min(2 ** attempt, 30)
                    logger.warning(
                        "Attempt %d/%d failed: %s — retrying in %ds",
                        attempt, self.config.max_retries, exc, backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.error("All %d attempts failed", self.config.max_retries)
        raise last_exc  # type: ignore[misc]

    @abstractmethod
    def _init_client(self) -> None:
        """Initialize the underlying SDK/client."""
        ...

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
    ) -> dict:
        """
        Non-streaming generation.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            stream: If True, should behave same as non-stream (for fallback).

        Returns:
            dict with 'text', 'prompt_tokens', 'completion_tokens', 'total_tokens'.
        """
        ...

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
    ) -> Generator[str, None, dict]:
        """
        Streaming generation. Yields content tokens as they arrive.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.

        Yields:
            str: Each chunk of content as it arrives.

        Returns:
            dict with final token usage (after generator is exhausted).
        """
        # Default fallback – non-streaming
        result = self.generate(messages, stream=False)
        yield result["text"]
        return {
            "text": result["text"],
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
            "total_tokens": result["total_tokens"],
        }

    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Build a messages list from prompt + optional system prompt."""
        msgs: List[Dict[str, str]] = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": prompt})
        return msgs


# ---------------------------------------------------------------------------
# Groq provider
# ---------------------------------------------------------------------------


class GroqProvider(BaseProvider):
    """Provider for Groq API (llama, mixtral, etc.)."""

    def _init_client(self) -> None:
        try:
            import groq as groq_sdk
        except ImportError:
            raise ImportError(
                "Groq SDK is required. Install it with: pip install groq"
            )
        self._groq = groq_sdk
        self._client = groq_sdk.Groq(api_key=self.config.api_key)

    def generate(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
    ) -> dict:
        groq_sdk = self._groq

        try:
            completion = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                timeout=self.config.timeout,
                stream=stream,
            )
        except groq_sdk.APITimeoutError:
            logger.error("Groq API request timed out after %ds", self.config.timeout)
            return {"text": "[Ошибка: таймаут запроса к Groq API]", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        except groq_sdk.RateLimitError:
            logger.error("Groq API rate limit exceeded")
            return {"text": "[Ошибка: превышен лимит запросов к Groq API]", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        except groq_sdk.APIError as e:
            logger.error("Groq API error: %s", e)
            error_msg = str(e)
            if "403" in error_msg or "Access denied" in error_msg:
                return {"text": "[Ошибка 403: Доступ к API запрещён. Проверьте:\n1. API-ключ в GROQ_API_KEY (nexus debug)\n2. Подключение к интернету / VPN\n3. Или используйте локальный Ollama: pip install nexus[ollama]]", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            return {"text": f"[Ошибка Groq API: {e}]", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        except Exception as e:
            logger.exception("Unexpected error during Groq request")
            return {"text": f"[Неожиданная ошибка: {e}]", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if stream:
            text_parts: List[str] = []
            for chunk in completion:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    text_parts.append(delta.content)
            text = "".join(text_parts).strip()
            last_usage = None
            for chunk in completion:
                if hasattr(chunk, "usage") and chunk.usage:
                    last_usage = chunk.usage
            usage = last_usage
        else:
            choice = completion.choices[0]
            text = (choice.message.content or "").strip()
            usage = completion.usage

        return {
            "text": text,
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
    ) -> Generator[str, None, dict]:
        groq_sdk = self._groq

        try:
            stream = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                timeout=self.config.timeout,
                stream=True,
            )
        except groq_sdk.RateLimitError:
            yield "[Ошибка: превышен лимит запросов к Groq API]"
            return {"text": "", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        except groq_sdk.APIError as e:
            yield f"[Ошибка Groq API: {e}]"
            return {"text": "", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        except Exception as e:
            logger.exception("Unexpected error during streaming")
            yield f"[Неожиданная ошибка: {e}]"
            return {"text": "", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        full_text = ""
        last_usage = None
        for chunk in stream:
            if not chunk.choices:
                if hasattr(chunk, "usage") and chunk.usage:
                    last_usage = chunk.usage
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                token = delta.content
                full_text += token
                yield token
            if hasattr(chunk, "usage") and chunk.usage:
                last_usage = chunk.usage

        usage = last_usage
        return {
            "text": full_text.strip(),
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI API (GPT-4, GPT-3.5)."""

    def _init_client(self) -> None:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI SDK is required. Install it with: pip install openai"
            )
        kwargs: Dict[str, Any] = {"api_key": self.config.api_key, "timeout": self.config.timeout}
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        self._client = OpenAI(**kwargs)
        self._openai = OpenAI

    def generate(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
    ) -> dict:
        try:
            completion = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                timeout=self.config.timeout,
                stream=stream,
            )
        except Exception as e:
            logger.exception("OpenAI API error")
            return {"text": f"[Ошибка OpenAI: {e}]", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if stream:
            text_parts: List[str] = []
            for chunk in completion:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    text_parts.append(delta.content)
            text = "".join(text_parts).strip()
            usage = getattr(chunk, "usage", None) if chunk else None
        else:
            choice = completion.choices[0]
            text = (choice.message.content or "").strip()
            usage = completion.usage

        return {
            "text": text,
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
    ) -> Generator[str, None, dict]:
        try:
            stream = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                timeout=self.config.timeout,
                stream=True,
            )
        except Exception as e:
            yield f"[Ошибка OpenAI: {e}]"
            return {"text": "", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        full_text = ""
        last_usage = None
        for chunk in stream:
            if not chunk.choices:
                if hasattr(chunk, "usage") and chunk.usage:
                    last_usage = chunk.usage
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                token = delta.content
                full_text += token
                yield token
            if hasattr(chunk, "usage") and chunk.usage:
                last_usage = chunk.usage

        return {
            "text": full_text.strip(),
            "prompt_tokens": last_usage.prompt_tokens if last_usage else 0,
            "completion_tokens": last_usage.completion_tokens if last_usage else 0,
            "total_tokens": last_usage.total_tokens if last_usage else 0,
        }


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic API (Claude)."""

    def _init_client(self) -> None:
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "Anthropic SDK is required. Install it with: pip install anthropic"
            )
        kwargs: Dict[str, Any] = {"api_key": self.config.api_key}
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        self._client = Anthropic(**kwargs)
        self._anthropic = Anthropic
        self._timeout = self.config.timeout

    def _build_anthropic_messages(
        self,
        messages: List[Dict[str, str]],
    ) -> Tuple[Optional[str], List[Dict[str, str]]]:
        """Extract system prompt and return (system, user/assistant messages)."""
        system = None
        msgs: List[Dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                msgs.append(m)
        return system, msgs

    def generate(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
    ) -> dict:
        system, msgs = self._build_anthropic_messages(messages)
        try:
            response = self._client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=system,
                messages=msgs,
                stream=stream,
            )
        except Exception as e:
            logger.exception("Anthropic API error")
            return {"text": f"[Ошибка Anthropic: {e}]", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if stream:
            text_parts: List[str] = []
            usage_dict = {"input_tokens": 0, "output_tokens": 0}
            for event in response:
                if event.type == "content_block_delta" and event.delta and event.delta.text:
                    text_parts.append(event.delta.text)
                if hasattr(event, "message") and event.message and hasattr(event.message, "usage"):
                    usage_dict = event.message.usage
            text = "".join(text_parts).strip()
            input_tokens = usage_dict.get("input_tokens", 0) if isinstance(usage_dict, dict) else getattr(usage_dict, "input_tokens", 0)
            output_tokens = usage_dict.get("output_tokens", 0) if isinstance(usage_dict, dict) else getattr(usage_dict, "output_tokens", 0)
        else:
            text = "".join(block.text for block in response.content if hasattr(block, "text")).strip()
            usage = response.usage
            input_tokens = usage.input_tokens if usage else 0
            output_tokens = usage.output_tokens if usage else 0

        return {
            "text": text,
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
    ) -> Generator[str, None, dict]:
        system, msgs = self._build_anthropic_messages(messages)
        try:
            response = self._client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=system,
                messages=msgs,
                stream=True,
            )
        except Exception as e:
            yield f"[Ошибка Anthropic: {e}]"
            return {"text": "", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        full_text = ""
        input_tokens = 0
        output_tokens = 0
        for event in response:
            if event.type == "content_block_delta" and hasattr(event.delta, "text") and event.delta.text:
                token = event.delta.text
                full_text += token
                yield token
            if hasattr(event, "message") and event.message and hasattr(event.message, "usage"):
                usage = event.message.usage
                input_tokens = usage.input_tokens if hasattr(usage, "input_tokens") else 0
                output_tokens = usage.output_tokens if hasattr(usage, "output_tokens") else 0

        return {
            "text": full_text.strip(),
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------


class OllamaProvider(BaseProvider):
    """Provider for local Ollama instances."""

    def _init_client(self) -> None:
        try:
            import ollama as ollama_sdk
        except ImportError:
            raise ImportError(
                "Ollama SDK is required. Install it with: pip install ollama"
            )
        self._ollama = ollama_sdk
        self._host = self.config.base_url or "http://localhost:11434"

    def generate(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
    ) -> dict:
        try:
            response = self._ollama.chat(
                model=self.config.model,
                messages=messages,
                stream=stream,
                host=self._host,
            )
        except Exception as e:
            logger.exception("Ollama error")
            return {"text": f"[Ошибка Ollama: {e}]", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if stream:
            text_parts: List[str] = []
            for chunk in response:
                if chunk.get("message", {}).get("content"):
                    text_parts.append(chunk["message"]["content"])
            text = "".join(text_parts).strip()
            eval_count = response[-1].get("eval_count", 0) if isinstance(response, list) else 0
        else:
            text = response.get("message", {}).get("content", "").strip()
            eval_count = response.get("eval_count", 0)

        return {
            "text": text,
            "prompt_tokens": 0,   # Ollama doesn't expose prompt tokens
            "completion_tokens": eval_count,
            "total_tokens": eval_count,
        }

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
    ) -> Generator[str, None, dict]:
        try:
            stream = self._ollama.chat(
                model=self.config.model,
                messages=messages,
                stream=True,
                host=self._host,
            )
        except Exception as e:
            yield f"[Ошибка Ollama: {e}]"
            return {"text": "", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        full_text = ""
        eval_count = 0
        for chunk in stream:
            content = chunk.get("message", {}).get("content", "")
            if content:
                full_text += content
                yield content
            eval_count = chunk.get("eval_count", eval_count)

        return {
            "text": full_text.strip(),
            "prompt_tokens": 0,
            "completion_tokens": eval_count,
            "total_tokens": eval_count,
        }


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDER_MAP: Dict[str, type] = {
    "groq": GroqProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "ollama": OllamaProvider,
}

DEFAULT_MODELS: Dict[str, str] = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "ollama": "llama3.2",
}


def create_provider(config: ProviderConfig) -> BaseProvider:
    """
    Factory: create a provider instance by name.

    Args:
        config: ProviderConfig with name, api_key, model, etc.

    Returns:
        A concrete provider instance.

    Raises:
        ValueError: If provider name is unknown.
    """
    cls = PROVIDER_MAP.get(config.name)
    if cls is None:
        raise ValueError(
            f"Unknown provider: {config.name}. "
            f"Available: {', '.join(PROVIDER_MAP.keys())}"
        )
    # Set default model if not provided
    if not config.model:
        config.model = DEFAULT_MODELS.get(config.name, "")
    logger.debug("Created provider: %s (model=%s)", config.name, config.model)
    return cls(config)