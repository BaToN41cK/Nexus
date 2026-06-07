"""Tests for the web search module."""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from nexus.core.config import ConfigError
from nexus.core.web_search import (
    BingBackend,
    DuckDuckGoBackend,
    SearchResult,
    SearXNGBackend,
    TavilyBackend,
    WebSearchConfig,
    WebSearcher,
    _SearchCache,
    load_config_from_yaml,
)


class TestSearchResult(unittest.TestCase):
    def test_to_from_dict(self):
        r = SearchResult(title="t", url="https://x", snippet="s", source="duckduckgo")
        d = r.to_dict()
        self.assertEqual(d["title"], "t")
        self.assertEqual(d["url"], "https://x")
        r2 = SearchResult.from_dict(d)
        self.assertEqual(r, r2)


class TestSearchCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        os.rmdir(self.tmp)

    def test_set_get_roundtrip(self):
        cache = _SearchCache(self.tmp, ttl_seconds=60)
        results = [SearchResult("a", "https://a", "sa", "duckduckgo")]
        cache.set("q1", results, "duckduckgo")
        loaded = cache.get("q1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded[0].title, "a")

    def test_ttl_expiry(self):
        cache = _SearchCache(self.tmp, ttl_seconds=1)
        cache.set("q", [SearchResult("a", "https://a", "sa", "x")], "x")
        time.sleep(1.2)
        self.assertIsNone(cache.get("q"))

    def test_zero_ttl_means_never_expire(self):
        cache = _SearchCache(self.tmp, ttl_seconds=0)
        cache.set("q", [SearchResult("a", "https://a", "sa", "x")], "x")
        # No sleep — should still be available.
        self.assertIsNotNone(cache.get("q"))

    def test_key_is_normalized(self):
        cache = _SearchCache(self.tmp, ttl_seconds=60)
        cache.set("Hello World", [SearchResult("a", "u", "s", "x")], "x")
        self.assertIsNotNone(cache.get("hello world"))


class TestDuckDuckGoParsing(unittest.TestCase):
    def test_unwrap_redirect(self):
        url = DuckDuckGoBackend._unwrap_redirect(
            "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F&foo=1"
        )
        self.assertEqual(url, "https://example.com/")

    def test_unwrap_no_redirect(self):
        self.assertEqual(
            DuckDuckGoBackend._unwrap_redirect("https://example.com/"),
            "https://example.com/",
        )

    def test_parse_extracts_results(self):
        html = """
        <html><body>
          <div class="result">
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.test%2F">
              Title A
            </a>
            <a class="result__snippet">Snippet A</a>
          </div>
          <div class="result">
            <a class="result__a" href="https://b.test/">Title B</a>
            <a class="result__snippet">Snippet B</a>
          </div>
        </body></html>
        """
        backend = DuckDuckGoBackend(timeout=1)
        results = backend._parse(html, max_results=5)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].url, "https://a.test/")
        self.assertEqual(results[0].snippet, "Snippet A")
        self.assertEqual(results[1].url, "https://b.test/")
        self.assertEqual(results[1].title, "Title B")


