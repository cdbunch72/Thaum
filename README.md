# Thaum
## Chat‑Driven On‑Call and Team Alerting

Thaum was written to solve the problem of users who expect operations to be actively monitoring a chat room all night in case they need help.  It is a modular framework to tie a chat bot to an on-call alerting system. 

I have implemented Webex and Jira Service Manager Ops.  But plugins could be written for PagerDuty or even something as simple as a team broadcast via Pushover.  A plugin could also be written to make it a Teams bot instead of webex.

I have over 30 years of experience in IT operations and I know the pain of on-call.  I also know the pain of trying to use logging to troubleshoot an operational system. I keep **human-visible** consoles readable (full tracebacks there only when you opt into SPAM), while optional **structured JSON** logging can carry tracebacks for failure analysis without widening console noise—so troubleshooting does not force noisy defaults.

Some code in this repository was written with the help of **Cursor** and **GitHub Copilot** (assistive tooling; human review and integration remain the author’s responsibility).

## Requirements

- **Python 3.11 or newer** — enforced in `pyproject.toml` (`requires-python`) so installers and tools can detect an unsupported interpreter. Dependencies are declared in `pyproject.toml` (`[project.dependencies]`); `requirements.txt` mirrors the same pins for `pip install -r` / Docker. Install into a virtual environment (e.g. `python3.11 -m venv .venv`), then run **`pip install .`** or **`pip install -r requirements.txt`** from the repo root.

## Documentation

Narrative guides live under [`docs/`](docs/). Build a styled HTML site (Furo theme,
Thaum branding) with Sphinx:

```bash
pip install ".[docs]"
make -C docs/sphinx_config html
# open docs/_build/html/index.html
```

This installs Thaum runtime dependencies so Sphinx autodoc can import plugin base
classes, plus Sphinx and the Furo theme.

- [Architecture](docs/ARCHITECTURE.md) — bootstrap, config model, logging, plugins.
- [Quickstart](quickstart/QUICKSTART.md) — Quadlet (Podman) or containerless (Unix socket + nginx), with encrypted credentials.
- [Deployment quickstarts](docs/deployment-quickstarts.md) — [Thaum Cloud](https://gemstone-software-dev.github.io/thaum-cloud/) (public-cloud deploy template) and Kubernetes.
- [Style guide](docs/STYLE_GUIDE.md) — code and test conventions.
- [Admin log level API](docs/admin-log-level.md) — signed runtime log level changes.
- [Release notes](RELEASE_NOTES.md)
- [Cut a release](.release/README.md)

**Container / load-balancer probes:** `GET /health` returns 200 when the process can serve HTTP (liveness). `GET /ready` returns 200 when the app can reach its database (`SELECT 1` via the normal SQLAlchemy pool); it returns 503 if the database check fails (readiness). Example: `curl -sf http://127.0.0.1:5165/health` and `curl -sf http://127.0.0.1:5165/ready` (adjust host/port to your bind).

## Container images

Signed production images are **`ghcr.io/<owner>/thaum`** and **`thaum-external-db`** (bundled PostgreSQL + supervisord, and gunicorn-only). Maintainers publish them locally with [`.release/cut-release.sh`](.release/cut-release.sh) (or the PowerShell twin): GPG-signed `thaum-utils` zip on the GitHub Release, a signed git tag, then Docker/Podman build, push, and **cosign** by digest. See [`.release/README.md`](.release/README.md). Cloud-specific Python extras (for example `gemstone_utils[azure]` for experimental `azexp:` references) belong in **deploy-repo** images, not in the published Thaum tags—see [Thaum Cloud](https://gemstone-software-dev.github.io/thaum-cloud/).

Each GitHub Release includes **`thaum-utils-<tag>.zip`**, its `.asc`, and binary **`SHA256SUMS.zip`**. The archive contains a `thaum-utils/` folder with `quickstart/`, `docs/`, `scripts/`, `sample.thaum.toml`, and `incident_prompt_card.sample.j2`. Source integrity is committed **`SHA256SUMS.txt`** / **`SHA256SUMS.txt.asc`** (text-mode GNU `sha256sum -c`, runtime Python, `scripts/`, `docker/`, `Dockerfile`, `pyproject.toml`, `requirements.txt`).

Unsigned CI smoke images are **`thaum-debug`** and **`thaum-debug-external-db`**, published only from the **Debug images** workflow (`workflow_dispatch`). They never share tags with the signed packages.

| Image | Tag | When it is updated | Trust |
|-------|-----|-------------------|--------|
| **`thaum`** / **`thaum-external-db`** | **`<version>`** | Every local cut-release | Signed (cosign). Pin production here. |
| | **`:latest`** | Stable cut-release (not a prerelease) | Signed. Rolling latest stable. |
| | **`:devel`** | Prerelease or stable cut-release | Signed. On a prerelease, that build; on stable, same digest as `:latest`. |
| | **`:edge`** | Every cut-release (stable or pre) | Signed. Most recently published (pre)release. |
| **`thaum-debug`** / **`thaum-debug-external-db`** | **`:edge`** | **Debug images** dispatch from **`main`** | Unsigned. Do not use in production. |
| | **`:edge-<branch>`** | **Debug images** dispatch from any other branch | Unsigned. Sanitized branch name (e.g. `feature-foo` from `feature/foo`). |

Build args **`THAUM_IMAGE_VERSION`** and **`THAUM_IMAGE_CHANNEL`** are baked into OCI-style labels (`org.opencontainers.image.version`, `thaum.image.channel`). Inspect with `docker inspect` / `podman inspect`. Verify a signed image with `cosign verify --key .release/cosign.pub <image>@<digest>` after you have committed the public key.