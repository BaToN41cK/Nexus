"""
Nexus CLI - Command Line Interface
"""

import argparse
import logging
import os
import shutil
import sys

# --- Python version gate (before any heavy imports) ---
if sys.version_info < (3, 9):
    print("Nexus requires Python 3.9 or higher.")
    print(f"  You are running Python {sys.version}")
    sys.exit(1)

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nexus.commands.run import (
    DEFAULT_CONFIG_PATH,
    _load_env,
    _render_response,
    _save_history,
    run_command,
)
from nexus.core.agent import NexusAgent
from nexus.core.config import ConfigError, load_config
from nexus.core.banners import available_banners
from nexus.core.logo import list_banners, print_logo
from nexus.core.history import clear as clear_conversation
from nexus.core.i18n import current_language, set_language, supported_languages, t
from nexus.core.paths import (
    CACHE_DIR,
    HISTORY_LOG,
    NEXUS_DIR,
    SEARCH_CACHE_DIR,
    ensure_dirs,
)
from nexus.core.web_search import WebSearcher, load_config_from_yaml

logger = logging.getLogger(__name__)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _build_interactive_completer():
    try:
        from prompt_toolkit.completion import WordCompleter
    except ImportError:
        return None
    commands = [
        "!search on",
        "!search off",
        "!search status",
        "!lang ru",
        "!lang en",
        "!help",
        "exit",
        "quit",
    ]
    return WordCompleter(commands, ignore_case=True)


def _build_prompt_session(history_path, completer):
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.history import FileHistory
    return PromptSession(
        history=FileHistory(history_path),
        auto_suggest=AutoSuggestFromHistory(),
        completer=completer,
        complete_while_typing=True,
    )


def cmd_run(args) -> None:
    run_command(args)


