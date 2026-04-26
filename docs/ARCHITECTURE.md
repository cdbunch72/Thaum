# Thaum System Architecture

## Overview

Thaum is a modular, plugin-driven orchestration framework designed for
deterministic, admin-friendly operations. Its architecture emphasizes
predictable lifecycle sequencing, clean separation of concerns, and
strict avoidance of import-time side effects. The system is composed of
a central server process, a shared database, a plugin layer, and one or
more bot instances.

------------------------------------------------------------------------

## 1. Bootstrap Sequence

Bootstrap is implemented in `bootstrap.py` and invoked from `app.py` before the
Flask app is created.

### **Phase 1 - Load and validate core config**

- `config.load_and_validate()` reads `config.toml` and builds `ServerConfig` and
  `LogConfig`.

- Bot tables are kept as dicts: each `[bots.<id>]` includes `alert_type` and an
  optional nested `[bots.<id>.alert]` table for per-bot alert options.

- `log_setup.configure_logging()` runs next.

### **Phase 2 - Import plugin modules and validate typed configs**

- `plugin_loader.ensure_plugin_loaded(family, name)` imports lookup, bot driver,
  and every distinct `alert_type` module.

- Lookup, each bot driver row, and each merged alert config (defaults +
  `[bots.<id>.alert]`) are validated with the plugin’s `get_config_model()`.

- ORM models used by lookup live in `lookup/models.py` as subclasses of
  `GemstoneDB`; importing plugins before `init_db` registers metadata.

- **No bot or alert plugin instances** exist yet.

### **Phase 3 - Initialize database**

- `thaum.db_bootstrap.init_app_db()` calls `gemstone_utils.db.init_db()` with the URL from `[server.database].db_url` (via `thaum.db_bootstrap.resolve_app_db_url`).

#### Database URL resolution (`resolve_app_db_url`)

- If **`db_url`** is set (after secret resolution), that URL is used (PostgreSQL, SQLite, etc.).

- If **`db_url`** is empty:

  - **`THAUM_EXTERNAL_DB`** true (`1`, `true`, `yes`, `on`): **error** — set an explicit `db_url` for your external or dev database.

  - Otherwise (unset/false): **bundled PostgreSQL** — the URL is built by `default_bundled_db_url()` as `postgresql+psycopg://…` over a **Unix socket** (`host` query parameter), using **peer** authentication (no password in the URL; the process OS user must match the role, e.g. `thaum` in the container). Optional: **`THAUM_PG_USER`** (default `thaum`), **`THAUM_PG_DATABASE`** (default `thaum`), **`THAUM_PG_SOCKET_DIR`** (default `/tmp/postgres`).

- The single container image uses **`THAUM_EXTERNAL_DB`** in `entrypoint.sh`: external DB → `gunicorn` only; bundled → `supervisord` (PostgreSQL + app). See the `Dockerfile` and `docker/` assets.

### **Phase 4 - Instantiate lookup, bots, and alert plugins**

- `initialize_lookup_plugin()` then `thaum.factory.initialize_bots()` build
  runtime objects, attach alert plugins, and `bind_thaum_handlers()`.

### **Phase 5 - HTTP**

- `web.create_app()` registers Flask routes (e.g. `POST /bot/<bot_key>`) and
  calls `register_all_bot_webhooks()`.

------------------------------------------------------------------------

## 2. Configuration Model

Thaum uses a layered configuration model.

### **ServerConfig**

- Core deployment fields under `[server]` (base URL, bot driver, lookup plugin name, state dir)

- Nested `[server.database]` (SQLAlchemy `db_url` via secret resolver, vault passphrase, DEK rotation; see **Database URL resolution** under §1 Phase 3)

- Nested `[server.election]` (namespace, lease, heartbeat interval)

- Nested `[server.admin]` (signed HTTP admin for runtime log level)

- Separate `[logging]` table → `LogConfig`

- `[lookup]` merged with `[lookup.<plugin>]` for cache paths and plugin-specific options (not the DB URL)

- Lookup plugins: public contract includes ``get_person_by_email`` (default: DB cache only); implementations may override to query their source of truth, then ``merge_person``. See ``lookup/base.py``.

### **BotConfig**

- Driver-specific model (e.g. Webex) extending ``BaseChatBotConfig``

- Required ``alert_type`` (alert plugin module name; use ``null`` when
  ``send_alerts`` is false)

- Optional ``[bots.<id>.alert]`` table merged with ``[defaults.alert.<alert_type>]``
  for that bot’s alert instance (e.g. responders)

- Responder lists, room templates, and other bot fields

- Help/emergency incident prompt card templating via either:
  - ``incident_prompt_card_template_path`` (path to a ``.j2`` file)
  - ``incident_prompt_card_template`` (inline Jinja template)
  - Inline template takes precedence if both are set.
  - Templates render to JSON and are parsed before send; use ``|tojson`` for interpolated values.

### **PluginConfig**

Each plugin config contains:

- Typed Pydantic config

- Reference to plugin ClassType

- Raw configuration for plugin-specific behavior

This structure mirrors the plugin object hierarchy and ensures clean
separation between configuration and instantiation.

------------------------------------------------------------------------

## 3. Plugin Architecture

Plugins are first-class components in Thaum.

### **Plugin Module Requirements**

Each plugin module must:

- Define ORM models as subclasses of GemstoneDB.

