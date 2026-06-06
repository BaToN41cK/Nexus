"""Tests for the MCP server module.

Most of the server logic requires the optional ``mcp`` SDK, so we mock it
out and verify that the tool wiring / error handling work correctly.
"""

import unittest
from unittest.mock import MagicMock, patch

from nexus import mcp_server


class TestImportMcp(unittest.TestCase):
    def test_clear_error_when_mcp_missing(self):
        with patch.dict("sys.modules", {"mcp": None, "mcp.server": None, "mcp.server.stdio": None, "mcp.types": None}):
            with patch("builtins.__import__", side_effect=ImportError("no mcp")):
                with self.assertRaises(SystemExit) as cm:
                    mcp_server._import_mcp()
        self.assertIn("pip install mcp", str(cm.exception))


class TestToolImplementations(unittest.TestCase):
    def test_nexus_run_without_agent(self):
        out = mcp_server._tool_nexus_run({}, "hello")
        self.assertIn("No API key", out)

    def test_nexus_search_without_searcher(self):
        out = mcp_server._tool_nexus_search({}, "x")
        self.assertIn("not enabled", out)

    def test_nexus_search_formats_results(self):
        from nexus.core.web_search import SearchResult, WebSearcher

        searcher = MagicMock(spec=WebSearcher)
        searcher.search.return_value = [
            SearchResult("T", "https://t", "sn", "duckduckgo"),
        ]
        out = mcp_server._tool_nexus_search({"searcher": searcher}, "q", 3)
        self.assertIn("https://t", out)
        searcher.search.assert_called_once_with("q", max_results=3)

    def test_nexus_search_no_results(self):
        from nexus.core.web_search import WebSearcher

        searcher = MagicMock(spec=WebSearcher)
        searcher.search.return_value = []
        out = mcp_server._tool_nexus_search({"searcher": searcher}, "q")
        self.assertEqual(out, "(no results)")

    def test_nexus_fetch_reports_loader_error(self):
        # No network: a non-existent URL will hit the loader's error path.
        out = mcp_server._tool_nexus_fetch({}, "https://nonexistent.invalid.local/abc")
        self.assertTrue(out.startswith("[Nexus MCP]"))


if __name__ == "__main__":
    unittest.main()