def cmd_interactive(args) -> None:
    # Показываем баннер при старте сессии (использует --banner / $NEXUS_BANNER)
    print_logo(console, banner=getattr(args, "banner", None))
    console.print(f"[dim]{t('cmd.interactive_exit_hint')}[/dim]\n")
    console.print(f"[dim]{t('cmd.interactive_commands_hint')}[/dim]\n")

    config_path = getattr(args, "config", None)
    try:
        config = load_config(config_path)
    except ConfigError as e:
        console.print(f"[red]{t('config.invalid', error=e)}[/red]")
        return
    web_config = load_config_from_yaml(config.to_dict())

    cli_flag_search = getattr(args, "search", False)
    if cli_flag_search:
        search_enabled = True
    elif getattr(args, "no_search", False):
        search_enabled = False
    else:
        search_enabled = bool(web_config.enabled)

    web_searcher = None
    if search_enabled:
        try:
            web_searcher = WebSearcher(web_config, SEARCH_CACHE_DIR)
            console.print(
                f"[blue]{t('search.toggle_on', backend=web_searcher.backend_name)}[/blue]"
            )
        except Exception as e:
            logger.warning("WebSearcher init failed: %s", e)
            web_searcher = None
            search_enabled = False
    else:
        console.print(f"[dim]{t('search.toggle_off')}[/dim]")

    api_key = _load_env(config_path or DEFAULT_CONFIG_PATH, config={"provider": config.provider})
    if not api_key:
        env_var = config.api_key_env_var()
        if env_var:
            api_key = os.getenv(env_var, "")

    if config.provider != "ollama" and not api_key:
        console.print(f"[red]{t('agent.api_key_missing')}[/red]")
        return

    agent = NexusAgent(
        api_key=api_key,
        model=config.groq_model,
        provider=config.provider,
        base_url=config.base_url,
        timeout=config.timeout,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )

    messages = []
    if config.system_prompt:
        messages.append({"role": "system", "content": config.system_prompt})

    history_path = os.path.join(NEXUS_DIR, "interactive_history")
    completer = _build_interactive_completer()
    session = None
    if completer is not None:
        try:
            session = _build_prompt_session(history_path, completer)
        except Exception as e:
            logger.debug("prompt_toolkit init failed: %s", e)

    def _read():
        prompt_text = f"[bold green]{t('cmd.interactive_prompt')}[/bold green]"
        if session is not None:
            return session.prompt(prompt_text)
        return console.input(prompt_text)

    try:
        while True:
            try:
                user_input = _read().strip()
            except EOFError:
                break
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                console.print(f"[yellow]{t('cmd.interactive_goodbye')}[/yellow]")
                break

            cmd_low = user_input.lower().strip()

            if cmd_low in ("!search on", "!search on!"):
                if web_searcher is None:
                    try:
                        web_searcher = WebSearcher(web_config, SEARCH_CACHE_DIR)
                    except Exception as e:
                        console.print(
                            f"[red]{t('search.toggle_failed', error=e)}[/red]"
                        )
                        continue
                search_enabled = True
                console.print(
                    f"[green]{t('search.toggle_on', backend=web_searcher.backend_name)}[/green]"
                )
                continue
            if cmd_low in ("!search off", "!search off!"):
                search_enabled = False
                console.print(f"[yellow]{t('search.toggle_off')}[/yellow]")
                continue
            if cmd_low in ("!search status", "!search"):
                state = t("search.state_on") if search_enabled else t("search.state_off")
                backend = (
                    web_searcher.backend_name
                    if web_searcher
                    else t("search.backend_none")
                )
                console.print(
                    f"[cyan]{t('search.toggle_status', state=state, backend=backend)}[/cyan]"
                )
                continue

            if cmd_low.startswith("!lang "):
                requested = cmd_low.split(" ", 1)[1].strip()
                actual = set_language(requested)
                if actual != requested:
                    console.print(
                        f"[yellow]{t('lang.invalid', lang=requested, supported=', '.join(supported_languages()))}[/yellow]"
                    )
                else:
                    console.print(f"[cyan]{t('lang.switched', lang=actual)}[/cyan]")
                continue
            if cmd_low in ("!lang", "!lang status"):
                console.print(
                    f"[cyan]{t('lang.current', lang=current_language())}[/cyan]"
                )
                continue
            if cmd_low in ("!help", "?"):
                console.print(f"[dim]{t('cmd.interactive_commands_hint')}[/dim]")
                continue

            messages.append({"role": "user", "content": user_input})
            sources = []
            gen = None
            if search_enabled and web_searcher is not None:
                gen, sources = agent.search_and_answer_stream(
                    prompt=user_input,
                    web_searcher=web_searcher,
                    web_config=web_config,
                    system_prompt=config.system_prompt,
                )
            else:
                gen = agent.generate_stream(
                    user_input,
                    system_prompt=config.system_prompt,
                    history=messages[:-1] if len(messages) > 1 else None,
                )

            response_text = ""
            with Live(
                Panel(
                    Text("", style="green"),
                    title="[green]Nexus[/green]",
                    border_style="green",
                ),
                console=console,
                refresh_per_second=10,
                transient=False,
            ) as live:
                try:
                    for token in gen:
                        response_text += token
                        live.update(
                            Panel(
                                Text(response_text + " ", style="green"),
                                title="[green]Nexus[/green]",
                                border_style="green",
                            )
                        )
                    try:
                        gen.throw(StopIteration)
                    except StopIteration:
                        pass
                except Exception as e:
                    logger.exception("Streaming error")
                    console.print(f"[red]{t('error.streaming', error=e)}[/red]")
                    continue

            response_text = response_text.strip()
            if response_text:
                messages.append({"role": "assistant", "content": response_text})
                # Persist the exchange to history log
                _save_history(user_input, response_text, {})
            if sources:
                src_text = "\n".join(f"- {u}" for u in sources)
                console.print(
                    Panel(
                        Text(src_text, style="green"),
                        title=f"[green]{t('web.sources_title')}[/green]",
                        border_style="green",
                    )
                )

    except KeyboardInterrupt:
        console.print(f"\n[yellow]{t('cmd.interactive_interrupted')}[/yellow]")


