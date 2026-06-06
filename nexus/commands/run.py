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
import time
from datetime import datetime
from typing import List, Optional

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

from nexus.core.agent import NexusAgent
from nexus.core.content_loader import load
from nexus.core.history import add_exchange, build_context
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
# Default config (used when config file is missing)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "provider": "groq",
    "groq_model": "llama-3.3-70b-versatile",
    "base_url": "",
    "max_content_length": 50000,
    "summarize_threshold": 40000,
    "cache_ttl": 3600,
    "max_cache_size_mb": 50,
    "max_retries": 3,
    "rate_limit": 5,
    "timeout": 30,
    "max_tokens": 4096,
    "temperature": 0.7,
    "conversation_history_size": 5,
    "system_prompt": "Ты — полезный ассистент. Отвечай кратко и по делу.",
}

NEXUS_DIR = os.path.join(os.path.expanduser("~"), ".nexus")
CACHE_DIR = os.path.join(NEXUS_DIR, "cache")
HISTORY_DIR = os.path.join(NEXUS_DIR, "history")
SEARCH_CACHE_DIR = os.path.join(NEXUS_DIR, "search_cache")
DEFAULT_CONFIG_PATH = os.path.join(NEXUS_DIR, "config.yaml")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)
os.makedirs(SEARCH_CACHE_DIR, exist_ok=True)


