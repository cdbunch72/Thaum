#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# Cut a signed Thaum GitHub Release from a bare version (e.g. 0.7.0rc2).
set -euo pipefail

usage() {
  cat <<'EOF'
usage: cut-release.sh <bare-version> [options]

Validate pins, write SHA256SUMS.txt, detach-sign it with code@gemstone.software,
commit the sums (unsigned git commit; integrity is the code@ .asc), package and
GPG-sign thaum-utils, create signed tag v<version> with
git-commit@gemstone.software, publish the GitHub Release, and (unless
--skip-images) build/push/cosign GHCR images.

Options:
  --skip-images              Do not build or push GHCR images
  --code-key USER            GPG user id for SHA256SUMS.txt and the zip
                             (default: code@gemstone.software)
  --git-commit-key USER      GPG user id for git tag -s
                             (default: git-commit@gemstone.software)
  --cosign-key PATH          Cosign private key for publish-images.sh
EOF
}

SKIP_IMAGES=0
VERSION=""
CODE_KEY="code@gemstone.software"
GIT_COMMIT_KEY="git-commit@gemstone.software"
COSIGN_KEY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-images)
      SKIP_IMAGES=1
      shift
      ;;
    --code-key)
      CODE_KEY="${2:?cut-release.sh: --code-key requires a GPG user id}"
      shift 2
      ;;
    --git-commit-key)
      GIT_COMMIT_KEY="${2:?cut-release.sh: --git-commit-key requires a GPG user id}"
      shift 2
      ;;
    --cosign-key)
      COSIGN_KEY="${2:?cut-release.sh: --cosign-key requires a path}"
      shift 2
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

SUMS="${ROOT}/SHA256SUMS.txt"
SUMS_ASC="${SUMS}.asc"

"$PYTHON" "${ROOT}/.release/generate_checksums.py" --output "$SUMS"

SUMS_CHANGED=1
if git cat-file -e "HEAD:SHA256SUMS.txt" 2>/dev/null && git diff --quiet -- SHA256SUMS.txt; then
  SUMS_CHANGED=0
fi
if [[ "$SUMS_CHANGED" -eq 1 || ! -f "$SUMS_ASC" ]]; then
  "${ROOT}/.release/sign-artifacts.sh" --key "$CODE_KEY" "$SUMS"
fi

git add -- SHA256SUMS.txt SHA256SUMS.txt.asc
if git diff --cached --quiet -- SHA256SUMS.txt SHA256SUMS.txt.asc; then
  echo "SHA256SUMS.txt already committed"
else
  git commit -m "$(cat <<EOF
Record SHA256SUMS signed by ${CODE_KEY} for ${THAUM_RELEASE_TAG}.

EOF
)"
fi

"${ROOT}/.release/package-thaum-utils.sh" "$THAUM_RELEASE_TAG"
ZIP="${ROOT}/dist/thaum-utils-${THAUM_RELEASE_TAG}.zip"
"${ROOT}/.release/sign-artifacts.sh" --key "$CODE_KEY" "$ZIP"

git tag -s -u "$GIT_COMMIT_KEY" -m "Thaum ${THAUM_RELEASE_TAG}" "$THAUM_RELEASE_TAG"
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
  if [[ -n "$COSIGN_KEY" ]]; then
    "${ROOT}/.release/publish-images.sh" "$VERSION" --cosign-key "$COSIGN_KEY"
  else
    "${ROOT}/.release/publish-images.sh" "$VERSION"
  fi
fi
