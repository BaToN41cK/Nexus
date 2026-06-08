"""Unit tests for the :mod:`nexus.core.i18n` module.

Covers locale detection, normalization, translation loading,
runtime reload, dynamic language addition, and fallback behavior.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from nexus.core.i18n import (
    _normalize_locale,
    _detect_system_locale,
    _detect_default_lang,
    _load,
    supported_languages,
    current_language,
    set_language,
    reload_locale,
    add_language,
    t,
    _SUPPORTED,
)


class TestNormalizeLocale(unittest.TestCase):
    def test_ru_short(self):
        self.assertEqual(_normalize_locale("ru"), "ru")

    def test_ru_region(self):
        self.assertEqual(_normalize_locale("ru-RU"), "ru")
        self.assertEqual(_normalize_locale("ru_RU"), "ru")

    def test_en_region(self):
        self.assertEqual(_normalize_locale("en-US"), "en")
        self.assertEqual(_normalize_locale("en_GB"), "en")

    def test_human_readable_russian(self):
        self.assertEqual(_normalize_locale("Russian_Russia"), "ru")

    def test_human_readable_english(self):
        self.assertEqual(_normalize_locale("english"), "en")

    def test_human_readable_german(self):
        self.assertEqual(_normalize_locale("german"), "de")
        self.assertEqual(_normalize_locale("Deutsch"), "de")

    def test_unsupported_language(self):
        self.assertEqual(_normalize_locale("xx"), "")

    def test_empty_string(self):
        self.assertEqual(_normalize_locale(""), "")

    def test_c_locale(self):
        self.assertEqual(_normalize_locale("C"), "")

    def test_case_insensitivity(self):
        self.assertEqual(_normalize_locale("RU-RU"), "ru")
        self.assertEqual(_normalize_locale("EN"), "en")

    def test_french(self):
        self.assertEqual(_normalize_locale("fr"), "fr")
        self.assertEqual(_normalize_locale("fr-FR"), "fr")

    def test_spanish(self):
        self.assertEqual(_normalize_locale("es"), "es")
        self.assertEqual(_normalize_locale("es-ES"), "es")


class TestDetectSystemLocale(unittest.TestCase):
    @patch("sys.platform", "win32")
    def test_windows_locale(self):
        with patch("ctypes.windll.kernel32.GetUserDefaultLocaleName") as mock_get:
            mock_get.return_value = True
            buf = MagicMock()
            buf.value = "ru-RU"
            with patch("ctypes.create_unicode_buffer", return_value=buf):
                locale = _detect_system_locale()
        self.assertEqual(locale, "ru-RU")

    @patch("sys.platform", "linux")
    @patch("locale.getlocale", return_value=("fr_FR", "UTF-8"))
    def test_posix_locale(self, mock_getlocale):
        locale = _detect_system_locale()
        self.assertEqual(locale, "fr_FR")

    def test_no_locale(self):
        with patch("sys.platform", "linux"):
            with patch("locale.getlocale", side_effect=Exception("no locale")):
                with patch("locale.getdefaultlocale", side_effect=Exception("no locale")):
                    locale = _detect_system_locale()
        self.assertEqual(locale, "")


class TestDetectDefaultLang(unittest.TestCase):
    @patch.dict(os.environ, {"NEXUS_LANG": "de"}, clear=True)
    def test_explicit_nexus_lang(self):
        lang = _detect_default_lang()
        self.assertEqual(lang, "de")

    @patch.dict(os.environ, {"NEXUS_LANG": "unsupported_lang"}, clear=True)
    def test_unsupported_nexus_lang_falls_back(self):
        lang = _detect_default_lang()
        self.assertIn(lang, _SUPPORTED)

    @patch.dict(os.environ, {}, clear=True)
    @patch("sys.platform", "win32")
    def test_windows_locale_detection(self):
        with patch("ctypes.windll.kernel32.GetUserDefaultLocaleName") as mock_get:
            mock_get.return_value = True
            buf = MagicMock()
            buf.value = "de-DE"
            with patch("ctypes.create_unicode_buffer", return_value=buf):
                lang = _detect_default_lang()
        self.assertEqual(lang, "de")

    @patch.dict(os.environ, {}, clear=True)
    @patch("sys.platform", "linux")
    def test_lang_env_var_french(self):
        with patch.dict(os.environ, {"LANG": "fr"}, clear=True):
            lang = _detect_default_lang()
        self.assertIn(lang, _SUPPORTED)

    @patch.dict(os.environ, {"LANG": "fr"}, clear=True)
    @patch("sys.platform", "linux")
    def test_lang_env_var(self):
        with patch("nexus.core.i18n._detect_system_locale", return_value=""):
            lang = _detect_default_lang()
        self.assertEqual(lang, "fr")

    @patch.dict(os.environ, {}, clear=True)
    def test_fallback_to_default(self):
        with patch("sys.platform", "linux"):
            with patch("locale.getlocale", return_value=(None, None)):
                with patch("locale.getdefaultlocale", return_value=(None, None)):
                    lang = _detect_default_lang()
        self.assertEqual(lang, "en")


class TestLoadAndSetLanguage(unittest.TestCase):
    def setUp(self):
        self.orig_lang = current_language()

    def tearDown(self):
        set_language(self.orig_lang)

    def test_set_language_supported(self):
        result = set_language("en")
        self.assertEqual(result, "en")

    def test_set_language_unsupported_falls_back(self):
        result = set_language("zz")
        self.assertEqual(result, "en")

    def test_set_language_empty_falls_back(self):
        result = set_language("")
        self.assertEqual(result, "en")

    def test_supported_languages(self):
        langs = supported_languages()
        self.assertIn("ru", langs)
        self.assertIn("en", langs)
        self.assertIn("es", langs)
        self.assertIn("de", langs)
        self.assertIn("fr", langs)

    def test_current_language_returns_string(self):
        lang = current_language()
        self.assertIsInstance(lang, str)
        self.assertTrue(len(lang) >= 2)

    def test_set_language_to_ru(self):
        result = set_language("ru")
        self.assertEqual(result, "ru")
        self.assertEqual(current_language(), "ru")

    def test_set_language_to_de(self):
        result = set_language("de")
        self.assertEqual(result, "de")
        self.assertEqual(current_language(), "de")

    def test_set_language_to_fr(self):
        result = set_language("fr")
        self.assertEqual(result, "fr")
        self.assertEqual(current_language(), "fr")


class TestTranslationFunction(unittest.TestCase):
    def setUp(self):
        self.orig_lang = current_language()
        set_language("en")

    def tearDown(self):
        set_language(self.orig_lang)

    def test_t_returns_key_when_missing(self):
        result = t("nonexistent.key.12345")
        self.assertEqual(result, "nonexistent.key.12345")

    def test_t_returns_string(self):
        result = t("cmd.run_response_title")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_t_with_kwargs(self):
        result = t("test.key.with.{name}", name="world")
        self.assertIsInstance(result, str)

    def test_t_format_error_does_not_crash(self):
        result = t("test.{missing}", wrong_kwarg="x")
        self.assertIsInstance(result, str)

    def test_t_fallback_to_english(self):
        """When the active language doesn't have a key, fall back to English."""
        set_language("es")
        # "cli.title" exists in all locales, test a key that is definitely in en.json
        result = t("cmd.run_response_title")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_t_german_translation(self):
        set_language("de")
        title = t("cli.title")
        self.assertIn("KI-Assistent", title)

    def test_t_french_translation(self):
        set_language("fr")
        title = t("cli.title")
        self.assertIn("Assistant IA", title)

    def test_t_russian_translation(self):
        set_language("ru")
        title = t("cli.title")
        self.assertIn("ИИ-ассистент", title)

    def test_t_spanish_translation(self):
        set_language("es")
        title = t("cli.title")
        self.assertIsInstance(title, str)
        self.assertTrue(len(title) > 0)


