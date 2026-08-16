#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# Detached-sign files with code@gemstone.software (override with --key).
set -euo pipefail

usage() {
  echo "usage: sign-artifacts.sh [--key USER] <file> [file...]" >&2
}

KEY="code@gemstone.software"
FILES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --key)
      KEY="${2:?sign-artifacts.sh: --key requires a GPG user id}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      FILES+=("$@")
      break
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage
      exit 2
      ;;
    *)
      FILES+=("$1")
      shift
      ;;
  esac
done

if [[ ${#FILES[@]} -lt 1 ]]; then
  usage
  exit 2
fi

for f in "${FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "not a file: $f" >&2
    exit 1
  fi
  gpg --yes --local-user "$KEY" --detach-sign --armor "$f"
done