- Expose ``get_config_model()`` (and the family-specific factory:
  ``create_instance_plugin`` / ``create_instance_bot`` / ``create_instance_lookup``).

- Avoid import-time side effects.

- Keep constructors free of DB access until after Phase 3.

### **Plugin Object Lifecycle**

Plugin constructors may:

- Open DB sessions

- Load cached state

- Register webhook handlers

- Schedule periodic tasks

- Load secrets

- Attach themselves to bots

Plugins must not:

- Perform DB operations before Phase 3

- Register handlers before bot instantiation

- Trigger background tasks before initialization completes

------------------------------------------------------------------------

## 4. Database Layer

Thaum uses a shared database for:

- Alert lifecycle tracking

- Pending event buffering

- Plugin state

- Identity cache

- Leader election metadata

### **DB Initialization Rules**

- All ORM models must be imported before init_db().

- No plugin may create tables independently.

- All migrations (future) must run after plugin import.

------------------------------------------------------------------------

## 5. Event Processing and Lifecycle

Thaum processes events from external systems (e.g., alerting platforms)
in a deterministic manner.

### **Alert Lifecycle**

- Alerts are created with a short_id stored in extraProperties.

- Webhooks may arrive out of order.

- Thaum uses a DB-backed pending-event buffer to handle:

  - ack before create

  - escalate before ack

  - delayed create events

### **Pending Create Handling**

- When an alert is sent, Thaum immediately notifies the room with the
  short_id.

- A DB row is created with state = pending_create.

- When the create webhook arrives, the alert is activated.

- A watchdog timer marks alerts as failed if creation does not complete.

------------------------------------------------------------------------

## 6. Logging and Diagnostics

Thaum uses structured logging with multiple levels:

- INFO - normal operational messages

- NOTICE - important but non-urgent events

- VERBOSE - routine status messages

- DEBUG - developer-level detail

- SPAM - full diagnostics, including JSON bodies and stack traces

Multi-line output uses the blob helper for readability.

Stack traces are only emitted at SPAM level.

Optional **file logging** under `[logging]` is opt-in via `file`: boolean `true`, integer `1`, or strings `yes` / `true` / `1` select the default path `/var/log/thaum/thaum.log`; any other non-empty string is a custom path. The log file’s parent directory must already exist (otherwise a message is written to stderr and only stdout logging is used). The file sink uses a timed-rotating handler; timestamps on file lines are controlled per formatter instance (file output always includes timestamps by default, independent of `no_timestamp` on the console formatter). At runtime, **`THAUM_LOG_TO_VAR_LOG`** (`1` / `true` / `yes` / `on`) enables that same default file path when `[logging].file` was not set in TOML (explicit TOML wins).

Optional JSON logging uses a single `[logging].json_log` selector:
- falsy/missing (`false`, `0`, `no`, `off`, empty, missing) -> disabled
- truthy (`true`, `1`, `yes`, `on`, `truthy`) -> `/var/log/thaum/thaum.json`
- `stderr` -> stderr sink
- `file:/path/to/file` -> explicit file sink

Environment precedence for JSON is controlled by `[logging].env_override`:
- falsy/missing (default): truthy `THAUM_JSON_LOG` can force JSON logging to stderr in final config
- truthy: TOML is authoritative for final JSON logging existence (`[logging].json_log`)

`THAUM_LOG_LEVEL` overrides `[logging].level` when set to a valid level name, unless `[logging].env_override` is truthy (in that case TOML level is authoritative for final config).

### Runtime log level (admin API)

Changing the process root log level at runtime is **not** done via a local file. When
`[server.admin].route_id` and a valid HMAC secret are configured, Thaum exposes
`POST /{route_id}/log-level` with an **HS256** request signature over a
documented canonical string. State is stored in the shared DB (`admin_log_level_state`
and `admin_log_nonce`); optional polling keeps multiple workers aligned. Operators
typically use `scripts/powershell/Set-ThaumLogLevel.ps1` or
`scripts/python/thaum_log_override.py` with a small INI profile. Full details:
[admin-log-level.md](admin-log-level.md).

------------------------------------------------------------------------

## 7. Import-Time Side-Effect Rules

To maintain deterministic startup:

- No plugin may perform DB access during import.

- No plugin may register handlers during import.

- No plugin may start background tasks during import.

- Importing a plugin module must only:

  - define ORM models

  - define config models

  - expose plugin class

------------------------------------------------------------------------

## 8. Directory Structure

A typical Thaum deployment uses:

  ------------
  thaum/\
  app.py\
  bootstrap.py\
  web.py\
  config.py\
  bots/\
  plugins/\
  db/\
  utils/\
  logging/\
  docs/

  ------------

This structure keeps concerns isolated and predictable.

------------------------------------------------------------------------

## 9. Operational Philosophy

Thaum is designed around:

- Deterministic behavior

- Admin-friendly operations

- Predictable concurrency

- Clear separation of concerns

- Minimal magic

- Explicit lifecycle sequencing

- Low-noise logging

- Safe, humane on-call workflows

------------------------------------------------------------------------

## 10. Summary

Thaum's architecture is built to be:

- Modular

- Predictable

- Maintainable

- Extensible

- Operationally safe

By enforcing strict bootstrap sequencing, clean plugin boundaries, and
disciplined logging and exception handling, Thaum provides a stable
foundation for complex operational automation.
