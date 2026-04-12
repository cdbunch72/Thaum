# Thaum release notes

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
