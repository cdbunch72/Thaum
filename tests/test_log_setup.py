# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_log_setup.py
from __future__ import annotations

import io
import logging
import os
import unittest
from contextlib import redirect_stderr
from pathlib import Path
import tempfile
from unittest.mock import patch

from log_setup import configure_logging, init_early_logging_from_env
from thaum.types import DEFAULT_JSON_LOG_FILE_PATH, DEFAULT_LOG_FILE_PATH, LogConfig, LogLevel


class LogFileNormalizationTest(unittest.TestCase):
    def test_log_level_string_normalized(self) -> None:
        self.assertEqual(LogConfig(level="info").level, LogLevel.INFO)
        self.assertEqual(LogConfig(level="  debug  ").level, LogLevel.DEBUG)

    def test_default_off(self) -> None:
        self.assertIsNone(LogConfig().file)

    def test_truthy_literals(self) -> None:
        for v in (True, 1, "yes", "YES", "true", "1"):
            with self.subTest(v=v):
                self.assertEqual(LogConfig(file=v).file, DEFAULT_LOG_FILE_PATH)

    def test_explicit_path(self) -> None:
        self.assertEqual(LogConfig(file="/tmp/x.log").file, "/tmp/x.log")

    def test_disabled(self) -> None:
        for v in (False, 0, "no", "false", "0", None, ""):
            with self.subTest(v=v):
                self.assertIsNone(LogConfig(file=v).file)

    def test_invalid_int(self) -> None:
        with self.assertRaises(ValueError):
            LogConfig(file=2)


class JsonLogNormalizationTest(unittest.TestCase):
    def test_json_default_off(self) -> None:
        self.assertIsNone(LogConfig().json_log)

    def test_json_truthy_literals(self) -> None:
        for v in (True, 1, "yes", "YES", "true", "1", "on", "truthy"):
            with self.subTest(v=v):
                self.assertEqual(LogConfig(json_log=v).json_log, DEFAULT_JSON_LOG_FILE_PATH)

    def test_json_stderr_literal(self) -> None:
        self.assertEqual(LogConfig(json_log="stderr").json_log, "stderr")

    def test_json_file_prefix(self) -> None:
        self.assertEqual(LogConfig(json_log="file:/tmp/thaum.json").json_log, "/tmp/thaum.json")

    def test_json_disabled_literals(self) -> None:
        for v in (False, 0, "no", "false", "0", "off", None, ""):
            with self.subTest(v=v):
                self.assertIsNone(LogConfig(json_log=v).json_log)

    def test_json_invalid_value(self) -> None:
        with self.assertRaises(ValueError):
            LogConfig(json_log="banana")

    def test_override_env_default(self) -> None:
        self.assertFalse(LogConfig().override_env)

    def test_override_env_truthy_value(self) -> None:
        self.assertTrue(LogConfig(override_env="true").override_env)


class ConfigureLoggingFileTest(unittest.TestCase):
    def tearDown(self) -> None:
        configure_logging(LogConfig(level=LogLevel.INFO))

    def test_adds_file_handler_when_dir_exists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.log"
            configure_logging(LogConfig(level=LogLevel.INFO, file=str(p)))
            logging.getLogger("thaum.test").info("hello_line")
            logging.shutdown()
            data = p.read_text(encoding="utf-8")
            self.assertIn("hello_line", data)
            self.assertRegex(data, r"\d{4}-\d{2}-\d{2}T")

    def test_file_has_timestamp_when_no_timestamp_console(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.log"
            configure_logging(
                LogConfig(level=LogLevel.INFO, file=str(p), no_timestamp=True),
            )
            logging.getLogger("thaum.test").info("m")
            logging.shutdown()
            line = p.read_text(encoding="utf-8").strip()
            self.assertRegex(line, r"^\d{4}-\d{2}-\d{2}T")

    def test_missing_log_dir_stderr(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            configure_logging(
                LogConfig(level=LogLevel.INFO, file="/nonexistent_dir_thaum_xyz/thaum.log"),
            )
        self.assertIn("does not exist", err.getvalue())
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)
        self.assertIsInstance(root.handlers[0], logging.StreamHandler)

    def test_werkzeug_shares_root_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.log"
            configure_logging(LogConfig(level=LogLevel.INFO, file=str(p)))
            w = logging.getLogger("werkzeug")
            r = logging.getLogger()
            self.assertEqual(len(w.handlers), 2)
            self.assertEqual(len(w.handlers), len(r.handlers))
            self.assertIs(w.handlers[0], r.handlers[0])
            self.assertIs(w.handlers[1], r.handlers[1])

    def test_json_log_to_stderr_from_toml(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            configure_logging(LogConfig(level=LogLevel.INFO, json_log="stderr"))
            logging.getLogger("thaum.test").warning("json_stderr_line")
        self.assertIn('"message":"json_stderr_line"', err.getvalue())

    def test_json_log_to_file_from_toml_file_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "events.json"
            configure_logging(LogConfig(level=LogLevel.INFO, json_log=f"file:{p}"))
            logging.getLogger("thaum.test").warning("json_file_line")
            logging.shutdown()
            data = p.read_text(encoding="utf-8")
            self.assertIn('"message":"json_file_line"', data)

    def test_json_log_env_truthy_overrides_when_truthy_mode(self) -> None:
        with patch.dict(os.environ, {"THAUM_JSON_LOG": "true"}, clear=False):
            configure_logging(
                LogConfig(level=LogLevel.INFO, json_log=False, override_env=False),
            )
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 2)

    def test_json_log_env_truthy_ignored_when_override_env_truthy(self) -> None:
        with patch.dict(os.environ, {"THAUM_JSON_LOG": "true"}, clear=False):
            configure_logging(
                LogConfig(level=LogLevel.INFO, json_log=False, override_env=True),
            )
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)

    def test_thaum_log_level_overrides_toml(self) -> None:
        with patch.dict(os.environ, {"THAUM_LOG_LEVEL": "DEBUG"}, clear=False):
            configure_logging(LogConfig(level=LogLevel.ERROR))
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    def test_override_env_truthy_uses_toml_log_level_over_env(self) -> None:
        with patch.dict(os.environ, {"THAUM_LOG_LEVEL": "DEBUG"}, clear=False):
            configure_logging(LogConfig(level=LogLevel.ERROR, override_env=True))
        self.assertEqual(logging.getLogger().level, logging.ERROR)

    def test_early_init_then_override_env_truthy_can_disable_final_json(self) -> None:
        with patch.dict(os.environ, {"THAUM_JSON_LOG": "true"}, clear=False):
            init_early_logging_from_env()
            configure_logging(LogConfig(level=LogLevel.INFO, json_log=False, override_env=True))
        self.assertEqual(len(logging.getLogger().handlers), 1)


class LogEnvDefaultFileTest(unittest.TestCase):
    def test_thaum_log_to_var_log_sets_default_path(self) -> None:
        from bootstrap import _log_config_with_env_defaults

        with patch.dict(os.environ, {"THAUM_LOG_TO_VAR_LOG": "1"}):
            merged = _log_config_with_env_defaults(LogConfig())
        self.assertEqual(merged.file, DEFAULT_LOG_FILE_PATH)

    def test_explicit_file_in_toml_untouched(self) -> None:
        from bootstrap import _log_config_with_env_defaults

        with patch.dict(os.environ, {"THAUM_LOG_TO_VAR_LOG": "1"}):
            merged = _log_config_with_env_defaults(LogConfig(file="/tmp/custom.log"))
        self.assertEqual(merged.file, "/tmp/custom.log")