def _load_config(config_path: Optional[str] = None) -> dict:
    """
    Load configuration from YAML file. If the file doesn't exist,
    create it from defaults and return defaults.

    Args:
        config_path: Path to YAML config file. If None, uses ~/.nexus/config.yaml.

    Returns:
        Configuration dictionary.
    """
    path = config_path or DEFAULT_CONFIG_PATH

    if not os.path.isfile(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(_DEFAULT_CONFIG, fh, default_flow_style=False, allow_unicode=True)
        logger.info("Created default config at %s", path)
        return dict(_DEFAULT_CONFIG)

    with open(path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    merged = dict(_DEFAULT_CONFIG)
    merged.update(config)
    return merged


def _load_env(config_path: Optional[str] = None) -> Optional[str]:
    """
    Load .env file and return GROQ_API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY
    depending on provider).

    Search order (first found wins):
      1. NEXUS_ENV_PATH environment variable (if set)
      2. ~/.nexus/.env
      3. config/.env in current working directory
      4. config/.env walking up from current directory
      5. GROQ_API_KEY environment variable (direct)

    If ~/.nexus/.env doesn't exist but a .env is found elsewhere,
    it will be COPIED to ~/.nexus/.env for future use.
    """
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
            key = os.getenv("GROQ_API_KEY")
            if key:
                found_path = env_path
                logger.debug("Loaded .env from %s", env_path)
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
        return os.getenv("GROQ_API_KEY")

    return os.getenv("GROQ_API_KEY")


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
    timestamp = datetime.now().isoformat()
    entry = (
        f"=== {timestamp} ===\n"
        f"Prompt: {prompt}\n"
        f"Tokens: {tokens}\n"
        f"Response:\n{response}\n\n"
    )
    history_file = os.path.join(HISTORY_DIR, "history.log")
    with open(history_file, "a", encoding="utf-8") as fh:
        fh.write(entry)


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
    """Extract all HTTP/HTTPS URLs from a string."""
    return list(set(_URL_RE.findall(text)))


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------


def _render_response(text: str) -> Panel:
    """
    Render a response inside a Panel, with Markdown support.

    Args:
        text: Response text to render.

    Returns:
        Rich Panel with formatted content.
    """
    try:
        md = Markdown(text, code_theme="monokai")
        return Panel(md, title="[#90EE90]Ответ[/#90EE90]", border_style="#90EE90")
    except Exception:
        return Panel(
            f"[#90EE90]{text}[/#90EE90]",
            title="[#90EE90]Ответ[/#90EE90]",
            border_style="#90EE90",
        )


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


def run_command(args) -> None:
    """
    Execute the `run` command: process prompt with URLs, call the agent,
    stream the response, and display the result.
    """
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled")

    prompt = args.prompt
    no_cache = getattr(args, "no_cache", False)
    config_path = getattr(args, "config", None)
    use_search = getattr(args, "search", None)
    no_search = getattr(args, "no_search", False)

    # --- Configuration ---
    config = _load_config(config_path)
    provider = config.get("provider", "groq")
    groq_model = config.get("groq_model", "llama-3.3-70b-versatile")
    base_url = config.get("base_url", "")
    max_content_length = config.get("max_content_length", 50000)
    summarize_threshold = config.get("summarize_threshold", 40000)
    cache_ttl = config.get("cache_ttl", 3600)
    max_cache_size_mb = config.get("max_cache_size_mb", 50)
    timeout = config.get("timeout", 30)
    max_tokens = config.get("max_tokens", 4096)
    temperature = config.get("temperature", 0.7)
    system_prompt = config.get("system_prompt")
    conversation_history_size = config.get("conversation_history_size", 5)

    # Auto-clean cache if needed
    _auto_clean_cache(max_cache_size_mb)

    # --- API key ---
    api_key = _load_env(config_path or DEFAULT_CONFIG_PATH)
    if not api_key:
        # Try resolving from env vars by provider
        api_key = _resolve_api_key(config) or ""

    if provider != "ollama" and not api_key:
        console.print("[red]❌ API ключ не найден. Проверьте .env файл или переменную окружения.[/red]")
        return

    # --- Extract URLs & load content ---
    urls = extract_urls(prompt)
    loaded_parts = []

    for url in urls:
        console.print(f"[blue]📥 Загружаю:[/blue] {url}")
        content = load(url)
        if content.startswith("[Ошибка"):
            console.print(f"[yellow]⚠️  {content}[/yellow]")
        else:
            loaded_parts.append(content)

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
                f"[#90EE90]{web_searcher.backend_name}[/#90EE90]"
            )
        except Exception as e:
            logger.warning("Не удалось инициализировать WebSearcher: %s", e)
            web_searcher = None

    # Summarize if content is very long
    if len(full_prompt) > summarize_threshold:
        console.print("[yellow]\U0001f4dd Контент большой, суммаризирую...[/yellow]")
        with Progress(
            SpinnerColumn(spinner_name="dots", style="#90EE90"),
            TextColumn("[#90EE90]Думаю..."),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("", total=None)
            summary = agent.summarize(full_prompt)
        full_prompt = f"{prompt}\n\nSummary of loaded content:\n{summary}"

    # --- Stream response (with or without web context) ---
    response_text = ""
    token_info: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    sources: List[str] = []
    with Live(
        Panel(
            Text("", style="#90EE90"),
            title="[#90EE90]Ответ[/#90EE90]",
            border_style="#90EE90",
        ),
        console=console,
        refresh_per_second=10,
        transient=False,
    ) as live:
        try:
            if web_searcher is not None:
                gen, sources = agent.search_and_answer_stream(
                    prompt=prompt,
                    web_searcher=web_searcher,
                    web_config=web_config,
                    system_prompt=system_prompt,
                )
            else:
                gen = agent.generate_stream(full_prompt, system_prompt=system_prompt)
            # Collect all tokens and the final return value
            try:
                while True:
                    try:
                        token = next(gen)
                        response_text += token
                        # Render as Markdown for live preview
                        try:
                            md = Markdown(response_text + "▌", code_theme="monokai")
                            live.update(
                                Panel(md, title="[#90EE90]Ответ[/#90EE90]", border_style="#90EE90")
                            )
                        except Exception:
                            live.update(
                                Panel(
                                    f"[#90EE90]{response_text}[/#90EE90]",
                                    title="[#90EE90]Ответ[/#90EE90]",
                                    border_style="#90EE90",
                                )
                            )
                    except StopIteration as e:
                        # Generator finished - return value is in e.value
                        if hasattr(e, 'value') and e.value:
                            token_info = e.value
                        break
            except Exception as e:
                logger.exception("Streaming error")
                console.print(f"[red]Ошибка при стриминге: {e}[/red]")
                return
        except Exception as e:
            logger.exception("Stream init error")
            console.print(f"[red]Ошибка при запуске стриминга: {e}[/red]")
            return

    # Print sources used (if any) for citation
    if sources:
        src_text = "\n".join(f"- {u}" for u in sources)
        console.print(
            Panel(
                Text(src_text, style="#90EE90"),
                title="[#90EE90]\U0001f4da Источники[/#90EE90]",
                border_style="#90EE90",
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
    console.print(f"[#90EE90]{token_str}[/#90EE90]")
