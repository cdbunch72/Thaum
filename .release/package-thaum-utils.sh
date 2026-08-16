#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# Package thaum-utils/<layout> into dist/thaum-utils-<tag>.zip.
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

rm -f "${OUT}/${ZIP_NAME}"
(
  cd "$OUT"
  zip -r "$ZIP_NAME" thaum-utils
)

echo "${OUT}/${ZIP_NAME}"
