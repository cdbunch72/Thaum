# Thaum release tools

Local scripts to cut a **signed** GitHub Release and publish **signed** GHCR images (`thaum` / `thaum-external-db`). GitHub Actions never holds GPG or cosign keys and never writes those image names.

Unsigned smoke builds go to `thaum-debug` / `thaum-debug-external-db` via **Actions → Debug images** (`workflow_dispatch` only).

## Prerequisites

| Tool | Used for |
|------|----------|
| Python 3.11+ | Pin checks (`.release/release_meta.py`) |
| `git` | Signed tag `v<version>` |
| `gpg` | Artifact signatures; `git tag -s` |
| `gh` | Push-visible repo, `gh release create --verify-tag`, GHCR login |
| `zip` (bash) or `Compress-Archive` (PowerShell) | `thaum-utils` archive |
| Docker **or** Podman | Image builds |
| [`cosign`](https://docs.sigstore.dev/cosign/system_config/installation/) | Sign image digests |

GPG keys (secret keys stay on this machine):

- `git-commit@gemstone.software` — annotated signed git tags
- `code@gemstone.software` — detached signatures on the zip and `SHA256SUMS.txt`

Override with `GIT_COMMIT_SIGNING_KEY` and `CODE_GPG_KEY` if needed.

Upload the **public** `git-commit@` key to GitHub (**Settings → SSH and GPG keys → New GPG key**) so `gh release create --verify-tag` can verify the tag.

## Cut a release

From a clean worktree on the commit you want to ship. The bare version must match `[project].version` in `pyproject.toml`, the `gemstone_utils==` pins in `pyproject.toml` and `requirements.txt`, and a `## v<version>` heading in `RELEASE_NOTES.md`.

```bash
./.release/cut-release.sh 0.7.0rc2
# images only skipped:
./.release/cut-release.sh 0.7.0rc2 --skip-images
```

```powershell
.\.release\cut-release.ps1 0.7.0rc2
.\.release\cut-release.ps1 0.7.0rc2 -SkipImages
```

That will:

1. Validate pins and write `dist/NOTES.md` from `RELEASE_NOTES.md`
2. Zip `thaum-utils` into `dist/`, write `SHA256SUMS.txt`, detach-sign both with `code@`
3. `git tag -s v<version>` and push the tag
4. `gh release create --verify-tag` with the zip, `.asc` files, and checksums (`--prerelease` when the version is not a final PEP 440 release)
5. Build and push GHCR images, then `cosign sign --key` **by digest** (unless `--skip-images`)

Prerelease tags: `:<version> :devel :edge`. Stable adds `:latest`.

Publish images later:

```bash
./.release/publish-images.sh 0.7.0rc2
```

`COSIGN_KEY` defaults to `.release/cosign.key` (gitignored). First-time keypair:

```bash
cosign generate-key-pair --output-key-prefix .release/cosign
# commit .release/cosign.pub only
```

`SKIP_LOGIN=1` skips `gh auth token | docker login ghcr.io`. `THAUM_IMAGE` overrides the default `ghcr.io/<owner>/<repo>` from `gh repo view`. `CONTAINER_ENGINE` forces `docker` or `podman`. `PYTHON_VERSION` defaults to `3.13`.

Verify:

```bash
cosign verify --key .release/cosign.pub ghcr.io/<owner>/thaum@sha256:<digest>
gpg --verify dist/thaum-utils-v0.7.0rc2.zip.asc dist/thaum-utils-v0.7.0rc2.zip
gpg --verify dist/SHA256SUMS.txt.asc dist/SHA256SUMS.txt
(cd dist && sha256sum -c SHA256SUMS.txt)
```

## Unsigned debug images

**Actions → Debug images → Run workflow.** From `main` the tag is `edge`; from another branch it is `edge-<sanitized-branch>`. Image names:

- `ghcr.io/<owner>/<repo>-debug`
- `ghcr.io/<owner>/<repo>-debug-external-db`

These are **unsigned**. Do not point production Quadlet or Kubernetes at them.

## Manual GitHub configuration

Do this **after** merging the workflows that stop CI from pushing `thaum` / `thaum-external-db`, then lock those packages so Actions cannot overwrite them again.

### A. Stop Actions writing the release packages

1. Open [github.com/orgs/gemstone-software-dev/packages](https://github.com/orgs/gemstone-software-dev/packages) (or the repo **Packages** list in the right sidebar).
2. Open package **`thaum`**.
3. **Package settings** (right-hand **… → Package settings**, or **Settings** on the package page).
4. **Manage Actions access**: repositories allowed to use `GITHUB_TOKEN` against this package.
5. Remove **write** for `gemstone-software-dev/thaum` (or remove the repository). Leave visibility **public** if it is public today.
6. Repeat for **`thaum-external-db`**.

Your user `docker login` / `gh auth` can still push. A workflow with `packages: write` must not be able to tag `thaum:latest`.

### B. First debug packages

`thaum-debug` and `thaum-debug-external-db` appear after the first successful **Debug images** run.

1. **Actions → Debug images → Run workflow** (branch `main` → tag `edge`).
2. Open the new packages. Keep Actions **write** for this repository (the default when `GITHUB_TOKEN` created them).
3. Set visibility **public** if GitHub created them private.

Do **not** grant the debug workflow (or this repository’s Actions access) write on the `thaum` / `thaum-external-db` packages.

### C. Keys

1. **`git-commit@gemstone.software`**: `gpg --list-secret-keys`; add the **public** key under GitHub **Settings → SSH and GPG keys**.
2. **`code@gemstone.software`**: local only. Never store the secret key as an Actions secret.
3. **Cosign**: generate locally, commit **`.release/cosign.pub`**, keep **`.release/cosign.key`** off git.
4. **GHCR login** for `publish-images`: `gh auth login` with `write:packages`, or `docker login ghcr.io`. Do not put Docker Hub or GHCR PATs in Actions secrets for signed publishing.

### D. Optional

- Repo **Settings → Actions → General**: disable “Allow GitHub Actions to create and approve pull requests” if you do not use that.
- Do not add a PAT with `write:packages` on the `thaum` package as a repository secret.
