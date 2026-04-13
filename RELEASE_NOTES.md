# Thaum release notes

## v0.2.0a5 (alpha 5) — 2026-04-12

- **Containers (bundled PostgreSQL)** — Debian installs server programs under **`/usr/lib/postgresql/<major>/bin/`**, so **`initdb`** / **`pg_ctl`** / **`postgres`** were not always on the default **`PATH`** inside the image, and **`gosu postgres initdb`** could fail at startup. The image now adds **symlinks in `/usr/local/bin`** to those binaries (version discovered at build time), and **supervisord** runs **`/usr/local/bin/postgres`**. No change to **`PGDATA`**, sockets, or app config for bundled DB.

### Upgrade from v0.2.0a4

- **Containers**: rebuild or pull the **`0.2.0a5`** image; existing **`/var/lib/thaum`** volumes are compatible (same data layout as **a4**).
- **pip / venv**: no dependency changes from **a4**; upgrade only if you want the packaging version bump.

### Alpha caveats

- Breaking changes may occur before **v0.2.0** stable.

---

## v0.2.0a4 (alpha 4) — 2026-04-12

- **Documentation** — **[`docs/deployment-quickstarts.md`](docs/deployment-quickstarts.md)** indexes cloud and Kubernetes paths. New **Kubernetes** example manifests under **`quickstart/kubernetes/`**; **Azure App Service** (Linux container) + **GitHub Actions** guide under **`quickstart/cloud/azure/github/`**; **[`quickstart/cloud/README.md`](quickstart/cloud/README.md)** lists available cloud quickstarts.
- **Dependencies** — **`gemstone_utils`** is installed from **`gemstone-software-dev/gemstone_utils`** and pinned to **`v0.3.0a2`** (see **`pyproject.toml`** and **`requirements.txt`**).
- **CI / images** — README and release workflow clarify **`:devel`**, **`:latest`**, and **`:edge`** container tags (no change to application behavior).

### Upgrade from v0.2.0a3

- **pip / venv**: if you install from the repo, **`pip install -U .`** (or **`-r requirements.txt`**) picks up the **`gemstone_utils`** URL and tag above.
- **Containers**: **`ghcr.io`** (or your registry) **`0.2.0a4`** and **`:devel`** images include the same dependency pin; no database or probe changes from **a3**.

### Alpha caveats

- Breaking changes may occur before **v0.2.0** stable.

---

## v0.2.0a3 (alpha 3) — 2026-04-12

- **HTTP probes** — **`GET /health`** returns **200** with JSON `{"status": "ok"}` for liveness (process can serve HTTP). **`GET /ready`** returns **200** after a **`SELECT 1`** against the configured app database, or **503** with `{"status": "unavailable", "reason": "database"}` if the check fails (readiness for load balancers and orchestrators).
- **Packaging** — **gunicorn** is listed in **`requirements.txt`** and **`pyproject.toml`** dependencies; the **Dockerfile** no longer installs it in a separate **`pip`** step (same image contents, single dependency path for container and **pip**/venv installs).

### Upgrade from v0.2.0a2

- **Container image**: no PostgreSQL layout change from **a2**. Configure probes to use **`/health`** (liveness) and **`/ready`** (readiness) on your app bind or reverse proxy path as needed.
- **pip / containerless venvs**: reinstall or **`pip install -U .`** (or **`-r requirements.txt`**) so **gunicorn** is installed from project metadata if you previously installed it manually.

### Alpha caveats

- Breaking changes may occur before **v0.2.0** stable.

---

## v0.2.0a2 (alpha 2) — 2026-04-11

Container image change: bundled PostgreSQL now uses **`PGDATA`** at **`/var/lib/thaum/postgresql/data`** and Unix sockets under **`/run/thaum/postgres`**, matching the default in **`thaum.db_bootstrap`** (`DEFAULT_PG_SOCKET_DIR`) and the **`/var/lib/thaum`** volume used by Podman quadlet quickstart. The image declares a single app data volume at **`/var/lib/thaum`** (replacing a separate **`/var/lib/postgresql/data`** volume).

### Upgrade from v0.2.0a1

