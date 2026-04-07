# Thaum release notes

## v0.1.0_a1 (alpha 1) — 2026-04-05

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
