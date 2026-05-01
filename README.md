# Thaum
## Chat‑Driven On‑Call and Team Alerting

Thaum was written to solve the problem of users who expect operations to be actively monitoring a chat room all night in case they need help.  It is a modular framework to tie a chat bot to an on-call alerting system. 

I have implemented Webex and Jira Service Manager Ops.  But plugins could be written for PagerDuty or even something as simple as a team broadcast via Pushover.  A plugin could also be written to make it a Teams bot instead of webex.

I have over 30 years of experience in IT operations and I know the pain of on-call.  I also know the pain of trying to use logging to troubleshoot an operational system. (Stacktraces are not logs!)  I built something I want to use, and I hope you'll find it useful too.

Some code in this repository was written with the help of **Cursor** and **GitHub Copilot** (assistive tooling; human review and integration remain the author’s responsibility).

## Requirements

- **Python 3.11 or newer** — enforced in `pyproject.toml` (`requires-python`) so installers and tools can detect an unsupported interpreter. Dependencies are declared in `pyproject.toml` (`[project.dependencies]`); `requirements.txt` mirrors the same pins for `pip install -r` / Docker. Install into a virtual environment (e.g. `python3.11 -m venv .venv`), then run **`pip install .`** or **`pip install -r requirements.txt`** from the repo root.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — bootstrap, config model, logging, plugins.
- [Quickstart](quickstart/QUICKSTART.md) — Quadlet (Podman) or containerless (Unix socket + nginx), with encrypted credentials.
- [Deployment quickstarts](docs/deployment-quickstarts.md) — cloud (Azure; AWS/GCP planned) and Kubernetes.
- [Style guide](docs/STYLE_GUIDE.md) — code and test conventions.
- [Admin log level API](docs/admin-log-level.md) — signed runtime log level changes.
- [Release notes](RELEASE_NOTES.md)

**Container / load-balancer probes:** `GET /health` returns 200 when the process can serve HTTP (liveness). `GET /ready` returns 200 when the app can reach its database (`SELECT 1` via the normal SQLAlchemy pool); it returns 503 if the database check fails (readiness). Example: `curl -sf http://127.0.0.1:5165/health` and `curl -sf http://127.0.0.1:5165/ready` (adjust host/port to your bind).

## Container images (CI)

Publishing runs from [`.github/workflows/release.yml`](.github/workflows/release.yml) when a **GitHub Release is published** or when you **Run workflow** manually (`workflow_dispatch`). The job runs the unit tests, then builds [`Dockerfile`](Dockerfile) and pushes **four** image name variants to your registry (same tag scheme on each): the default image, **`<name>-azure`**, **`<name>-external-db`** (no bundled PostgreSQL or supervisord; set `[server.database].db_url`), and **`<name>-azure-external-db`**.

On **GitHub Release publish** (including **prereleases**), the workflow also uploads **`thaum-utils-<release-tag>.zip`** to that release. The archive contains a `thaum-utils/` folder with `quickstart/`, `docs/`, `scripts/`, `sample.thaum.toml`, and `incident_prompt_card.sample.j2`.

| Tag | When it is updated | Use case |
|-----|-------------------|----------|
| **`<version>`** | Every **release** publish | Immutable tag matching `[project].version` in `pyproject.toml` (pin to a specific release). |
| **`:latest`** | **Stable** release (not a GitHub prerelease) | Rolling tag for the latest stable release. |
| **`:devel`** | **Prerelease** or **stable** release publish | On a **prerelease**, points at that prerelease image. On a **stable** release, updated to the **same digest as `:latest`** so it tracks the latest published release; the **next prerelease** moves `:devel` to that prerelease image. |
| **`:edge`** | **Stable** or **prerelease** GitHub Release publish, or **manual** workflow from branch **`main`** | Always points at the **image from the most recent** of those events (same digest as that build’s version tag). Rolling “current” image for smoke tests and releases. |
| **`:edge-<branch>`** | **Manual** workflow from any **other** branch | Same as `:edge`, but tag is **`edge-`** plus a sanitized branch name (e.g. `feature-foo` from `feature/foo`) so topic branches do not overwrite `:edge`. Long suffixes are truncated to fit registry tag limits. |

CI passes **`THAUM_IMAGE_VERSION`** and **`THAUM_IMAGE_CHANNEL`** into the image build; the runtime image sets OCI-style labels (`org.opencontainers.image.version`, `thaum.image.channel`). Inspect with `docker inspect` / `podman inspect` on a pulled image.

By default images go to **GitHub Container Registry** (`ghcr.io/<owner>/<repo>`, lowercase). The workflow needs **`packages: write`** (already set) for GHCR. To use **Docker Hub** instead, run the workflow with inputs `registry: docker.io` and `image: docker.io/<user>/<name>`, and configure repository secrets **`DOCKERHUB_USERNAME`** and **`DOCKERHUB_TOKEN`**. Other registries can use secrets **`REGISTRY_USERNAME`** and **`REGISTRY_PASSWORD`** with the `registry` / `image` inputs.