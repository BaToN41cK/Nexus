"""
Web Search Module for Nexus.

Provides a unified interface for searching the web from multiple backends:
  - DuckDuckGo (HTML, no API key required) — default fallback
  - Tavily (REST API; recommended for LLM agents)
  - SearXNG (self-hosted or public instance)
  - Bing (Azure Bing Web Search)

The :class:`WebSearcher` facade auto-selects a backend based on the
availability of API keys / configuration, applies a TTL-based disk cache
in ``~/.nexus/search_cache/`` and exposes a single ``search()`` method that
returns a list of :class:`SearchResult` objects.

The class is designed to fail silently: any backend error is logged and
returns an empty list, so the rest of Nexus can fall back to plain LLM mode
without crashing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import asyncio
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# Optional async HTTP client – used if available for faster I/O.
try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None

from nexus.core.config import WebSearchConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str
    source: str = ""  # backend name that produced this result

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "SearchResult":
        return cls(
            title=data.get("title", ""),
            url=data.get("url", ""),
            snippet=data.get("snippet", ""),
            source=data.get("source", ""),
        )


# ---------------------------------------------------------------------------
# Cache (TTL, JSON, per-query)
# ---------------------------------------------------------------------------


class _SearchCache:
    """Disk-backed TTL cache for search results.

    Files are stored as JSON in ``~/.nexus/search_cache/<md5>.json`` with
    timestamp + backend name + results list. Expired entries are deleted
    on read.
    """

    def __init__(self, cache_dir: str, ttl_seconds: int = 3600):
        self.cache_dir = cache_dir
        self.ttl = ttl_seconds
        os.makedirs(self.cache_dir, exist_ok=True)

    @staticmethod
    def _key(query: str) -> str:
        normalized = query.strip().lower()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[List[SearchResult]]:
        path = os.path.join(self.cache_dir, f"{self._key(query)}.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, IOError) as e:
            logger.debug("Cache read error for %s: %s", path, e)
            return None
        ts = data.get("ts", 0)
        if self.ttl > 0 and (time.time() - ts) > self.ttl:
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        return [SearchResult.from_dict(r) for r in data.get("results", [])]

    def set(self, query: str, results: List[SearchResult], backend: str) -> None:
        path = os.path.join(self.cache_dir, f"{self._key(query)}.json")
        payload = {
            "ts": time.time(),
            "backend": backend,
            "query": query,
            "results": [r.to_dict() for r in results],
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.debug("Cache write error for %s: %s", path, e)


# ---------------------------------------------------------------------------
# Backend base
# ---------------------------------------------------------------------------


class SearchBackend:
    """Base class for all search backends."""

    name: str = "base"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
        )

    def search(self, query: str, max_results: int) -> List[SearchResult]:
        """Execute the search and return a list of results."""
        raise NotImplementedError

    # ---- helpers ----

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None,
              headers: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Synchronous GET request using ``requests``.

        This method is retained for compatibility when ``aiohttp`` is not
        available or when a backend does not implement an async variant.
        """
        try:
            resp = self.session.get(
                url, params=params, headers=headers, timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning("[%s] HTTP error: %s", self.name, e)
            return None

    async def _get_async(self, url: str, params: Optional[Dict[str, Any]] = None,
                         headers: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Asynchronous GET request using ``aiohttp`` if available.

        Falls back to the synchronous ``_get`` implementation when ``aiohttp``
        cannot be imported. This provides a non‑blocking alternative for
        backends that support async operation.
        """
        if aiohttp is None:
            # aiohttp not installed – use the sync version in a thread.
            return await asyncio.to_thread(self._get, url, params, headers)
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=headers) as resp:
                    resp.raise_for_status()
                    return await resp.text()
        except Exception as e:
            logger.warning("[%s] Async HTTP error: %s", self.name, e)
            return None

    def _post(self, url: str, json_body: Dict[str, Any],
              headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        """Synchronous POST request using ``requests``.

        Kept for compatibility when async is not available.
        """
        try:
            resp = self.session.post(
                url, json=json_body, headers=headers, timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning("[%s] HTTP error: %s", self.name, e)
            return None
        except ValueError as e:
            logger.warning("[%s] JSON decode error: %s", self.name, e)
            return None

    async def _post_async(self, url: str, json_body: Dict[str, Any],
                          headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        """Asynchronous POST request using ``aiohttp`` if available.

        Falls back to the synchronous version executed in a thread when
        ``aiohttp`` is missing.
        """
        if aiohttp is None:
            return await asyncio.to_thread(self._post, url, json_body, headers)
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=json_body, headers=headers) as resp:
                    resp.raise_for_status()
                    return await resp.json()
        except Exception as e:
            logger.warning("[%s] Async HTTP error: %s", self.name, e)
            return None


# ---------------------------------------------------------------------------
# DuckDuckGo (HTML, no API key)
# ---------------------------------------------------------------------------


class DuckDuckGoBackend(SearchBackend):
    """DuckDuckGo HTML endpoint backend — no API key required."""

    name = "duckduckgo"
    ENDPOINT = "https://html.duckduckgo.com/html/"

    def search(self, query: str, max_results: int) -> List[SearchResult]:
        html = self._get(self.ENDPOINT, params={"q": query})
        if not html:
            return []
        return self._parse(html, max_results)

    def _parse(self, html: str, max_results: int) -> List[SearchResult]:
        soup = BeautifulSoup(html, "html.parser")
        results: List[SearchResult] = []
        # Modern DDG HTML layout: <a class="result__a"> with <a class="result__snippet">
        for block in soup.select("div.result, div.web-result"):
            title_el = block.select_one("a.result__a, a.result__title")
            snippet_el = block.select_one(".result__snippet, .result__snippet.js-result-snippet")
            href = title_el.get("href", "") if title_el else ""
            # DDG wraps the real URL in a redirect: //duckduckgo.com/l/?uddg=<encoded>
            url = self._unwrap_redirect(href)
            if not url or not url.startswith(("http://", "https://")):
                continue
            title = title_el.get_text(strip=True) if title_el else ""
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            if not title:
                continue
            results.append(SearchResult(
                title=title, url=url, snippet=snippet, source=self.name
            ))
            if len(results) >= max_results:
                break
        if not results:
            # Fallback: scrape any links inside result-like containers
            for a in soup.select("a.result__a, a.result__url"):
                href = a.get("href", "")
                url = self._unwrap_redirect(href)
                if not url.startswith(("http://", "https://")):
                    continue
                title = a.get_text(strip=True) or url
                results.append(SearchResult(
                    title=title, url=url, snippet="", source=self.name
                ))
                if len(results) >= max_results:
                    break
        return results

    @staticmethod
    def _unwrap_redirect(href: str) -> str:
        """DDG wraps links in a redirect: //duckduckgo.com/l/?uddg=<encoded>."""
        if not href:
            return ""
        if "duckduckgo.com/l/?" in href or "uddg=" in href:
            m = re.search(r"uddg=([^&]+)", href)
            if m:
                from urllib.parse import unquote
                return unquote(m.group(1))
        return href


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------


class TavilyBackend(SearchBackend):
    """Tavily Search API (recommended for LLM agents)."""

    name = "tavily"
    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: str, timeout: int = 15):
        super().__init__(timeout=timeout)
        if not api_key:
            raise ValueError("Tavily API key is required")
        self.api_key = api_key

    def search(self, query: str, max_results: int) -> List[SearchResult]:
        body = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
            "search_depth": "basic",
        }
        data = self._post(self.ENDPOINT, body)
        if not data:
            return []
        results: List[SearchResult] = []
        for item in data.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", "") or item.get("snippet", ""),
                source=self.name,
            ))
        return results