- If you used **bundled** PostgreSQL with the **0.2.0a1** image, migrate the data directory from **`/var/lib/postgresql/data`** to **`/var/lib/thaum/postgresql/data`** inside your volume, or plan for a **fresh cluster** and restore from backup.
- If you **pinned** **`db_url`** with **`host=/var/run/postgresql`**, update it to **`host=/run/thaum/postgres`** (or rely on the default by omitting an explicit bundled URL).

### Alpha caveats

- Breaking changes may occur before **v0.2.0** stable.

---

## v0.2.0a1 (alpha 1) — 2026-04-11

First **0.2.x** prerelease. Development since **v0.1.0a1** included substantial refactors and new capabilities; the **0.2** line better matches that scope than another snapshot labeled as marching toward **0.1.0** stable.

### Highlights since v0.1.0a1

- **Database** — **PostgreSQL** support alongside the bundled layout; **`db_url`**-centric configuration (replacing earlier `db_spec`-style wiring), connection testing and validation, and integration with **gemstone_utils** for schema/bootstrap (including migration from earlier **emerald_utils** usage). Ongoing refinements to encryption, key handling, and lookup/bootstrap paths.
- **Plugins** — Dedicated **`plugins/`** layout for bots, lookups, and alerts; shared **`BasePlugin`** and clearer registry/config loading; **Jira** alert plugin split into focused modules with improved webhooks, status handling, and escalation-related configuration.
- **Security / HTTP** — **Webhook bearer** token lifecycle with database-backed warnings; **signed admin API** for runtime log level (see [docs/admin-log-level.md](docs/admin-log-level.md)).
- **Ops** — Multi-stage **Dockerfile**, **README** notes on **GHCR** publishing via CI, **quickstart** and **systemd** samples (including credential-oriented patterns), optional **file logging** and structured logging improvements.
- **Config** — Stricter **Pydantic** validation, **`ResolvedSecret`** and related patterns for secrets in config (e.g. database URL), and tooling/scripts for configuration checks.

### Alpha caveats

- Breaking changes may occur before **v0.2.0** stable.
- Validate behavior in your environment before relying on Thaum for critical on-call paths.

### Thanks

Feedback and patches are welcome as Thaum moves toward a stable **0.2** line.

---

## v0.1.0a1 (alpha 1) — 2026-04-05

First public **alpha** tag. This release is intended for early adopters who can tolerate rough edges while the API, packaging story, and operations guides stabilize.

### What Thaum is

Thaum connects chat platforms to on-call style alerting. It ships with a **Webex** bot driver and **Jira Service Management Ops** alerting; lookup and alert surfaces are **plugin-based** so other backends (Teams, PagerDuty, and so on) can be added without rewriting the core.

### Highlights in this alpha

- **Configuration** — `config.toml` with typed **Pydantic** models (`ServerConfig`, `LogConfig`, per-bot and plugin configs).
- **HTTP surface** — Flask app (`web.py`), bot webhooks, and optional **signed admin API** for runtime root log level (`POST /{route_id}/log-level`); see [docs/admin-log-level.md](docs/admin-log-level.md).
- **Database** — Shared app database (SQLAlchemy / Gemstone); optional field encryption and DEK rotation hooks.
- **Multi-worker** — Leader election so only the leader registers Webex webhooks when multiple processes run.
- **Logging** — ISO8601-aware formatters, custom levels (including SPAM for full diagnostics), optional **file logging** (`[logging].file`) with timed rotation and strict opt-in semantics; stdout remains the default for container-style deployments.
- **Documentation** — Architecture and style guides live under [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md).

### Documentation layout

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — bootstrap sequence, configuration model, logging, import rules.
- [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md) — project conventions for Python and tests.
- [docs/admin-log-level.md](docs/admin-log-level.md) — signed log-level admin API.

### Alpha caveats

- Breaking changes may occur before **v0.1.0** stable.
- Production hardening (packaging, upgrade paths, and broader platform coverage) is still evolving; validate behavior in your environment before relying on it for critical on-call paths.

### Thanks

Feedback and patches are welcome as Thaum moves toward a stable **0.1** line.
