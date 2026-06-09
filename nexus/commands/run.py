"""
Run Command Module

Implements the core logic for the `nexus run` command:
- Extracts URLs from the prompt
- Loads content from those URLs
- Merges loaded content with the prompt
- Checks cache, calls the agent, saves results
- Streams response in non-cached mode
- Renders Markdown with syntax highlighting
"""

import hashlib
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.text import Text

from nexus.core.agent import NexusAgent
from nexus.core.config import NexusConfig, ConfigError, load_config as load_config_validated
from nexus.core.content_loader import load
from nexus.core.history import add_exchange, build_context
from nexus.core.i18n import t
from nexus.core.web_search import (
    WebSearcher,
    load_config_from_yaml,
)

logger = logging.getLogger(__name__)
console = Console()

# Suppress noisy INFO logs from httpx and agent
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("nexus.core.agent").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Imported from the centralised `nexus.core.paths` module to keep a single
# source of truth and avoid side effects at import time.
from nexus.core.paths import (  # noqa: F401  (re-exported for back-compat)
    CACHE_DIR,
    DEFAULT_CONFIG_PATH,
    HISTORY_DIR,
    NEXUS_DIR,
    SEARCH_CACHE_DIR,
    ensure_dirs,
)


def _load_config(config_path: Optional[str] = None) -> dict:
    """
    Load configuration from YAML file using the validated NexusConfig.

    Args:
        config_path: Path to YAML config file. If None, uses ~/.nexus/config.yaml.

    Returns:
        Configuration dictionary.
    """
    try:
        nexus_cfg = load_config_validated(config_path)
        return nexus_cfg.to_dict()
    except ConfigError as e:
        logger.warning("Config validation error, falling back to defaults: %s", e)
        return NexusConfig().to_dict()


def _load_env(config_path: Optional[str] = None, config: Optional[dict] = None) -> Optional[str]:
    """
    Load .env file and return the API key for the configured provider.

    Search order (first found wins):
      1. NEXUS_ENV_PATH environment variable (if set)
      2. ~/.nexus/.env
      3. config/.env in current working directory
      4. config/.env walking up from current directory
      5. Direct environment variable

    If ~/.nexus/.env doesn't exist but a .env is found elsewhere,
    it will be COPIED to ~/.nexus/.env for future use.
    """
    provider = (config or {}).get("provider", "groq")
    env_var_map = {
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "ollama": None,
    }
    target_var = env_var_map.get(provider)
    if target_var is None:
        return ""  # Ollama: no key needed

    search_paths: List[str] = []

    nexus_env = os.environ.get("NEXUS_ENV_PATH")
    if nexus_env:
        search_paths.append(nexus_env)

    nexus_dotenv = os.path.join(NEXUS_DIR, ".env")
    search_paths.append(nexus_dotenv)

    search_paths.append(os.path.join(os.getcwd(), "config", ".env"))

    cwd = os.getcwd()
    parts = cwd.split(os.sep)
    for i in range(len(parts), 0, -1):
        candidate = os.path.join(os.sep.join(parts[:i]), "config", ".env")
        if candidate not in search_paths:
            search_paths.append(candidate)

    found_path = None
    for env_path in search_paths:
        if os.path.isfile(env_path):
            load_dotenv(env_path)
            key = os.getenv(target_var)
            if key:
                found_path = env_path
                logger.debug("Loaded .env from %s (key=%s)", env_path, target_var)
                break

    if found_path and found_path != nexus_dotenv:
        try:
            os.makedirs(NEXUS_DIR, exist_ok=True)
            with open(found_path, "r", encoding="utf-8") as src_fh:
                content = src_fh.read()
            with open(nexus_dotenv, "w", encoding="utf-8") as dst_fh:
                dst_fh.write(content)
            logger.info("Copied .env to %s for future use", nexus_dotenv)
        except Exception as e:
            logger.debug("Could not copy .env to ~/.nexus/: %s", e)

    if found_path:
        return os.getenv(target_var)

    return os.getenv(target_var)


