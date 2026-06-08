"""Unit tests for the :mod:`nexus.commands.run` module.

The tests focus on the helper functions that are pure and can be exercised
without invoking the full CLI.  They verify URL extraction, cache‑key
generation, automatic cache cleaning, API‑key resolution, and the config/environment
loading logic.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, mock_open

# Import the private helpers from the run command module.
from nexus.commands.run import (
    extract_urls,
    _cache_key,
    _auto_clean_cache,
    _resolve_api_key,
    _get_cache,
    _set_cache,
    _save_history,
    _load_config,
    _load_env,
    _response_title,
    _sources_title,
    _URL_RE,
    CACHE_DIR,
    HISTORY_DIR,
    NEXUS_DIR,
)


class TestExtractUrls(unittest.TestCase):
    def test_extract_urls_unique(self):
        text = (
            "Visit https://example.com for info. Also see http://test.org! "
            "Duplicate https://example.com should be ignored."
        )
        urls = extract_urls(text)
        self.assertCountEqual(urls, ["https://example.com", "http://test.org"])

    def test_extract_urls_no_urls(self):
        self.assertEqual(extract_urls("plain text without URLs"), [])

    def test_extract_urls_empty_string(self):
        self.assertEqual(extract_urls(""), [])

    def test_extract_urls_strip_trailing_punctuation(self):
        text = "Check https://example.com/path! and https://test.org/page?q=1."
        urls = extract_urls(text)
        self.assertIn("https://example.com/path", urls)
        self.assertIn("https://test.org/page?q=1", urls)

    def test_extract_urls_multiple_duplicates(self):
        text = "https://a.com https://a.com https://a.com"
        urls = extract_urls(text)
        self.assertEqual(len(urls), 1)
        self.assertEqual(urls[0], "https://a.com")

    def test_extract_urls_preserves_order_of_first_occurrence(self):
        text = "https://b.com then https://a.com then https://b.com again"
        urls = extract_urls(text)
        self.assertEqual(urls, ["https://b.com", "https://a.com"])

    def test_extract_urls_https_only(self):
        """Should only match http/https URLs."""
        text = "ftp://ftp.example.com https://web.example.com"
        urls = extract_urls(text)
        self.assertEqual(urls, ["https://web.example.com"])

    def test_extract_urls_url_with_query_params(self):
        text = "See https://example.com/search?q=hello&lang=en for details"
        urls = extract_urls(text)
        self.assertEqual(len(urls), 1)
        self.assertIn("https://example.com/search?q=hello&lang=en", urls)


class TestCacheKey(unittest.TestCase):
    def test_cache_key_consistency(self):
        key1 = _cache_key("some query")
        key2 = _cache_key("some query")
        self.assertEqual(key1, key2)
        self.assertNotEqual(key1, _cache_key("different"))

    def test_cache_key_different_inputs(self):
        keys = set(_cache_key(t) for t in ["a", "b", "c", "", "test query"])
        self.assertEqual(len(keys), 5)

    def test_cache_key_encoding(self):
        """Non-ASCII text should still produce a valid hash."""
        key = _cache_key("Привет, мир! 🎉")
        self.assertIsInstance(key, str)
        self.assertEqual(len(key), 32)  # md5 hex digest length


class TestGetSetCache(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_set_and_get(self):
        key = _cache_key("test_query")
        with patch("nexus.commands.run.CACHE_DIR", self.tmp_dir):
            _set_cache(key, "response text")
            cached = _get_cache(key, ttl=3600)
        self.assertEqual(cached, "response text")

    def test_get_missing_key(self):
        with patch("nexus.commands.run.CACHE_DIR", self.tmp_dir):
            cached = _get_cache("nonexistent", ttl=3600)
        self.assertIsNone(cached)

    def test_get_expired_key(self):
        key = _cache_key("test")
        with patch("nexus.commands.run.CACHE_DIR", self.tmp_dir):
            _set_cache(key, "old response")
            # Use a TTL of 0 so it's immediately expired
            cached = _get_cache(key, ttl=0)
        self.assertIsNone(cached)

    def test_get_expired_removes_file(self):
        key = _cache_key("test")
        with patch("nexus.commands.run.CACHE_DIR", self.tmp_dir):
            _set_cache(key, "old")
            _get_cache(key, ttl=0)
            cache_path = os.path.join(self.tmp_dir, key)
            self.assertFalse(os.path.isfile(cache_path))


class TestAutoCleanCache(unittest.TestCase):
    def test_auto_clean_cache_removes_old_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                __import__("nexus.commands.run", fromlist=["CACHE_DIR"]),
                "CACHE_DIR",
                tmp_dir,
            ):
                for i in range(3):
                    path = os.path.join(tmp_dir, f"file{i}.cache")
                    with open(path, "wb") as fh:
                        fh.write(b"0" * 200 * 1024)
                _auto_clean_cache(max_size_mb=0.4)
                remaining = os.listdir(tmp_dir)
                self.assertTrue(len(remaining) < 3)

    def test_auto_clean_cache_within_limit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                __import__("nexus.commands.run", fromlist=["CACHE_DIR"]),
                "CACHE_DIR",
                tmp_dir,
            ):
                for i in range(2):
                    path = os.path.join(tmp_dir, f"file{i}.cache")
                    with open(path, "wb") as fh:
                        fh.write(b"0" * 100 * 1024)
                _auto_clean_cache(max_size_mb=10)
                remaining = os.listdir(tmp_dir)
                self.assertEqual(len(remaining), 2)

    def test_auto_clean_cache_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                __import__("nexus.commands.run", fromlist=["CACHE_DIR"]),
                "CACHE_DIR",
                tmp_dir,
            ):
                _auto_clean_cache(max_size_mb=1)
                remaining = os.listdir(tmp_dir)
                self.assertEqual(remaining, [])


class TestResolveApiKey(unittest.TestCase):
    def test_resolve_api_key_from_env(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "secret-key"}):
            key = _resolve_api_key({"provider": "groq"})
            self.assertEqual(key, "secret-key")

    def test_resolve_api_key_ollama_returns_empty(self):
        key = _resolve_api_key({"provider": "ollama"})
        self.assertEqual(key, "")

    def test_resolve_api_key_openai(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-xxx"}):
            key = _resolve_api_key({"provider": "openai"})
            self.assertEqual(key, "sk-xxx")

    def test_resolve_api_key_anthropic(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-xxx"}):
            key = _resolve_api_key({"provider": "anthropic"})
            self.assertEqual(key, "sk-ant-xxx")

    def test_resolve_api_key_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            key = _resolve_api_key({"provider": "groq"})
            self.assertIsNone(key)


class TestLoadConfig(unittest.TestCase):
    @patch("nexus.commands.run.load_config_validated")
    @patch("nexus.commands.run.NexusConfig")
    def test_load_config_success(self, MockNexusConfig, mock_load):
        mock_cfg = MagicMock()
        mock_cfg.to_dict.return_value = {"provider": "groq", "timeout": 30}
        mock_load.return_value = mock_cfg
        result = _load_config("/path/to/config.yaml")
        self.assertEqual(result["provider"], "groq")

    @patch("nexus.commands.run.load_config_validated")
    @patch("nexus.commands.run.NexusConfig")
    def test_load_config_fallback_on_error(self, MockNexusConfig, mock_load):
        from nexus.core.config import ConfigError
        mock_load.side_effect = ConfigError("invalid config")
        mock_default = MockNexusConfig.return_value
        mock_default.to_dict.return_value = {"provider": "groq", "timeout": 30}
        result = _load_config(None)
        self.assertEqual(result["provider"], "groq")


class TestLoadEnv(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.patcher = patch("nexus.commands.run.NEXUS_DIR", self.tmp_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_ollama_no_key_needed(self):
        result = _load_env(config={"provider": "ollama"})
        self.assertEqual(result, "")

    def test_load_env_direct_env_var(self):
        """Should find the key from the environment variable directly."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "env-key"}, clear=True):
            result = _load_env(config={"provider": "groq"})
        self.assertEqual(result, "env-key")

    def test_load_env_from_dotenv(self):
        """Should find the key from ~/.nexus/.env when env var is not set."""
        # Create a .env file in the mocked NEXUS_DIR
        env_path = os.path.join(self.tmp_dir, ".env")
        with open(env_path, "w") as f:
            f.write("GROQ_API_KEY=from-dotenv\n")

        with patch.dict(os.environ, {}, clear=True):
            # On first call, load_dotenv will load it, then os.getenv should find it
            result = _load_env(config={"provider": "groq"})
        self.assertEqual(result, "from-dotenv")


