#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# Package thaum-utils/<layout> into dist/thaum-utils-<tag>.zip and SHA256SUMS.txt.
set -euo pipefail

TAG="${1:?usage: package-thaum-utils.sh <tag>   e.g. v0.7.0rc2}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/dist"
STAGING="${OUT}/thaum-utils"
ZIP_NAME="thaum-utils-${TAG}.zip"

mkdir -p "$OUT"
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -a "${ROOT}/quickstart" "${ROOT}/docs" "${ROOT}/scripts" "$STAGING/"
cp "${ROOT}/sample.thaum.toml" "${ROOT}/incident_prompt_card.sample.j2" "$STAGING/"

rm -f "${OUT}/${ZIP_NAME}" "${OUT}/SHA256SUMS.txt"
(
  cd "$OUT"
  zip -r "$ZIP_NAME" thaum-utils
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$ZIP_NAME" > SHA256SUMS.txt
  else
    shasum -a 256 "$ZIP_NAME" > SHA256SUMS.txt
  fi
)

echo "${OUT}/${ZIP_NAME}"
echo "${OUT}/SHA256SUMS.txt"