def cmd_history(args) -> None:
    ensure_dirs()
    if not os.path.isfile(HISTORY_LOG):
        console.print(f"[yellow]{t('cmd.history_empty')}[/yellow]")
        return
    with open(HISTORY_LOG, "r", encoding="utf-8") as fh:
        content = fh.read()
    console.print(
        Panel(
            content,
            title=f"[blue]{t('cmd.history_title')}[/blue]",
            border_style="blue",
        )
    )


def cmd_cache_clear(args) -> None:
    ensure_dirs()
    if os.path.isdir(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)
        os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.isfile(HISTORY_LOG):
        os.remove(HISTORY_LOG)
    clear_conversation()
    console.print(f"[green]{t('cmd.cache_clear_done')}[/green]")


def cmd_version(args) -> None:
    """Print the Nexus version and exit."""
    from nexus import __version__

    console.print(f"[bold]Nexus[/bold] v{__version__}")
    console.print(f"Python {sys.version.split()[0]}")
    console.print(f"Platform: {sys.platform}")


def cmd_doctor(args) -> None:
    """Run diagnostics: Python, API keys, providers, FTS5, config."""
    from nexus import __version__
    from nexus.core.config import load_config

    checks = []

    def _ok(label: str, detail: str = "") -> None:
        msg = f"  ✅ {label}"
        if detail:
            msg += f" — {detail}"
        console.print(f"[green]{msg}[/green]")
        checks.append(True)

    def _warn(label: str, detail: str = "") -> None:
        msg = f"  ⚠️  {label}"
        if detail:
            msg += f" — {detail}"
        console.print(f"[yellow]{msg}[/yellow]")
        checks.append(True)

    def _fail(label: str, detail: str = "") -> None:
        msg = f"  ❌ {label}"
        if detail:
            msg += f" — {detail}"
        console.print(f"[red]{msg}[/red]")
        checks.append(False)

    console.print(f"\n[bold]Nexus Doctor — v{__version__}[/bold]\n")

    # --- Python ---
    console.print("[bold cyan]Python[/bold cyan]")
    _ok(f"Python {sys.version.split()[0]}", sys.executable)

    # --- Config ---
    console.print("\n[bold cyan]Configuration[/bold cyan]")
    try:
        config = load_config()
        _ok("Config loaded", config.to_dict().get("provider", "groq"))
    except Exception as e:
        _fail("Config error", str(e))
        config = None

    # --- API keys ---
    console.print("\n[bold cyan]API Keys[/bold cyan]")
    if config:
        for prov in ("groq", "openai", "anthropic", "ollama"):
            env_var = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY",
                       "anthropic": "ANTHROPIC_API_KEY"}.get(prov)
            if prov == "ollama":
                _ok("ollama", "no key needed")
            elif env_var and os.getenv(env_var):
                _ok(f"{prov}", f"{env_var} is set")
            else:
                _warn(f"{prov}", f"{env_var} not set")
    else:
        _warn("Skipped (no config)")

    # --- Providers ---
    console.print("\n[bold cyan]Providers[/bold cyan]")
    for prov_name, sdk_name in [("groq", "groq"), ("openai", "openai"),
                                  ("anthropic", "anthropic"), ("ollama", "ollama")]:
        try:
            __import__(sdk_name)
            _ok(prov_name, f"SDK installed ({sdk_name})")
        except ImportError:
            _warn(prov_name, f"SDK not installed (pip install {sdk_name})")

    # --- Web search ---
    console.print("\n[bold cyan]Web Search[/bold cyan]")
    for sdk_name in ("tavily", "requests"):
        try:
            __import__(sdk_name)
            _ok(sdk_name, "installed")
        except ImportError:
            _warn(sdk_name, "not installed")

    # --- SQLite FTS5 ---
    console.print("\n[bold cyan]SQLite FTS5[/bold cyan]")
    try:
        import sqlite3 as _sql
        conn = _sql.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        conn.execute("DROP TABLE _probe")
        conn.close()
        _ok("FTS5 available")
    except Exception:
        _warn("FTS5 not available", "LIKE fallback will be used")

    # --- Summary ---
    passed = sum(checks)
    total = len(checks)
    console.print(f"\n[bold]Result: {passed}/{total} checks passed[/bold]\n")

    if passed < total:
        sys.exit(1)


