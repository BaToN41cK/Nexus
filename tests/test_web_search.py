"""Tests for the web search module."""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from nexus.core.config import ConfigError
from nexus.core.web_search import (
    BingBackend,
    DuckDuckGoBackend,
    SearchBackend,
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

    def test_to_from_dict_empty(self):
        r = SearchResult(title="", url="", snippet="", source="")
        d = r.to_dict()
        self.assertEqual(d["title"], "")
        r2 = SearchResult.from_dict(d)
        self.assertEqual(r2.title, "")
        self.assertEqual(r2.url, "")

    def test_from_dict_missing_keys(self):
        r = SearchResult.from_dict({})
        self.assertEqual(r.title, "")
        self.assertEqual(r.url, "")
        self.assertEqual(r.snippet, "")
        self.assertEqual(r.source, "")

    def test_from_dict_partial_keys(self):
        r = SearchResult.from_dict({"title": "T"})
        self.assertEqual(r.title, "T")
        self.assertEqual(r.url, "")


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
        self.assertIsNotNone(cache.get("q"))

    def test_key_is_normalized(self):
        cache = _SearchCache(self.tmp, ttl_seconds=60)
        cache.set("Hello World", [SearchResult("a", "u", "s", "x")], "x")
        self.assertIsNotNone(cache.get("hello world"))

    def test_get_non_existent(self):
        cache = _SearchCache(self.tmp, ttl_seconds=60)
        self.assertIsNone(cache.get("no such query"))

    def test_get_corrupted_json(self):
        cache = _SearchCache(self.tmp, ttl_seconds=60)
        key = cache._key("corrupted")
        path = os.path.join(self.tmp, f"{key}.json")
        with open(path, "w") as f:
            f.write("not valid json")
        self.assertIsNone(cache.get("corrupted"))

    def test_get_io_error_returns_none(self):
        # Simulate IOError by patching json.load
        cache = _SearchCache(self.tmp, ttl_seconds=60)
        cache.set("q", [SearchResult("a", "https://a", "sa", "x")], "x")
        with patch("json.load", side_effect=IOError("read error")):
            result = cache.get("q")
        self.assertIsNone(result)

    def test_set_io_error_does_not_raise(self):
        cache = _SearchCache(self.tmp, ttl_seconds=60)
        results = [SearchResult("a", "https://a", "sa", "x")]
        # Patch open to raise IOError
        with patch("builtins.open", side_effect=IOError("permission denied")):
            # Should not raise
            cache.set("q", results, "x")

    def test_get_expired_removes_file(self):
        cache = _SearchCache(self.tmp, ttl_seconds=0)
        cache.set("q", [SearchResult("a", "https://a", "sa", "x")], "x")
        # Change TTL so entry becomes expired
        cache2 = _SearchCache(self.tmp, ttl_seconds=1)
        time.sleep(1.2)
        self.assertIsNone(cache2.get("q"))
        # File should be removed
        key = cache._key("q")
        path = os.path.join(self.tmp, f"{key}.json")
        self.assertFalse(os.path.isfile(path))


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

    def test_unwrap_empty(self):
        self.assertEqual(DuckDuckGoBackend._unwrap_redirect(""), "")

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

    def test_parse_fallback_without_snippet(self):
        """Fallback path: scrape bare links when no result blocks matched."""
        html = """
        <html><body>
          <a class="result__a" href="https://fallback.test/">Fallback Title</a>
        </body></html>
        """
        backend = DuckDuckGoBackend(timeout=1)
        results = backend._parse(html, max_results=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://fallback.test/")

    def test_parse_skips_non_http_links(self):
        html = """
        <html><body>
          <div class="result">
            <a class="result__a" href="/relative/path">Relative</a>
            <a class="result__snippet">sn</a>
          </div>
          <div class="result">
            <a class="result__a" href="ftp://files.test/">FTP</a>
            <a class="result__snippet">sn</a>
          </div>
        </body></html>
        """
        backend = DuckDuckGoBackend(timeout=1)
        results = backend._parse(html, max_results=5)
        self.assertEqual(len(results), 0)

    def test_parse_respects_max_results(self):
        html = """
        <html><body>
          <div class="result">
            <a class="result__a" href="https://a.test/">A</a>
            <a class="result__snippet">sn</a>
          </div>
          <div class="result">
            <a class="result__a" href="https://b.test/">B</a>
            <a class="result__snippet">sn</a>
          </div>
          <div class="result">
            <a class="result__a" href="https://c.test/">C</a>
            <a class="result__snippet">sn</a>
          </div>
        </body></html>
        """
        backend = DuckDuckGoBackend(timeout=1)
        results = backend._parse(html, max_results=2)
        self.assertEqual(len(results), 2)

    def test_search_returns_empty_on_http_error(self):
        backend = DuckDuckGoBackend(timeout=1)
        with patch.object(backend, "_get", return_value=None):
            results = backend.search("q", max_results=5)
        self.assertEqual(results, [])


class TestBackendHTTPErrors(unittest.TestCase):
    """Verify that backends gracefully handle HTTP/network errors."""

    def test_tavily_post_returns_empty(self):
        backend = TavilyBackend(api_key="fake", timeout=1)
        with patch.object(backend, "_post", return_value=None):
            results = backend.search("q", max_results=5)
        self.assertEqual(results, [])

    def test_searxng_get_returns_empty_on_none(self):
        backend = SearXNGBackend(base_url="https://searx.test", timeout=1)
        with patch.object(backend, "_get", return_value=None):
            results = backend.search("q", max_results=5)
        self.assertEqual(results, [])

    def test_searxng_get_returns_empty_on_non_json(self):
        backend = SearXNGBackend(base_url="https://searx.test", timeout=1)
        with patch.object(backend, "_get", return_value="not json at all"):
            results = backend.search("q", max_results=5)
        self.assertEqual(results, [])

    def test_bing_get_returns_empty_on_none(self):
        backend = BingBackend(api_key="fake", timeout=1)
        with patch.object(backend, "_get", return_value=None):
            results = backend.search("q", max_results=5)
        self.assertEqual(results, [])

    def test_bing_get_returns_empty_on_non_json(self):
        backend = BingBackend(api_key="fake", timeout=1)
        with patch.object(backend, "_get", return_value="not json"):
            results = backend.search("q", max_results=5)
        self.assertEqual(results, [])

    def test_bing_missing_webPages_section(self):
        backend = BingBackend(api_key="fake", timeout=1)
        with patch.object(backend, "_get", return_value=json.dumps({"not_webpages": {}})):
            results = backend.search("q", max_results=5)
        self.assertEqual(results, [])


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

    def test_tavily_falls_back_to_snippet(self):
        backend = TavilyBackend(api_key="fake", timeout=1)
        body = {
            "results": [
                {"title": "T1", "url": "https://1", "snippet": "sn1"},
            ]
        }
        with patch.object(backend, "_post", return_value=body):
            results = backend.search("q", max_results=5)
        self.assertEqual(results[0].snippet, "sn1")

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

    def test_bing_respects_max_results(self):
        backend = BingBackend(api_key="fake", timeout=1)
        body = {
            "webPages": {
                "value": [
                    {"name": f"B{i}", "url": f"https://b{i}", "snippet": sn}
                    for i, sn in enumerate(["sn1", "sn2", "sn3"])
                ]
            }
        }
        with patch.object(backend, "_get", return_value=json.dumps(body)):
            results = backend.search("q", max_results=2)
        self.assertEqual(len(results), 2)

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

    def test_searxng_fallback_to_snippet(self):
        backend = SearXNGBackend(base_url="https://searx.test", timeout=1)
        body = {
            "results": [
                {"title": "S1", "url": "https://s1", "snippet": "sn1"},
            ]
        }
        with patch.object(backend, "_get", return_value=json.dumps(body)):
            results = backend.search("q", max_results=5)
        self.assertEqual(results[0].snippet, "sn1")

    def test_searxng_respects_max_results(self):
        backend = SearXNGBackend(base_url="https://searx.test", timeout=1)
        body = {
            "results": [
                {"title": f"S{i}", "url": f"https://s{i}", "content": f"sn{i}"}
                for i in range(5)
            ]
        }
        with patch.object(backend, "_get", return_value=json.dumps(body)):
            results = backend.search("q", max_results=2)
        self.assertEqual(len(results), 2)


class TestBackendGetPost(unittest.TestCase):
    """Test the HTTP helper methods in SearchBackend."""

    def test_get_success(self):
        backend = SearchBackend(timeout=1)
        mock_resp = MagicMock()
        mock_resp.text = "response text"
        with patch.object(backend.session, "get", return_value=mock_resp):
            text = backend._get("https://example.com")
        self.assertEqual(text, "response text")

    def test_get_request_exception_returns_none(self):
        backend = SearchBackend(timeout=1)
        import requests
        with patch.object(backend.session, "get", side_effect=requests.RequestException("connection error")):
            text = backend._get("https://example.com")
        self.assertIsNone(text)

    def test_post_success(self):
        backend = SearchBackend(timeout=1)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"key": "value"}
        with patch.object(backend.session, "post", return_value=mock_resp):
            data = backend._post("https://example.com", {"q": "test"})
        self.assertEqual(data, {"key": "value"})

    def test_post_request_exception_returns_none(self):
        backend = SearchBackend(timeout=1)
        import requests
        with patch.object(backend.session, "post", side_effect=requests.RequestException("post error")):
            data = backend._post("https://example.com", {})
        self.assertIsNone(data)

    def test_post_json_decode_error_returns_none(self):
        backend = SearchBackend(timeout=1)
        mock_resp = MagicMock()
        mock_resp.json.side_effect = ValueError("no json")
        with patch.object(backend.session, "post", return_value=mock_resp):
            data = backend._post("https://example.com", {})
        self.assertIsNone(data)

    def test_post_http_error_returns_none(self):
        backend = SearchBackend(timeout=1)
        mock_resp = MagicMock()
        import requests
        mock_resp.raise_for_status.side_effect = requests.RequestException("401")
        with patch.object(backend.session, "post", return_value=mock_resp):
            data = backend._post("https://example.com", {})
        self.assertIsNone(data)

    async def _test_get_async_fallback(self):
        """When aiohttp is unavailable, _get_async falls back to sync."""
        backend = SearchBackend(timeout=1)
        with patch("nexus.core.web_search.aiohttp", None):
            with patch.object(backend, "_get", return_value="sync fallback"):
                text = await backend._get_async("https://example.com")
        self.assertEqual(text, "sync fallback")

    async def _test_post_async_fallback(self):
        backend = SearchBackend(timeout=1)
        with patch("nexus.core.web_search.aiohttp", None):
            with patch.object(backend, "_post", return_value={"sync": True}):
                data = await backend._post_async("https://example.com", {})
        self.assertEqual(data, {"sync": True})


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
        with self.assertRaises(ConfigError):
            WebSearchConfig(enabled=True, backend="unknown")

    def test_search_returns_empty_when_no_backend_available(self):
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

    def test_search_cache_disabled(self):
        cfg = WebSearchConfig(enabled=True, backend="auto", cache_enabled=False)
        ws = WebSearcher(cfg, self.tmp)
        self.assertIsNone(ws.cache)
        # Should still work, just bypasses cache
        results = ws.search("anything")
        self.assertIsInstance(results, list)

    def test_search_backend_exception_is_caught(self):
        cfg = WebSearchConfig(enabled=True, backend="auto")
        ws = WebSearcher(cfg, self.tmp)
        ws._backend.search = MagicMock(side_effect=RuntimeError("backend crash"))
        results = ws.search("q")
        self.assertEqual(results, [])

    def test_search_clamps_max_results(self):
        cfg = WebSearchConfig(enabled=True, backend="auto", max_results=5)
        ws = WebSearcher(cfg, self.tmp)
        # Go above max of 20
        results = ws.search("q", max_results=100)
        self.assertLessEqual(len(results), 20)

    def test_search_min_at_least_one(self):
        cfg = WebSearchConfig(enabled=True, backend="auto", max_results=5)
        ws = WebSearcher(cfg, self.tmp)
        # Should be clamped to at least 1
        results = ws.search("q", max_results=0)
        self.assertIsInstance(results, list)

    def test_search_skips_cache_when_empty(self):
        """Cache should not be written when results are empty."""
        cfg = WebSearchConfig(enabled=True, backend="auto", cache_ttl=60)
        ws = WebSearcher(cfg, self.tmp)
        ws._backend.search = MagicMock(return_value=[])
        with patch.object(ws.cache, "set") as mock_set:
            results = ws.search("q")
        self.assertEqual(results, [])
        mock_set.assert_not_called()

    def test_auto_priority_tavily_first(self):
        cfg = WebSearchConfig(
            enabled=True, backend="auto",
            tavily_api_key="tvly-key",
            bing_api_key="bing-key",
            searxng_url="https://sx.test",
        )
        ws = WebSearcher(cfg, self.tmp)
        self.assertEqual(ws.backend_name, "tavily")

    def test_auto_priority_bing_when_no_tavily(self):
        cfg = WebSearchConfig(
            enabled=True, backend="auto",
            tavily_api_key="",
            bing_api_key="bing-key",
            searxng_url="https://sx.test",
        )
        ws = WebSearcher(cfg, self.tmp)
        self.assertEqual(ws.backend_name, "bing")

    def test_select_backend_explicit_duckduckgo(self):
        cfg = WebSearchConfig(enabled=True, backend="duckduckgo")
        with patch.dict(os.environ, {}, clear=True):
            ws = WebSearcher(cfg, self.tmp)
            self.assertEqual(ws.backend_name, "duckduckgo")

    def test_explicit_backend_selection(self):
        cfg = WebSearchConfig(enabled=True, backend="bing", bing_api_key="bk")
        ws = WebSearcher(cfg, self.tmp)
        self.assertEqual(ws.backend_name, "bing")

    def test_explicit_backend_missing_key_falls_to_unknown(self):
        """If explicit backend is set but key is missing, auto is used."""
        cfg = WebSearchConfig(enabled=True, backend="tavily")
        with patch.dict(os.environ, {}, clear=True):
            ws = WebSearcher(cfg, self.tmp)
            self.assertEqual(ws.backend_name, "none")


class TestFetchTop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = WebSearchConfig(enabled=True, backend="auto", fetch_top_n=2)
        self.ws = WebSearcher(self.cfg, self.tmp)

    def tearDown(self):
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        os.rmdir(self.tmp)

    def test_fetch_top_empty_results(self):
        result = self.ws.fetch_top([])
        self.assertEqual(result, [])

    def test_fetch_top_zero_limit(self):
        cfg = WebSearchConfig(enabled=True, backend="auto", fetch_top_n=0)
        ws = WebSearcher(cfg, self.tmp)
        result = ws.fetch_top([SearchResult("t", "https://x", "s", "x")])
        self.assertEqual(result, [])

    def test_fetch_top_skips_failed_urls(self):
        results = [
            SearchResult("T1", "https://1", "sn1", "x"),
            SearchResult("T2", "https://2", "sn2", "x"),
        ]
        with patch("nexus.core.content_loader.load",
                   side_effect=[None, RuntimeError("network error")]):
            fetched = self.ws.fetch_top(results)
        self.assertEqual(len(fetched), 0)

    def test_fetch_top_skips_error_text(self):
        results = [SearchResult("T1", "https://1", "sn1", "x")]
        with patch("nexus.core.content_loader.load",
                   return_value="[Ошибка: not found]"):
            fetched = self.ws.fetch_top(results)
        self.assertEqual(len(fetched), 0)

    def test_fetch_top_respects_n_parameter(self):
        results = [
            SearchResult("T1", "https://1", "sn1", "x"),
            SearchResult("T2", "https://2", "sn2", "x"),
            SearchResult("T3", "https://3", "sn3", "x"),
        ]
        with patch("nexus.core.content_loader.load",
                   return_value="some content"):
            fetched = self.ws.fetch_top(results, n=1)
        self.assertEqual(len(fetched), 1)


class TestLoadConfigFromYaml(unittest.TestCase):
    def test_defaults_when_section_missing(self):
        cfg = load_config_from_yaml({})
        self.assertEqual(cfg.backend, "auto")
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.max_results, 5)

    def test_defaults_when_section_is_none(self):
        cfg = load_config_from_yaml({"web_search": None})
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.backend, "auto")

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

    def test_unknown_keys_ignored(self):
        cfg = load_config_from_yaml({
            "web_search": {
                "unknown_key": "value",
                "backend": "duckduckgo",
            }
        })
        self.assertEqual(cfg.backend, "duckduckgo")


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

    def test_long_text_truncated(self):
        results = [SearchResult("T", "https://x", "sn", "duckduckgo")]
        long_body = "X" * 10000
        fetched = [(results[0], long_body)]
        with patch.object(self.ws, "search", return_value=results), \
             patch.object(self.ws, "fetch_top", return_value=fetched):
            ctx, used = self.ws.search_and_format("q")
        self.assertIn("[...обрезано...]", ctx)
        self.assertLess(len(ctx), 10000)


class TestWebSearchConfigValidation(unittest.TestCase):
    """Test WebSearchConfig validation in __post_init__."""

    def test_invalid_timeout(self):
        with self.assertRaises(ConfigError):
            WebSearchConfig(enabled=True, timeout=0)

    def test_invalid_cache_ttl_negative(self):
        with self.assertRaises(ConfigError):
            WebSearchConfig(enabled=True, cache_ttl=-1)

    def test_max_results_too_high(self):
        with self.assertRaises(ConfigError):
            WebSearchConfig(enabled=True, max_results=25)

    def test_max_results_too_low(self):
        with self.assertRaises(ConfigError):
            WebSearchConfig(enabled=True, max_results=0)

    def test_fetch_top_n_too_high(self):
        with self.assertRaises(ConfigError):
            WebSearchConfig(enabled=True, fetch_top_n=15)


if __name__ == "__main__":
    unittest.main()