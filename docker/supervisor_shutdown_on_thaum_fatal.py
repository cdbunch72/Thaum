# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
"""Supervisor event listener: stop supervisord when ``thaum`` reaches FATAL (e.g. startretries exhausted)."""
from __future__ import annotations

import os
import signal
import sys


def _write_stdout(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def _write_stderr(s: str) -> None:
    sys.stderr.write(s)
    sys.stderr.flush()


def _shutdown_supervisord() -> None:
    pidfile = "/var/run/supervisord.pid"
    try:
        with open(pidfile, encoding="utf-8") as f:
            pid = int(f.read().strip())
    except Exception as e:
        _write_stderr(f"[debug-131a48][H22] fatal listener: could not read {pidfile}: {e}\n")
        return
    _write_stderr(f"[debug-131a48][H22] fatal listener: sending SIGTERM to supervisord pid={pid}\n")
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        _write_stderr(f"[debug-131a48][H22] fatal listener: kill failed: {e}\n")


def main() -> None:
    _write_stdout("READY\n")
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        parts = line.strip().split()
        headers: dict[str, str] = {}
        for p in parts:
            if ":" in p:
                k, v = p.split(":", 1)
                headers[k] = v
        try:
            length = int(headers["len"])
        except Exception:
            continue
        payload = sys.stdin.read(length)
        if headers.get("eventname") != "PROCESS_STATE_FATAL":
            continue
        if "processname:thaum" not in payload:
            continue
        _shutdown_supervisord()


if __name__ == "__main__":
    main()