def cmd_mcp(args) -> None:
    """Start the Nexus MCP stdio server (blocks until the client disconnects)."""
    # Imported lazily so the rest of the CLI works even if `mcp` is missing.
    from nexus.mcp_server import main as mcp_main

    mcp_main()


def cmd_banner(args) -> None:
    """Предпросмотр ASCII-баннеров: один по имени или все (``nexus banner all``).

    Приоритеты имени:
      1. Позиционный аргумент ``nexus banner <name>``;
      2. Флаг ``--banner <name>`` (если был передан без подкоманды);
      3. ``None`` → используется дефолт из темы.
    """
    name = getattr(args, "name", None) or getattr(args, "banner", None)

    if name and name.lower() == "all":
        for n in list_banners():
            console.print(f"\n[bold cyan]── {n} ──[/bold cyan]")
            print_logo(console, banner=n)
        return

    print_logo(console, banner=name)


def cmd_status(args) -> None:
    ensure_dirs()

    cache_files = [
        f for f in os.listdir(CACHE_DIR) if os.path.isfile(os.path.join(CACHE_DIR, f))
    ]
    cache_size = (
        sum(os.path.getsize(os.path.join(CACHE_DIR, f)) for f in cache_files)
        if cache_files
        else 0
    )

    history_exists = os.path.isfile(HISTORY_LOG)
    history_size = os.path.getsize(HISTORY_LOG) if history_exists else 0
    history_lines = 0
    if history_exists:
        with open(HISTORY_LOG, "r", encoding="utf-8") as fh:
            history_lines = sum(1 for _ in fh)

    table = Table(title=f"[bold]{t('cmd.status_title')}[/bold]")
    table.add_column("Component", style="cyan")
    table.add_column("Value", style="green")

    table.add_row(t("cmd.status_cache_entries"), str(len(cache_files)))
    table.add_row(t("cmd.status_cache_size"), f"{cache_size / 1024:.1f} KB")
    table.add_row(
        t("cmd.status_history_file"),
        t("cmd.status_yes") if history_exists else t("cmd.status_no"),
    )
    table.add_row(t("cmd.status_history_size"), f"{history_size / 1024:.1f} KB")
    table.add_row(t("cmd.status_history_lines"), str(history_lines))
    table.add_row(t("cmd.status_nexus_dir"), NEXUS_DIR)

    console.print(table)


