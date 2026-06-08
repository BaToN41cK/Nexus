"""Tests for the :mod:`nexus.core.security` module."""

import logging
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from nexus.core.security import (
    SensitiveDataFilter,
    check_env_file_permissions,
    mask_api_key,
    mask_sensitive,
    run_pip_audit,
)


class TestMaskSensitive(unittest.TestCase):
    def test_masks_groq_api_key(self):
        text = "api_key=gsk_abcdef1234567890abcdef1234567890"
        masked = mask_sensitive(text)
        self.assertNotIn("gsk_abcdef1234567890", masked)
        self.assertIn("***", masked)

    def test_masks_openai_api_key(self):
        text = "api_key=sk-abcdef1234567890abcdef1234567890"
        masked = mask_sensitive(text)
        self.assertNotIn("sk-abcdef1234567890", masked)
        self.assertIn("***", masked)

    def test_masks_anthropic_key(self):
        text = "key=sk-ant-api03-abcdefghij1234567890abcdef"
        masked = mask_sensitive(text)
        self.assertIn("***", masked)
        # Key value should not be in the masked output
        self.assertNotIn("abcdefghij", masked)

    def test_masks_key_value_pair(self):
        text = "API_KEY=secret-value-1234"
        masked = mask_sensitive(text)
        self.assertNotIn("secret-value-1234", masked)

    def test_leaves_normal_text_alone(self):
        text = "Hello world, this is normal text"
        masked = mask_sensitive(text)
        self.assertEqual(masked, text)

    def test_replacement_param(self):
        text = "api_key=secret123"
        masked = mask_sensitive(text, replacement="[REDACTED]")
        self.assertIn("[REDACTED]", masked)


class TestMaskApiKey(unittest.TestCase):
    def test_basic_masking(self):
        masked = mask_api_key("gsk_abcdef1234567890wxyz", visible_chars=4)
        self.assertEqual(masked, "gsk_****wxyz")

    def test_empty_key(self):
        self.assertEqual(mask_api_key(""), "****")

    def test_short_key(self):
        self.assertEqual(mask_api_key("abc"), "****")

    def test_custom_visible_chars(self):
        masked = mask_api_key("verylongkey123", visible_chars=2)
        self.assertEqual(masked, "ve****23")


class TestSensitiveDataFilter(unittest.TestCase):
    def test_filter_modifies_msg(self):
        filt = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="api_key=gsk_abcdef1234567890",
            args=(),
            exc_info=None,
        )
        filt.filter(record)
        self.assertIn("***", record.msg)
        self.assertNotIn("gsk_abcdef", record.msg)

    def test_filter_modifies_args(self):
        filt = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test %s",
            args=("gsk_abcdef1234567890",),
            exc_info=None,
        )
        filt.filter(record)
        self.assertNotIn("gsk_abcdef", record.args[0])

    def test_filter_with_non_string_args(self):
        filt = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(42, None, [1, 2]),
            exc_info=None,
        )
        # Should not raise
        result = filt.filter(record)
        self.assertTrue(result)


class TestCheckEnvFilePermissions(unittest.TestCase):
    def test_nonexistent_file(self):
        result = check_env_file_permissions("/nonexistent/path/.env")
        self.assertIsNone(result)

    def test_existing_safe_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".env") as f:
            f.write("KEY=value")
            path = f.name
        try:
            result = check_env_file_permissions(path)
            # On Windows there's no "other" permission, so result is None
            # On Unix with default permissions (0o600 or 0o644), result may also be None
            if result is not None:
                # If we get a warning, it should mention chmod
                self.assertIn("chmod", result)
        finally:
            os.unlink(path)


class TestRunPipAudit(unittest.TestCase):
    def test_pip_audit_not_available(self):
        """When pip-audit is not installed, return empty dict."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = run_pip_audit()
        self.assertEqual(result, {})

    def test_pip_audit_timeout(self):
        with patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("pip-audit", 60)):
            result = run_pip_audit()
        self.assertEqual(result, {})

    def test_pip_audit_success_no_vulns(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"vulnerabilities": []}'
        with patch("subprocess.run", return_value=mock_result):
            result = run_pip_audit()
        self.assertEqual(result, {})

    def test_pip_audit_success_with_vulns(self):
        import json
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "vulnerabilities": [
                {
                    "name": "requests",
                    "id": "CVE-2024-0001",
                    "description": "Test vuln",
                }
            ]
        })
        with patch("subprocess.run", return_value=mock_result):
            result = run_pip_audit()
        self.assertIn("requests", result)
        self.assertEqual(len(result["requests"]), 1)


if __name__ == "__main__":
    unittest.main()