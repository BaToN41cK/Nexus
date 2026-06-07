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
        # The translated prompt (e.g. "Вы: " / "You: ") is plain text.
        # Don't wrap it in Rich markup — both ``session.prompt()`` (from
        # prompt_toolkit) and ``console.input()`` would otherwise show
        # the brackets literally.
        prompt_text = t("cmd.interactive_prompt")
        if session is not None:
            return session.prompt(prompt_text)
        return console.input(prompt_text)

    try:
        while True:
            try:
                user_input = _read().strip()
            except (EOFError, KeyboardInterrupt):
                console.print(f"\n[yellow]{t('cmd.interactive_goodbye')}[/yellow]")
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
                except KeyboardInterrupt:
                    # Allow graceful cancellation during streaming
                    console.print(f"\n[yellow]{t('cmd.interactive_interrupted')}[/yellow]")
                    continue
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
        console.print(f"\n[yellow]{t('cmd.interactive_goodbye')}[/yellow]")


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


def cmd_update(args) -> None:
    """Update Nexus to the latest version via pip."""
    from nexus import __version__

    console.print(f"\n[bold]Nexus Update — current v{__version__}[/bold]\n")
    console.print("[blue]Updating Nexus from PyPI...[/blue]\n")

    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "nexus"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            console.print("[green]✅ Update completed successfully![/green]")
            # Show the last few lines of output
            lines = result.stdout.strip().splitlines()
            for line in lines[-5:]:
                console.print(f"  {line}")
        else:
            console.print("[red]❌ Update failed:[/red]")
            console.print(result.stderr or result.stdout or "(no output)")
    except subprocess.TimeoutExpired:
        console.print("[red]❌ Update timed out after 120 seconds.[/red]")
    except Exception as e:
        console.print(f"[red]❌ Update error: {e}[/red]")


def cmd_test(args) -> None:
    """Run built-in tests to verify all modules work."""
    from nexus import __version__

    console.print(f"\n[bold]Nexus Test — v{__version__}[/bold]\n")

    import importlib
    import time

    modules = [
        ("nexus.core.config", "Configuration"),
        ("nexus.core.agent", "Agent"),
        ("nexus.core.history", "History"),
        ("nexus.core.i18n", "i18n"),
        ("nexus.core.paths", "Paths"),
        ("nexus.core.banners", "Banners"),
        ("nexus.core.logo", "Logo"),
        ("nexus.core.web_search", "Web Search"),
        ("nexus.commands.run", "Run Command"),
    ]

    passed = 0
    failed = 0
    results = []

    for mod_name, label in modules:
        start = time.monotonic()
        try:
            mod = importlib.import_module(mod_name)
            elapsed = (time.monotonic() - start) * 1000
            console.print(f"  [green]✅ {label:20s} ({mod_name})[/green]  [dim]{elapsed:.0f}ms[/dim]")
            passed += 1
            results.append((label, True, f"{elapsed:.0f}ms"))
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            console.print(f"  [red]❌ {label:20s} ({mod_name})[/red]  [dim]{elapsed:.0f}ms[/dim]")
            console.print(f"     [red]{e}[/red]")
            failed += 1
            results.append((label, False, str(e)))

    # Test TTS5
    start = time.monotonic()
    try:
        import sqlite3 as _sql
        conn = _sql.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        conn.execute("DROP TABLE _probe")
        conn.close()
        elapsed = (time.monotonic() - start) * 1000
        console.print(f"  [green]✅ {'SQLite FTS5':20s}[/green]  [dim]{elapsed:.0f}ms[/dim]")
        passed += 1
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        console.print(f"  [yellow]⚠️  {'SQLite FTS5':20s}[/yellow]  [dim]{elapsed:.0f}ms[/dim]")
        console.print(f"     [yellow]{e}[/yellow]")

    # Test translation system
    start = time.monotonic()
    try:
        _ = t("cli.title")
        elapsed = (time.monotonic() - start) * 1000
        console.print(f"  [green]✅ {'Translations':20s}[/green]  [dim]{elapsed:.0f}ms[/dim]")
        passed += 1
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        console.print(f"  [red]❌ {'Translations':20s}[/red]  [dim]{elapsed:.0f}ms[/dim]")
        console.print(f"     [red]{e}[/red]")
        failed += 1

    # Test web searcher (config only, not actual search)
    start = time.monotonic()
    try:
        from nexus.core.web_search import WebSearchConfig
        elapsed = (time.monotonic() - start) * 1000
        console.print(f"  [green]✅ {'Web Search Config':20s}[/green]  [dim]{elapsed:.0f}ms[/dim]")
        passed += 1
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        console.print(f"  [yellow]⚠️  {'Web Search Config':20s}[/yellow]  [dim]{elapsed:.0f}ms[/dim]")
        console.print(f"     [yellow]{e}[/yellow]")

    console.print(f"\n[bold]Result: {passed}/{passed + failed} checks passed[/bold]\n")

    if failed > 0:
        sys.exit(1)