def cmd_web_search(args) -> None:
    query = getattr(args, "query", "")
    max_results = getattr(args, "max_results", 5)
    fetch = getattr(args, "fetch", False)

    if not query:
        console.print(f"[yellow]{t('cmd.search_missing_query')}[/yellow]")
        return

    config_path = getattr(args, "config", None)
    try:
        config = load_config(config_path)
    except ConfigError as e:
        console.print(f"[red]{t('config.invalid', error=e)}[/red]")
        return
    web_config = load_config_from_yaml(config.to_dict())
    web_config.max_results = max_results

    searcher = WebSearcher(web_config, SEARCH_CACHE_DIR)
    console.print(
        f"[blue]{t('cmd.search_backend', backend=searcher.backend_name)}[/blue]"
    )

    results = searcher.search(query, max_results=max_results)
    if not results:
        console.print(f"[yellow]{t('cmd.search_empty', query=query)}[/yellow]")
        return

    table = Table(title=t("cmd.search_table_title", query=query), show_lines=False)
    table.add_column("#", style="cyan", width=3)
    table.add_column("Title", style="green")
    table.add_column("URL", style="dim")
    for i, r in enumerate(results, 1):
        table.add_row(str(i), r.title[:80], r.url)
    console.print(table)

    if not fetch:
        return

    api_key = _load_env(config_path or DEFAULT_CONFIG_PATH, config={"provider": config.provider})
    if not api_key:
        env_var = config.api_key_env_var()
        if env_var:
            api_key = os.getenv(env_var, "")
    if config.provider != "ollama" and not api_key:
        console.print(f"[red]{t('agent.api_key_missing_short')}[/red]")
        return

    agent = NexusAgent(
        api_key=api_key,
        model=config.groq_model,
        provider=config.provider,
        base_url=config.base_url,
        timeout=config.timeout,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )
    context_text, fetched = searcher.search_and_format(query, max_results=max_results)
    if not context_text:
        console.print(f"[yellow]{t('cmd.search_no_context')}[/yellow]")
        result = agent.generate_response(query, system_prompt=config.system_prompt)
    else:
        augmented = (
            f"{query}\n\n"
            f"{t('web.context_block')}\n{context_text}\n{t('web.context_end')}"
        )
        result = agent.generate_response(
            augmented, system_prompt=t("cmd.search_instruction")
        )

    console.print(_render_response(result.get("text", "")))
    sources = [r.url for r in fetched]
    if sources:
        src_text = "\n".join(f"- {u}" for u in sources)
        console.print(
            Panel(
                Text(src_text, style="green"),
                title=f"[green]{t('web.sources_title')}[/green]",
                border_style="green",
            )
        )


class _LogoHelpParser(argparse.ArgumentParser):
    """ArgumentParser subclass that prints the Nexus logo before help text."""

    def print_help(self, file=None):
        # Используем --banner, если он указан; иначе — дефолт/env.
        chosen = getattr(self, "_nexus_banner", None)
        print_logo(console, banner=chosen)
        super().print_help(file)