class TestSaveHistory(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.patcher = patch("nexus.commands.run.HISTORY_DIR", self.tmp_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_save_history_creates_file(self):
        _save_history("prompt text", "response text", {"total_tokens": 10})
        history_file = os.path.join(self.tmp_dir, "history.log")
        self.assertTrue(os.path.isfile(history_file))
        with open(history_file, "r") as f:
            content = f.read()
        self.assertIn("prompt text", content)
        self.assertIn("response text", content)

    def test_save_history_io_error_does_not_raise(self):
        with patch("builtins.open", side_effect=OSError("permission denied")):
            _save_history("p", "r", {})  # Should not raise

    def test_save_history_appends(self):
        _save_history("first", "resp1", {})
        _save_history("second", "resp2", {})
        history_file = os.path.join(self.tmp_dir, "history.log")
        with open(history_file, "r") as f:
            content = f.read()
        self.assertIn("first", content)
        self.assertIn("second", content)


class TestTitleHelpers(unittest.TestCase):
    def test_response_title(self):
        """Should return a translated string (either key or translated)."""
        title = _response_title()
        self.assertIsInstance(title, str)
        self.assertTrue(len(title) > 0)

    def test_sources_title(self):
        """Should return a translated string."""
        title = _sources_title()
        self.assertIsInstance(title, str)
        self.assertTrue(len(title) > 0)


class TestExtractUrlsRegex(unittest.TestCase):
    def test_url_regex(self):
        """Test the URL regex directly."""
        text = "See https://example.com/path?q=1#frag for more."
        matches = _URL_RE.findall(text)
        self.assertEqual(len(matches), 1)
        # Note: regex may include trailing punctuation
        self.assertIn("https://example.com/path?q=1", matches[0])


if __name__ == "__main__":
    unittest.main()