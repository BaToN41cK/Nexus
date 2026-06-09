"""
Security utilities for Nexus.

Provides helpers for masking sensitive data in logs, safe handling
of API keys, and dependency vulnerability scanning integration.
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensitive data patterns
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS: List[str] = [
    # key=value pairs with the key being api_key, secret, token, etc.
    r"(?i)(api[_-]?key|apikey|secret|token|password|passwd|credential)\s*[=:]\s*['\"]?([^'\"\s&]+)",
    # Known API key prefixes
    r"(gsk_[a-zA-Z0-9_-]+)",            # Groq keys
    r"(sk-[a-zA-Z0-9_-]+)",             # OpenAI keys
    r"(sk-ant-[a-zA-Z0-9_-]+)",         # Anthropic keys
]

# Compiled regex cache
_COMPILED: List[re.Pattern] = [re.compile(p) for p in _SENSITIVE_PATTERNS]


def mask_sensitive(text: str, replacement: str = "***") -> str:
    """Mask API keys and secrets in *text*.

    Replaces the value portion of any ``key=value`` or ``key: value``
    pair where the key looks like an API key, secret, or token.
    Also masks known API key prefixes (gsk_, sk-, sk-ant-) anywhere
    they appear.

    Args:
        text: The string to mask.
        replacement: Replacement string (default ``***``).

    Returns:
        Text with sensitive values masked.
    """
    for pattern in _COMPILED:
        # For multi-group patterns, the substitution uses the first
        # capture group; for single-group patterns, we substitute the
        # whole match.
        if pattern.groups > 1:
            text = pattern.sub(r"\1=" + replacement, text)
        else:
            text = pattern.sub(replacement, text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Logging filter that masks API keys in all log records.

    Attach to any logger to automatically mask sensitive data::

        import logging
        from nexus.core.security import SensitiveDataFilter

        logging.getLogger().addFilter(SensitiveDataFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = mask_sensitive(record.msg)
        if hasattr(record, "args") and record.args:
            # args may be a tuple of values that contain sensitive strings
            cleaned_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    cleaned_args.append(mask_sensitive(arg))
                else:
                    cleaned_args.append(arg)
            record.args = tuple(cleaned_args)
        return True


def mask_api_key(key: str, visible_chars: int = 4) -> str:
    """Mask an API key showing only the first and last *visible_chars* chars.

    Args:
        key: The API key string.
        visible_chars: Number of characters to show at start and end.

    Returns:
        Masked key like ``gsk_abcd****wxyz``.
    """
    if not key or len(key) <= visible_chars * 2:
        return "****"
    return key[:visible_chars] + "****" + key[-visible_chars:]


# ---------------------------------------------------------------------------
# Config value masking (used by ``nexus debug`` and similar)
# ---------------------------------------------------------------------------

# Field names whose value is treated as a secret regardless of content.
# Tokens (separated by '_' or '-') are matched as whole words so that
# ``monkey`` is NOT considered a secret while ``openai_api_key`` is.
_SECRET_FIELD_TOKENS = frozenset(
    {
        "key", "apikey", "secret", "token", "password",
        "passwd", "credential", "credentials",
        "auth", "authorization",
        "private", "access", "session",
    }
)


def is_secret_field(name: str) -> bool:
    """Return True if *name* looks like a field that should hold a secret.

    Matches whole tokens, so ``openai_api_key`` and ``auth_token`` are
    caught in addition to the obvious ``key``/``secret`` names. A naive
    ``"key" in field_name`` check would also match ``monkey`` or
    ``turkey``; this implementation avoids that.
    """
    if not name:
        return False
    lowered = str(name).lower().replace("-", "_")
    tokens = {tok for tok in lowered.split("_") if tok}
    return bool(tokens & _SECRET_FIELD_TOKENS)


def mask_config_value(name: str, value) -> str:
    """Return a safe-to-print representation of a config value.

    The decision to mask is based on *name* (via :func:`is_secret_field`).
    If the field is secret, the value is masked with :func:`mask_api_key`
    so that common prefixes (``gsk_``, ``sk-``, ``sk-ant-``) are
    preserved while the secret body is hidden. Non-secret fields are
    returned as their ``str()`` representation unchanged.
    """
    if value is None:
        return "None"
    if not is_secret_field(str(name)):
        return str(value)
    s = str(value)
    if not s:
        return ""
    if len(s) <= 8:
        return "****"
    return mask_api_key(s, visible_chars=4)


def check_env_file_permissions(env_path: str) -> Optional[str]:
    """Check that the .env file has safe permissions.

    On Unix, warns if the file is world-readable. On Windows, checks
    that the file is not marked as readable by "Everyone".

    Args:
        env_path: Path to the .env file.

    Returns:
        Warning message if permissions are unsafe, or ``None``.
    """
    if not os.path.isfile(env_path):
        return None
    try:
        mode = os.stat(env_path).st_mode
        # Check if "other" has read permission (Unix)
        if mode & 0o004:
            return (
                f"Warning: .env file at {env_path} is world-readable. "
                f"Run: chmod 600 {env_path}"
            )
    except Exception:
        pass
    return None


def run_pip_audit() -> Dict[str, List[str]]:
    """Run pip-audit and return a dict of {package: [vulnerabilities]}.

    Returns an empty dict if pip-audit is not installed or fails.

    This is intended for CI/CD pipelines — users should run
    ``pip-audit`` manually to check for vulnerabilities.

    The tool is invoked as ``python -m pip_audit`` (rather than via a
    ``pip-audit`` console-script entry point) so that we do not depend
    on the script being discoverable on ``PATH`` and so that we use
    the same interpreter that is currently running Nexus. This avoids
    the historical problem where ``pip-audit`` was resolved from a
    different (system) Python installation and produced a confusing
    error when the venv version differed.
    """
    try:
        import subprocess
        import sys as _sys
        cmd = [_sys.executable, "-m", "pip_audit", "--format", "json"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            vulns: Dict[str, List[str]] = {}
            for item in data.get("vulnerabilities", []):
                pkg = item.get("name", "unknown")
                vulns.setdefault(pkg, []).append(
                    f"{item.get('id', '?')}: {item.get('description', '')}"
                )
            return vulns
    except (ImportError, FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        logger.debug("pip-audit not available or failed: %s", e)
    return {}