def _resolve_api_key(config: dict) -> Optional[str]:
    """
    Resolve the correct API key based on provider.

    Args:
        config: Configuration dict with 'provider' key.

    Returns:
        API key or None.
    """
    provider = config.get("provider", "groq")
    env_var_map = {
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "ollama": None,  # Ollama doesn't need an API key
    }
    env_var = env_var_map.get(provider)
    if env_var is None:
        return ""  # Ollama: no key needed
    return os.getenv(env_var)


# ---------------------------------------------------------------------------
# Cache / History helpers
# ---------------------------------------------------------------------------


def _cache_key(text: str) -> str:
    """Create a simple hex hash as a cache key."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _get_cache(key: str, ttl: int = 3600) -> Optional[str]:
    """Return cached response if it exists and is not expired."""
    path = os.path.join(CACHE_DIR, key)
    if not os.path.isfile(path):
        return None
    age = time.time() - os.path.getmtime(path)
    if age > ttl:
        os.remove(path)
        logger.debug("Cache expired for key %s", key)
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _set_cache(key: str, text: str) -> None:
    """Save response text into cache."""
    path = os.path.join(CACHE_DIR, key)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _save_history(prompt: str, response: str, tokens: dict) -> None:
    """Append an entry to the history log."""
    try:
        timestamp = datetime.now().isoformat()
        entry = (
            f"=== {timestamp} ===\n"
            f"Prompt: {prompt}\n"
            f"Tokens: {tokens}\n"
            f"Response:\n{response}\n\n"
        )
        history_file = os.path.join(HISTORY_DIR, "history.log")
        os.makedirs(HISTORY_DIR, exist_ok=True)
        with open(history_file, "a", encoding="utf-8") as fh:
            fh.write(entry)
    except OSError as e:
        logger.warning("Failed to write history: %s", e)


def _auto_clean_cache(max_size_mb: int = 50) -> None:
    """
    Automatically clean old cache entries if total cache size exceeds max_size_mb.

    Args:
        max_size_mb: Maximum allowed cache size in MB.
    """
    max_bytes = max_size_mb * 1024 * 1024
    cache_files = []
    total_size = 0

    for fname in os.listdir(CACHE_DIR):
        fpath = os.path.join(CACHE_DIR, fname)
        if os.path.isfile(fpath):
            fsize = os.path.getsize(fpath)
            cache_files.append((fpath, fsize, os.path.getmtime(fpath)))
            total_size += fsize

    if total_size <= max_bytes:
        return

    # Sort by modification time (oldest first)
    cache_files.sort(key=lambda x: x[2])

    removed = 0
    for fpath, fsize, _ in cache_files:
        if total_size <= max_bytes:
            break
        try:
            os.remove(fpath)
            total_size -= fsize
            removed += 1
        except OSError:
            continue

    if removed:
        logger.info("Auto-cleaned %d cache entries (total now %.1f MB)", removed, total_size / (1024 * 1024))


# ---------------------------------------------------------------------------
# URL extraction
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s,;'\"]+")


def extract_urls(text: str) -> List[str]:
    """Extract all HTTP/HTTPS URLs from a string.

    The regular expression ``_URL_RE`` captures URLs but may include trailing
    punctuation such as ``!``, ``.`` or ``?`` when they appear directly after
    the URL in natural language.  To provide clean URLs for downstream
    processing we strip a set of common trailing punctuation characters.
    """
    raw_urls = _URL_RE.findall(text)
    # Strip trailing punctuation that is not part of the URL.
    cleaned = [url.rstrip('!.,?;:') for url in raw_urls]
    # Return unique URLs while preserving deterministic order for testing.
    # ``set`` would lose order, so we deduplicate while preserving the first
    # occurrence order.
    seen = set()
    unique = []
    for u in cleaned:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------


# The exact shade of green used by `nexus cache-clear` for the
# "Кэш, история запросов и история разговора очищены." message.
# Matches the colour of plain ``[green]`` markup on Windows Terminal
# (default colour scheme, ANSI 16-colour palette). Exposed as a hex
# string so that the Panel border/title render with the *same* colour
# as the message text below the panel.
CACHE_CLEAR_GREEN = "#00cc00"


def _response_title() -> str:
    """Translated title for the response Panel (e.g. "Ответ" / "Response")."""
    return t("cmd.run_response_title")


def _sources_title() -> str:
    """Translated title for the sources Panel (e.g. "📚 Источники" / "📚 Sources")."""
    return t("cmd.run_sources_title")


def _render_response(text: str) -> Panel:
    """
    Render a response inside a Panel whose border and title are coloured
    with the exact same green used by ``nexus cache-clear`` for the
    "Кэш, история запросов и история разговора очищены." message (see
    :data:`CACHE_CLEAR_GREEN`).

    The body is rendered as :class:`rich.markdown.Markdown`, so the LLM
    response is parsed as Markdown: **bold** / *italic*, bullet and
    numbered lists, ``inline code`` and fenced ```python``` code blocks
    (with full Pygments syntax highlighting).

    Args:
        text: Response text (assumed to be Markdown).

    Returns:
        Rich Panel with a Markdown body, green title and green border.
    """
    return Panel(
        Markdown(text, code_theme="monokai", inline_code_lexer="python"),
        title=f"[{CACHE_CLEAR_GREEN}]{_response_title()}[/{CACHE_CLEAR_GREEN}]",
        border_style=CACHE_CLEAR_GREEN,
    )


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


def run_command(args) -> None:
    """
    Execute the `run` command: process prompt with URLs, call the agent,
    stream the response, and display the result.
    """
    try:
        _run_command_impl(args)
    except KeyboardInterrupt:
        console.print(f"\n[yellow]{t('cmd.run_interrupted')}[/yellow]")
    except Exception as e:
        logger.exception("Unexpected error in run_command")
        console.print(f"[red]Неожиданная ошибка: {e}[/red]")


def _run_command_impl(args) -> None:
    """Internal implementation of the ``run`` command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")

    prompt = args.prompt
    no_cache = getattr(args, "no_cache", False)
    config_path = getattr(args, "config", None)
    use_search = getattr(args, "search", None)
    no_search = getattr(args, "no_search", False)

    # --- Configuration ---
    try:
        cfg = load_config_validated(config_path)
    except ConfigError as e:
        console.print(f"[red]Ошибка конфигурации: {e}[/red]")
        return
    provider = cfg.provider
    groq_model = cfg.groq_model
    base_url = cfg.base_url
    max_content_length = cfg.max_content_length
    summarize_threshold = cfg.summarize_threshold
    cache_ttl = cfg.cache_ttl
    max_cache_size_mb = cfg.max_cache_size_mb
    timeout = cfg.timeout
    max_tokens = cfg.max_tokens
    temperature = cfg.temperature
    system_prompt = cfg.system_prompt
    conversation_history_size = cfg.conversation_history_size
    config = cfg.to_dict()

    # Auto-clean cache if needed
    _auto_clean_cache(max_cache_size_mb)

    # --- API key ---
    api_key = _load_env(config_path or DEFAULT_CONFIG_PATH, config=config)
    if not api_key:
        # Try resolving from env vars by provider
        api_key = _resolve_api_key(config) or ""

    if provider != "ollama" and not api_key:
        console.print("[red]❌ API ключ не найден. Проверьте .env файл или переменную окружения.[/red]")
        return

    # --- Extract URLs & load content ---
    urls = extract_urls(prompt)
    loaded_parts = []

    if urls:
        with Progress(
            SpinnerColumn(spinner_name="dots", style="blue"),
            TextColumn("[blue]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("[green]{task.completed}/{task.total}"),
            console=console,
            transient=True,
        ) as progress:
            load_task = progress.add_task("Загрузка URL", total=len(urls))
            for url in urls:
                progress.update(load_task, description=f"[blue]📥 {url[:60]}[/blue]")
                content = load(url)
                if content.startswith("[Ошибка"):
                    console.print(f"[yellow]⚠️  {content}[/yellow]")
                else:
                    loaded_parts.append(content)
                progress.advance(load_task)

    # Build the final prompt
    if loaded_parts:
        combined_content = "\n\n---\n\n".join(loaded_parts)
        if len(combined_content) > max_content_length:
            combined_content = combined_content[:max_content_length] + "\n\n[Content truncated]"
        full_prompt = f"{prompt}\n\nContext:\n{combined_content}"
    else:
        full_prompt = prompt

    # --- Check cache ---
    cache_key = _cache_key(full_prompt)
    if not no_cache:
        cached = _get_cache(cache_key, ttl=cache_ttl)
        if cached is not None:
            console.print(_render_response(cached))
            return

    # --- Build conversation context from history ---
    context_text, _ = build_context(
        system_prompt=system_prompt,
        max_exchanges=conversation_history_size,
    )
    if context_text:
        full_prompt = f"{context_text}\n\nNew message: {full_prompt}"

    # --- Create agent ---
    agent = NexusAgent(
        api_key=api_key,
        model=groq_model,
        provider=provider,
        base_url=base_url,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    # --- Decide whether to use web search ---
    web_config = load_config_from_yaml(config)
    if use_search is None:
        # Default behaviour follows the YAML config
        use_search_flag = bool(web_config.enabled)
    else:
        use_search_flag = bool(use_search)
    if no_search:
        use_search_flag = False

    web_searcher: Optional[WebSearcher] = None
    if use_search_flag:
        try:
            web_searcher = WebSearcher(web_config, SEARCH_CACHE_DIR)
            console.print(
                f"[blue]\U0001f50d Web-поиск:[/blue] бэкенд "
                f"[green]{web_searcher.backend_name}[/green]"
            )
        except Exception as e:
            logger.warning("Не удалось инициализировать WebSearcher: %s", e)
            web_searcher = None

    # Summarize if content is very long
    if len(full_prompt) > summarize_threshold:
        console.print("[yellow]\U0001f4dd Контент большой, суммаризирую...[/yellow]")
        with Progress(
            SpinnerColumn(spinner_name="dots", style="green"),
            TextColumn("[green]Думаю..."),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("", total=None)
            summary = agent.summarize(full_prompt)
        full_prompt = f"{prompt}\n\nSummary of loaded content:\n{summary}"

    # --- Stream response (with or without web context) ---
    # During streaming we display a Rich spinner so the user knows
    # the model is working.  Once the generator finishes, we render
    # the full response inside a Markdown-highlighted Panel.
    # (The old ``\r``-prefixed raw-text trick broke for multi-line
    # output because ``\\r`` only returns the cursor to column 0 of
    # the *current* terminal line, causing the entire accumulated
    # text to be rewritten on screen each token.)
    response_text = ""
    token_info: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    sources: List[str] = []
    title_md = f"[{CACHE_CLEAR_GREEN}]{_response_title()}[/{CACHE_CLEAR_GREEN}]"
    streaming_failed = False
    is_error_response = False
    error_type_for_stats = ""

    if web_searcher is not None:
        gen, sources = agent.search_and_answer_stream(
            prompt=prompt,
            web_searcher=web_searcher,
            web_config=web_config,
            system_prompt=system_prompt,
        )
    else:
        gen = agent.generate_stream(full_prompt, system_prompt=system_prompt)

    with Progress(
        SpinnerColumn(spinner_name="dots", style="green"),
        TextColumn("[green]Думаю..."),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("", total=None)
        try:
            for token in gen:
                response_text += token
        except Exception as e:
            logger.exception("Streaming error")
            streaming_failed = True
            console.print(f"[red]Ошибка при стриминге: {e}[/red]")

    # --- Final frame: render the buffered text in a green Panel.
    # Use Markdown for a normal LLM response, plain Text when the
    # response is an error string (e.g. ``[Ошибка Groq API: ...]``)
    # or when the stream raised an exception.
    final_text = response_text.rstrip()
    # Heuristic: if the response looks like a Nexus/i18n error message
    # (starts with ``[`` on its own line, or the first line contains
    # ``Ошибка`` / ``Error``), render it as plain Text — no point in
    # trying to highlight an error string.
    # NOTE: we only check the FIRST LINE of the response, not the entire
    # body, because the LLM may include words like "Ошибка" inside
    # code examples (e.g. ``return "Ошибка: деление на ноль"``).
    first_line = final_text.split("\n", 1)[0].strip() if final_text else ""
    is_error_response = (
        streaming_failed
        or first_line.startswith("[")
        or "Ошибка" in first_line
        or "Error" in first_line
    )

    # --- Smart error parsing with solutions ---
    if is_error_response and final_text:
        try:
            from nexus.core.error_parser import parse_error, format_diagnostic

            diag = parse_error(
                final_text, provider=provider, model=groq_model, timeout=timeout,
            )
            # Classify error type for stats
            error_type_for_stats = diag.title or "unknown"
            # Display the smart diagnostic panel
            console.print(Panel(
                format_diagnostic(diag, use_rich=True),
                title=f"[bold red]🔴 {t('error.parsed_title')}[/bold red]",
                border_style="red",
            ))
        except Exception as e:
            logger.debug("Error parser failed: %s", e)
            # Fallback: display raw error
            if final_text:
                console.print(Panel(
                    Text(final_text),
                    title=title_md,
                    border_style=CACHE_CLEAR_GREEN,
                ))
    elif final_text:
        body: object = (
            Text(final_text)
            if is_error_response
            else Markdown(
                final_text,
                code_theme="monokai",
                inline_code_lexer="python",
            )
        )
        console.print(
            Panel(
                body,
                title=title_md,
                border_style=CACHE_CLEAR_GREEN,
            )
        )

    # Print sources used (if any) for citation (also inside a Panel
    # using the same green as the response panel above).
    if sources:
        src_text = "\n".join(f"- {u}" for u in sources)
        console.print(
            Panel(
                Markdown(src_text, code_theme="monokai"),
                title=f"[{CACHE_CLEAR_GREEN}]{_sources_title()}[/{CACHE_CLEAR_GREEN}]",
                border_style=CACHE_CLEAR_GREEN,
            )
        )

    response_text = response_text.strip()

    if not response_text:
        console.print("[red]Пустой ответ от API.[/red]")
        return

    # --- Save to conversation history ---
    add_exchange(prompt, response_text, max_exchanges=conversation_history_size)

    # --- Cache & Log History ---
    _set_cache(cache_key, response_text)
    _save_history(prompt, response_text, token_info)

    # --- Display token info ---
    token_str = (
        f"Prompt: {token_info.get('prompt_tokens', 0)} | "
        f"Completion: {token_info.get('completion_tokens', 0)} | "
        f"Total: {token_info.get('total_tokens', 0)}"
    )
    console.print(f"[green]{token_str}[/green]")

    # --- Record usage statistics ---
    try:
        from nexus.core.usage_stats import record_request, record_error

        record_request(
            provider=provider,
            model=groq_model,
            prompt_tokens=token_info.get("prompt_tokens", 0),
            completion_tokens=token_info.get("completion_tokens", 0),
            total_tokens=token_info.get("total_tokens", 0),
        )
        # Record error if the response was an error
        if is_error_response and error_type_for_stats:
            record_error(provider=provider, error_type=error_type_for_stats)
    except Exception as e:
        logger.debug("Failed to record usage stats: %s", e)