# ---------------------------------------------------------------------------
# SearXNG
# ---------------------------------------------------------------------------


class SearXNGBackend(SearchBackend):
    """SearXNG metasearch engine (self-hosted or public instance)."""

    name = "searxng"

    def __init__(self, base_url: str, timeout: int = 15):
        super().__init__(timeout=timeout)
        if not base_url:
            raise ValueError("SearXNG base_url is required")
        self.base_url = base_url.rstrip("/")
        self.search_endpoint = f"{self.base_url}/search"

    def search(self, query: str, max_results: int) -> List[SearchResult]:
        params = {
            "q": query,
            "format": "json",
            "language": "ru",
            "safesearch": 0,
        }
        data = self._get(self.search_endpoint, params=params)
        if not data:
            return []
        try:
            payload = json.loads(data)
        except ValueError:
            return []
        results: List[SearchResult] = []
        for item in payload.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", "") or item.get("snippet", ""),
                source=self.name,
            ))
            if len(results) >= max_results:
                break
        return results


# ---------------------------------------------------------------------------
# Bing (Azure)
# ---------------------------------------------------------------------------


class BingBackend(SearchBackend):
    """Azure Bing Web Search API."""

    name = "bing"
    ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

    def __init__(self, api_key: str, timeout: int = 15):
        super().__init__(timeout=timeout)
        if not api_key:
            raise ValueError("Bing API key is required")
        self.api_key = api_key

    def search(self, query: str, max_results: int) -> List[SearchResult]:
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {"q": query, "count": max_results, "mkt": "ru-RU", "textDecorations": False}
        data = self._get(self.ENDPOINT, params=params, headers=headers)
        if not data:
            return []
        try:
            payload = json.loads(data)
        except ValueError:
            return []
        results: List[SearchResult] = []
        # Web pages section
        for item in payload.get("webPages", {}).get("value", []):
            results.append(SearchResult(
                title=item.get("name", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", ""),
                source=self.name,
            ))
            if len(results) >= max_results:
                break
        return results


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class WebSearcher:
    """High-level facade: auto-pick a backend, apply cache, fetch results."""

    def __init__(self, config: WebSearchConfig, cache_dir: str):
        self.config = config
        self.cache = (
            _SearchCache(cache_dir, ttl_seconds=config.cache_ttl)
            if config.cache_enabled
            else None
        )
        self._backend: Optional[SearchBackend] = self._select_backend()
        if self._backend:
            logger.info("Web search backend: %s", self._backend.name)
        else:
            logger.warning("No web search backend available")

    # ---- backend selection ----

    def _select_backend(self) -> Optional[SearchBackend]:
        backend_name = (self.config.backend or "auto").lower()
        order: List[str]
        if backend_name == "auto":
            order = self._auto_priority()
        elif backend_name in ("duckduckgo", "tavily", "searxng", "bing"):
            order = [backend_name]
        else:
            logger.warning("Unknown backend '%s', falling back to auto", backend_name)
            order = self._auto_priority()

        for name in order:
            try:
                if name == "duckduckgo":
                    return DuckDuckGoBackend(timeout=self.config.timeout)
                if name == "tavily":
                    key = self.config.tavily_api_key or os.getenv("TAVILY_API_KEY", "")
                    if key:
                        return TavilyBackend(api_key=key, timeout=self.config.timeout)
                if name == "searxng":
                    url = self.config.searxng_url or os.getenv("SEARXNG_URL", "")
                    if url:
                        return SearXNGBackend(base_url=url, timeout=self.config.timeout)
                if name == "bing":
                    key = self.config.bing_api_key or os.getenv("BING_API_KEY", "")
                    if key:
                        return BingBackend(api_key=key, timeout=self.config.timeout)
            except Exception as e:
                logger.debug("Failed to init backend %s: %s", name, e)
        return None

    def _auto_priority(self) -> List[str]:
        priority: List[str] = []
        if self.config.tavily_api_key or os.getenv("TAVILY_API_KEY"):
            priority.append("tavily")
        if self.config.bing_api_key or os.getenv("BING_API_KEY"):
            priority.append("bing")
        if self.config.searxng_url or os.getenv("SEARXNG_URL"):
            priority.append("searxng")
        priority.append("duckduckgo")  # fallback
        return priority

    @property
    def backend_name(self) -> str:
        return self._backend.name if self._backend else "none"

    # ---- public API ----

    def search(self, query: str, max_results: Optional[int] = None) -> List[SearchResult]:
        """Search the web and return up to *max_results* results.

        Returns an empty list on any error or if no backend is configured.
        Never raises.
        """
        if not self._backend:
            return []
        limit = max(1, min(max_results or self.config.max_results, 20))

        if self.cache:
            cached = self.cache.get(query)
            if cached is not None:
                logger.debug("Search cache hit: '%s' (%d)", query, len(cached))
                return cached[:limit]

        try:
            results = self._backend.search(query, max_results=limit)
        except Exception as e:
            logger.warning("Search backend '%s' failed: %s", self._backend.name, e)
            results = []

        if self.cache and results:
            self.cache.set(query, results, self._backend.name)
        return results

    def fetch_top(
        self, results: List[SearchResult], n: Optional[int] = None
    ) -> List[Tuple[SearchResult, str]]:
        """Fetch the top-N result pages through the existing content_loader.

        Returns a list of ``(result, text)`` tuples, skipping any URL that
        could not be loaded (e.g. due to network errors or unsupported types).
        """

        from nexus.core.content_loader import load as load_content

        limit = max(0, min(n if n is not None else self.config.fetch_top_n, 10))
        if limit == 0:
            return []
        fetched: List[Tuple[SearchResult, str]] = []
        for r in results[:limit]:
            try:
                text = load_content(r.url)
            except Exception as e:  # never crash on a single URL
                logger.debug("fetch_top: failed to load %s: %s", r.url, e)
                continue
            if not text or text.startswith("[Ошибка") or text.startswith("[Неизвестный"):
                continue
            fetched.append((r, text))
        return fetched

    def search_and_format(
        self, query: str, max_results: Optional[int] = None
    ) -> Tuple[str, List[SearchResult]]:
        """Search the web, fetch top pages, and produce a context block.

        Returns:
            (context_text, fetched_results) — context_text is ready to be
            injected into a LLM prompt, fetched_results is the list of pages
            actually used (with URLs for citing sources).
        """

        results = self.search(query, max_results=max_results)
        if not results:
            return "", []
        fetched = self.fetch_top(results)
        if not fetched:
            return "", results
        blocks: List[str] = []
        for i, (r, text) in enumerate(fetched, 1):
            # Truncate very long pages to keep prompt reasonable
            max_chars = 6000
            snippet = text if len(text) <= max_chars else text[:max_chars] + "\n\n[...обрезано...]"
            blocks.append(
                f"[Источник {i}] {r.title}\nURL: {r.url}\n\n{snippet}"
            )
        context_text = "\n\n---\n\n".join(blocks)
        return context_text, [r for r, _ in fetched]


# ---------------------------------------------------------------------------
# Config loader (parses the ``web_search`` section of a YAML config dict)
# ---------------------------------------------------------------------------


def load_config_from_yaml(config: Dict[str, Any]) -> WebSearchConfig:
    """Build a :class:`WebSearchConfig` from the ``web_search`` YAML section.

    Missing keys fall back to defaults, so the function is safe to call on
    configs that don't yet have the section.
    """

    section = config.get("web_search") or {}
    return WebSearchConfig(
        enabled=bool(section.get("enabled", False)),
        backend=str(section.get("backend", "auto")).lower(),
        max_results=int(section.get("max_results", 5)),
        fetch_top_n=int(section.get("fetch_top_n", 3)),
        timeout=int(section.get("timeout", 15)),
        cache_enabled=bool(section.get("cache_enabled", True)),
        cache_ttl=int(section.get("cache_ttl", 3600)),
        tavily_api_key=str(section.get("tavily_api_key", "") or os.getenv("TAVILY_API_KEY", "")),
        bing_api_key=str(section.get("bing_api_key", "") or os.getenv("BING_API_KEY", "")),
        searxng_url=str(section.get("searxng_url", "") or os.getenv("SEARXNG_URL", "")),
    )
