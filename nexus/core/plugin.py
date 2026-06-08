"""
Plugin system for Nexus.

Allows third-party modules to extend Nexus functionality by registering
custom LLM providers, search backends, content loaders, CLI commands,
and lifecycle hooks.

Usage:
    # my_plugin.py
    from nexus.core.plugin import register_provider, register_search_backend

    class MyProvider(BaseProvider):
        name = "my_provider"
        ...

    register_provider(MyProvider)

    class MySearch(SearchBackend):
        name = "my_search"
        ...

    register_search_backend(MySearch)
"""

import importlib
import importlib.util
import inspect
import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Type

from nexus.core.provider_factory import ProviderFactory
from nexus.core.web_search import SearchBackend, WebSearcher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plugin registry
# ---------------------------------------------------------------------------

_loaded_plugins: Dict[str, Any] = {}
_registered_hooks: Dict[str, List[Callable]] = {
    "pre_command": [],
    "post_command": [],
    "on_startup": [],
    "on_shutdown": [],
}
_custom_commands: Dict[str, dict] = {}


def register_provider(provider_cls: Type) -> None:
    """Register a custom LLM provider class."""
    name = getattr(provider_cls, "name", provider_cls.__name__.lower())
    ProviderFactory.register(name, provider_cls)


def register_search_backend(backend_cls: Type[SearchBackend]) -> None:
    """Register a custom search backend class."""
    from nexus.core.web_search import _custom_backends
    name = getattr(backend_cls, "name", backend_cls.__name__.lower())
    if name in _custom_backends:
        raise ValueError(f"Search backend '{name}' is already registered.")
    if not issubclass(backend_cls, SearchBackend):
        raise TypeError(f"{backend_cls.__name__} must inherit from SearchBackend")
    _custom_backends[name] = backend_cls
    logger.info("Registered custom search backend: %s", name)


def register_hook(hook_name: str, fn: Callable) -> None:
    """Register a lifecycle hook function.

    Supported hooks:
        - ``pre_command``: Called before each CLI command.
        - ``post_command``: Called after each CLI command.
        - ``on_startup``: Called when the application starts.
        - ``on_shutdown``: Called when the application exits.
    """
    if hook_name not in _registered_hooks:
        raise ValueError(
            f"Unknown hook: {hook_name!r}. "
            f"Supported: {', '.join(_registered_hooks.keys())}"
        )
    _registered_hooks[hook_name].append(fn)
    logger.debug("Registered hook '%s': %s.%s", hook_name, fn.__module__, fn.__qualname__)


def run_hook(hook_name: str, *args, **kwargs) -> None:
    """Execute all registered hooks of type *hook_name*."""
    for fn in _registered_hooks.get(hook_name, []):
        try:
            fn(*args, **kwargs)
        except Exception as e:
            logger.warning("Hook '%s' failed in %s: %s", hook_name, fn.__qualname__, e)


def register_cli_command(name: str, help_text: str, handler: Callable) -> None:
    """Register a custom CLI command.

    The *handler* should be a function that accepts a parsed arguments
    namespace and returns ``None``.
    """
    _custom_commands[name] = {
        "help": help_text,
        "handler": handler,
    }
    logger.info("Registered CLI command: %s", name)


def list_custom_commands() -> Dict[str, dict]:
    """Return dict of custom CLI commands registered by plugins."""
    return dict(_custom_commands)


def discover_plugins(
    plugin_dir: Optional[str] = None,
    *,
    require_owned_by_user: bool = True,
) -> List[str]:
    """Discover and load plugins from a directory.

    Scans *plugin_dir* (default: ``~/.nexus/plugins/``) for Python files
    and loads any module that defines a ``setup`` function.

    Security:
        Loading a plugin executes arbitrary Python code. To reduce the
        risk of loading a plugin installed by a different user on a
        shared system, each candidate file is checked against the
        current process uid (POSIX) and skipped with a warning if the
        ownership does not match. This check can be disabled by
        passing ``require_owned_by_user=False`` (use only in trusted
        environments such as CI containers).

    Returns a list of successfully loaded plugin names.
    """
    if plugin_dir is None:
        plugin_dir = os.path.join(os.path.expanduser("~"), ".nexus", "plugins")

    if not os.path.isdir(plugin_dir):
        logger.debug("Plugin directory %s does not exist, skipping", plugin_dir)
        return []

    current_uid: Optional[int] = getattr(os, "getuid", lambda: None)()

    loaded: List[str] = []
    for fname in sorted(os.listdir(plugin_dir)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        module_name = fname[:-3]
        path = os.path.join(plugin_dir, fname)

        # Security: refuse to load plugins not owned by the current user.
        if require_owned_by_user and current_uid is not None:
            try:
                file_uid = os.stat(path).st_uid
            except OSError as e:
                logger.warning(
                    "Cannot stat plugin %s, skipping: %s", path, e
                )
                continue
            if file_uid != current_uid:
                logger.warning(
                    "Skipping plugin %s: owned by uid %s, current uid is %s. "
                    "Refusing to load plugins not owned by the current user "
                    "to prevent execution of foreign code. Pass "
                    "require_owned_by_user=False to override (trusted envs only).",
                    path, file_uid, current_uid,
                )
                continue

        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            # Call setup() if it exists
            if hasattr(mod, "setup"):
                mod.setup()
            _loaded_plugins[module_name] = mod
            loaded.append(module_name)
            logger.warning(
                "Loaded plugin '%s' from %s "
                "(plugin code is executed with full user privileges)",
                module_name, path,
            )
        except Exception as e:
            logger.warning("Failed to load plugin %s: %s", path, e)
    return loaded


def get_loaded_plugins() -> Dict[str, Any]:
    """Return dict of loaded plugin modules."""
    return dict(_loaded_plugins)