class TestBackendConstruction(unittest.TestCase):
    def test_tavily_requires_key(self):
        with self.assertRaises(ValueError):
            TavilyBackend(api_key="")

    def test_bing_requires_key(self):
        with self.assertRaises(ValueError):
            BingBackend(api_key="")

    def test_searxng_requires_url(self):
        with self.assertRaises(ValueError):
            SearXNGBackend(base_url="")

    def test_tavily_parses_results(self):
        backend = TavilyBackend(api_key="fake", timeout=1)
        body = {
            "results": [
                {"title": "T1", "url": "https://1", "content": "C1"},
                {"title": "T2", "url": "https://2", "content": "C2"},
            ]
        }
        with patch.object(backend, "_post", return_value=body):
            results = backend.search("q", max_results=5)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "T1")
        self.assertEqual(results[0].source, "tavily")

    def test_bing_parses_results(self):
        backend = BingBackend(api_key="fake", timeout=1)
        body = {
            "webPages": {
                "value": [
                    {"name": "B1", "url": "https://b1", "snippet": "sn1"},
                ]
            }
        }
        with patch.object(backend, "_get", return_value=json.dumps(body)):
            results = backend.search("q", max_results=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://b1")

    def test_searxng_parses_results(self):
        backend = SearXNGBackend(base_url="https://searx.test", timeout=1)
        body = {
            "results": [
                {"title": "S1", "url": "https://s1", "content": "sn1"},
            ]
        }
        with patch.object(backend, "_get", return_value=json.dumps(body)):
            results = backend.search("q", max_results=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "searxng")


class TestWebSearcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        os.rmdir(self.tmp)

    def test_auto_picks_duckduckgo_without_keys(self):
        cfg = WebSearchConfig(enabled=True, backend="auto")
        with patch.dict(os.environ, {}, clear=True):
            ws = WebSearcher(cfg, self.tmp)
            self.assertEqual(ws.backend_name, "duckduckgo")

    def test_auto_picks_tavily_when_key_present(self):
        cfg = WebSearchConfig(enabled=True, backend="auto", tavily_api_key="tvly-fake")
        ws = WebSearcher(cfg, self.tmp)
        self.assertEqual(ws.backend_name, "tavily")

    def test_unknown_backend_raises_error(self):
        # An unknown backend name now raises ConfigError (validated in __post_init__).
        with self.assertRaises(ConfigError):
            WebSearchConfig(enabled=True, backend="unknown")

    def test_search_returns_empty_when_no_backend_available(self):
        # If DuckDuckGo backend is forced unavailable (no session, etc.) and no
        # keys are present, we expect empty list.
        cfg = WebSearchConfig(enabled=True, backend="auto")
        with patch.dict(os.environ, {}, clear=True), \
             patch("nexus.core.web_search.DuckDuckGoBackend",
                   side_effect=RuntimeError("blocked")):
            ws = WebSearcher(cfg, self.tmp)
        self.assertEqual(ws.backend_name, "none")
        self.assertEqual(ws.search("anything"), [])

    def test_search_uses_cache(self):
        cfg = WebSearchConfig(enabled=True, backend="auto", cache_ttl=60)
        ws = WebSearcher(cfg, self.tmp)
        cached = [SearchResult("cached", "https://c", "sn", "duckduckgo")]
        ws.cache.set("cached query", cached, "duckduckgo")
        results = ws.search("cached query")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "cached")


class TestLoadConfigFromYaml(unittest.TestCase):
    def test_defaults_when_section_missing(self):
        cfg = load_config_from_yaml({})
        self.assertEqual(cfg.backend, "auto")
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.max_results, 5)

    def test_full_section(self):
        cfg = load_config_from_yaml({
            "web_search": {
                "enabled": True,
                "backend": "tavily",
                "max_results": 7,
                "fetch_top_n": 2,
                "timeout": 20,
                "cache_enabled": False,
                "cache_ttl": 600,
                "tavily_api_key": "tvly-x",
                "bing_api_key": "b-x",
                "searxng_url": "https://sx",
            }
        })
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.backend, "tavily")
        self.assertEqual(cfg.max_results, 7)
        self.assertEqual(cfg.fetch_top_n, 2)
        self.assertEqual(cfg.timeout, 20)
        self.assertFalse(cfg.cache_enabled)
        self.assertEqual(cfg.cache_ttl, 600)
        self.assertEqual(cfg.tavily_api_key, "tvly-x")
        self.assertEqual(cfg.bing_api_key, "b-x")
        self.assertEqual(cfg.searxng_url, "https://sx")


class TestSearchAndFormat(unittest.TestCase):
    """Test the high-level format pipeline with mocked search + fetch."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = WebSearchConfig(enabled=True, backend="auto", fetch_top_n=2)
        self.ws = WebSearcher(self.cfg, self.tmp)

    def tearDown(self):
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        os.rmdir(self.tmp)

    def test_empty_results_returns_empty(self):
        with patch.object(self.ws, "search", return_value=[]):
            ctx, results = self.ws.search_and_format("q")
        self.assertEqual(ctx, "")
        self.assertEqual(results, [])

    def test_no_pages_loaded_returns_url_list(self):
        with patch.object(
            self.ws, "search",
            return_value=[SearchResult("t", "https://x", "s", "duckduckgo")],
        ), patch.object(self.ws, "fetch_top", return_value=[]):
            ctx, results = self.ws.search_and_format("q")
        self.assertEqual(ctx, "")
        self.assertEqual(len(results), 1)

    def test_full_pipeline(self):
        results = [
            SearchResult("T1", "https://1", "sn1", "duckduckgo"),
            SearchResult("T2", "https://2", "sn2", "duckduckgo"),
        ]
        fetched = [
            (results[0], "Body of page 1 with some content"),
            (results[1], "Body of page 2 with more content"),
        ]
        with patch.object(self.ws, "search", return_value=results), \
             patch.object(self.ws, "fetch_top", return_value=fetched):
            ctx, used = self.ws.search_and_format("q")
        self.assertIn("T1", ctx)
        self.assertIn("https://1", ctx)
        self.assertIn("Body of page 1", ctx)
        self.assertEqual(len(used), 2)


if __name__ == "__main__":
    unittest.main()
