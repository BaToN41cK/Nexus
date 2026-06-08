"""
Enhanced interactive UI for Nexus chat mode.

Provides a richer user experience with:
  - Themed colors (customizable via config)
  - Dynamic autocomplete (history-based suggestions)
  - Progress bar for long operations
  - Command descriptions
  - Dark/light mode awareness
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UI Configuration (can be overridden via config file)
# ---------------------------------------------------------------------------


@dataclass
class UIConfig:
    """User interface configuration.

    Can be loaded from the ``ui`` section of ``nexus.yaml``.
    """

    # Color scheme (Rich markup colors)
    user_color: str = "bold cyan"
    assistant_color: str = "green"
    system_color: str = "dim cyan"
    error_color: str = "bold red"
    warning_color: str = "yellow"
    info_color: str = "blue"
    muted_color: str = "dim white"

    # Panel styling
    panel_border_color: str = "green"
    panel_title_color: str = "bold green"

    # Progress bar
    spinner_style: str = "dots"
    progress_bar_width: int = 40

    # Prompt
    prompt_prefix: str = "💬 "

    # Whether to show token usage after each response
    show_token_usage: bool = False

    # Whether to show response time
    show_response_time: bool = True


# Default UI config
_DEFAULT_UI = UIConfig()


# ---------------------------------------------------------------------------
# Command descriptions for autocomplete help
# ---------------------------------------------------------------------------

COMMAND_DESCRIPTIONS: Dict[str, str] = {
    "!search on": "Enable web search for the next messages",
    "!search off": "Disable web search",
    "!search status": "Show current web search status",
    "!lang ru": "Switch interface to Russian",
    "!lang en": "Switch interface to English",
    "!lang de": "Switch interface to German",
    "!lang fr": "Switch interface to French",
    "!lang es": "Switch interface to Spanish",
    "!help": "Show this help message",
    "!clear": "Clear the conversation history",
    "!status": "Show current configuration and status",
    "exit": "Exit the interactive mode",
    "quit": "Exit the interactive mode",
}


def build_interactive_completer(history_words: Optional[List[str]] = None) -> Any:
    """Build a dynamic WordCompleter with command descriptions.

    Args:
        history_words: Optional list of words from user's history
            to include as suggestions.

    Returns:
        A ``prompt_toolkit`` ``WordCompleter`` instance, or ``None``
        if ``prompt_toolkit`` is not installed.
    """
    try:
        from prompt_toolkit.completion import WordCompleter
    except ImportError:
        return None

    # Base commands
    commands = list(COMMAND_DESCRIPTIONS.keys())

    # Add dynamic history words (limited to avoid clutter)
    if history_words:
        for word in history_words[-50:]:
            if word not in commands:
                commands.append(word)

    return WordCompleter(commands, ignore_case=True, display_dict=COMMAND_DESCRIPTIONS)


def create_progress(console: Console, description: str = "Thinking...") -> Progress:
    """Create a Rich Progress instance suitable for interactive mode.

    Args:
        console: The Rich Console to render to.
        description: Description text shown during the operation.

    Returns:
        A ``Progress`` context manager.
    """
    return Progress(
        SpinnerColumn(spinner_name="dots", style="green"),
        TextColumn("[green]{task.description}[/green]"),
        BarColumn(bar_width=40),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )


def create_search_progress(console: Console, backend: str = "") -> Progress:
    """Create a Progress instance for web search operations."""
    desc = f"🔍 Searching web (backend: {backend})..."
    return Progress(
        SpinnerColumn(spinner_name="earth", style="blue"),
        TextColumn("[blue]{task.description}[/blue]"),
        console=console,
        transient=True,
    )


def load_ui_config(config_dict: Optional[Dict[str, Any]] = None) -> UIConfig:
    """Load UI configuration from a config dict.

    Looks for the ``ui`` section and maps known keys to UIConfig fields.

    Args:
        config_dict: Full config dict (e.g. from ``NexusConfig.to_dict()``).

    Returns:
        A UIConfig instance with overrides from config.
    """
    cfg = UIConfig()
    if not config_dict:
        return cfg

    ui_section = config_dict.get("ui") or {}
    for key in ui_section:
        if hasattr(cfg, key):
            setattr(cfg, key, ui_section[key])
    return cfg


def format_sources(sources: List[str], color: str = "green") -> Panel:
    """Format source URLs into a Rich Panel."""
    src_text = "\n".join(f"- {u}" for u in sources)
    return Panel(
        Text(src_text, style=color),
        title=f"[{color}]📚 Sources[/{color}]",
        border_style=color,
    )


def format_token_info(prompt_tokens: int, completion_tokens: int,
                      total_tokens: int, elapsed_secs: float = 0) -> str:
    """Format token usage info as a dim string."""
    parts = [
        f"Prompt: {prompt_tokens:,}",
        f"Completion: {completion_tokens:,}",
        f"Total: {total_tokens:,}",
    ]
    if elapsed_secs:
        parts.append(f"Time: {elapsed_secs:.1f}s")
    return " | ".join(parts) + " "