def cmd_debug(args) -> None:
    """Deep debug mode: dump all requests/responses with full diagnostics."""
    from nexus import __version__
    from nexus.core.config import load_config

    console.print(f"\n[bold]Nexus Debug — v{__version__}[/bold]\n")

    # Enable maximum verbosity
    _setup_logging(True)
    logger = logging.getLogger("nexus")
    logger.setLevel(logging.DEBUG)

    # --- System info ---
    console.print("[bold cyan]System[/bold cyan]")
    console.print(f"  Python: {sys.version.split()[0]} ({sys.executable})")
    console.print(f"  Platform: {sys.platform}")
    console.print(f"  Nexus: v{__version__}")

    # --- Config ---
    console.print("\n[bold cyan]Configuration[/bold cyan]")
    try:
        config = load_config()
        console.print(f"  [green]✅ Config loaded[/green]")
        config_dict = config.to_dict()
        for key, value in config_dict.items():
            # Mask API keys in output
            if "key" in key.lower() and value and len(str(value)) > 8:
                masked = str(value)[:4] + "****" + str(value)[-4:]
                console.print(f"    {key}: {masked}")
            else:
                console.print(f"    {key}: {value}")
    except Exception as e:
        console.print(f"  [red]❌ Config error: {e}[/red]")
        config = None

    # --- API keys ---
    console.print("\n[bold cyan]API Keys (masked)[/bold cyan]")
    key_map = {"GROQ_API_KEY": "groq", "OPENAI_API_KEY": "openai",
               "ANTHROPIC_API_KEY": "anthropic"}
    for env_var, prov in key_map.items():
        val = os.getenv(env_var, "")
        if val:
            masked = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
            console.print(f"  [green]✅ {prov}: {env_var} = {masked}[/green]")
        else:
            console.print(f"  [yellow]⚠️  {prov}: {env_var} not set[/yellow]")
    # Ollama doesn't need a key
    console.print(f"  [green]✅ ollama: no key needed[/green]")

    # --- Providers ---
    console.print("\n[bold cyan]Providers[/bold cyan]")
    for prov_name, sdk_name in [("groq", "groq"), ("openai", "openai"),
                                  ("anthropic", "anthropic"), ("ollama", "ollama")]:
        try:
            mod = __import__(sdk_name)
            ver = getattr(mod, "__version__", "unknown")
            console.print(f"  [green]✅ {prov_name}: SDK installed ({sdk_name} {ver})[/green]")
        except ImportError:
            console.print(f"  [yellow]⚠️  {prov_name}: SDK not installed[/yellow]")

    # --- Dependencies ---
    console.print("\n[bold cyan]Dependencies[/bold cyan]")
    for pkg in ("requests", "beautifulsoup4", "rich", "pyyaml", "youtube_transcript_api",
                "pypdf", "docx", "pptx", "openpyxl", "tavily"):
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "installed")
            console.print(f"  [green]✅ {pkg}: {ver}[/green]")
        except ImportError:
            console.print(f"  [yellow]⚠️  {pkg}: not installed[/yellow]")

    # --- SQLite FTS5 ---
    console.print("\n[bold cyan]SQLite FTS5[/bold cyan]")
    try:
        import sqlite3 as _sql
        conn = _sql.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        conn.execute("DROP TABLE _probe")
        conn.close()
        console.print("  [green]✅ FTS5 available[/green]")
    except Exception:
        console.print("  [yellow]⚠️  FTS5 not available[/yellow]")

    # --- Debug summary ---
    console.print(f"\n[bold dim]Debug mode complete. All values shown above.[/bold dim]\n")


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


