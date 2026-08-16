#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# Detached-sign files with code@gemstone.software (or CODE_GPG_KEY).
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: sign-artifacts.sh <file> [file...]" >&2
  exit 2
fi

KEY="${CODE_GPG_KEY:-code@gemstone.software}"
for f in "$@"; do
  if [[ ! -f "$f" ]]; then
    echo "not a file: $f" >&2
    exit 1
  fi
  gpg --yes --local-user "$KEY" --detach-sign --armor "$f"
done
