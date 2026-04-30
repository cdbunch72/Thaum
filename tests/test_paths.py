# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# tests/test_paths.py
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from thaum.paths import ConfigResolutionError, resolve_config_path


class ResolveConfigPathTest(unittest.TestCase):
    def test_env_override_short_circuits_candidates(self) -> None:
        with patch.dict(os.environ, {"THAUM_CONFIG_FILE": "/tmp/custom.toml"}, clear=False):
            self.assertEqual(resolve_config_path(), "/tmp/custom.toml")

    def test_candidate_order_prefers_etc_before_local(self) -> None:
        existing = {
            Path("/etc/thaum/thaum.conf").as_posix(),
            Path("./thaum.toml").as_posix(),
        }

        def _exists(p: Path) -> bool:
            return p.as_posix() in existing

        with patch.dict(os.environ, {}, clear=True):
            with patch("thaum.paths.Path.exists", autospec=True, side_effect=_exists):
                self.assertEqual(
                    resolve_config_path(),
                    str(Path("/etc/thaum/thaum.conf")),
                )

    def test_missing_candidates_raises_config_resolution_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("thaum.paths.Path.exists", autospec=True, return_value=False):
                with self.assertRaises(ConfigResolutionError) as ctx:
                    resolve_config_path()

        self.assertIn("THAUM_CONFIG_FILE", str(ctx.exception))