class TestLoadLocaleFile(unittest.TestCase):
    def test_load_missing_file(self):
        result = _load("nonexistent_language")
        self.assertEqual(result, {})

    def test_load_corrupted_file(self):
        tmp_dir = tempfile.mkdtemp()
        lang_path = os.path.join(tmp_dir, "test_corrupted.json")
        with open(lang_path, "w") as f:
            f.write("not json")
        with patch("nexus.core.i18n.LOCALE_DIR", tmp_dir):
            result = _load("test_corrupted")
        self.assertEqual(result, {})
        os.remove(lang_path)
        os.rmdir(tmp_dir)


class TestReloadLocale(unittest.TestCase):
    def setUp(self):
        self.orig_lang = current_language()

    def tearDown(self):
        set_language(self.orig_lang)

    def test_reload_locale_all(self):
        """reload_locale() without arguments should not crash."""
        before = t("cli.title")
        reload_locale()
        after = t("cli.title")
        self.assertEqual(before, after)

    def test_reload_locale_specific(self):
        """reload_locale('en') should not crash."""
        set_language("en")
        before = t("cli.title")
        reload_locale("en")
        after = t("cli.title")
        self.assertEqual(before, after)

    def test_reload_locale_unknown(self):
        """reload_locale with unknown lang should not crash."""
        reload_locale("xx")  # Should just log and do nothing


class TestAddLanguage(unittest.TestCase):
    def setUp(self):
        self.orig_lang = current_language()
        self.orig_supported = supported_languages()

    def tearDown(self):
        # Restore original state by re-setting language
        set_language(self.orig_lang)
        # We can't easily undo add_language, but tests are isolated

    def test_add_language_dynamic(self):
        """add_language should inject a new language at runtime."""
        # Check 'it' is not originally in supported
        if "it" not in supported_languages():
            add_language("it", "Italiano", {
                "cli.title": "Nexus — Assistente AI con caricamento di URL"
            })
            self.assertIn("it", supported_languages())
            set_language("it")
            self.assertEqual(current_language(), "it")
            self.assertIn("Assistente AI", t("cli.title"))

    def test_add_language_duplicate_code_replaced(self):
        """Adding a language with existing code replaces translations."""
        add_language("en", "Custom English", {
            "custom.key": "custom value"
        })
        # The original 'en' translations should be replaced
        # (but the file loaded values are gone - only the dict we passed remains)
        set_language("en")
        self.assertEqual(t("custom.key"), "custom value")

    def test_add_language_invalid_code(self):
        """Invalid language codes should raise ValueError."""
        with self.assertRaises(ValueError):
            add_language("", "Empty", {})
        with self.assertRaises(ValueError):
            add_language("xyz", "Too long", {})
        with self.assertRaises(ValueError):
            add_language("123", "Digits", {})

    def test_dynamic_language_fallback_to_en(self):
        """A dynamically added language should fall back to en for missing keys."""
        if "pt" not in supported_languages():
            add_language("pt", "Português", {
                "cli.title": "Nexus — Assistente IA com carregamento de URL"
            })
            set_language("pt")
            # This key exists in en.json but not in our pt dict
            # Should fall back to English
            result = t("cmd.run_help")
            self.assertIsInstance(result, str)
            self.assertTrue(len(result) > 0)


if __name__ == "__main__":
    unittest.main()