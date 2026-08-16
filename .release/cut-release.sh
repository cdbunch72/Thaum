#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# Cut a signed Thaum GitHub Release from a bare version (e.g. 0.7.0rc2).
set -euo pipefail

usage() {
  cat <<'EOF'
usage: cut-release.sh <bare-version> [--skip-images]

Validate pins, write and commit signed SHA256SUMS.txt for source integrity,
package (and GPG-sign) thaum-utils, create signed tag v<version> with
git-commit@gemstone.software, publish the GitHub Release, and (unless
--skip-images) build/push/cosign GHCR images.
EOF
}

SKIP_IMAGES=0
VERSION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-images)
      SKIP_IMAGES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$VERSION" ]]; then
        echo "unexpected argument: $1" >&2
        usage >&2
        exit 2
      fi
      VERSION="$1"
      shift
      ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  usage >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "python3 or python is required" >&2
  exit 1
fi

mkdir -p "${ROOT}/dist"
# shellcheck disable=SC1090
source <(
  "$PYTHON" "${ROOT}/.release/release_meta.py" "$VERSION" \
    --format env --notes-out "${ROOT}/dist/NOTES.md"
)

if [[ -n "$(git status --porcelain)" ]]; then
  echo "working tree is dirty" >&2
  git status --porcelain >&2
  exit 1
fi

if git rev-parse -q --verify "refs/tags/${THAUM_RELEASE_TAG}" >/dev/null; then
  echo "tag ${THAUM_RELEASE_TAG} already exists" >&2
  exit 1
fi

GIT_KEY="${GIT_COMMIT_SIGNING_KEY:-git-commit@gemstone.software}"
SUMS="${ROOT}/SHA256SUMS.txt"
SUMS_ASC="${SUMS}.asc"

"$PYTHON" "${ROOT}/.release/generate_checksums.py" --output "$SUMS"

SUMS_CHANGED=1
if git cat-file -e "HEAD:SHA256SUMS.txt" 2>/dev/null && git diff --quiet -- SHA256SUMS.txt; then
  SUMS_CHANGED=0
fi
if [[ "$SUMS_CHANGED" -eq 1 || ! -f "$SUMS_ASC" ]]; then
  "${ROOT}/.release/sign-artifacts.sh" "$SUMS"
fi

git add -- SHA256SUMS.txt SHA256SUMS.txt.asc
if git diff --cached --quiet -- SHA256SUMS.txt SHA256SUMS.txt.asc; then
  echo "SHA256SUMS.txt already committed"
else
  git commit -S -u "$GIT_KEY" -m "$(cat <<EOF
Record signed SHA256SUMS for ${THAUM_RELEASE_TAG}.

EOF
)"
fi

"${ROOT}/.release/package-thaum-utils.sh" "$THAUM_RELEASE_TAG"
ZIP="${ROOT}/dist/thaum-utils-${THAUM_RELEASE_TAG}.zip"
"${ROOT}/.release/sign-artifacts.sh" "$ZIP"

git tag -s -u "$GIT_KEY" -m "Thaum ${THAUM_RELEASE_TAG}" "$THAUM_RELEASE_TAG"
git push origin HEAD "refs/tags/${THAUM_RELEASE_TAG}"

PRE=()
if [[ "${THAUM_RELEASE_PRERELEASE}" == "1" ]]; then
  PRE=(--prerelease)
fi

gh release create "$THAUM_RELEASE_TAG" \
  --verify-tag \
  --title "$THAUM_RELEASE_TAG" \
  --notes-file "${ROOT}/dist/NOTES.md" \
  "${PRE[@]}" \
  "$ZIP" \
  "${ZIP}.asc" \
  "$SUMS" \
  "$SUMS_ASC"

if [[ "$SKIP_IMAGES" -eq 0 ]]; then
  "${ROOT}/.release/publish-images.sh" "$VERSION"
fi
