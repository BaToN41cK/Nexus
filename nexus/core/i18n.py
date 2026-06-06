"""
Lightweight i18n layer for Nexus.

Loads translations from ``nexus/locale/<lang>.json`` and exposes a
``t(key)`` function that returns the localised string (or the key
itself if the translation is missing — so it's always safe to call).

The language is selected via :func:`set_language`, normally driven by
the ``--lang`` CLI flag, the ``NEXUS_LANG`` / ``LANG`` / ``LANGUAGE``
environment variables, or — on Windows where these are usually unset —
the operating system locale.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from typing import Dict, Optional

from nexus.core.paths import LOCALE_DIR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_DEFAULT_LANG = "en"
_SUPPORTED = ("ru", "en")

_translations: Dict[str, Dict[str, str]] = {}
_current_lang: str = "en"
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Human-readable locale names sometimes returned by ``locale.getlocale()``
# on Windows (e.g. ``"Russian_Russia"`` instead of ``"ru_RU"``).
_HUMAN_LANG_TO_ISO = {
    "russian": "ru",
    "english": "en",
    "ukrainian": "uk",
    "belarusian": "be",
    "german": "de",
    "deutsch": "de",
    "french": "fr",
    "spanish": "es",
    "italian": "it",
    "portuguese": "pt",
    "polish": "pl",
    "dutch": "nl",
    "czech": "cs",
    "greek": "el",
    "turkish": "tr",
    "japanese": "ja",
    "chinese": "zh",
    "korean": "ko",
    "arabic": "ar",
    "hebrew": "he",
    "hindi": "hi",
    "hungarian": "hu",
    "romanian": "ro",
    "swedish": "sv",
    "thai": "th",
    "vietnamese": "vi",
    "indonesian": "id",
}


def _normalize_locale(raw: str) -> str:
    """
    Turn any locale string (``"ru-RU"``, ``"ru_RU"``, ``"Russian_Russia"``,
    ``"C"``, ...) into an ISO 639-1 code such as ``"ru"`` or ``"en"``,
    or an empty string if it cannot be mapped.
    """
    if not raw or raw.upper() == "C":
        return ""
    # BCP-47 / POSIX split
    short = raw.split("_")[0].split("-")[0].strip().lower()
    if not short:
        return ""
    if short in {"ru", "en", "uk", "de", "fr", "es", "it", "pt", "pl", "nl", "cs", "el", "tr", "ja", "zh", "ko", "ar", "he", "hi", "hu", "ro", "sv", "th", "vi", "id", "be"}:
        return short
    # Human-readable form (e.g. "Russian")
    if short in _HUMAN_LANG_TO_ISO:
        return _HUMAN_LANG_TO_ISO[short]
    return ""


def _detect_system_locale() -> str:
    """
    Best-effort detection of the operating-system locale.

    Returns a BCP-47-ish string such as ``"ru-RU"`` or ``"en-US"``, or
    an empty string if it cannot be determined.
    """
    # 1. Windows: prefer the Win32 API — it returns a stable BCP-47 tag
    #    regardless of the C runtime's language settings.
    if sys.platform == "win32":
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
                return buf.value
        except Exception:
            pass

    # 2. Python's stdlib locale module.  On Windows this may return a
    #    human-readable form like ``"Russian_Russia"``; ``_normalize_locale``
    #    handles both.
    try:
        import locale as _locale

        for getter in (_locale.getlocale, _locale.getdefaultlocale):
            try:
                value = getter()
            except Exception:
                value = None
            if value and value[0]:
                return value[0]
    except Exception:
        pass

    return ""


def _detect_default_lang() -> str:
    """
    Detect the most appropriate default language.

    Lookup order:
      1. Explicit ``NEXUS_LANG`` env var (highest priority)
      2. The Windows system locale via Win32 on Windows, since
        ``LANG`` is often left over from a Git-Bash/WSL shell and
        does not reflect the user's actual UI language.
      3. ``LANG`` / ``LANGUAGE`` env vars
      4. The POSIX ``locale`` module's idea of the locale
      5. ``"en"`` (hard-coded fallback)
    """
    explicit = os.environ.get("NEXUS_LANG", "").strip()
    if explicit:
        short = _normalize_locale(explicit)
        if short in _SUPPORTED:
            return short

    # Prefer the OS-reported UI locale on Windows.
    if sys.platform == "win32":
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
                short = _normalize_locale(buf.value)
                if short in _SUPPORTED:
                    return short
        except Exception:
            pass

    for var in ("LANG", "LANGUAGE"):
        raw = os.environ.get(var, "")
        if not raw:
            continue
        short = _normalize_locale(raw)
        if short in _SUPPORTED:
            return short

    system_locale = _detect_system_locale()
    if system_locale:
        short = _normalize_locale(system_locale)
        if short in _SUPPORTED:
            return short

    return _DEFAULT_LANG


def _load(lang: str) -> Dict[str, str]:
    """Load ``<LOCALE_DIR>/<lang>.json`` (returns empty dict on failure)."""
    path = os.path.join(LOCALE_DIR, f"{lang}.json")
    if not os.path.isfile(path):
        logger.debug("Locale file not found: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to load locale %s: %s", lang, e)
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def supported_languages() -> tuple:
    """Return the list of supported language codes."""
    return _SUPPORTED


def current_language() -> str:
    """Return the currently active language code."""
    with _lock:
        return _current_lang


def set_language(lang: str) -> str:
    """
    Switch to *lang* and load its translation table.

    Returns the actually active language (may differ from *lang* if the
    requested one is not supported — in that case we fall back to
    ``"en"``).
    """
    global _current_lang
    lang = (lang or "").lower().split("_")[0].split(".")[0]
    if lang not in _SUPPORTED:
        logger.debug("Unsupported language %r, falling back to %s", lang, _DEFAULT_LANG)
        lang = _DEFAULT_LANG
    with _lock:
        if lang not in _translations:
            _translations[lang] = _load(lang)
        _current_lang = lang
    return _current_lang


def t(key: str, **kwargs) -> str:
    """
    Look up *key* in the active translation table.

    Lookup order:
      1. Current language
      2. English fallback
      3. The key itself (so calls are always safe)

    Format placeholders (``{name}``) in the translation string are
    filled from *kwargs* via :func:`str.format`.
    """
    with _lock:
        lang = _current_lang
        table = _translations.get(lang) or {}
        en_table = _translations.get("en") or {}
    text = table.get(key) or en_table.get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

# Eagerly load both supported languages so ``t()`` never touches disk.
_translations["en"] = _load("en")
_translations["ru"] = _load("ru")
set_language(_detect_default_lang())
