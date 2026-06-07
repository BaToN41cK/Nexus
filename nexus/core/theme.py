"""
Nexus Theme — единая палитра и стилевые константы для CLI.

Все цвета и Rich-стили определены в одном месте, чтобы вывод
выглядел консистентно (логотип, панели, таблицы, спиннеры, логи
используют одни и те же оттенки).

Использование:
    from nexus.core.theme import THEME, gradients

    console.print(THEME.assistant_text)        # → "#10B981"
    console.print(f"[{THEME.primary}]hello[/{THEME.primary}]")
    text = gradients.purple(logo_lines)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Tuple


# ---------------------------------------------------------------------------
# Палитра
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NexusTheme:
    """Брендовая палитра Nexus.

    Цвета подобраны так, чтобы:
      * хорошо читаться на тёмных и светлых терминалах;
      * быть узнаваемо «AI/tech» (фиолетовый + бирюзовый);
      * иметь достаточный контраст для панелей и заголовков.
    """

    # Базовые оттенки
    primary: str = "#7C3AED"      # фиолетовый — основной брендовый
    primary_alt: str = "#A78BFA"  # светло-фиолетовый
    accent: str = "#06B6D4"       # бирюзовый
    success: str = "#10B981"      # зелёный (ответы ассистента, OK)
    warning: str = "#F59E0B"      # янтарный
    error: str = "#EF4444"        # красный
    info: str = "#3B82F6"         # синий (web-поиск, логи)
    muted: str = "#6B7280"        # серый (подсказки, dim-элементы)

    # Классический красный — оставлен для баннера «classic», чтобы
    # старые пользователи не пугались нового цвета. Использовать ТОЛЬКО
    # в ``banners.CLASSIC``.
    legacy_red: str = "#FF0000"

    # Текст
    text: str = "#E5E7EB"
    text_muted: str = "#9CA3AF"

    # Готовые Rich-стили (можно использовать как style="...")
    style_user_prompt: str = "bold #7C3AED"
    style_assistant: str = "#10B981"
    style_code: str = "#06B6D4"
    style_panel_border: str = "#7C3AED"
    style_panel_title: str = "bold #A78BFA"
    style_table_header: str = "bold #7C3AED"
    style_table_row: str = "#E5E7EB"
    style_dim: str = "dim #6B7280"

    # Баннер по умолчанию
    default_banner: str = "classic"

    # Разделитель для fastfetch-style блока
    separator_char: str = "─"
    separator_width: int = 55


THEME = NexusTheme()


# ---------------------------------------------------------------------------
# Градиенты
# ---------------------------------------------------------------------------


class _Gradients:
    """Несколько готовых градиентов для баннеров и подсветок."""

    @property
    def purple_colors(self) -> Tuple[str, ...]:
        return ("#7C3AED", "#8B5CF6", "#A78BFA", "#C4B5FD", "#DDD6FE", "#EDE9FE")

    @property
    def cyan_purple(self) -> Tuple[str, ...]:
        return ("#06B6D4", "#0EA5E9", "#6366F1", "#8B5CF6", "#7C3AED", "#6D28D9")

    @property
    def ocean(self) -> Tuple[str, ...]:
        return ("#0EA5E9", "#06B6D4", "#22D3EE", "#67E8F9", "#A5F3FC", "#CFFAFE")

    @property
    def aurora(self) -> Tuple[str, ...]:
        return ("#10B981", "#06B6D4", "#6366F1", "#8B5CF6", "#EC4899", "#F59E0B")

    @property
    def legacy_red(self) -> Tuple[str, ...]:
        return ("#FF0000", "#E60000", "#CC0000", "#B30000", "#990000", "#800000")


gradients = _Gradients()


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def style_banner(name: str | None = None) -> str:
    """Вернуть имя баннера по умолчанию или провалидировать пользовательский.

    Используется в ``--banner`` аргументе CLI.
    """
    available = ("classic",)
    if not name:
        return THEME.default_banner
    name = name.lower()
    if name not in available:
        raise ValueError(
            f"Unknown banner '{name}'. Available: {', '.join(available)}"
        )
    return name


def themed(text: str, color: str) -> str:
    """Обёртка для f-строк, чтобы не дублировать ``[{c}]...[/{c}]``."""
    return f"[{color}]{text}[/{color}]"
