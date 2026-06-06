"""
Nexus Logo — fastfetch-style banner with project info.

Displays a styled ASCII logo on the left and key-value system info
on the right, similar to ``fastfetch`` / ``neofetch``.
"""

import platform
import sys

from rich.console import Console
from rich.table import Table
from rich.text import Text

from nexus import __version__


_LOGO_LINES: list[str] = [
    "__  __ _______ __   __ __   __  _____ ",
    "| \\ | ||  ___| \\ \\ / / | | | |/  ___|",
    "|  \\| || |__    \\ V /  | | | |\\ `--. ",
    "| . ` ||  __|   /   \\  | | | | `--. \\",
    "| |\\  || |___  / /^\ \\ \\ | | //\\__/ /",
    "\\_| \\_/\\____/  \\/   \\/  \\___/ \\____/ ",
]


def _colorize_logo(console: Console) -> Text:
    """Return a Rich ``Text`` object with the multi-coloured ASCII art."""
    colors = ["#FF0000", "#E60000", "#CC0000", "#B30000", "#990000", "#800000"]
    text = Text()
    for i, line in enumerate(_LOGO_LINES):
        style = colors[i % len(colors)]
        text.append(line + "\n", style=style)
    return text


def _info_rows() -> list[tuple[str, str, str]]:
    """Build a list of (label, value) pairs shown next to the logo."""
    try:
        import nexus.core.config as _cfg

        _cfg_obj = _cfg.load_config()
        provider = _cfg_obj.to_dict().get("provider", "groq")
        model = _cfg_obj.to_dict().get("groq_model", "—")
    except Exception:
        provider = "—"
        model = "—"

    return [
        ("Project", "Nexus"),
        ("Version", __version__),
        ("Python", sys.version.split()[0]),
        ("OS", f"{platform.system()} {platform.release()}"),
        ("Provider", provider),
        ("Model", model),
    ]


def print_logo(console: Console | None = None) -> None:
    """Print the fastfetch-style Nexus banner to the console.

    Parameters
    ----------
    console:
        An optional pre-configured ``rich.console.Console``.  When *None* a
        new instance is created.
    """
    if console is None:
        console = Console()

    # --- Build the info side as a small table (no borders) ----------------
    info_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    info_table.add_column("Key", style="bold white", no_wrap=True)
    info_table.add_column("Value", style="green")

    for label, value in _info_rows():
        info_table.add_row(label, value)

    # --- Combine logo + info in a top-level table -------------------------
    logo_text = _colorize_logo(console)

    outer = Table(show_header=False, box=None, padding=(0, 0, 0, 1))
    outer.add_column("Logo", no_wrap=True, min_width=42)
    outer.add_column("Info", no_wrap=False)
    outer.add_row(logo_text, info_table)

    # --- Separator line ---------------------------------------------------
    separator = Text("─" * 55, style="dim")

    console.print()
    console.print(outer)
    console.print(separator)
    console.print()