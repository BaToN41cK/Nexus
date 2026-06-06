"""
Nexus MCP Server

Exposes Nexus as a Model Context Protocol (MCP) server so that MCP-aware
clients (Claude Desktop, Cursor, Continue, etc.) can call Nexus as a tool.

The server speaks MCP over stdio.  Three tools are registered:

  - ``nexus_run``      : ask Nexus a question (uses the configured provider)
  - ``nexus_search``   : web search only (returns formatted results)
  - ``nexus_fetch``    : load & extract text from a URL

The :func:`main` entry point is also wired to the ``nexus mcp`` subcommand in
:mod:`nexus.cli`.

Dependencies
------------
The official MCP Python SDK is required at runtime::

    pip install mcp

If the SDK is not installed, :func:`main` prints a friendly error and exits
with a non-zero code.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional import of the MCP SDK
# ---------------------------------------------------------------------------


def _import_mcp() -> Dict[str, Any]:
    """Import the MCP SDK, raising a clear error if it is not installed."""
    try:
        from mcp.server import Server  # type: ignore
        from mcp.server.stdio import stdio_server  # type: ignore
        from mcp.types import TextContent, Tool  # type: ignore
    except ImportError as e:  # pragma: no cover - depends on optional dep
        raise SystemExit(
            "The 'mcp' package is required to run the Nexus MCP server.\n"
            "Install it with:  pip install mcp\n"
            f"Original error: {e}"
        ) from e
    return {
        "Server": Server,
        "stdio_server": stdio_server,
        "TextContent": TextContent,
        "Tool": Tool,
    }


# ---------------------------------------------------------------------------
# Nexus backend helpers
# ---------------------------------------------------------------------------


def _build_nexus_toolkit() -> Dict[str, Any]:
    """
    Construct a small toolkit that the MCP tools can call.  We import the
    heavy dependencies lazily so that simply listing ``python -m nexus.mcp_server``
    does not require them.
    """
    from nexus.core.config import ConfigError, load_config
    from nexus.core.agent import NexusAgent
    from nexus.core.web_search import WebSearcher, load_config_from_yaml
    from nexus.core.paths import SEARCH_CACHE_DIR, ensure_dirs

    try:
        config = load_config()
    except ConfigError as e:
        raise SystemExit(f"Invalid Nexus configuration: {e}")
    ensure_dirs()
    web_config = load_config_from_yaml(config.to_dict())

    api_key = os.getenv(config.api_key_env_var() or "", "") if config.api_key_env_var() else ""
    agent = None
    if config.provider == "ollama" or api_key:
        agent = NexusAgent(
            api_key=api_key,
            model=config.groq_model,
            provider=config.provider,
            base_url=config.base_url,
            timeout=config.timeout,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

    searcher = None
    if web_config.enabled:
        try:
            searcher = WebSearcher(web_config, SEARCH_CACHE_DIR)
        except Exception as e:  # pragma: no cover
            logger.warning("WebSearcher init failed: %s", e)

    return {"config": config, "agent": agent, "searcher": searcher}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _tool_nexus_run(toolkit: Dict[str, Any], prompt: str, system_prompt: Optional[str] = None) -> str:
    agent = toolkit.get("agent")
    if agent is None:
        return "[Nexus MCP] No API key configured for the active provider."
    result = agent.generate_response(prompt, system_prompt=system_prompt)
    return result.get("text", "")


def _tool_nexus_search(toolkit: Dict[str, Any], query: str, max_results: int = 5) -> str:
    searcher = toolkit.get("searcher")
    if searcher is None:
        return "[Nexus MCP] Web search is not enabled in the configuration."
    results = searcher.search(query, max_results=max_results)
    if not results:
        return "(no results)"
    return "\n".join(f"- {r.title} | {r.url} | {r.snippet}" for r in results)


def _tool_nexus_fetch(toolkit: Dict[str, Any], url: str) -> str:
    from nexus.core.content_loader import load
    text = load(url)
    if not text or text.startswith("["):
        return f"[Nexus MCP] Could not fetch {url}: {text}"
    max_chars = 12_000
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... truncated, total {len(text)} chars ...]"
    return text


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def build_server() -> Any:
    """Create and return the configured MCP :class:`Server` instance."""
    mcp = _import_mcp()
    Server = mcp["Server"]
    TextContent = mcp["TextContent"]
    Tool = mcp["Tool"]
    stdio_server = mcp["stdio_server"]

    server = Server("nexus")
    toolkit = _build_nexus_toolkit()

    @server.list_tools()
    async def _list_tools():
        return [
            Tool(
                name="nexus_run",
                description=(
                    "Ask Nexus anything. Uses the configured LLM provider "
                    "(Groq, OpenAI, Anthropic, or Ollama) and may use web "
                    "search automatically when enabled."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The user's question or task."},
                        "system_prompt": {"type": "string", "description": "Optional system instruction override."},
                    },
                    "required": ["prompt"],
                },
            ),
            Tool(
                name="nexus_search",
                description="Search the web via the configured search backend.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="nexus_fetch",
                description="Load and extract text from a URL (web page, PDF, DOCX, YouTube, ...).",
                inputSchema={
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any]):
        try:
            if name == "nexus_run":
                text = _tool_nexus_run(toolkit, arguments.get("prompt", ""), arguments.get("system_prompt"))
            elif name == "nexus_search":
                text = _tool_nexus_search(toolkit, arguments.get("query", ""), int(arguments.get("max_results", 5)))
            elif name == "nexus_fetch":
                text = _tool_nexus_fetch(toolkit, arguments.get("url", ""))
            else:
                text = f"[Nexus MCP] Unknown tool: {name!r}"
        except Exception as e:  # never let a tool crash the server
            logger.exception("Tool %s raised", name)
            text = f"[Nexus MCP] Error in {name}: {e}"
        return [TextContent(type="text", text=text)]

    return server, stdio_server


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server over stdio (blocks until the client disconnects)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    server, stdio_server = build_server()

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    try:
        import asyncio
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("Nexus MCP server stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
