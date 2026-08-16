#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# Build, push, and cosign signed GHCR images for a bare Thaum version.
set -euo pipefail

usage() {
  cat <<'EOF'
usage: publish-images.sh <bare-version>

Builds thaum and thaum-external-db, pushes version plus floating tags
(devel/edge, and latest when stable), and cosign-signs each image digest.
Requires docker or podman, gh, and cosign. COSIGN_KEY defaults to
.release/cosign.key. Set SKIP_LOGIN=1 to skip ghcr.io login.
EOF
}

VERSION="${1:-}"
if [[ -z "$VERSION" || "$VERSION" == "-h" || "$VERSION" == "--help" ]]; then
  usage
  [[ -n "$VERSION" ]] && exit 0
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

if [[ -z "${THAUM_RELEASE_VERSION:-}" || "${THAUM_RELEASE_VERSION}" != "$VERSION" ]]; then
  # shellcheck disable=SC1090
  source <("$PYTHON" "${ROOT}/.release/release_meta.py" "$VERSION" --format env)
fi

PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
COSIGN_KEY="${COSIGN_KEY:-${ROOT}/.release/cosign.key}"
if [[ ! -f "$COSIGN_KEY" ]]; then
  echo "cosign private key not found: ${COSIGN_KEY}" >&2
  echo "Generate with: cosign generate-key-pair --output-key-prefix ${ROOT}/.release/cosign" >&2
  echo "Commit the .pub file; keep the private key off GitHub." >&2
  exit 1
fi
if ! command -v cosign >/dev/null 2>&1; then
  echo "cosign is required on PATH" >&2
  exit 1
fi

resolve_engine() {
  if [[ -n "${CONTAINER_ENGINE:-}" ]]; then
    echo "$CONTAINER_ENGINE"
    return
  fi
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo docker
    return
  fi
  if command -v podman >/dev/null 2>&1; then
    echo podman
    return
  fi
  echo "docker or podman is required" >&2
  exit 1
}

ENGINE="$(resolve_engine)"

if [[ -z "${THAUM_IMAGE:-}" ]]; then
  NWO="$(gh repo view --json nameWithOwner --jq .nameWithOwner | tr '[:upper:]' '[:lower:]')"
  THAUM_IMAGE="ghcr.io/${NWO}"
fi
IMAGE_EXTERNAL="${THAUM_IMAGE}-external-db"

if [[ "${SKIP_LOGIN:-0}" != "1" ]]; then
  GHCR_USER="$(gh api user --jq .login)"
  gh auth token | "$ENGINE" login ghcr.io -u "$GHCR_USER" --password-stdin
fi

tags_for() {
  local image="$1"
  echo "${image}:${THAUM_RELEASE_VERSION}"
  echo "${image}:devel"
  echo "${image}:edge"
  if [[ "${THAUM_RELEASE_PRERELEASE}" != "1" ]]; then
    echo "${image}:latest"
  fi
}

image_digest() {
  local ref="$1"
  local digest
  digest="$("$ENGINE" image inspect --format '{{index .RepoDigests 0}}' "$ref")"
  if [[ -z "$digest" || "$digest" == "<no value>" ]]; then
    echo "no RepoDigest for ${ref}; push succeeded but digest is missing" >&2
    exit 1
  fi
  echo "$digest"
}

build_push_sign() {
  local image="$1"
  local bundled="$2"
  local version_ref="${image}:${THAUM_RELEASE_VERSION}"

  "$ENGINE" build \
    --build-arg "PYTHON_VERSION=${PYTHON_VERSION}" \
    --build-arg "GEMSTONE_UTILS_REF=${GEMSTONE_UTILS_REF}" \
    --build-arg "THAUM_BUNDLED_POSTGRES=${bundled}" \
    --build-arg "THAUM_IMAGE_VERSION=${THAUM_RELEASE_VERSION}" \
    --build-arg "THAUM_IMAGE_CHANNEL=${THAUM_IMAGE_CHANNEL}" \
    -t "$version_ref" \
    -f "${ROOT}/Dockerfile" \
    "$ROOT"

  local tag
  while IFS= read -r tag; do
    [[ "$tag" == "$version_ref" ]] && continue
    "$ENGINE" tag "$version_ref" "$tag"
  done < <(tags_for "$image")

  while IFS= read -r tag; do
    "$ENGINE" push "$tag"
  done < <(tags_for "$image")

  local digest
  digest="$(image_digest "$version_ref")"
  cosign sign --yes --key "$COSIGN_KEY" "$digest"
}

build_push_sign "$THAUM_IMAGE" 1
build_push_sign "$IMAGE_EXTERNAL" 0