# NOTE: we don't subclass argparse's HelpFormatter because Python 3.14
# initialises the ``_optionals`` / ``_positionals`` / ``_usage_prefix``
# attributes lazily, so setting them in ``__init__`` raises AttributeError.
# Instead, the section titles are translated on the parser itself right
# after construction (see ``build_parser()``), and the help action is
# registered manually with a translated description.




class _LogoHelpParser(argparse.ArgumentParser):
    """ArgumentParser subclass that prints the Nexus logo before help text."""

    def print_help(self, file=None):
        # Используем --banner, если он указан; иначе — дефолт/env.
        chosen = getattr(self, "_nexus_banner", None)
        print_logo(console, banner=chosen)
        super().print_help(file)


class _LocalizedSubparser(_LogoHelpParser):
    """Subparser that ships with localised help text and section titles.

    We can't simply reuse :class:`_LogoHelpParser` because argparse adds
    ``-h/--help`` automatically on construction with a hard-coded English
    description.  This subclass disables that and re-registers ``-h/--help``
    with a translated description, then overrides the built-in section
    titles (``"options"`` and ``"positional arguments"``) on the parser's
    formatter groups.
    """

    def __init__(self, *args, **kwargs):
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        # Section titles for the two default formatter groups.
        self._optionals.title = t("cli.options")
        self._positionals.title = t("cli.positional")
        # Localised -h/--help.
        self.add_argument(
            "-h", "--help",
            action="help",
            default=argparse.SUPPRESS,
            help=t("cli.help_action"),
        )


def build_parser():
    parser = _LogoHelpParser(
        prog="nexus",
        description=t("cli.title"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,  # we register a localised -h/--help manually below
    )
    # Translate argparse's built-in section titles ("options", "positional
    # arguments", ...) so the help screen is fully localised.  These
    # attributes live on the formatter's action groups and are filled in
    # as soon as the first argument is added.
    parser._optionals.title = t("cli.options")
    parser._positionals.title = t("cli.positional")
    # Localised "usage:" prefix that argparse prepends to the usage line.
    # Register the help flag ourselves with a translated description.
    parser.add_argument(
        "-h", "--help",
        action="help",
        default=argparse.SUPPRESS,
        help=t("cli.help_action"),
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
        help=t("cli.lang_help", supported=", ".join(supported_languages())),
    )
    parser.add_argument(
        "--banner",
        choices=list(list_banners()),
        default=None,
        help=t("cli.banner_help", available=", ".join(list_banners())),
    )

    subparsers = parser.add_subparsers(parser_class=_LocalizedSubparser, dest="command", help=t("cli.commands_help"))

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
    subparsers.add_parser("version", help=t("cmd.version_help"))
    subparsers.add_parser("update", help=t("cmd.update_help"))
    subparsers.add_parser("test", help=t("cmd.test_help"))
    subparsers.add_parser("debug", help=t("cmd.debug_help"))

    # `nexus banner [name]` — показать ASCII-баннер (для превью и демо).
    banner_parser = subparsers.add_parser(
        "banner",
        help=t("cmd.banner_help"),
    )
    banner_parser.add_argument(
        "name",
        nargs="?",
        default=None,
        help=t("cmd.banner_name_help"),
    )

    # `nexus mcp` — run the MCP stdio server so MCP-aware clients (Claude
    # Desktop, Cursor, etc.) can use Nexus as a tool.  See nexus/mcp_server.py.
    subparsers.add_parser(
        "mcp",
        help=t("cmd.mcp_help"),
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
    "update": cmd_update,
    "test": cmd_test,
    "debug": cmd_debug,
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

    # version, debug, update, test и banner не требуют валидации конфига.
    if args.command in ("version", "debug", "update", "test", "banner"):
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
