"""
Nexus Banners — коллекция ASCII-логотипов для fastfetch-style вывода.

Каждый баннер представляет собой кортеж ``(lines, gradient)``, где:
  * ``lines``  — список строк одинаковой ширины;
  * ``gradient`` — кортеж hex-цветов, накладываемых на строки циклически.

В коллекции остался только исторический баннер ``classic`` (красный градиент) —
для преемственности со старыми пользователями.

Пользователь выбирает баннер флагом ``--banner <name>`` или
переменной ``NEXUS_BANNER``. По умолчанию — ``THEME.default_banner``.
"""
from __future__ import annotations

from typing import Dict, Sequence, Tuple

from nexus.core.theme import THEME, gradients


# ---------------------------------------------------------------------------
# Баннеры. Каждая запись — tuple(lines, gradient).
# ---------------------------------------------------------------------------


# --- CLASSIC ---------------------------------------------------------------
# Исходный логотип проекта (красный градиент). Не трогаем — оставлен для
# пользователей, которые привыкли к нему.
CLASSIC: Tuple[Sequence[str], Sequence[str]] = (
    [
        "__  __ _______ __   __ __   __  _____ ",
        "| \\ | ||  ___| \\ \\ / / | | | |/  ___|",
        "|  \\| || |__    \\ V /  | | | |\\ `--. ",
        "| . ` ||  __|   /   \\  | | | | `--. \\\\",
        "| |\\  || |___  / /^\\ \\ \\ | | //\\__/ /",
        "\\_| \\_/\\____/  \\/   \\/  \\___/ \\____/ ",
    ],
    gradients.legacy_red,
)


# ---------------------------------------------------------------------------
# Реестр
# ---------------------------------------------------------------------------


BANNERS: Dict[str, Tuple[Sequence[str], Sequence[str]]] = {
    "classic": CLASSIC,
}


def available_banners() -> Tuple[str, ...]:
    """Возвращает кортеж имён доступных баннеров (для --help)."""
    return tuple(BANNERS.keys())


def get_banner(name: str | None = None) -> Tuple[Sequence[str], Sequence[str]]:
    """Вернуть ``(lines, gradient)`` по имени, или дефолтный, или кинуть ``ValueError``."""
    key = (name or THEME.default_banner).lower()
    if key not in BANNERS:
        raise ValueError(
            f"Unknown banner '{name}'. Available: {', '.join(BANNERS)}"
        )
    return BANNERS[key]


def is_pure_ascii(name: str) -> bool:
    """True, если баннер не содержит Unicode-блоков (рисование работает везде)."""
    return name in ("classic",)
