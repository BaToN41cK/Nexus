"""
Interactive config editor for Nexus.

Provides a guided CLI wizard that reads the current configuration file,
displays each setting with its current value and type, and lets the user
change it interactively.

Usage:
    nexus config edit
"""

import logging
import os
import sys
from typing import Any, Dict, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from nexus.core.config import ConfigError, NexusConfig, WebSearchConfig, load_config
from nexus.core.i18n import t
from nexus.core.paths import DEFAULT_CONFIG_PATH

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Field metadata for the interactive wizard
# ---------------------------------------------------------------------------

_CONFIG_FIELDS = [
    # (key, type, label, default, help_text)
    ("provider", str, "LLM Provider", "groq",
     "Provider name: groq, openai, anthropic, ollama"),
    ("groq_model", str, "Model", "llama-3.3-70b-versatile",
     "Model name (e.g. gpt-4o, llama-3.3-70b-versatile, claude-sonnet-4-20250514)"),
    ("base_url", str, "Base URL", "",
     "Custom API base URL (leave empty for default)"),
    ("timeout", int, "Timeout (sec)", 30,
     "Request timeout in seconds"),
    ("max_tokens", int, "Max Tokens", 4096,
     "Maximum tokens in the response (1 - 1000000)"),
    ("temperature", float, "Temperature", 0.7,
     "Sampling temperature (0.0 - 2.0)"),
    ("max_content_length", int, "Max Content Length", 50000,
     "Maximum loaded content length in characters"),
    ("summarize_threshold", int, "Summarize Threshold", 40000,
     "Content length that triggers summarization"),
    ("cache_ttl", int, "Cache TTL (sec)", 3600,
     "How long to cache responses (seconds)"),
    ("max_cache_size_mb", int, "Max Cache Size (MB)", 50,
     "Maximum cache size in megabytes"),
    ("conversation_history_size", int, "History Size", 5,
     "Number of conversation turns to keep"),
    ("system_prompt", str, "System Prompt", "",
     "Custom system prompt for the LLM"),
]

_WEB_SEARCH_FIELDS = [
    ("enabled", bool, "Web Search Enabled", False,
     "Enable web search by default"),
    ("backend", str, "Search Backend", "auto",
     "Backend: auto, duckduckgo, tavily, searxng, bing"),
    ("max_results", int, "Max Results", 5,
     "Maximum search results (1 - 20)"),
    ("fetch_top_n", int, "Fetch Top N", 3,
     "Number of pages to fetch (0 - 10)"),
    ("timeout", int, "Search Timeout (sec)", 15,
     "Search request timeout"),
    ("cache_enabled", bool, "Cache Enabled", True,
     "Whether to cache search results"),
    ("cache_ttl", int, "Search Cache TTL (sec)", 3600,
     "Search cache TTL in seconds"),
]


def _format_value(value: Any) -> str:
    """Format a config value for display."""
    if isinstance(value, bool):
        return t("cmd.status_yes") if value else t("cmd.status_no")
    if value == "" or value is None:
        return "[dim](empty)[/dim]"
    return str(value)


def _prompt_field(key: str, current_value: Any, field_type: type,
                  label: str, help_text: str) -> Any:
    """Prompt the user for a new value for a config field.

    Returns the new value, or the original value if the user leaves it empty.
    """
    hint = _format_value(current_value)
    prompt_text = f"[cyan]{label}[/cyan] [dim]({hint})[/dim]"

    if field_type == bool:
        # Use Rich Confirm for booleans
        default_bool = bool(current_value) if current_value is not None else False
        result = Confirm.ask(prompt_text, default=default_bool)
        return result

    while True:
        raw = Prompt.ask(prompt_text, default="")
        if not raw:
            return current_value  # Keep the current value
        try:
            if field_type == int:
                return int(raw)
            elif field_type == float:
                return float(raw)
            else:
                return raw
        except (ValueError, TypeError) as e:
            console.print(f"[red]Invalid value for {field_type.__name__}: {e}[/red]")