def build_parser():
    parser = _LogoHelpParser(
        prog="nexus",
        description=t("cli.title"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", action="store_true", help=t("cli.verbose"))
    parser.add_argument(
        "--config",
        type=str,
        default=DEFAULT_CONFIG_PATH,
        help=t("cli.config", default=DEFAULT_CONFIG_PATH),
    )
    parser.add_argument(
        "--lang",
        choices=list(supported_languages()),
        default=None,
        help=(
            "Interface language (default: auto-detect). "
            "Supported: " + ", ".join(supported_languages())
        ),
    )
    parser.add_argument(
        "--banner",
        choices=list(list_banners()),
        default=None,
        help=(
            "ASCII banner style (default: from $NEXUS_BANNER or 'classic'). "
            "Available: " + ", ".join(list_banners())
        ),
    )

    subparsers = parser.add_subparsers(dest="command", help=t("cli.commands_help"))

    run_parser = subparsers.add_parser("run", help=t("cmd.run_help"))
    run_parser.add_argument("prompt", type=str, help=t("cmd.run_prompt"))
    run_parser.add_argument("--no-cache", action="store_true", help=t("cmd.run_no_cache"))
    run_parser.add_argument(
        "--search",
        dest="search",
        action="store_true",
        default=None,
        help=t("cmd.run_search"),
    )
    run_parser.add_argument(
        "--no-search",
        dest="no_search",
        action="store_true",
        help=t("cmd.run_no_search"),
    )

    interactive_parser = subparsers.add_parser(
        "interactive", help=t("cmd.interactive_help")
    )
    interactive_parser.add_argument(
        "--search",
        dest="search",
        action="store_true",
        default=False,
        help=t("cmd.interactive_search"),
    )
    interactive_parser.add_argument(
        "--no-search",
        dest="no_search",
        action="store_true",
        help=t("cmd.interactive_no_search"),
    )

    search_parser = subparsers.add_parser("search", help=t("cmd.search_help"))
    search_parser.add_argument("query", type=str, help=t("cmd.search_query"))
    search_parser.add_argument(
        "--max",
        dest="max_results",
        type=int,
        default=5,
        help=t("cmd.search_max"),
    )
    search_parser.add_argument(
        "--fetch",
        dest="fetch",
        action="store_true",
        help=t("cmd.search_fetch"),
    )

    subparsers.add_parser("history", help=t("cmd.history_help"))
    subparsers.add_parser("cache-clear", help=t("cmd.cache_clear_help"))
    subparsers.add_parser("status", help=t("cmd.status_help"))
    subparsers.add_parser("version", help="Show Nexus version")
    subparsers.add_parser("doctor", help="Run diagnostics")

    # `nexus banner [name]` — показать ASCII-баннер (для превью и демо).
    banner_parser = subparsers.add_parser(
        "banner",
        help="Print the Nexus banner (preview all styles).",
    )
    banner_parser.add_argument(
        "name",
        nargs="?",
        default=None,
        help=(
            "Banner style to print. If omitted, prints the default one. "
            "Use 'all' to preview every available banner."
        ),
    )

    # `nexus mcp` — run the MCP stdio server so MCP-aware clients (Claude
    # Desktop, Cursor, etc.) can use Nexus as a tool.  See nexus/mcp_server.py.
    subparsers.add_parser(
        "mcp",
        help="Run the Nexus MCP server (stdio). For Claude Desktop / Cursor.",
    )

    return parser


COMMAND_MAP = {
    "run": cmd_run,
    "interactive": cmd_interactive,
    "search": cmd_web_search,
    "history": cmd_history,
    "cache-clear": cmd_cache_clear,
    "status": cmd_status,
    "version": cmd_version,
    "doctor": cmd_doctor,
    "banner": cmd_banner,
    "mcp": cmd_mcp,
}


def _extract_lang_from_argv(argv):
    """Best-effort extraction of ``--lang <value>`` from a sys.argv list."""
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


def _extract_banner_from_argv(argv):
    """Best-effort extraction of ``--banner <value>`` from a sys.argv list."""
    for i, arg in enumerate(argv):
        if arg == "--banner" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--banner="):
            return arg.split("=", 1)[1]
    return None


def main() -> None:
    # Apply the language BEFORE building the parser so that --help and the
    # description are already localised.  We peek at ``--lang`` directly
    # in ``sys.argv`` because the parser doesn't exist yet at this point.
    requested = _extract_lang_from_argv(sys.argv)
    if requested:
        set_language(requested)

    # Same trick for --banner: if the user passed it, propagate it to
    # the logo printer so ``--help``/``--version`` already show the chosen
    # banner style.
    chosen_banner = _extract_banner_from_argv(sys.argv)

    parser = build_parser()
    parser._nexus_banner = chosen_banner  # используется в _LogoHelpParser

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    _setup_logging(args.verbose)
    ensure_dirs()

    # ``--lang`` was already honoured above; nothing else to do here.
    # The flag stays in the parser so it shows up in ``--help``.

    # version, doctor и banner не требуют валидации конфига.
    if args.command in ("version", "doctor", "banner"):
        handler = COMMAND_MAP.get(args.command)
        if handler:
            handler(args)
        else:
            parser.print_help()
        return

    # Validate the config up-front so users see a clear error instead of
    # a confusing KeyError somewhere deep in the call stack.
    try:
        load_config(
            args.config if hasattr(args, "config") and args.config else None
        )
    except ConfigError as e:
        console.print(f"[red]{t('config.invalid', error=e)}[/red]")
        sys.exit(2)

    handler = COMMAND_MAP.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
