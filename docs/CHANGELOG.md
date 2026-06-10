# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-06-11

### 🎉 Initial stable release

#### Core Features
- **Multi-provider LLM support** — Groq, OpenAI, Anthropic, Ollama with automatic fallback
- **Web search** — DuckDuckGo (free), Tavily, Bing, SearXNG backends
- **Content loading** — YouTube transcripts, PDF, DOCX, PPTX, Excel, web pages
- **ReAct agent** — multi-step reasoning with tool calling
- **MCP server** — integration with Claude Desktop, Cursor, Continue
- **RAG (Retrieval-Augmented Generation)** — FAISS + BM25 hybrid search, ChromaDB support
- **Plugin system** — custom providers, backends, commands, hooks
- **Interactive CLI** — real-time streaming, prompt autocomplete
- **i18n** — 5+ languages (ru, en, de, fr, es), extensible
- **Usage statistics** — token tracking, cost estimation, per-provider breakdown

#### Resilience
- **Circuit Breaker** — automatic failure detection (CLOSED → OPEN → HALF_OPEN)
- **Pre-emptive Health Checker** — background thread pings OPEN providers, auto-recovery
- **Emergency Fallback** — Ollama tiny model → rules-based patterns → offline message
- **Retry with exponential backoff** — jitter, configurable limits
- **Idempotency** — deduplication of identical requests

#### DevOps & Packaging
- **PyPI publishing** — automated via GitHub Actions (trusted publishing)
- **CI/CD** — Python 3.10–3.13, ruff lint/format, mypy, pip-audit security scan
- **Pre-commit hooks** — ruff, mypy, trailing whitespace, detect private keys
- **Makefile** — `make test`, `make lint`, `make release`, `make install-dev`
- **requirements.txt** — one-command full install of all dependencies
- **Docker support** — multi-stage build, Alpine runtime image