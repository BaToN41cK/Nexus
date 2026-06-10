"""
Tiny fallback responder — rules-based answers when all providers are down.

When every LLM provider is unreachable, this module provides:

1. **Emergency Ollama fallback** — tries a local tiny model (e.g. ``tinyllama``)
   via Ollama if available.
2. **Rules-based fallback** — pattern-matches common questions and returns
   canned responses without any API call at all.

Usage::

    from nexus.core.tiny_fallback import TinyFallbackResponder

    responder = TinyFallbackResponder()
    result = responder.respond(messages)  # returns dict
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TINY_OLLAMA_MODEL = "tinyllama"


# ---------------------------------------------------------------------------
# Rules-based responder
# ---------------------------------------------------------------------------


@dataclass
class ResponseRule:
    """A single pattern → response rule."""

    patterns: List[str]          # regex patterns (lowercased)
    response: str                # canned response
    priority: int = 0            # higher = checked first


# Common question patterns in Russian and English.
DEFAULT_RULES: List[ResponseRule] = [
    ResponseRule(
        patterns=[
            r"(?i)(?:который час|сколько времени|time|current time)",
        ],
        response=(
            "Я не могу сказать точное время, так как это rules-based fallback-режим. "
            "Все провайдеры LLM временно недоступны. "
            "Пожалуйста, проверьте подключение к интернету и статус API-ключей."
        ),
        priority=100,
    ),
    ResponseRule(
        patterns=[
            r"(?i)(?:привет|здравствуй|hello|hi|hey)",
        ],
        response=(
            "Привет! Я работаю в офлайн-режиме, так как все LLM-провайдеры "
            "временно недоступны. Я могу ответить только на базовые вопросы. "
            "Пожалуйста, проверьте подключение к интернету и статус API-ключей."
        ),
        priority=90,
    ),
    ResponseRule(
        patterns=[
            r"(?i)(?:help|помощь|помоги|команды|commands|usage|использование)",
        ],
        response=(
            "Я нахожусь в fallback-режиме (все LLM-провайдеры недоступны). "
            "Доступные команды:\n"
            "  /help  — показать эту справку\n"
            "  /clear — очистить историю\n"
            "  /models — показать доступные модели\n"
            "  /exit  — выйти из Nexus\n\n"
            "Для восстановления полной функциональности проверьте:\n"
            "1. Подключение к интернету\n"
            "2. API-ключи (nexus debug)\n"
            "3. Попробуйте переключиться на Ollama (nexus --provider ollama)"
        ),
        priority=80,
    ),
    ResponseRule(
        patterns=[
            r"(?i)(?:sum\s+\d+|сложи|add\s+\d+|сколько будет|\d+\s*[\+\-\*\/]\s*\d+)",
        ],
        response=(
            "Извините, в текущем fallback-режиме вычисления недоступны. "
            "Все провайдеры LLM временно недоступны."
        ),
        priority=70,
    ),
    ResponseRule(
        patterns=[
            r"(?i)(?:кто ты|who are you|what are you|расскажи о себе)",
        ],
        response=(
            "Я Nexus — AI-ассистент с поддержкой множества LLM-провайдеров "
            "(Groq, OpenAI, Anthropic, Ollama).\n\n"
            "В данный момент я работаю в офлайн-режиме, так как все провайдеры "
            "временно недоступны.\n\n"
            "Проверьте:\n"
            "  • Интернет-соединение\n"
            "  • API-ключи: GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY\n"
            "  • nexus debug для диагностики"
        ),
        priority=60,
    ),
    ResponseRule(
        patterns=[
            r"(?i)(?:статус|status|debug|диагностика|check|провер)",
        ],
        response=(
            "Статус: все LLM-провайдеры недоступны.\n\n"
            "Рекомендации:\n"
            "  1. Проверьте подключение к интернету\n"
            "  2. Проверьте API-ключи: GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY\n"
            "  3. Если есть локальная Ollama, запустите: nexux --provider ollama\n"
            "  4. Выполните: nexus debug"
        ),
        priority=50,
    ),
    ResponseRule(
        patterns=[
            r"(?i)(?:спасиб|thanks|thank you|благодар)",
        ],
        response="Пожалуйста! Когда провайдеры восстановятся, я смогу отвечать полноценно.",
        priority=40,
    ),
    ResponseRule(
        patterns=[
            r"(?i)(?:что ты можешь|what can you|capabilities|функции|возможности)",
        ],
        response=(
            "В обычном режиме я могу:\n"
            "  • Отвечать на вопросы на разных языках\n"
            "  • Писать и объяснять код\n"
            "  • Искать информацию в интернете\n"
            "  • Работать с файлами и документацией\n"
            "  • Использовать инструменты (MCP, плагины)\n\n"
            "Сейчас я в офлайн-режиме (все провайдеры недоступны). "
            "Проверьте подключение к интернету и API-ключи."
        ),
        priority=30,
    ),
    ResponseRule(
        patterns=[
            r"(?i)(?:пока|bye|goodbye|до свидания|увидим)",
        ],
        response="До свидания! Надеюсь, провайдеры скоро восстановятся.",
        priority=20,
    ),
]


class TinyFallbackResponder:
    """
    Rules-based responder for basic questions when no LLM is available.

    Matches user input against a set of patterns and returns canned responses.
    If no pattern matches, returns a generic fallback message.
    """

    def __init__(self, rules: Optional[List[ResponseRule]] = None):
        """
        Args:
            rules: Custom rules (defaults to :const:`DEFAULT_RULES`).
        """
        self._rules = sorted(rules or DEFAULT_RULES, key=lambda r: -r.priority)

    def respond(self, messages: List[Dict[str, str]]) -> Optional[dict]:
        """
        Try to answer a conversation using rules-based matching.

        Args:
            messages: The messages payload (last user message is matched).

        Returns:
            ``dict`` with ``text``, token usage, or ``None`` if no rule matches.
        """
        # Extract the last user message.
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        if not user_text:
            return None

        for rule in self._rules:
            for pattern in rule.patterns:
                if re.search(pattern, user_text):
                    logger.info(
                        "TinyFallbackResponder: matched rule '%s' (priority=%d)",
                        pattern[:40], rule.priority,
                    )
                    return {
                        "text": rule.response,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "fallback_provider": "rules-based",
                        "fallback_model": "tiny-fallback",
                    }

        return None


# ---------------------------------------------------------------------------
# Emergency Ollama fallback
# ---------------------------------------------------------------------------


def try_ollama_tiny_fallback(messages: List[Dict[str, str]]) -> Optional[dict]:
    """
    Try to call Ollama with a tiny model as emergency fallback.

    This is attempted *before* the rules-based responder — if Ollama is
    running locally with ``tinyllama`` (or any available model), it can
    provide a real (but low-quality) response without internet access.

    Args:
        messages: The full messages list.

    Returns:
        ``dict`` with response text, or ``None`` if Ollama is unavailable.
    """
    try:
        from nexus.core.providers import OllamaProvider, ProviderConfig

        config = ProviderConfig(
            name="ollama",
            model=TINY_OLLAMA_MODEL,
            timeout=10,  # short timeout — it's a fallback
            max_tokens=512,
            temperature=0.3,
        )
        provider = OllamaProvider(config)
        result = provider.generate(messages, stream=False)
        text = result.get("text", "")

        if text and not text.startswith("["):
            logger.info("Emergency Ollama fallback succeeded with %s", TINY_OLLAMA_MODEL)
            result["fallback_provider"] = "ollama"
            result["fallback_model"] = TINY_OLLAMA_MODEL
            return result

        logger.debug("Emergency Ollama fallback returned error: %s", text[:100])

    except ImportError:
        logger.debug("Emergency Ollama fallback: ollama SDK not installed")
    except Exception as exc:
        logger.debug("Emergency Ollama fallback failed: %s", exc)

    return None


def emergency_fallback(messages: List[Dict[str, str]]) -> dict:
    """
    Ultimate fallback — tries Ollama tiny model, then rules-based.

    This is called when all primary providers in the fallback chain are
    unavailable. It provides a best-effort response even when completely
    offline.

    Args:
        messages: The full messages list.

    Returns:
        ``dict`` with response text, token usage, and fallback metadata.
    """
    # 1. Try Ollama with a tiny model (local, no internet needed).
    result = try_ollama_tiny_fallback(messages)
    if result is not None:
        return result

    # 2. Rules-based matching.
    responder = TinyFallbackResponder()
    result = responder.respond(messages)
    if result is not None:
        return result

    # 3. Absolute last resort — generic message.
    return {
        "text": (
            "[Офлайн-режим] Все LLM-провайдеры временно недоступны. "
            "Я не могу ответить на этот вопрос без подключения к API.\n\n"
            "Пожалуйста, проверьте:\n"
            "  • Интернет-соединение\n"
            "  • API-ключи: GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY\n"
            "  • Запущен ли локальный Ollama сервер\n"
            "  • nexus debug для диагностики"
        ),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "fallback_provider": "rules-based",
        "fallback_model": "generic-fallback",
    }