def _show_current_config(config: NexusConfig) -> None:
    """Display the current configuration in a table."""
    table = Table(title="Current Configuration", show_lines=True)
    table.add_column("Section", style="cyan")
    table.add_column("Key", style="green")
    table.add_column("Value", style="white")
    table.add_column("Type", style="dim")

    for key, ftype, label, default, _ in _CONFIG_FIELDS:
        value = getattr(config, key, default)
        table.add_row("General", key, str(value), ftype.__name__)

    ws = config.web_search
    for key, ftype, label, default, _ in _WEB_SEARCH_FIELDS:
        value = getattr(ws, key, default)
        table.add_row("Web Search", key, str(value), ftype.__name__)

    console.print(table)


def config_edit(args) -> None:
    """Interactive config editor — ``nexus config edit``."""
    config_path = getattr(args, "config", None) or DEFAULT_CONFIG_PATH

    # Load existing config
    try:
        config = load_config(config_path)
        console.print(f"[green]Loaded config from: {config_path}[/green]")
    except ConfigError as e:
        console.print(f"[yellow]Config error: {e}[/yellow]")
        console.print("[yellow]Starting with defaults...[/yellow]")
        config = NexusConfig()

    # Show current config
    _show_current_config(config)

    console.print()
    console.print(Panel(
        "[bold]Config Editor[/bold]\n\n"
        "Press Enter to keep the current value for any field.",
        title="Interactive Config Edit",
        border_style="blue",
    ))
    console.print()

    if not Confirm.ask("[yellow]Edit configuration?[/yellow]", default=True):
        console.print("[dim]Canceled.[/dim]")
        return

    # --- Edit general settings ---
    console.print("\n[bold cyan]═══ General Settings ═══[/bold cyan]\n")

    changed_keys: Dict[str, Any] = {}
    for key, ftype, label, default, help_text in _CONFIG_FIELDS:
        current = getattr(config, key, default)
        console.print(f"  [dim]{help_text}[/dim]")
        new_value = _prompt_field(key, current, ftype, label, help_text)
        if new_value != current:
            changed_keys[key] = new_value
            setattr(config, key, new_value)

    # --- Edit web search settings ---
    console.print("\n[bold cyan]═══ Web Search Settings ═══[/bold cyan]\n")

    ws = config.web_search
    for key, ftype, label, default, help_text in _WEB_SEARCH_FIELDS:
        current = getattr(ws, key, default)
        console.print(f"  [dim]{help_text}[/dim]")
        new_value = _prompt_field(f"web_search.{key}", current, ftype, label, help_text)
        if new_value != current:
            changed_keys[f"web_search.{key}"] = new_value
            setattr(ws, key, new_value)

    config.web_search = ws

    if not changed_keys:
        console.print("[yellow]No changes made.[/yellow]")
        return

    # --- Validate ---
    try:
        # __post_init__ runs validation
        NexusConfig(
            provider=config.provider,
            groq_model=config.groq_model,
            base_url=config.base_url,
            timeout=config.timeout,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            max_content_length=config.max_content_length,
            summarize_threshold=config.summarize_threshold,
            cache_ttl=config.cache_ttl,
            max_cache_size_mb=config.max_cache_size_mb,
            conversation_history_size=config.conversation_history_size,
            system_prompt=config.system_prompt,
            web_search=config.web_search,
        )
    except ConfigError as e:
        console.print(f"[red]Validation error: {e}[/red]")
        return

    # --- Write ---
    import yaml

    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as fh:
            yaml.dump(config.to_dict(), fh, default_flow_style=False, allow_unicode=True)
        console.print(f"[green]✓ Configuration saved to {config_path}[/green]")

        # Show changed values
        table = Table(title="Changed Values", show_lines=False)
        table.add_column("Key", style="cyan")
        table.add_column("New Value", style="green")
        for k, v in changed_keys.items():
            table.add_row(k, str(v))
        console.print(table)
    except OSError as e:
        console.print(f"[red]Failed to write config: {e}[/red]")