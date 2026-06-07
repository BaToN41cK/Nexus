"""
Nexus Logo — fastfetch-style banner with project info.

Displays a styled ASCII logo on the left and key-value system info
on the right, similar to ``fastfetch`` / ``neofetch``.

Поддерживает несколько вариантов баннеров (см. :mod:`nexus.core.banners`).
Имя баннера берётся в порядке приоритета:
  1. Аргумент ``banner=`` в :func:`print_logo`;
  2. Переменная окружения ``NEXUS_BANNER``;
  3. ``THEME.default_banner`` (== ``"classic"``).
"""
from __future__ import annotations

import os
import platform
import sys
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from nexus import __version__
from nexus.core.banners import available_banners, get_banner
from nexus.core.theme import THEME, gradients


__all__ = ["print_logo", "resolve_banner", "list_banners"]


# ---------------------------------------------------------------------------
# Публичные хелперы
# ---------------------------------------------------------------------------


def resolve_banner(explicit: Optional[str] = None) -> str:
    """Вернуть имя баннера: явно → env → дефолт.

    Не валидирует существование — этим занимается :func:`get_banner`.
    """
    if explicit:
        return explicit.lower()
    env = os.environ.get("NEXUS_BANNER", "").strip().lower()
    if env:
        return env
    return THEME.default_banner


def list_banners() -> tuple:
    """Список имён доступных баннеров (для --help и интерактивных подсказок)."""
    return available_banners()


# ---------------------------------------------------------------------------
# Отрисовка
# ---------------------------------------------------------------------------


def _colorize_lines(lines, gradient) -> Text:
    """Раскрасить строки ``lines`` цветами из ``gradient`` циклически."""
    text = Text()
    for i, line in enumerate(lines):
        style = gradient[i % len(gradient)]
        text.append(line + "\n", style=style)
    return text


def _info_rows() -> list:
    """Собрать пары ``(label, value)`` для правой колонки."""
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


def print_logo(console: Console | None = None, banner: Optional[str] = None) -> None:
    """Напечатать fastfetch-style баннер ``Nexus`` + системную информацию.

    Parameters
    ----------
    console:
        Существующий :class:`rich.console.Console`. Если ``None`` — создаётся
        новый (полезно для быстрого вызова из ``python -c``).
    banner:
        Имя баннера (``"classic"``). Если ``None`` —
        берётся из ``NEXUS_BANNER`` или :data:`THEME.default_banner`.
    """
    if console is None:
        console = Console()

    name = resolve_banner(banner)
    try:
        lines, gradient = get_banner(name)
    except ValueError as e:
        # Мягко падаем обратно в classic, чтобы CLI не крашнулся
        # из-за неправильного NEXUS_BANNER.
        console.print(f"[{THEME.warning}]⚠ {e}. Falling back to '{THEME.default_banner}'[/{THEME.warning}]")
        lines, gradient = get_banner(THEME.default_banner)
        name = THEME.default_banner

    # --- правая колонка: key/value --------------------------------------
    info_table = Table(
        show_header=False,
        box=None,
        padding=(0, 2, 0, 0),
    )
    info_table.add_column("Key", style="bold white", no_wrap=True)
    info_table.add_column("Value", style=THEME.success)
    for label, value in _info_rows():
        info_table.add_row(label, value)

    # --- левая колонка: логотип -----------------------------------------
    logo_text = _colorize_lines(lines, gradient)

    # --- общая компоновка -----------------------------------------------
    outer = Table(
        show_header=False,
        box=None,
        padding=(0, 0, 0, 1),
    )
    outer.add_column("Logo", no_wrap=True, min_width=42)
    outer.add_column("Info", no_wrap=False)
    outer.add_row(logo_text, info_table)

    # --- разделитель + бейдж активного баннера -------------------------
    separator = Text(THEME.separator_char * THEME.separator_width, style=THEME.muted)
    banner_badge = Text(
        f"  ✦ banner: {name}",
        style=f"dim {THEME.primary_alt}",
    )

    console.print()
    console.print(outer)
    console.print(separator)
    console.print(banner_badge)
    console.print()
