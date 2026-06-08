"""
Smart error parser for Nexus.

Analyses error messages from LLM providers and returns structured
diagnostics with suggested solutions in the user's language.

Usage::

    from nexus.core.error_parser import parse_error, ErrorDiagnostic

    diagnostic = parse_error("Ошибка Groq API: 403 Forbidden", provider="groq")
    print(diagnostic.title)       # "Доступ запрещён (403)"
    print(diagnostic.cause)       # "Невалидный или просроченный API-ключ"
    print(diagnostic.solutions)   # ["Проверьте GROQ_API_KEY в .env", ...]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from nexus.core.i18n import t


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ErrorDiagnostic:
    """Structured representation of a parsed error with solutions."""

    raw_error: str
    provider: str = ""
    title: str = ""
    cause: str = ""
    solutions: List[str] = field(default_factory=list)
    error_code: Optional[int] = None
    is_retryable: bool = False


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------


class _ErrorPattern:
    """Internal helper: a regex-based error matcher."""

    def __init__(
        self,
        regex: str,
        code: Optional[int] = None,
        title_ru: str = "",
        title_en: str = "",
        cause_ru: str = "",
        cause_en: str = "",
        solutions_ru: Optional[List[str]] = None,
        solutions_en: Optional[List[str]] = None,
        is_retryable: bool = False,
    ):
        self.regex = re.compile(regex, re.IGNORECASE)
        self.code = code
        self.title_ru = title_ru
        self.title_en = title_en
        self.cause_ru = cause_ru
        self.cause_en = cause_en
        self.solutions_ru = solutions_ru or []
        self.solutions_en = solutions_en or []
        self.is_retryable = is_retryable

    def match(self, text: str) -> Optional[re.Match]:
        return self.regex.search(text)


# Common patterns across all providers
_PATTERNS: List[_ErrorPattern] = [
    # --- Rate limiting ---
    _ErrorPattern(
        regex=r"(rate.?limit|429|too.?many.?requests|quota.?exceeded|requests.?per.?second)",
        code=429,
        title_ru="Превышен лимит запросов (429)",
        title_en="Rate limit exceeded (429)",
        cause_ru="API-провайдер временно заблокировал запросы из-за слишком частого обращения.",
        cause_en="The API provider temporarily blocked requests due to excessive usage.",
        solutions_ru=[
            "Подождите 10–60 секунд и попробуйте снова",
            "Уменьшите частоту запросов",
            "Используйте более дешёвую модель (например, llama-3.1-8b-instant для Groq)",
            "Проверьте квоту на странице провайдера",
        ],
        solutions_en=[
            "Wait 10–60 seconds and try again",
            "Reduce request frequency",
            "Use a cheaper model (e.g. llama-3.1-8b-instant for Groq)",
            "Check your quota on the provider's dashboard",
        ],
        is_retryable=True,
    ),
    # --- Authentication / 401 ---
    _ErrorPattern(
        regex=r"(401|unauthorized|invalid.?api.?key|authentication.?failed|bad.?credentials|incorrect.?api.?key)",
        code=401,
        title_ru="Ошибка аутентификации (401)",
        title_en="Authentication error (401)",
        cause_ru="API-ключ невалидный, просрочен или отсутствует.",
        cause_en="The API key is invalid, expired, or missing.",
        solutions_ru=[
            "Проверьте переменную окружения с API-ключом (GROQ_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)",
            "Убедитесь, что ключ скопирован без лишних пробелов и переносов строк",
            "Сгенерируйте новый ключ на странице провайдера",
            "Выполните `nexus debug` для диагностики",
        ],
        solutions_en=[
            "Check the API key environment variable (GROQ_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)",
            "Make sure the key has no extra spaces or line breaks",
            "Generate a new key on the provider's dashboard",
            "Run `nexus debug` for diagnostics",
        ],
        is_retryable=False,
    ),
    # --- Access denied / 403 ---
    _ErrorPattern(
        regex=r"(403|forbidden|access.?denied|not.?permitted)",
        code=403,
        title_ru="Доступ запрещён (403)",
        title_en="Access denied (403)",
        cause_ru="Ваш аккаунт или API-ключ не имеет прав на использование данного ресурса.",
        cause_en="Your account or API key does not have permission to use this resource.",
        solutions_ru=[
            "Проверьте, что ваш аккаунт провайдера активен и не заблокирован",
            "Убедитесь, что выбранная модель доступна для вашего тарифного плана",
            "Проверьте地区-ограничения (некоторые регионы могут быть ограничены)",
            "Попробуйте другую модель или провайдера",
        ],
        solutions_en=[
            "Verify your provider account is active and not suspended",
            "Ensure the selected model is available on your plan",
            "Check regional restrictions (some regions may be blocked)",
            "Try a different model or provider",
        ],
        is_retryable=False,
    ),
    # --- Timeout ---
    _ErrorPattern(
        regex=r"(timeout|timed?.?out|deadline.?exceeded|request.?took.?too.?long)",
        title_ru="Таймаут запроса",
        title_en="Request timeout",
        cause_ru="Сервер не успел ответить за отведённое время.",
        cause_en="The server did not respond within the allowed time.",
        solutions_ru=[
            "Увеличьте параметр timeout в конфигурации (сейчас {timeout})",
            "Попробуйте более быструю модель (Groq обычно быстрее OpenAI)",
            "Сократите длину промпта или используйте суммаризацию",
            "Проверьте подключение к интернету",
        ],
        solutions_en=[
            "Increase the timeout in configuration (currently {timeout})",
            "Try a faster model (Groq is usually faster than OpenAI)",
            "Shorten the prompt or use summarization",
            "Check your internet connection",
        ],
        is_retryable=True,
    ),
    # --- Model not found / 404 ---
    _ErrorPattern(
        regex=r"(model.?not.?found|404|no.?model|does.?not.?exist|unknown.?model|invalid.?model|not.?found.?for.?this.?user)",
        code=404,
        title_ru="Модель не найдена (404)",
        title_en="Model not found (404)",
        cause_ru="Указанное имя модели не существует или недоступно для вашего аккаунта.",
        cause_en="The specified model name does not exist or is unavailable for your account.",
        solutions_ru=[
            "Проверьте имя модели — оно чувствительно к регистру",
            "Убедитесь, что модель доступна для вашего провайдера",
            "Используйте модель по умолчанию: уберите groq_model из конфига",
            "Выполните `nexus debug` для просмотра доступных моделей",
        ],
        solutions_en=[
            "Check the model name — it is case-sensitive",
            "Ensure the model is available for your provider",
            "Use the default model: remove groq_model from config",
            "Run `nexus debug` to see available models",
        ],
        is_retryable=False,
    ),
    # --- Context length exceeded ---
    _ErrorPattern(
        regex=r"(context.?length|maximum.?context|token.?limit.?exceeded|too.?many.?tokens|max.?tokens.?exceeded|context.?window|request.?too.?large)",
        title_ru="Превышен лимит контекста",
        title_en="Context length exceeded",
        cause_ru="Запрос (промпт + история) слишком длинный для выбранной модели.",
        cause_en="The request (prompt + history) is too long for the selected model.",
        solutions_ru=[
            "Сократите длину промпта или удалите URL из запроса",
            "Уменьшите conversation_history_size в конфигурации",
            "Используйте модель с большим контекстным окном (например, claude-sonnet-4-20250514)",
            "Включите суммаризацию длинного контента",
        ],
        solutions_en=[
            "Shorten the prompt or remove URLs from the request",
            "Reduce conversation_history_size in configuration",
            "Use a model with a larger context window (e.g. claude-sonnet-4-20250514)",
            "Enable long content summarization",
        ],
        is_retryable=False,
    ),
    # --- Network / connection errors ---
    _ErrorPattern(
        regex=r"(connection.?error|connection.?refused|name.?not.?resolved|dns.?resolution|network.?unreachable|ssl.?error|certificate|connect.?error)",
        title_ru="Ошибка сети",
        title_en="Network error",
        cause_ru="Не удаётся установить соединение с сервером провайдера.",
        cause_en="Cannot establish connection to the provider's server.",
        solutions_ru=[
            "Проверьте подключение к интернету",
            "Проверьте, нет ли блокировки VPN / файрвола",
            "Попробуйте другой DNS (8.8.8.8, 1.1.1.1)",
            "Для Ollama: убедитесь, что Ollama запущен (`ollama serve`)",
        ],
        solutions_en=[
            "Check your internet connection",
            "Check for VPN / firewall blocking",
            "Try a different DNS (8.8.8.8, 1.1.1.1)",
            "For Ollama: ensure Ollama is running (`ollama serve`)",
        ],
        is_retryable=True,
    ),
    # --- Ollama specific: model not pulled ---
    _ErrorPattern(
        regex=r"(pull.?model|not.?found.?locally|ollama.*not.?found|status.?code.*404.*model)",
        title_ru="Модель Ollama не загружена",
        title_en="Ollama model not pulled",
        cause_ru="Локальная модель не скачана в Ollama.",
        cause_en="The local model has not been pulled in Ollama.",
        solutions_ru=[
            "Выполните: ollama pull {model}",
            "Проверьте список моделей: ollama list",
            "Используйте другую уже загруженную модель",
        ],
        solutions_en=[
            "Run: ollama pull {model}",
            "Check available models: ollama list",
            "Use another model that is already pulled",
        ],
        is_retryable=False,
    ),
    # --- Ollama not running ---
    _ErrorPattern(
        regex=r"(connection.?refused.*11434|localhost:11434|ollama.*not.?running|Could.?not.?connect.?to.?Ollama)",
        title_ru="Ollama не запущен",
        title_en="Ollama is not running",
        cause_ru="Сервис Ollama не запущен или не слушает порт 11434.",
        cause_en="The Ollama service is not running or not listening on port 11434.",
        solutions_ru=[
            "Запустите Ollama: ollama serve",
            "Проверьте, что Ollama установлен: ollama --version",
            "Установите Ollama: https://ollama.com/download",
        ],
        solutions_en=[
            "Start Ollama: ollama serve",
            "Check Ollama is installed: ollama --version",
            "Install Ollama: https://ollama.com/download",
        ],
        is_retryable=True,
    ),
    # --- Server overloaded / 503 ---
    _ErrorPattern(
        regex=r"(503|service.?unavailable|overloaded|server.?overloaded|try.?again.?later|capacity)",
        code=503,
        title_ru="Сервер перегружен (503)",
        title_en="Server overloaded (503)",
        cause_ru="Сервер провайдера временно перегружен и не может обработать запрос.",
        cause_en="The provider's server is temporarily overloaded and cannot process the request.",
        solutions_ru=[
            "Подождите 30–120 секунд и попробуйте снова",
            "Переключитесь на другого провайдера",
            "Попробуйте более лёгкую модель",
        ],
        solutions_en=[
            "Wait 30–120 seconds and try again",
            "Switch to another provider",
            "Try a lighter model",
        ],
        is_retryable=True,
    ),
    # --- Content policy violation ---
    _ErrorPattern(
        regex=r"(content.?policy|safety.?filter|blocked.?content|moderation|nsfw|inappropriate.?content)",
        title_ru="Нарушение политики контента",
        title_en="Content policy violation",
        cause_ru="Запрос или ответ был заблокирован фильтрами безопасности провайдера.",
        cause_en="The request or response was blocked by the provider's safety filters.",
        solutions_ru=[
            "Переформулируйте запрос более нейтрально",
            "Избегайте тем, нарушающих правила провайдера",
            "Попробуйте другую модель с менее строгими фильтрами",
        ],
        solutions_en=[
            "Rephrase the request more neutrally",
            "Avoid topics that violate the provider's policies",
            "Try a different model with less strict filters",
        ],
        is_retryable=False,
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_error(
    error_text: str,
    provider: str = "",
    model: str = "",
    timeout: int = 30,
) -> ErrorDiagnostic:
    """
    Parse an error message and return a structured :class:`ErrorDiagnostic`.

    Args:
        error_text: The raw error string (may contain provider prefix like
            ``[Ошибка Groq API: ...]``).
        provider: The provider name (``"groq"``, ``"openai"``, etc.).
        model: The current model name (used in solution suggestions).
        timeout: Current timeout value (used in timeout-related solutions).

    Returns:
        An :class:`ErrorDiagnostic` with title, cause, and solutions.
    """
    diag = ErrorDiagnostic(raw_error=error_text, provider=provider)

    # Strip common Nexus prefixes like [Ошибка ...] or [Error ...]
    cleaned = re.sub(r"^\[.*?(?:ошибка|error)\s*:?\s*", "", error_text, flags=re.IGNORECASE)
    cleaned = cleaned.rstrip("]").strip()

    # Try each pattern
    for pattern in _PATTERNS:
        m = pattern.match(cleaned) or pattern.match(error_text)
        if m:
            diag.error_code = pattern.code
            diag.is_retryable = pattern.is_retryable
            diag.title = pattern.title_ru
            diag.cause = pattern.cause_ru
            diag.solutions = list(pattern.solutions_ru)
            break

    # Provider-specific title prefix
    if provider and diag.title:
        provider_names = {
            "groq": "Groq",
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "ollama": "Ollama",
        }
        prov_name = provider_names.get(provider, provider.title())
        diag.title = f"{prov_name}: {diag.title}"

    # If no pattern matched, provide a generic diagnostic
    if not diag.title:
        provider_names = {
            "groq": "Groq",
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "ollama": "Ollama",
        }
        prov_name = provider_names.get(provider, provider.title() if provider else "LLM")
        diag.title = f"{prov_name}: неизвестная ошибка"
        diag.cause = "Не удалось автоматически определить причину ошибки."
        diag.solutions = [
            "Проверьте логи: `nexus debug`",
            "Убедитесь, что конфигурация корректна",
            f"Скопируйте ошибку и поищите решение: {cleaned[:100]}",
        ]

    # Fill in dynamic placeholders in solutions
    filled: List[str] = []
    for sol in diag.solutions:
        sol = sol.replace("{model}", model or "unknown")
        sol = sol.replace("{timeout}", str(timeout))
        filled.append(sol)
    diag.solutions = filled

    return diag


def format_diagnostic(diag: ErrorDiagnostic, use_rich: bool = True) -> str:
    """
    Format an :class:`ErrorDiagnostic` as a human-readable string.

    Args:
        diag: The diagnostic to format.
        use_rich: If True, include Rich markup for terminal display.

    Returns:
        Formatted string with title, cause, and solutions.
    """
    lines: List[str] = []

    if use_rich:
        lines.append(f"[bold red]🔴 {diag.title}[/bold red]")
        if diag.cause:
            lines.append(f"[yellow]Причина:[/yellow] {diag.cause}")
        if diag.solutions:
            lines.append("")
            lines.append("[bold cyan]💡 Решения:[/bold cyan]")
            for i, sol in enumerate(diag.solutions, 1):
                lines.append(f"  [cyan]{i}.[/cyan] {sol}")
        if diag.is_retryable:
            lines.append("")
            lines.append("[dim]Эта ошибка временная — повторите запрос позже.[/dim]")
    else:
        lines.append(f"🔴 {diag.title}")
        if diag.cause:
            lines.append(f"Причина: {diag.cause}")
        if diag.solutions:
            lines.append("")
            lines.append("💡 Решения:")
            for i, sol in enumerate(diag.solutions, 1):
                lines.append(f"  {i}. {sol}")
        if diag.is_retryable:
            lines.append("")
            lines.append("Эта ошибка временная — повторите запрос позже.")

    return "\n".join(lines)