# Thaum
## Chat‑Driven On‑Call and Team Alerting

Thaum was written to solve the problem of users who expect operations to be actively monitoring a chat room all night in case they need help.  It is a modular framework to tie a chat bot to an on-call alerting system. 

I have implemented Webex and Jira Service Manager Ops.  But plugins could be written for PagerDuty or even something as simple as a team broadcast via Pushover.  A plugin could also be written to make it a Teams bot instead of webex.

I have over 30 years of experience in IT operations and I know the pain of on-call.  I also know the pain of trying to use logging to troubleshoot an operational system. (Stacktraces are not logs!)  I built something I want to use, and I hope you'll find it useful too.

## Requirements

- **Python 3.11 or newer** — enforced in `pyproject.toml` (`requires-python`) so installers and tools can detect an unsupported interpreter. Dependencies are declared in `pyproject.toml` (`[project.dependencies]`); `requirements.txt` mirrors the same pins for `pip install -r` / Docker. Install into a virtual environment (e.g. `python3.11 -m venv .venv`), then run **`pip install .`** or **`pip install -r requirements.txt`** from the repo root.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — bootstrap, config model, logging, plugins.
- [Quickstart](quickstart/QUICKSTART.md) — Quadlet (Podman) or containerless (Unix socket + nginx), with encrypted credentials.
- [Style guide](docs/STYLE_GUIDE.md) — code and test conventions.
- [Admin log level API](docs/admin-log-level.md) — signed runtime log level changes.
- [Release notes](RELEASE_NOTES.md)

## Container images (CI)

Publishing runs from [`.github/workflows/release.yml`](.github/workflows/release.yml) when a **GitHub Release is published** or when you **Run workflow** manually (`workflow_dispatch`). The job runs the unit tests, then builds [`Dockerfile`](Dockerfile) and pushes two tags: **`<version>`** from `[project].version` in `pyproject.toml`, plus **`:devel`** for manual runs and GitHub prereleases, or **`:latest`** for stable releases.

By default images go to **GitHub Container Registry** (`ghcr.io/<owner>/<repo>`, lowercase). The workflow needs **`packages: write`** (already set) for GHCR. To use **Docker Hub** instead, run the workflow with inputs `registry: docker.io` and `image: docker.io/<user>/<name>`, and configure repository secrets **`DOCKERHUB_USERNAME`** and **`DOCKERHUB_TOKEN`**. Other registries can use secrets **`REGISTRY_USERNAME`** and **`REGISTRY_PASSWORD`** with the `registry` / `image` inputs.